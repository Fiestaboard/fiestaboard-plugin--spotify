"""Spotify Web API payloads for the tests.

Shaped like real responses from ``GET /me/player``, ``/me/player/queue``,
``/me/player/recently-played`` and ``/playlists/{id}``, trimmed to the
fields that matter plus a few the plugin must ignore. Every artist, track,
album, show, playlist and device name is invented.
"""

import copy


def artist(name, artist_id):
    return {
        "external_urls": {"spotify": f"https://open.spotify.com/artist/{artist_id}"},
        "href": f"https://api.spotify.com/v1/artists/{artist_id}",
        "id": artist_id,
        "name": name,
        "type": "artist",
        "uri": f"spotify:artist:{artist_id}",
    }


def track(name, artists, album_name="Midnight Ferry", duration_ms=225000, track_id="4fakeTrackNeonHarbor"):
    return {
        "album": {
            "album_type": "album",
            "artists": artists[:1],
            "id": "2fakeAlbumMidnightFerry",
            "images": [{"height": 640, "url": "https://i.scdn.co/image/fake-cover", "width": 640}],
            "name": album_name,
            "release_date": "2024-05-17",
            "type": "album",
            "uri": "spotify:album:2fakeAlbumMidnightFerry",
        },
        "artists": artists,
        "disc_number": 1,
        "duration_ms": duration_ms,
        "explicit": False,
        "id": track_id,
        "is_local": False,
        "name": name,
        "track_number": 3,
        "type": "track",
        "uri": f"spotify:track:{track_id}",
    }


PAPER_LANTERNS = artist("Paper Lanterns", "1fakeArtistPaperLanterns")
JUNE_ARCADE = artist("June Arcade", "1fakeArtistJuneArcade")


def neon_harbor():
    return track("Neon Harbor", [PAPER_LANTERNS])


def episode(name="Episode 42: Tide Tables", duration_ms=3723000):
    return {
        "description": "A fake episode.",
        "duration_ms": duration_ms,
        "id": "5fakeEpisode42",
        "name": name,
        "release_date": "2026-09-28",
        "show": {
            "id": "6fakeShowHarborHours",
            "name": "Harbor Hours",
            "publisher": "Example Audio Co",
            "type": "show",
            "uri": "spotify:show:6fakeShowHarborHours",
        },
        "type": "episode",
        "uri": "spotify:episode:5fakeEpisode42",
    }


def player_state(
    item=None,
    *,
    is_playing=True,
    progress_ms=83000,
    context="playlist",
    shuffle=False,
    repeat="off",
    playing_type=None,
    device=None,
):
    item = neon_harbor() if item is None else item
    contexts = {
        "playlist": {"type": "playlist", "uri": "spotify:playlist:37i9fakeplaylist01"},
        "album": {"type": "album", "uri": "spotify:album:2fakeAlbumMidnightFerry"},
        "artist": {"type": "artist", "uri": "spotify:artist:1fakeArtistPaperLanterns"},
        "show": {"type": "show", "uri": "spotify:show:6fakeShowHarborHours"},
        "collection": {"type": "collection", "uri": "spotify:user:fakeuser:collection"},
    }
    ctx = contexts.get(context) if isinstance(context, str) else context
    if ctx is not None:
        ctx = dict(
            ctx, href="https://api.spotify.com/v1/fake", external_urls={"spotify": "https://open.spotify.com/fake"}
        )
    return {
        "device": device
        if device is not None
        else {
            "id": "fakeDevice01",
            "is_active": True,
            "is_private_session": False,
            "is_restricted": False,
            "name": "Kitchen Speaker",
            "type": "Speaker",
            "volume_percent": 65,
            "supports_volume": True,
        },
        "repeat_state": repeat,
        "shuffle_state": shuffle,
        "smart_shuffle": False,
        "context": ctx,
        "timestamp": 1790000000000,
        "progress_ms": progress_ms,
        "is_playing": is_playing,
        "item": item,
        "currently_playing_type": playing_type or (item or {}).get("type", "unknown"),
        "actions": {"disallows": {"resuming": True}},
    }


def queue_response(items=None):
    if items is None:
        items = [
            track("Low Tide", [JUNE_ARCADE], "Shoreline", 198000, "4fakeTrackLowTide"),
            track("Salt and Static", [PAPER_LANTERNS], "Midnight Ferry", 241000, "4fakeTrackSaltStatic"),
            track("Lighthouse Radio", [JUNE_ARCADE, PAPER_LANTERNS], "Shoreline", 205000, "4fakeTrackLighthouse"),
            episode(),
            track("Undertow", [JUNE_ARCADE], "Shoreline", 187000, "4fakeTrackUndertow"),
            track("Sixth Song", [JUNE_ARCADE], "Shoreline", 187000, "4fakeTrackSixth"),
        ]
    return {"currently_playing": neon_harbor(), "queue": copy.deepcopy(items)}


def recently_played(played_at="2026-10-01T17:48:00.000Z"):
    return {
        "items": [
            {
                "track": track("Low Tide", [JUNE_ARCADE], "Shoreline", 198000, "4fakeTrackLowTide"),
                "played_at": played_at,
                "context": {"type": "album", "uri": "spotify:album:2fakeAlbumShoreline"},
            }
        ],
        "next": "https://api.spotify.com/v1/me/player/recently-played?before=1",
        "cursors": {"after": "1", "before": "1"},
        "limit": 1,
        "href": "https://api.spotify.com/v1/me/player/recently-played?limit=1",
    }


def playlist(name):
    return {"name": name}
