"""Tests for the request retry policy: never duplicate work the server may finish."""

import pytest
from openai import APIConnectionError, APITimeoutError

from resume_matcher import llm_client
from resume_matcher.config import Config
from resume_matcher.llm_client import LocalLLM


def _timeout():
    exc = APITimeoutError.__new__(APITimeoutError)
    Exception.__init__(exc, "Request timed out.")
    return exc


def _connection_error():
    exc = APIConnectionError.__new__(APIConnectionError)
    Exception.__init__(exc, "Connection error.")
    return exc


class Busy(Exception):
    status_code = 503


class BadRequest(Exception):
    status_code = 400


class _Reply:
    def __init__(self):
        msg = type("Msg", (), {"content": '{"score": 70, "comment": "ok"}', "model_extra": None})()
        self.choices = [type("Choice", (), {"message": msg, "finish_reason": "stop"})()]


def _llm(monkeypatch, script):
    """LocalLLM whose completions raise/return the scripted outcomes in order."""
    calls = []

    class FakeCompletions:
        def create(self, **kw):
            calls.append(kw)
            outcome = script[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    class FakeClient:
        def __init__(self, **kw):
            assert kw.get("max_retries") == 0, "SDK retries must be off"
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(llm_client, "OpenAI", FakeClient)
    monkeypatch.setattr(llm_client.time, "sleep", lambda s: None)
    return LocalLLM(Config()), calls


def test_busy_server_is_retried_without_duplicating_work(monkeypatch):
    llm, calls = _llm(monkeypatch, [Busy(), Busy(), _Reply()])
    assert '"score": 70' in llm.complete("sys", "user")
    assert len(calls) == 3


def test_timeout_is_never_retried(monkeypatch):
    llm, calls = _llm(monkeypatch, [_timeout(), _Reply()])
    with pytest.raises(RuntimeError, match="timed out.*lower the concurrency"):
        llm.complete("sys", "user")
    assert len(calls) == 1


def test_connection_error_is_retried_once(monkeypatch):
    llm, calls = _llm(monkeypatch, [_connection_error(), _Reply()])
    llm.complete("sys", "user")
    assert len(calls) == 2
    llm2, calls2 = _llm(monkeypatch, [_connection_error(), _connection_error(), _Reply()])
    with pytest.raises(APIConnectionError):
        llm2.complete("sys", "user")
    assert len(calls2) == 2


def test_other_errors_are_raised_immediately(monkeypatch):
    llm, calls = _llm(monkeypatch, [BadRequest("no model loaded"), _Reply()])
    with pytest.raises(BadRequest):
        llm.complete("sys", "user")
    assert len(calls) == 1


def test_busy_gives_up_after_busy_wait(monkeypatch):
    llm, calls = _llm(monkeypatch, [Busy()] * 50)
    llm.config.llm_busy_wait = 5.0   # 1 + 2 + 4 seconds of backoff, then stop
    with pytest.raises(Busy):
        llm.complete("sys", "user")
    assert 3 <= len(calls) <= 5
