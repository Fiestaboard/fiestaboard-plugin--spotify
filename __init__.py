"""Spotify plugin for FiestaBoard.

Shows what is playing on a Spotify account: the track or podcast episode, its
progress, the device it is playing on, where it is playing from, and what is
up next. When nothing is playing it can show the last track played instead.

Sign-in uses FiestaBoard's platform OAuth (the manifest's ``oauth`` block):
each user creates their own Spotify app, pastes its Client ID into the
plugin's settings and presses Connect. The platform runs the PKCE flow,
stores the tokens and refreshes them; this plugin only ever calls
``self.get_oauth_token()`` and sends the result as a bearer token. There is
no client secret anywhere.

Endpoints (Spotify Web API):

* ``GET /me/player``                      playback state, item, device, context
* ``GET /me/player/queue``                up next
* ``GET /me/player/recently-played``      last track when nothing is playing
* ``GET /playlists/{id}?fields=name``     the playlist name for the context
"""

import logging
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests
from src.board_chars import BoardChars
from src.plugins.base import PluginBase, PluginResult
from src.text_to_board import take_tiles

logger = logging.getLogger(__name__)

API_BASE = "https://api.spotify.com/v1"
USER_AGENT = "FiestaBoard Spotify Plugin (https://github.com/Fiestaboard/fiestaboard-plugin--spotify)"
REQUEST_TIMEOUT_SECONDS = 10

# Every board a plugin renders on asks for its own data (the platform caches
# per board shape), so a Flagship and a Note would each call Spotify. One
# snapshot of Spotify's state is shared between them for this long.
SNAPSHOT_TTL_SECONDS = 5
# The queue rarely changes within a track, so it is fetched again only when
# the track changes or after this long.
QUEUE_TTL_SECONDS = 60
# The last-played track changes only when something plays.
RECENT_TTL_SECONDS = 120
QUEUE_SIZE = 5
MAX_CACHED_PLAYLIST_NAMES = 50

# After a failure, Spotify is left alone for a while instead of being asked
# again on every render. 429 uses Spotify's Retry-After instead.
TRANSIENT_COOLDOWN_SECONDS = 15
AUTH_COOLDOWN_SECONDS = 60
DEFAULT_RETRY_AFTER_SECONDS = 30
MAX_RETRY_AFTER_SECONDS = 3600
# During a cooldown, keep showing the last good data while it is this fresh.
STALE_DATA_LIMIT_SECONDS = 120

DEFAULT_COLS = 22
DEFAULT_ROWS = 6

TILE_PLAYING = "{66}"  # green
TILE_PAUSED = "{65}"  # yellow
TILE_STOPPED = "{63}"  # red
TILE_BAR = "{66}"
BAR_EMPTY = "-"

# get_oauth_token() returns None both before the first sign-in and after
# Spotify refused a refresh, so the message covers Connect and Reconnect.
NOT_CONNECTED_ERROR = "Not signed in to Spotify. Open this plugin's settings and sign in."
PLATFORM_TOO_OLD_ERROR = "This FiestaBoard version cannot sign in to Spotify. Update FiestaBoard to use this plugin."
UNAUTHORIZED_ERROR = "Spotify rejected the sign-in (401). Open this plugin's settings and press Reconnect."
FORBIDDEN_ERROR = (
    "Spotify refused access (403). In the Spotify Developer Dashboard, add your Spotify account "
    "under User Management, and check the app owner has Spotify Premium."
)

CLIENT_ID_RE = re.compile(r"^[0-9a-fA-F]{32}$")

# Clutter that eats a 22-column row without telling you anything new.
_TIDY_PATTERNS = (
    # "Song - Remastered 2011", "Song - 2011 Remaster"
    re.compile(r"\s+-\s+[^-]*\bremaster(?:ed)?\b[^-]*$", re.IGNORECASE),
    # "Song (Remastered 2009)", "Song [2015 Remaster]"
    re.compile(r"\s*[(\[][^)\]]*\bremaster(?:ed)?\b[^)\]]*[)\]]", re.IGNORECASE),
    # "Song (feat. Someone)", "Song (with Someone)": the artist line names them
    re.compile(r"\s*[(\[]\s*(?:feat\.?|ft\.?|featuring|with)\s[^)\]]*[)\]]", re.IGNORECASE),
)

REPEAT_LABELS = {"off": "OFF", "context": "ALL", "track": "ONE"}
CONTEXT_LABELS = {
    "playlist": "PLAYLIST",
    "album": "ALBUM",
    "artist": "ARTIST",
    "show": "PODCAST",
    "collection": "LIKED SONGS",
}


class SpotifyError(Exception):
    """A Spotify request failed; the message is shown to the user."""

    def __init__(self, message: str, *, transient: bool, cooldown: float):
        super().__init__(message)
        self.transient = transient
        self.cooldown = cooldown


# ----------------------------------------------------------------------
# Pure helpers
# ----------------------------------------------------------------------


def _monotonic() -> float:
    return time.monotonic()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def board_safe(text: Any) -> str:
    """Uppercase *text* and keep only characters the board can show.

    Accents are folded (``Beyoncé`` -> ``BEYONCE``). Emoji and anything else
    without a board code are dropped, including braces, which the board would
    otherwise read as colour-tile markers.
    """
    folded = unicodedata.normalize("NFKD", str(text or ""))
    kept = []
    for ch in folded.upper():
        if ch.isspace():
            kept.append(" ")
        elif BoardChars.get_char_code(ch) is not None:
            kept.append(ch)
    return re.sub(r" {2,}", " ", "".join(kept)).strip()


def tidy_title(title: str) -> str:
    """Drop remaster and featuring notes from a track title."""
    tidied = title or ""
    for pattern in _TIDY_PATTERNS:
        tidied = pattern.sub("", tidied)
    return tidied.strip() or (title or "").strip()


def format_duration(ms: Any) -> str:
    """``83000`` -> ``1:23``; an hour or more -> ``1:02:03``."""
    try:
        total = max(int(ms or 0), 0) // 1000
    except (TypeError, ValueError):
        return "0:00"
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_ago(then: datetime, now: datetime) -> str:
    """Short relative time: ``JUST NOW``, ``12M AGO``, ``3H AGO``, ``2D AGO``."""
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 1:
        return "JUST NOW"
    if minutes < 60:
        return f"{minutes}M AGO"
    if minutes < 60 * 24:
        return f"{minutes // 60}H AGO"
    return f"{minutes // (60 * 24)}D AGO"


def parse_timestamp(value: str) -> datetime:
    """Parse Spotify's ISO-8601 timestamps (``2026-10-01T18:04:05.123Z``)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def progress_bar(progress_ms: int, duration_ms: int, width: int) -> str:
    """A bar *width* tiles wide: green tiles played, dashes to go."""
    if width <= 0:
        return ""
    filled = round(width * progress_ms / duration_ms) if duration_ms > 0 else 0
    filled = min(max(filled, 0), width)
    return TILE_BAR * filled + BAR_EMPTY * (width - filled)


def fit(text: str, width: int) -> str:
    """Truncate *text* to *width* tiles (colour markers count as one)."""
    return take_tiles(text, width)[0]


def _join(*parts: str, sep: str = " - ") -> str:
    return sep.join(part for part in parts if part)


def _uri_id(uri: str) -> str:
    """``spotify:playlist:37i9dQ`` -> ``37i9dQ``."""
    return (uri or "").rsplit(":", 1)[-1]


# ----------------------------------------------------------------------
# Plugin
# ----------------------------------------------------------------------


class SpotifyPlugin(PluginBase):
    """What's playing on Spotify, from the user's own account."""

    def __init__(self, manifest: Dict[str, Any]):
        super().__init__(manifest)
        self._lock = threading.RLock()
        self._reset_state()

    def _reset_state(self) -> None:
        self._snapshot: Optional[Dict[str, Any]] = None
        self._snapshot_at = 0.0
        self._last_good: Optional[Dict[str, Any]] = None
        self._last_good_at = 0.0
        self._cooldown_until = 0.0
        self._cooldown_error: Optional[SpotifyError] = None
        self._cooldown_token: Optional[str] = None
        self._queue: List[Dict[str, Any]] = []
        self._queue_key: Optional[str] = None
        self._queue_at = 0.0
        self._recent: Optional[Dict[str, Any]] = None
        self._recent_at: Optional[float] = None
        self._playlist_names: Dict[str, str] = {}

    @property
    def plugin_id(self) -> str:
        return "spotify"

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        # An empty Client ID is allowed: other settings can be saved before the
        # Spotify app exists, and the plugin reports "not connected" until
        # someone signs in. A value that cannot be a Client ID is still caught
        # here, before it turns into a confusing error on Spotify's site.
        client_id = str(config.get("client_id") or "").strip()
        if client_id and not CLIENT_ID_RE.match(client_id):
            errors.append("Client ID should be the 32-character code from your Spotify app's Settings page")
        errors.extend(self._validate_refresh_seconds(config))
        return errors

    def on_config_change(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        super().on_config_change(old_config, new_config)
        with self._lock:
            self._reset_state()

    def _setting(self, key: str, default: bool) -> bool:
        value = self.config.get(key)
        return default if value is None else bool(value)

    # ------------------------------------------------------------------
    # Spotify requests
    # ------------------------------------------------------------------

    def _get(self, token: str, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """GET a Web API path. Returns the JSON body, or ``None`` for 204."""
        try:
            response = requests.get(
                f"{API_BASE}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.exceptions.Timeout:
            raise SpotifyError("Timed out contacting Spotify", transient=True, cooldown=TRANSIENT_COOLDOWN_SECONDS)
        except requests.exceptions.RequestException as exc:
            raise SpotifyError(
                f"Could not reach Spotify: {type(exc).__name__}", transient=True, cooldown=TRANSIENT_COOLDOWN_SECONDS
            )

        status = response.status_code
        if status == 204:
            return None
        if status == 200:
            return response.json() if response.content else None
        if status == 401:
            raise SpotifyError(UNAUTHORIZED_ERROR, transient=False, cooldown=AUTH_COOLDOWN_SECONDS)
        if status == 403:
            raise SpotifyError(FORBIDDEN_ERROR, transient=False, cooldown=AUTH_COOLDOWN_SECONDS)
        if status == 404:
            raise SpotifyError(
                "Spotify could not find that (404)", transient=False, cooldown=TRANSIENT_COOLDOWN_SECONDS
            )
        if status == 429:
            wait = self._retry_after(response)
            raise SpotifyError(
                f"Spotify rate limit reached; trying again in {int(wait)}s", transient=True, cooldown=wait
            )
        if status >= 500:
            raise SpotifyError(
                f"Spotify is having trouble (HTTP {status}); will retry",
                transient=True,
                cooldown=TRANSIENT_COOLDOWN_SECONDS,
            )
        raise SpotifyError(
            f"Unexpected response from Spotify (HTTP {status})", transient=False, cooldown=TRANSIENT_COOLDOWN_SECONDS
        )

    @staticmethod
    def _retry_after(response: requests.Response) -> float:
        try:
            wait = float(response.headers.get("Retry-After", DEFAULT_RETRY_AFTER_SECONDS))
        except (TypeError, ValueError):
            wait = DEFAULT_RETRY_AFTER_SECONDS
        return min(max(wait, 1.0), MAX_RETRY_AFTER_SECONDS)

    def _optional(self, fetch: Callable[[], Any], what: str) -> Tuple[bool, Any]:
        """Run a secondary lookup; a failure there must not hide what is playing.

        Returns ``(ok, value)``. A 429 or outage still starts the cooldown, so
        the next render does not call Spotify again straight away.
        """
        try:
            return True, fetch()
        except SpotifyError as exc:
            logger.info("Spotify: %s lookup failed: %s", what, exc)
            if exc.transient:
                self._start_cooldown(exc)
            return False, exc

    # ------------------------------------------------------------------
    # Snapshot of Spotify's state, shared between boards
    # ------------------------------------------------------------------

    def _start_cooldown(self, exc: SpotifyError, token: Optional[str] = None) -> None:
        if exc.cooldown > 0:
            self._cooldown_until = max(self._cooldown_until, _monotonic() + exc.cooldown)
            self._cooldown_error = exc
            # A rejected token only blocks that token: reconnecting gives a
            # new one, which should be tried straight away.
            self._cooldown_token = None if exc.transient else token

    def _in_cooldown(self, token: str) -> bool:
        if self._cooldown_error is None or _monotonic() >= self._cooldown_until:
            return False
        return self._cooldown_token is None or self._cooldown_token == token

    def _load_snapshot(self, token: str) -> Dict[str, Any]:
        now = _monotonic()
        if self._snapshot is not None and now - self._snapshot_at < SNAPSHOT_TTL_SECONDS:
            return self._snapshot
        if self._in_cooldown(token):
            raise self._cooldown_error

        try:
            player = self._get(token, "/me/player", {"additional_types": "episode"})
        except SpotifyError as exc:
            self._start_cooldown(exc, token)
            raise

        item = (player or {}).get("item")
        snapshot: Dict[str, Any] = {"player": player, "queue": [], "playlist_name": "", "recent": None}

        if item:
            snapshot["queue"] = self._load_queue(token, item)
            snapshot["playlist_name"] = self._load_playlist_name(token, (player or {}).get("context"))
        elif self._setting("show_last_played", True):
            snapshot["recent"] = self._load_recent(token)

        self._snapshot = snapshot
        self._snapshot_at = _monotonic()
        return snapshot

    def _load_queue(self, token: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not self._setting("show_queue", True):
            return []
        key = item.get("uri") or item.get("id") or ""
        if key == self._queue_key and _monotonic() - self._queue_at < QUEUE_TTL_SECONDS:
            return self._queue
        ok, body = self._optional(lambda: self._get(token, "/me/player/queue"), "queue")
        if not ok:
            return self._queue if key == self._queue_key else []
        self._queue = [entry for entry in ((body or {}).get("queue") or []) if entry][:QUEUE_SIZE]
        self._queue_key = key
        self._queue_at = _monotonic()
        return self._queue

    def _load_playlist_name(self, token: str, context: Optional[Dict[str, Any]]) -> str:
        if not context or context.get("type") != "playlist":
            return ""
        playlist_id = _uri_id(context.get("uri", ""))
        if not playlist_id:
            return ""
        if playlist_id in self._playlist_names:
            return self._playlist_names[playlist_id]
        ok, body = self._optional(
            lambda: self._get(token, f"/playlists/{playlist_id}", {"fields": "name"}), "playlist name"
        )
        if not ok and body.transient:
            return ""  # try again next time
        # Spotify's own editorial and algorithmic playlists answer 404 to
        # apps; remember that so it is not asked again.
        name = (body or {}).get("name", "") if ok else ""
        if len(self._playlist_names) >= MAX_CACHED_PLAYLIST_NAMES:
            self._playlist_names.pop(next(iter(self._playlist_names)))
        self._playlist_names[playlist_id] = name
        return name

    def _load_recent(self, token: str) -> Optional[Dict[str, Any]]:
        if self._recent_at is not None and _monotonic() - self._recent_at < RECENT_TTL_SECONDS:
            return self._recent
        ok, body = self._optional(
            lambda: self._get(token, "/me/player/recently-played", {"limit": 1}), "recently played"
        )
        if not ok:
            return self._recent
        items = (body or {}).get("items") or []
        self._recent = items[0] if items else None
        self._recent_at = _monotonic()
        return self._recent

    # ------------------------------------------------------------------
    # fetch_data
    # ------------------------------------------------------------------

    def _board_size(self) -> Tuple[int, int]:
        board = self.board
        if board is None:
            return DEFAULT_COLS, DEFAULT_ROWS
        return board.cols, board.rows

    def fetch_data(self) -> PluginResult:
        try:
            get_token = getattr(self, "get_oauth_token", None)
            if get_token is None:
                return PluginResult(available=False, error=PLATFORM_TOO_OLD_ERROR)
            token = get_token()
            if not token:
                return PluginResult(available=False, error=NOT_CONNECTED_ERROR)

            cols, rows = self._board_size()
            with self._lock:
                try:
                    snapshot = self._load_snapshot(token)
                except SpotifyError as exc:
                    stale = self._stale_snapshot()
                    if exc.transient and stale is not None:
                        logger.info("Spotify: %s; showing the last data", exc)
                        snapshot = stale
                    else:
                        logger.warning("Spotify: %s", exc)
                        return PluginResult(available=False, error=str(exc))
                else:
                    self._last_good = snapshot
                    self._last_good_at = _monotonic()

            data = self._build_data(snapshot, cols)
            return PluginResult(available=True, data=data, formatted_lines=self._format_display(data, cols, rows))
        except Exception as exc:  # fetch_data must never raise
            logger.exception("Error fetching Spotify data")
            return PluginResult(available=False, error=str(exc))

    def _stale_snapshot(self) -> Optional[Dict[str, Any]]:
        if self._last_good is None or _monotonic() - self._last_good_at > STALE_DATA_LIMIT_SECONDS:
            return None
        return self._last_good

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _describe(self, item: Optional[Dict[str, Any]]) -> Dict[str, str]:
        """Title, artist and album for a track or a podcast episode."""
        if not item:
            return {"title": "", "artist": "", "album": "", "type": ""}
        if item.get("type") == "episode":
            show = item.get("show") or {}
            return {
                "title": board_safe(item.get("name")),
                "artist": board_safe(show.get("name")),
                "album": board_safe(show.get("publisher")),
                "type": "EPISODE",
            }
        title = item.get("name") or ""
        if self._setting("tidy_titles", True):
            title = tidy_title(title)
        artists = ", ".join(a.get("name", "") for a in item.get("artists") or [] if a.get("name"))
        return {
            "title": board_safe(title),
            "artist": board_safe(artists),
            "album": board_safe((item.get("album") or {}).get("name")),
            "type": "TRACK",
        }

    def _context(self, player: Dict[str, Any], item: Dict[str, Any], playlist_name: str) -> Tuple[str, str]:
        context = player.get("context") or {}
        kind = context.get("type") or ""
        label = CONTEXT_LABELS.get(kind, board_safe(kind))
        if kind == "playlist":
            return label, board_safe(playlist_name)
        if kind == "album":
            return label, board_safe((item.get("album") or {}).get("name"))
        if kind == "show":
            return label, board_safe((item.get("show") or {}).get("name"))
        if kind == "artist":
            artist_id = _uri_id(context.get("uri", ""))
            for artist in item.get("artists") or []:
                if artist.get("id") == artist_id:
                    return label, board_safe(artist.get("name"))
        return label, ""

    def _build_data(self, snapshot: Dict[str, Any], cols: int) -> Dict[str, Any]:
        player = snapshot.get("player") or {}
        item = player.get("item")
        playing_type = player.get("currently_playing_type") or ""
        is_playing = bool(player.get("is_playing")) and bool(item or playing_type == "ad")

        described = self._describe(item)
        progress_ms = int(player.get("progress_ms") or 0) if item else 0
        duration_ms = int((item or {}).get("duration_ms") or 0)
        last_played_ago = ""

        if item:
            headline = "NOW PLAYING" if is_playing else "PAUSED"
            state = "PLAYING" if is_playing else "PAUSED"
        elif playing_type == "ad":
            headline, state = "AD BREAK", "PLAYING" if is_playing else "PAUSED"
            described["type"] = "AD"
        else:
            state = "STOPPED"
            recent = snapshot.get("recent")
            if recent and recent.get("track"):
                described = self._describe(recent["track"])
                duration_ms = int(recent["track"].get("duration_ms") or 0)
                headline = "LAST PLAYED"
                if recent.get("played_at"):
                    last_played_ago = format_ago(parse_timestamp(recent["played_at"]), _utcnow())
            else:
                headline = "NOTHING PLAYING"

        tile = {"PLAYING": TILE_PLAYING, "PAUSED": TILE_PAUSED}.get(state, TILE_STOPPED)
        percent = min(100, round(100 * progress_ms / duration_ms)) if duration_ms else 0

        device = player.get("device") or {}
        volume = device.get("volume_percent")
        shuffle = bool(player.get("shuffle_state")) if player else False
        repeat = REPEAT_LABELS.get(player.get("repeat_state") or "off", "OFF") if player else "OFF"
        modes = _join("SHUFFLE" if shuffle else "", f"REPEAT {repeat}" if repeat != "OFF" else "", sep=" ")

        context_type, context_name = (
            self._context(player, item, snapshot.get("playlist_name", "")) if item else ("", "")
        )

        queue = [self._queue_entry(entry) for entry in snapshot.get("queue") or []]
        next_entry = queue[0] if queue else {"title": "", "artist": "", "line": ""}

        return {
            # Now playing
            "headline": headline,
            "title": described["title"],
            "artist": described["artist"],
            "album": described["album"],
            "title_artist": _join(described["title"], described["artist"]),
            "item_type": described["type"],
            "last_played_ago": last_played_ago,
            # Playback
            "is_playing": is_playing,
            "state": state,
            "state_tile": tile,
            "progress": format_duration(progress_ms) if item else "",
            "duration": format_duration(duration_ms) if duration_ms else "",
            "time_line": f"{format_duration(progress_ms)} / {format_duration(duration_ms)}"
            if item and duration_ms
            else "",
            "remaining": f"-{format_duration(max(duration_ms - progress_ms, 0))}" if item and duration_ms else "",
            "progress_ms": progress_ms,
            "duration_ms": duration_ms,
            "progress_percent": percent,
            "progress_bar": progress_bar(progress_ms, duration_ms, cols) if item else "",
            # Device and modes
            "device_name": board_safe(device.get("name")),
            "device_type": board_safe(device.get("type")),
            "volume_percent": volume if isinstance(volume, int) else "",
            "shuffle": shuffle,
            "repeat": repeat,
            "modes": modes,
            # Context
            "context_type": context_type,
            "context_name": context_name,
            # Up next
            "next_title": next_entry["title"],
            "next_artist": next_entry["artist"],
            "next_line": next_entry["line"],
            "queue": queue,
            "queue_count": len(queue),
        }

    def _queue_entry(self, entry: Dict[str, Any]) -> Dict[str, str]:
        described = self._describe(entry)
        return {
            "title": described["title"],
            "artist": described["artist"],
            "line": _join(described["title"], described["artist"]),
        }

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @staticmethod
    def _format_display(data: Dict[str, Any], cols: int, rows: int) -> List[str]:
        """Fallback layout for a board *cols* x *rows* tiles when there is no template."""
        status = _join(data["state_tile"], data["headline"], sep=" ")
        if data["last_played_ago"]:
            status = _join(status, data["last_played_ago"], sep=" ")
        if rows < 6:
            if data["title"]:
                detail = data["time_line"] or _join(data["state_tile"], data["last_played_ago"], sep=" ")
                lines = [data["title"], data["artist"], detail]
            else:
                lines = [data["headline"], "", ""]
        else:
            lines = [
                status,
                data["title"],
                data["artist"],
                data["context_name"] or data["album"],
                data["time_line"],
                data["progress_bar"],
            ]
            if rows > 6 and data["queue"]:
                lines += ["", "UP NEXT"] + [entry["line"] for entry in data["queue"]]
        return [fit(line, cols) for line in lines[:rows]]

    def get_formatted_display(self) -> Optional[List[str]]:
        result = self.get_data(self.board)
        if not result.available or not result.data:
            return None
        cols, rows = self._board_size()
        return self._format_display(result.data, cols, rows)


# Export hook: the loader looks for a module-level `Plugin`.
Plugin = SpotifyPlugin
