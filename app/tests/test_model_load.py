"""Tests for making sure the server has the model loaded, with a fake probe."""

import pytest

from resume_matcher import llm_client
from resume_matcher.config import Config
from resume_matcher.llm_client import ensure_model_loaded

UNLOADED = RuntimeError(
    "Error code: 400 - {'error': {'message': 'No model loaded. Call POST /inference/load first. "
    "Or enable Model auto-switch (Settings > API) to load a requested model automatically.'}}"
)


def _quick(monkeypatch):
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    clock = iter(range(0, 100000, 4))
    monkeypatch.setattr(llm_client.time, "monotonic", lambda: float(next(clock)))


def test_ready_model_answers_at_once(monkeypatch):
    monkeypatch.setattr(llm_client, "probe_model", lambda cfg, timeout=None: None)
    assert ensure_model_loaded(Config(), log=lambda _: None) == "ready"


def test_server_that_loads_asynchronously_is_waited_for(monkeypatch):
    _quick(monkeypatch)
    probes = {"n": 0}

    def probe(cfg, timeout=None):
        probes["n"] += 1
        if probes["n"] < 3:
            raise UNLOADED

    monkeypatch.setattr(llm_client, "probe_model", probe)
    logged = []
    assert ensure_model_loaded(Config(), log=logged.append) == "loaded"
    assert probes["n"] == 3
    assert any("waiting" in line for line in logged) and any("is loaded" in line for line in logged)


def test_refusal_names_the_setting_to_enable(monkeypatch):
    _quick(monkeypatch)

    def probe(cfg, timeout=None):
        raise UNLOADED

    monkeypatch.setattr(llm_client, "probe_model", probe)
    with pytest.raises(RuntimeError, match='Switch model by request'):
        ensure_model_loaded(Config(), log=lambda _: None, wait=10)


def test_other_errors_are_raised_unchanged(monkeypatch):
    def probe(cfg, timeout=None):
        raise RuntimeError("Error code: 401 - invalid api key")

    monkeypatch.setattr(llm_client, "probe_model", probe)
    with pytest.raises(RuntimeError, match="401"):
        ensure_model_loaded(Config(), log=lambda _: None)


def test_probe_uses_load_timeout_by_default(monkeypatch):
    seen = {}

    class FakeCompletions:
        def create(self, **kw):
            seen["model"] = kw["model"]

    class FakeClient:
        def __init__(self, base_url, api_key, timeout):
            seen["timeout"] = timeout
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_client, "OpenAI", FakeClient)
    cfg = Config()
    cfg.llm_load_timeout = 123.0
    llm_client.probe_model(cfg)
    assert seen == {"timeout": 123.0, "model": cfg.llm_model}
