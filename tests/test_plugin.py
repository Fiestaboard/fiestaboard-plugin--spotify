"""Tests for what the Spotify plugin shows."""

from datetime import datetime
from unittest.mock import patch

import pytest
from plugins.spotify import (
    SpotifyPlugin,
    board_safe,
    format_duration,
    progress_bar,
    tidy_title,
)
from src.devices import BoardContext
from src.plugins.geometry_conformance import assert_board_conformance, note_array
from src.text_to_board import count_tiles

from .conftest import TEST_CLIENT_ID
from .fixtures import JUNE_ARCADE, PAPER_LANTERNS, episode, player_state, track

FLAGSHIP = BoardContext.from_device_type("flagship")
NOTE = BoardContext.from_device_type("note")
NOW = datetime.fromisoformat("2026-10-01T18:00:00+00:00")


@pytest.fixture(autouse=True)
def fixed_now():
    with patch("plugins.spotify._utcnow", return_value=NOW):
        yield


def fetch(plugin, board=None):
    with plugin._bound_board(board):
        return plugin.fetch_data()


# ----------------------------------------------------------------------
# Manifest and metadata
# ----------------------------------------------------------------------


class TestManifest:
    def test_plugin_id_matches_manifest(self, plugin, manifest_data):
        assert plugin.plugin_id == manifest_data["id"] == "spotify"

    def test_every_declared_variable_is_returned(self, plugin, spotify_api, manifest_data):
        data = fetch(plugin).data
        for name in manifest_data["variables"]["simple"]:
            assert name in data, f"{name} declared in manifest but not returned"
        for name in manifest_data["variables"]["arrays"]:
            assert name in data

    def test_every_returned_variable_is_declared(self, plugin, spotify_api, manifest_data):
        declared = set(manifest_data["variables"]["simple"]) | set(manifest_data["variables"]["arrays"])
        assert set(fetch(plugin).data) == declared

    def test_queue_items_have_the_declared_fields(self, plugin, spotify_api, manifest_data):
        fields = set(manifest_data["variables"]["arrays"]["queue"]["item_fields"])
        for entry in fetch(plugin).data["queue"]:
            assert set(entry) == fields

    def test_every_variable_has_description_and_valid_group(self, manifest_data):
        groups = manifest_data["variables"]["groups"]
        for name, meta in manifest_data["variables"]["simple"].items():
            assert meta.get("description"), name
            assert meta.get("group") in groups, name

    def test_oauth_block_is_valid_and_has_no_secret(self, manifest_data):
        from src.oauth.provider import parse_provider_block, validate_provider_block

        block = manifest_data["oauth"]
        assert validate_provider_block(block) == []
        assert "client_secret" not in block and "client_secret_setting" not in block
        provider = parse_provider_block(block, "Spotify")
        assert provider.flows == ("relay",)
        assert provider.client_id == ""  # no shared client ID ships with the plugin
        assert provider.client_id_setting in manifest_data["settings_schema"]["properties"]

    def test_scopes_are_the_least_the_endpoints_need(self, manifest_data):
        assert sorted(manifest_data["oauth"]["scopes"]) == [
            "user-read-currently-playing",
            "user-read-playback-state",
            "user-read-recently-played",
        ]

    def test_manifest_passes_platform_validation(self, manifest_data):
        from src.plugins.manifest import validate_manifest

        assert validate_manifest(manifest_data) == (True, [])

    def test_one_primary_screenshot(self, manifest_data):
        assert [s["primary"] for s in manifest_data["screenshots"]].count(True) == 1


# ----------------------------------------------------------------------
# Now playing
# ----------------------------------------------------------------------


class TestNowPlaying:
    def test_playing_track(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["headline"] == "NOW PLAYING"
        assert data["title"] == "NEON HARBOR"
        assert data["artist"] == "PAPER LANTERNS"
        assert data["album"] == "MIDNIGHT FERRY"
        assert data["title_artist"] == "NEON HARBOR - PAPER LANTERNS"
        assert data["item_type"] == "TRACK"
        assert data["is_playing"] is True
        assert data["state"] == "PLAYING"
        assert data["state_tile"] == "{66}"
        assert data["last_played_ago"] == ""

    def test_playback_times(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["progress"] == "1:23"
        assert data["duration"] == "3:45"
        assert data["time_line"] == "1:23 / 3:45"
        assert data["remaining"] == "-2:22"
        assert data["progress_ms"] == 83000
        assert data["duration_ms"] == 225000
        assert data["progress_percent"] == 37

    def test_paused_track(self, plugin, spotify_api):
        spotify_api.player = player_state(is_playing=False)
        data = fetch(plugin).data
        assert data["headline"] == "PAUSED"
        assert data["state"] == "PAUSED"
        assert data["state_tile"] == "{65}"
        assert data["is_playing"] is False
        assert data["title"] == "NEON HARBOR"

    def test_several_artists_are_joined(self, plugin, spotify_api):
        spotify_api.player = player_state(track("Lighthouse Radio", [JUNE_ARCADE, PAPER_LANTERNS]))
        assert fetch(plugin).data["artist"] == "JUNE ARCADE, PAPER LANTERNS"

    def test_podcast_episode(self, plugin, spotify_api):
        spotify_api.player = player_state(episode(), context="show", progress_ms=125000)
        data = fetch(plugin).data
        assert data["item_type"] == "EPISODE"
        assert data["title"] == "EPISODE 42: TIDE TABLES"
        assert data["artist"] == "HARBOR HOURS"
        assert data["album"] == "EXAMPLE AUDIO CO"
        assert data["duration"] == "1:02:03"
        assert data["time_line"] == "2:05 / 1:02:03"
        assert data["context_type"] == "PODCAST"
        assert data["context_name"] == "HARBOR HOURS"

    def test_episode_title_is_not_tidied(self, plugin, spotify_api):
        spotify_api.player = player_state(episode("Interview (feat. A Guest)"), context="show")
        assert fetch(plugin).data["title"] == "INTERVIEW (FEAT. A GUEST)"

    def test_ad_break(self, plugin, spotify_api):
        state = player_state(playing_type="ad")
        state["item"] = None
        spotify_api.player = state
        data = fetch(plugin).data
        assert data["headline"] == "AD BREAK"
        assert data["item_type"] == "AD"
        assert data["title"] == ""
        assert data["time_line"] == ""
        assert data["is_playing"] is True

    def test_text_is_board_safe(self, plugin, spotify_api):
        spotify_api.player = player_state(
            track("Café {Noir} 🌙 Night", [{"name": "Beyoncé Fakename", "id": "x"}], album_name="Ünïcode ☕ Album")
        )
        data = fetch(plugin).data
        assert data["title"] == "CAFE NOIR NIGHT"
        assert data["artist"] == "BEYONCE FAKENAME"
        assert data["album"] == "UNICODE ALBUM"

    def test_track_with_missing_fields(self, plugin, spotify_api):
        spotify_api.player = player_state({"type": "track", "name": None, "uri": "spotify:track:x"})
        data = fetch(plugin).data
        assert data["title"] == ""
        assert data["artist"] == ""
        assert data["duration"] == ""
        assert data["time_line"] == ""
        assert data["progress_percent"] == 0


class TestNothingPlaying:
    def test_shows_last_played_track(self, plugin, spotify_api):
        spotify_api.player = None  # 204 No Content
        data = fetch(plugin).data
        assert data["headline"] == "LAST PLAYED"
        assert data["title"] == "LOW TIDE"
        assert data["artist"] == "JUNE ARCADE"
        assert data["last_played_ago"] == "12M AGO"
        assert data["is_playing"] is False
        assert data["state"] == "STOPPED"
        assert data["state_tile"] == "{63}"
        assert data["progress_bar"] == ""
        assert data["time_line"] == ""
        assert data["next_title"] == ""
        assert spotify_api.count("/me/player/queue") == 0

    def test_player_without_item_counts_as_nothing_playing(self, plugin, spotify_api):
        state = player_state(is_playing=False)
        state["item"] = None
        state["currently_playing_type"] = "unknown"
        spotify_api.player = state
        assert fetch(plugin).data["headline"] == "LAST PLAYED"

    def test_last_played_turned_off(self, make_plugin, spotify_api):
        plugin = make_plugin(show_last_played=False)
        spotify_api.player = None
        data = fetch(plugin).data
        assert data["headline"] == "NOTHING PLAYING"
        assert data["title"] == ""
        assert spotify_api.count("/me/player/recently-played") == 0

    def test_no_history(self, plugin, spotify_api):
        spotify_api.player = None
        spotify_api.recent = {"items": []}
        data = fetch(plugin).data
        assert data["headline"] == "NOTHING PLAYING"
        assert data["title"] == ""

    def test_recently_played_is_cached(self, plugin, spotify_api, clock):
        spotify_api.player = None
        fetch(plugin)
        clock.advance(10)
        fetch(plugin)
        assert spotify_api.count("/me/player/recently-played") == 1
        clock.advance(200)
        fetch(plugin)
        assert spotify_api.count("/me/player/recently-played") == 2

    @pytest.mark.parametrize(
        "played_at,expected",
        [
            ("2026-10-01T17:59:40.000Z", "JUST NOW"),
            ("2026-10-01T15:00:00.000Z", "3H AGO"),
            ("2026-09-29T12:00:00.000Z", "2D AGO"),
        ],
    )
    def test_last_played_ago(self, plugin, spotify_api, played_at, expected):
        spotify_api.player = None
        spotify_api.recent["items"][0]["played_at"] = played_at
        assert fetch(plugin).data["last_played_ago"] == expected


# ----------------------------------------------------------------------
# Device, modes and context
# ----------------------------------------------------------------------


class TestDeviceAndModes:
    def test_device(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["device_name"] == "KITCHEN SPEAKER"
        assert data["device_type"] == "SPEAKER"
        assert data["volume_percent"] == 65

    def test_device_without_volume(self, plugin, spotify_api):
        spotify_api.player = player_state(device={"name": "Car", "type": "Automobile", "volume_percent": None})
        assert fetch(plugin).data["volume_percent"] == ""

    @pytest.mark.parametrize(
        "shuffle,repeat,expected_repeat,expected_modes",
        [
            (False, "off", "OFF", ""),
            (True, "off", "OFF", "SHUFFLE"),
            (False, "context", "ALL", "REPEAT ALL"),
            (True, "track", "ONE", "SHUFFLE REPEAT ONE"),
        ],
    )
    def test_shuffle_and_repeat(self, plugin, spotify_api, shuffle, repeat, expected_repeat, expected_modes):
        spotify_api.player = player_state(shuffle=shuffle, repeat=repeat)
        data = fetch(plugin).data
        assert data["shuffle"] is shuffle
        assert data["repeat"] == expected_repeat
        assert data["modes"] == expected_modes


class TestContext:
    def test_playlist_name_is_looked_up(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["context_type"] == "PLAYLIST"
        assert data["context_name"] == "SUNDAY COFFEE"
        url, kwargs = spotify_api.calls[-1]
        assert url.endswith("/playlists/37i9fakeplaylist01")
        assert kwargs["params"] == {"fields": "name"}

    def test_playlist_name_is_cached(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(30)
        fetch(plugin)
        assert spotify_api.count("/playlists/37i9fakeplaylist01") == 1

    def test_unavailable_playlist_is_not_asked_again(self, plugin, spotify_api, clock):
        spotify_api.playlists.clear()  # Spotify's own playlists answer 404
        data = fetch(plugin).data
        assert data["context_type"] == "PLAYLIST"
        assert data["context_name"] == ""
        assert data["title"] == "NEON HARBOR"
        clock.advance(30)
        fetch(plugin)
        assert spotify_api.count("/playlists/37i9fakeplaylist01") == 1

    def test_playlist_lookup_outage_is_retried_later(self, plugin, spotify_api, clock):
        spotify_api.fail("/playlists/37i9fakeplaylist01", status=503)
        assert fetch(plugin).data["context_name"] == ""
        clock.advance(30)
        assert fetch(plugin).data["context_name"] == "SUNDAY COFFEE"

    def test_playlist_cache_is_bounded(self, plugin, spotify_api, clock):
        for i in range(60):
            playlist_id = f"fakeplaylist{i:02d}"
            spotify_api.playlists[playlist_id] = {"name": f"List {i}"}
            spotify_api.player = player_state(context={"type": "playlist", "uri": f"spotify:playlist:{playlist_id}"})
            fetch(plugin)
            clock.advance(10)
        assert len(plugin._playlist_names) == 50

    def test_playlist_without_id(self, plugin, spotify_api):
        spotify_api.player = player_state(context={"type": "playlist", "uri": ""})
        assert fetch(plugin).data["context_name"] == ""
        assert not any(p.startswith("/playlists/") for p in spotify_api.paths())

    def test_album_context(self, plugin, spotify_api):
        spotify_api.player = player_state(context="album")
        data = fetch(plugin).data
        assert (data["context_type"], data["context_name"]) == ("ALBUM", "MIDNIGHT FERRY")
        assert not any(p.startswith("/playlists/") for p in spotify_api.paths())

    def test_artist_context(self, plugin, spotify_api):
        spotify_api.player = player_state(context="artist")
        data = fetch(plugin).data
        assert (data["context_type"], data["context_name"]) == ("ARTIST", "PAPER LANTERNS")

    def test_artist_context_for_another_artist(self, plugin, spotify_api):
        spotify_api.player = player_state(context={"type": "artist", "uri": "spotify:artist:someoneelse"})
        assert fetch(plugin).data["context_name"] == ""

    def test_liked_songs(self, plugin, spotify_api):
        spotify_api.player = player_state(context="collection")
        data = fetch(plugin).data
        assert (data["context_type"], data["context_name"]) == ("LIKED SONGS", "")

    def test_no_context(self, plugin, spotify_api):
        spotify_api.player = player_state(context=None)
        data = fetch(plugin).data
        assert (data["context_type"], data["context_name"]) == ("", "")


# ----------------------------------------------------------------------
# Up next
# ----------------------------------------------------------------------


class TestQueue:
    def test_next_track(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["next_title"] == "LOW TIDE"
        assert data["next_artist"] == "JUNE ARCADE"
        assert data["next_line"] == "LOW TIDE - JUNE ARCADE"

    def test_queue_is_capped_at_five_and_includes_episodes(self, plugin, spotify_api):
        data = fetch(plugin).data
        assert data["queue_count"] == 5
        assert [e["title"] for e in data["queue"]] == [
            "LOW TIDE",
            "SALT AND STATIC",
            "LIGHTHOUSE RADIO",
            "EPISODE 42: TIDE TABLES",
            "UNDERTOW",
        ]
        assert data["queue"][3]["artist"] == "HARBOR HOURS"

    def test_empty_queue(self, plugin, spotify_api):
        spotify_api.queue = {"currently_playing": None, "queue": []}
        data = fetch(plugin).data
        assert data["next_title"] == ""
        assert data["next_line"] == ""
        assert data["queue_count"] == 0

    def test_queue_is_fetched_once_per_track(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(15)
        fetch(plugin)
        assert spotify_api.count("/me/player/queue") == 1

    def test_queue_is_fetched_again_when_the_track_changes(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(15)
        spotify_api.player = player_state(track("Low Tide", [JUNE_ARCADE], track_id="4fakeTrackLowTide"))
        fetch(plugin)
        assert spotify_api.count("/me/player/queue") == 2

    def test_queue_is_refreshed_after_a_minute(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(61)
        fetch(plugin)
        assert spotify_api.count("/me/player/queue") == 2

    def test_queue_turned_off(self, make_plugin, spotify_api):
        plugin = make_plugin(show_queue=False)
        data = fetch(plugin).data
        assert data["next_title"] == ""
        assert data["queue"] == []
        assert spotify_api.count("/me/player/queue") == 0

    def test_queue_failure_keeps_now_playing(self, plugin, spotify_api):
        spotify_api.fail("/me/player/queue", status=500)
        result = fetch(plugin)
        assert result.available is True
        assert result.data["title"] == "NEON HARBOR"
        assert result.data["next_title"] == ""

    def test_queue_failure_keeps_the_known_queue_for_the_same_track(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(61)
        spotify_api.fail("/me/player/queue", status=502)
        assert fetch(plugin).data["next_title"] == "LOW TIDE"


# ----------------------------------------------------------------------
# Titles, formatting and layout
# ----------------------------------------------------------------------


class TestTitles:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Neon Harbor - Remastered 2011", "Neon Harbor"),
            ("Neon Harbor - 2015 Remaster", "Neon Harbor"),
            ("Neon Harbor (Remastered 2009)", "Neon Harbor"),
            ("Neon Harbor [2019 Remaster]", "Neon Harbor"),
            ("Neon Harbor (feat. June Arcade)", "Neon Harbor"),
            ("Neon Harbor (with June Arcade)", "Neon Harbor"),
            ("Neon Harbor - Radio Edit", "Neon Harbor - Radio Edit"),
            ("Neon Harbor (Live)", "Neon Harbor (Live)"),
            ("(Remastered)", "(Remastered)"),
        ],
    )
    def test_tidy_title(self, raw, expected):
        assert tidy_title(raw) == expected

    def test_titles_are_tidied_by_default(self, plugin, spotify_api):
        spotify_api.player = player_state(track("Neon Harbor - Remastered 2011", [PAPER_LANTERNS]))
        assert fetch(plugin).data["title"] == "NEON HARBOR"

    def test_tidying_can_be_turned_off(self, make_plugin, spotify_api):
        plugin = make_plugin(tidy_titles=False)
        spotify_api.player = player_state(track("Neon Harbor - Remastered 2011", [PAPER_LANTERNS]))
        assert fetch(plugin).data["title"] == "NEON HARBOR - REMASTERED 2011"

    def test_queue_titles_are_tidied(self, plugin, spotify_api):
        spotify_api.queue = {"queue": [track("Low Tide (feat. Paper Lanterns)", [JUNE_ARCADE, PAPER_LANTERNS])]}
        assert fetch(plugin).data["next_title"] == "LOW TIDE"


class TestFormatting:
    @pytest.mark.parametrize(
        "ms,expected",
        [
            (0, "0:00"),
            (59999, "0:59"),
            (83000, "1:23"),
            (3600000, "1:00:00"),
            (None, "0:00"),
            ("bad", "0:00"),
            (-5, "0:00"),
        ],
    )
    def test_format_duration(self, ms, expected):
        assert format_duration(ms) == expected

    def test_board_safe_drops_braces_and_collapses_spaces(self):
        assert board_safe("a {66}  b\tc") == "A 66 B C"

    def test_progress_bar(self):
        bar = progress_bar(83000, 225000, 22)
        assert count_tiles(bar) == 22
        assert bar == "{66}" * 8 + "-" * 14

    @pytest.mark.parametrize(
        "progress,duration,width,filled",
        [(0, 1000, 10, 0), (1000, 1000, 10, 10), (2000, 1000, 10, 10), (500, 0, 10, 0), (-5, 1000, 10, 0)],
    )
    def test_progress_bar_limits(self, progress, duration, width, filled):
        bar = progress_bar(progress, duration, width)
        assert bar.count("{66}") == filled
        assert count_tiles(bar) == width

    def test_progress_bar_of_no_width(self):
        assert progress_bar(1, 2, 0) == ""

    @pytest.mark.parametrize("board,width", [(None, 22), (FLAGSHIP, 22), (NOTE, 15), (note_array(2, 1), 30)])
    def test_progress_bar_is_as_wide_as_the_board(self, plugin, spotify_api, board, width):
        assert count_tiles(fetch(plugin, board).data["progress_bar"]) == width


class TestDisplay:
    def test_flagship_layout(self, plugin, spotify_api):
        lines = fetch(plugin, FLAGSHIP).formatted_lines
        assert lines == [
            "{66} NOW PLAYING",
            "NEON HARBOR",
            "PAPER LANTERNS",
            "SUNDAY COFFEE",
            "1:23 / 3:45",
            "{66}" * 8 + "-" * 14,
        ]

    def test_note_layout(self, plugin, spotify_api):
        assert fetch(plugin, NOTE).formatted_lines == ["NEON HARBOR", "PAPER LANTERNS", "1:23 / 3:45"]

    def test_tall_board_lists_up_next(self, plugin, spotify_api):
        lines = fetch(plugin, note_array(2, 4)).formatted_lines
        assert lines[6:9] == ["", "UP NEXT", "LOW TIDE - JUNE ARCADE"]
        assert len(lines) == 12

    def test_last_played_layout(self, plugin, spotify_api):
        spotify_api.player = None
        lines = fetch(plugin, FLAGSHIP).formatted_lines
        assert lines[0] == "{63} LAST PLAYED 12M AGO"
        assert lines[1:3] == ["LOW TIDE", "JUNE ARCADE"]

    def test_note_layout_when_nothing_playing(self, make_plugin, spotify_api):
        plugin = make_plugin(show_last_played=False)
        spotify_api.player = None
        assert fetch(plugin, NOTE).formatted_lines == ["NOTHING PLAYING", "", ""]

    def test_note_layout_for_last_played(self, plugin, spotify_api):
        spotify_api.player = None
        assert fetch(plugin, NOTE).formatted_lines == ["LOW TIDE", "JUNE ARCADE", "{63} 12M AGO"]

    def test_long_lines_are_cut_to_the_board(self, plugin, spotify_api):
        spotify_api.player = player_state(track("A Very Long Song Title That Keeps Going", [PAPER_LANTERNS]))
        lines = fetch(plugin, NOTE).formatted_lines
        assert lines[0] == "A VERY LONG SON"

    def test_get_formatted_display(self, plugin, spotify_api):
        with plugin._bound_board(FLAGSHIP):
            lines = plugin.get_formatted_display()
        assert lines[1] == "NEON HARBOR"
        assert len(lines) == 6 and isinstance(lines, list)

    def test_get_formatted_display_when_unavailable(self, plugin, spotify_api, token):
        token.value = None
        assert plugin.get_formatted_display() is None

    def test_conforms_on_every_board_shape(self, make_plugin, spotify_api, manifest_data):
        report = assert_board_conformance(make_plugin, manifest=manifest_data)
        assert not [w for w in report.warnings if w.code != "MAX_LENGTH_EXCEEDS_NOTE"], report.summary()


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------


class TestConfig:
    def test_valid_config(self, plugin):
        assert plugin.validate_config({"client_id": TEST_CLIENT_ID, "refresh_seconds": 15}) == []

    def test_client_id_is_required(self, plugin):
        errors = plugin.validate_config({})
        assert len(errors) == 1 and "Client ID is required" in errors[0]

    @pytest.mark.parametrize("bad", ["abc", "your-client-id-here", TEST_CLIENT_ID + "0"])
    def test_client_id_shape(self, plugin, bad):
        errors = plugin.validate_config({"client_id": bad})
        assert errors == ["Client ID should be the 32-character code from your Spotify app's Settings page"]

    def test_client_id_whitespace_is_ignored(self, plugin):
        assert plugin.validate_config({"client_id": f"  {TEST_CLIENT_ID} "}) == []

    def test_refresh_below_minimum(self, plugin):
        errors = plugin.validate_config({"client_id": TEST_CLIENT_ID, "refresh_seconds": 2})
        assert len(errors) == 1 and "refresh" in errors[0].lower()

    def test_default_refresh_interval(self, plugin):
        assert plugin.refresh_seconds == 15

    def test_config_change_drops_cached_state(self, plugin, spotify_api, clock):
        fetch(plugin)
        plugin.config = dict(plugin.config, tidy_titles=False)
        clock.advance(1)
        fetch(plugin)
        assert spotify_api.count("/me/player") == 2
        assert spotify_api.count("/me/player/queue") == 2


def test_module_exports_plugin():
    import plugins.spotify as module

    assert module.Plugin is SpotifyPlugin
