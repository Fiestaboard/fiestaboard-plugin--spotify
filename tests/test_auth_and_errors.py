"""Tests for signing in, failures, rate limits and sharing one fetch between boards."""

import pytest
import requests
from plugins.spotify import (
    FORBIDDEN_ERROR,
    NOT_CONNECTED_ERROR,
    PLATFORM_TOO_OLD_ERROR,
    UNAUTHORIZED_ERROR,
    SpotifyPlugin,
)
from src.devices import BoardContext

from .conftest import TEST_TOKEN, FakeResponse

FLAGSHIP = BoardContext.from_device_type("flagship")
NOTE = BoardContext.from_device_type("note")


def fetch(plugin, board=None):
    with plugin._bound_board(board):
        return plugin.fetch_data()


# ----------------------------------------------------------------------
# Signing in
# ----------------------------------------------------------------------


class TestToken:
    def test_token_is_sent_as_bearer(self, plugin, spotify_api):
        fetch(plugin)
        for _, kwargs in spotify_api.calls:
            assert kwargs["headers"]["Authorization"] == f"Bearer {TEST_TOKEN}"
            assert kwargs["timeout"] == 10

    def test_player_request_includes_episodes(self, plugin, spotify_api):
        fetch(plugin)
        url, kwargs = spotify_api.calls[0]
        assert url == "https://api.spotify.com/v1/me/player"
        assert kwargs["params"] == {"additional_types": "episode"}

    @pytest.mark.parametrize("value", [None, ""])
    def test_not_connected(self, plugin, spotify_api, token, value):
        token.value = value
        result = fetch(plugin)
        assert result.available is False
        assert result.error == NOT_CONNECTED_ERROR
        assert spotify_api.calls == []

    def test_token_is_asked_for_on_every_fetch(self, plugin, spotify_api, clock, token):
        fetch(plugin)
        token.value = "test_refreshed_token"
        clock.advance(20)
        fetch(plugin)
        assert spotify_api.calls[-1][1]["headers"]["Authorization"] == "Bearer test_refreshed_token"

    def test_platform_without_oauth(self, manifest_data, spotify_api, monkeypatch):
        from src.plugins.base import PluginBase

        monkeypatch.delattr(PluginBase, "get_oauth_token")
        plugin = SpotifyPlugin(manifest_data)
        result = plugin.fetch_data()
        assert result.available is False
        assert result.error == PLATFORM_TOO_OLD_ERROR

    def test_uses_the_platform_token(self, manifest_data, spotify_api, monkeypatch):
        """The real PluginBase.get_oauth_token is what an unpatched plugin calls."""
        from src.plugins.base import PluginBase

        monkeypatch.setattr(PluginBase, "get_oauth_token", lambda self: "test_platform_token")
        plugin = SpotifyPlugin(manifest_data)
        assert plugin.fetch_data().available is True
        assert spotify_api.calls[0][1]["headers"]["Authorization"] == "Bearer test_platform_token"


# ----------------------------------------------------------------------
# HTTP failures
# ----------------------------------------------------------------------


class TestFailures:
    def test_401_asks_to_reconnect(self, plugin, spotify_api):
        spotify_api.fail("/me/player", status=401)
        result = fetch(plugin)
        assert result.available is False
        assert result.error == UNAUTHORIZED_ERROR

    def test_401_is_not_retried_with_the_same_token(self, plugin, spotify_api, clock):
        spotify_api.fail("/me/player", status=401)
        fetch(plugin)
        clock.advance(30)
        result = fetch(plugin)
        assert result.error == UNAUTHORIZED_ERROR
        assert spotify_api.count("/me/player") == 1
        clock.advance(31)
        assert fetch(plugin).available is True
        assert spotify_api.count("/me/player") == 2

    def test_new_token_after_401_is_tried_straight_away(self, plugin, spotify_api, clock, token):
        spotify_api.fail("/me/player", status=401)
        fetch(plugin)
        token.value = "test_reconnected_token"
        clock.advance(1)
        assert fetch(plugin).available is True

    def test_403_explains_the_development_mode_allowlist(self, plugin, spotify_api):
        spotify_api.fail("/me/player", status=403)
        result = fetch(plugin)
        assert result.available is False
        assert result.error == FORBIDDEN_ERROR
        assert "User Management" in result.error

    def test_403_is_not_shown_as_stale_data(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(20)
        spotify_api.fail("/me/player", status=403)
        assert fetch(plugin).available is False

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_error(self, plugin, spotify_api, status):
        spotify_api.fail("/me/player", status=status)
        result = fetch(plugin)
        assert result.available is False
        assert f"HTTP {status}" in result.error

    def test_unexpected_status(self, plugin, spotify_api):
        spotify_api.fail("/me/player", status=418)
        result = fetch(plugin)
        assert result.available is False
        assert "HTTP 418" in result.error

    def test_404(self, plugin, spotify_api):
        spotify_api.fail("/me/player", status=404)
        assert "404" in fetch(plugin).error

    def test_timeout(self, plugin, spotify_api, timeout_error):
        spotify_api.fail("/me/player", timeout_error)
        result = fetch(plugin)
        assert result.available is False
        assert result.error == "Timed out contacting Spotify"

    def test_connection_error(self, plugin, spotify_api):
        spotify_api.fail("/me/player", requests.exceptions.ConnectionError("no route to host"))
        result = fetch(plugin)
        assert result.available is False
        assert result.error == "Could not reach Spotify: ConnectionError"

    def test_unexpected_exception_never_escapes(self, plugin, spotify_api):
        spotify_api.fail("/me/player", FakeResponse(["not", "an", "object"]))
        result = fetch(plugin)
        assert result.available is False
        assert result.error

    def test_empty_200_body_is_nothing_playing(self, plugin, spotify_api):
        spotify_api.fail("/me/player", FakeResponse(None, 200))
        assert fetch(plugin).data["headline"] == "LAST PLAYED"


# ----------------------------------------------------------------------
# Rate limits and backing off
# ----------------------------------------------------------------------


class TestBackoff:
    def test_429_waits_for_retry_after(self, plugin, spotify_api, clock):
        spotify_api.fail("/me/player", status=429, headers={"Retry-After": "40"})
        result = fetch(plugin)
        assert result.available is False
        assert result.error == "Spotify rate limit reached; trying again in 40s"
        clock.advance(39)
        assert fetch(plugin).available is False
        assert spotify_api.count("/me/player") == 1
        clock.advance(2)
        assert fetch(plugin).available is True
        assert spotify_api.count("/me/player") == 2

    @pytest.mark.parametrize(
        "headers,expected",
        [({}, 30), ({"Retry-After": "soon"}, 30), ({"Retry-After": "0"}, 1), ({"Retry-After": "86400"}, 3600)],
    )
    def test_retry_after_is_bounded(self, plugin, spotify_api, headers, expected):
        spotify_api.fail("/me/player", status=429, headers=headers)
        assert fetch(plugin).error == f"Spotify rate limit reached; trying again in {expected}s"

    def test_server_error_backs_off(self, plugin, spotify_api, clock):
        spotify_api.fail("/me/player", status=503)
        fetch(plugin)
        clock.advance(10)
        fetch(plugin)
        assert spotify_api.count("/me/player") == 1
        clock.advance(6)
        assert fetch(plugin).available is True

    def test_last_data_is_shown_during_a_short_outage(self, plugin, spotify_api, clock):
        assert fetch(plugin).available is True
        clock.advance(20)
        spotify_api.fail("/me/player", status=429, headers={"Retry-After": "30"})
        result = fetch(plugin)
        assert result.available is True
        assert result.data["title"] == "NEON HARBOR"

    def test_last_data_expires(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(20)
        spotify_api.fail("/me/player", status=429, headers={"Retry-After": "600"})
        assert fetch(plugin).available is True
        clock.advance(121)
        result = fetch(plugin)
        assert result.available is False
        assert "rate limit" in result.error

    def test_rate_limit_on_queue_keeps_now_playing_and_backs_off(self, plugin, spotify_api, clock):
        spotify_api.fail("/me/player/queue", status=429, headers={"Retry-After": "60"})
        result = fetch(plugin)
        assert result.available is True
        assert result.data["title"] == "NEON HARBOR"
        clock.advance(10)
        assert fetch(plugin).available is True  # last data, no new request
        assert spotify_api.count("/me/player") == 1

    def test_recently_played_failure_keeps_the_last_known_track(self, plugin, spotify_api, clock):
        spotify_api.player = None
        fetch(plugin)
        clock.advance(200)
        spotify_api.fail("/me/player/recently-played", status=500)
        assert fetch(plugin).data["title"] == "LOW TIDE"


# ----------------------------------------------------------------------
# One Spotify call for several boards
# ----------------------------------------------------------------------


class TestSharedSnapshot:
    def test_flagship_and_note_share_one_request(self, plugin, spotify_api, clock):
        flagship = fetch(plugin, FLAGSHIP)
        clock.advance(1)
        note = fetch(plugin, NOTE)
        assert spotify_api.count("/me/player") == 1
        assert flagship.data["title"] == note.data["title"]
        assert len(flagship.data["progress_bar"]) != len(note.data["progress_bar"])

    def test_snapshot_expires(self, plugin, spotify_api, clock):
        fetch(plugin)
        clock.advance(6)
        fetch(plugin)
        assert spotify_api.count("/me/player") == 2

    def test_platform_cache_and_snapshot_together(self, plugin, spotify_api):
        plugin.get_data(FLAGSHIP)
        plugin.get_data(FLAGSHIP)
        plugin.get_data(NOTE)
        assert spotify_api.count("/me/player") == 1
