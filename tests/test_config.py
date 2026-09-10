"""Tests for configuration layering: defaults < settings.json < environment."""

import json
from pathlib import Path

from resume_matcher.config import SETTINGS_FIELDS, Config
from resume_matcher.providers import PROVIDERS, find


def test_bare_config_is_pure_defaults(monkeypatch):
    monkeypatch.setenv("RM_LLM_MODEL", "should-not-apply")
    assert Config().llm_model == "gemma-4-12b"


def test_settings_file_overrides_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_mode": "hosted", "llm_base_url": "https://x/v1",
                                "llm_api_key": "sk-test", "concurrency": 2}))
    c = Config.load(settings_path=path, environ={})
    assert (c.llm_mode, c.llm_base_url, c.llm_api_key) == ("hosted", "https://x/v1", "sk-test")
    assert c.concurrency == 2 and isinstance(c.concurrency, int)
    assert c.is_hosted


def test_env_overrides_settings_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"llm_model": "from-file", "concurrency": 2}))
    c = Config.load(settings_path=path, environ={"RM_LLM_MODEL": "from-env", "RM_CONCURRENCY": "8"})
    assert c.llm_model == "from-env"
    assert c.concurrency == 8


def test_empty_env_value_does_not_override(tmp_path):
    c = Config.load(settings_path=tmp_path / "none.json", environ={"RM_LLM_MODEL": ""})
    assert c.llm_model == "gemma-4-12b"


def test_missing_or_corrupt_settings_are_ignored(tmp_path):
    assert Config.load(settings_path=tmp_path / "missing.json", environ={}).llm_mode == "local"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert Config.load(settings_path=bad, environ={}).llm_mode == "local"
    lst = tmp_path / "list.json"
    lst.write_text("[1, 2]")
    assert Config.load(settings_path=lst, environ={}).llm_mode == "local"


def test_junk_typed_value_keeps_existing(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"concurrency": "lots"}))
    assert Config.load(settings_path=path, environ={}).concurrency == 4


def test_save_roundtrip_only_persists_whitelisted_fields(tmp_path):
    c = Config()
    c.llm_mode, c.llm_api_key, c.llm_model = "hosted", "sk-abc", "gpt-x"
    c.verbose = True  # not a settings field; must not be written
    path = c.save_settings(tmp_path / "settings.json")
    data = json.loads(path.read_text())
    assert set(data) == set(SETTINGS_FIELDS)
    assert "verbose" not in data
    again = Config.load(settings_path=path, environ={})
    assert (again.llm_mode, again.llm_api_key, again.llm_model) == ("hosted", "sk-abc", "gpt-x")


def test_with_model_copies_without_mutating():
    c = Config()
    d = c.with_model("other")
    assert d.llm_model == "other" and c.llm_model == "gemma-4-12b"


def test_provider_presets_are_well_formed():
    assert find("Unsloth Desktop").mode == "local"
    for p in PROVIDERS:
        assert p.mode in ("local", "hosted")
        if p.base_url:
            assert p.base_url.startswith("http"), p.name
        if p.mode == "hosted" and p.name.startswith("Custom"):
            assert p.base_url == ""
    assert find("nope") is None
