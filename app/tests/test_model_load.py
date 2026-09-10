"""Tests for probing and loading a model on the server, with fakes for the network."""

import pytest

from resume_matcher import llm_client
from resume_matcher.config import Config
from resume_matcher.llm_client import ensure_model_loaded, server_root

UNLOADED = RuntimeError(
    "Error code: 400 - {'error': {'message': 'No model loaded. Call POST /inference/load first.'}}"
)


def test_server_root_strips_version_suffix():
    assert server_root("http://localhost:8888/v1") == "http://localhost:8888"
    assert server_root("http://localhost:8888/v1/") == "http://localhost:8888"
    assert server_root("https://api.example.com") == "https://api.example.com"


def test_ready_model_needs_no_load(monkeypatch):
    monkeypatch.setattr(llm_client, "probe_model", lambda cfg, timeout=30.0: None)
    monkeypatch.setattr(llm_client, "request_model_load", lambda cfg, timeout: pytest.fail("must not load"))
    assert ensure_model_loaded(Config(), log=lambda _: None) == "ready"


def test_unloaded_model_is_loaded_then_ready(monkeypatch):
    calls = {"probe": 0, "load": 0}

    def probe(cfg, timeout=30.0):
        calls["probe"] += 1
        if calls["probe"] < 3:          # not ready on the first two probes
            raise UNLOADED

    monkeypatch.setattr(llm_client, "probe_model", probe)
    monkeypatch.setattr(llm_client, "request_model_load", lambda cfg, timeout: calls.__setitem__("load", calls["load"] + 1))
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    logged = []
    assert ensure_model_loaded(Config(), log=logged.append, wait=10) == "loaded"
    assert calls == {"probe": 3, "load": 1}
    assert any("Loading" in line for line in logged) and any("is loaded" in line for line in logged)


def test_other_errors_are_raised_without_loading(monkeypatch):
    def probe(cfg, timeout=30.0):
        raise RuntimeError("Error code: 401 - invalid api key")

    monkeypatch.setattr(llm_client, "probe_model", probe)
    monkeypatch.setattr(llm_client, "request_model_load", lambda cfg, timeout: pytest.fail("must not load"))
    with pytest.raises(RuntimeError, match="401"):
        ensure_model_loaded(Config(), log=lambda _: None)


def test_gives_up_after_timeout(monkeypatch):
    def probe(cfg, timeout=30.0):
        raise UNLOADED

    monkeypatch.setattr(llm_client, "probe_model", probe)
    monkeypatch.setattr(llm_client, "request_model_load", lambda cfg, timeout: None)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 3))
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: float(next(clock)))
    with pytest.raises(RuntimeError, match="Gave up"):
        ensure_model_loaded(Config(), log=lambda _: None, wait=10)


def test_load_request_tries_payloads_and_urls(monkeypatch):
    seen = []

    def post(url, payload, timeout):
        seen.append((url, tuple(payload)))
        if url.endswith("/v1/inference/load"):
            return 404, ""
        return (422, "unknown field") if "model" in payload else (200, "")

    monkeypatch.setattr(llm_client, "_post_json", post)
    cfg = Config()
    llm_client.request_model_load(cfg, timeout=5)
    # Beside /v1 first: {"model"} rejected with 422, {"model_id"} accepted.
    assert seen[0] == ("http://localhost:8888/inference/load", ("model",))
    assert seen[1] == ("http://localhost:8888/inference/load", ("model_id",))
    assert len(seen) == 2


def test_load_request_reports_rejection(monkeypatch):
    monkeypatch.setattr(llm_client, "_post_json", lambda url, payload, timeout: (400, "nope"))
    with pytest.raises(RuntimeError, match="did not accept"):
        llm_client.request_model_load(Config(), timeout=5)


def test_load_request_moves_on_when_url_unreachable(monkeypatch):
    import urllib.error

    seen = []

    def post(url, payload, timeout):
        seen.append(url)
        if "/v1/" not in url:
            raise urllib.error.URLError("connection refused")
        return 200, ""

    monkeypatch.setattr(llm_client, "_post_json", post)
    llm_client.request_model_load(Config(), timeout=5)
    assert seen == ["http://localhost:8888/inference/load", "http://localhost:8888/v1/inference/load"]
