"""Shared fixtures for the Spotify plugin tests.

``spotify_api`` patches ``requests.get`` with a fake Spotify Web API that
answers the endpoints this plugin uses with payloads shaped like the real
ones (see ``fixtures.py``). Tests change its state (what is playing, the
queue, recently played) or queue raw responses to simulate errors.

``get_oauth_token`` is patched on the plugin instance: the platform's OAuth
service is not under test here, only how the plugin uses what it returns.

All names in the fixtures are invented.
"""

import json
from collections import deque
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from plugins.spotify import SpotifyPlugin

from .fixtures import player_state, playlist, queue_response, recently_played

MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"
API = "https://api.spotify.com/v1"
TEST_CLIENT_ID = "0123456789abcdef0123456789abcdef"  # fake, 32 hex characters
TEST_TOKEN = "test_access_token"


class FakeResponse:
    def __init__(self, body=None, status_code=200, headers=None):
        self._body = body
        self.status_code = status_code
        self.headers = headers or {}
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


class FakeSpotify:
    """Answers requests.get the way the Spotify Web API would."""

    def __init__(self):
        self.player = player_state()
        self.queue = queue_response()
        self.recent = recently_played()
        self.playlists = {"37i9fakeplaylist01": playlist("Sunday Coffee")}
        # Raw responses (or exceptions) that override the next call to a path.
        self.overrides = {}
        self.calls = []

    def fail(self, path, response=None, *, status=None, headers=None, times=1):
        """Make the next *times* calls to *path* return *response* or raise it."""
        if response is None:
            response = FakeResponse({"error": {"status": status, "message": "test"}}, status, headers)
        self.overrides.setdefault(path, deque()).extend([response] * times)

    def paths(self):
        return [url[len(API) :] for url, _ in self.calls]

    def count(self, path):
        return self.paths().count(path)

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, {"params": params, "headers": headers, "timeout": timeout}))
        path = url[len(API) :]
        queued = self.overrides.get(path)
        if queued:
            response = queued.popleft()
            if isinstance(response, Exception):
                raise response
            return response
        if path == "/me/player":
            return FakeResponse(self.player, 200) if self.player is not None else FakeResponse(None, 204)
        if path == "/me/player/queue":
            return FakeResponse(self.queue)
        if path == "/me/player/recently-played":
            return FakeResponse(self.recent)
        if path.startswith("/playlists/"):
            body = self.playlists.get(path.split("/")[2])
            if body is None:
                return FakeResponse({"error": {"status": 404, "message": "Resource not found"}}, 404)
            return FakeResponse(body)
        raise AssertionError(f"Unexpected Spotify request: {url}")  # pragma: no cover


class Clock:
    """A controllable stand-in for time.monotonic()."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


@pytest.fixture
def manifest_data():
    with open(MANIFEST_PATH) as f:
        return json.load(f)


@pytest.fixture(autouse=True)
def clock():
    c = Clock()
    with patch("plugins.spotify._monotonic", side_effect=c):
        yield c


@pytest.fixture
def spotify_api():
    fake = FakeSpotify()
    with patch("plugins.spotify.requests.get", side_effect=fake):
        yield fake


@pytest.fixture
def token():
    """The token get_oauth_token() hands out; tests may change ``token.value``."""

    class Token:
        value = TEST_TOKEN

    return Token


@pytest.fixture
def make_plugin(manifest_data, token):
    def factory(**config):
        p = SpotifyPlugin(manifest_data)
        p.config = {"enabled": True, "client_id": TEST_CLIENT_ID, **config}
        p.get_oauth_token = lambda: token.value
        return p

    return factory


@pytest.fixture
def plugin(make_plugin):
    return make_plugin()


@pytest.fixture
def timeout_error():
    return requests.exceptions.Timeout("read timed out")
