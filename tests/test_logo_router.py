"""Tests for the local-AI (ai_router) logo generator and 'local' provider dispatch."""

import logging

from flights import logo_resolver


def test_generate_with_router_extracts_svg(monkeypatch):
    svg = '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>'

    import ai_router

    captured = {}

    def _fake_chat(prompt, *, model=None, max_tokens=None, **kw):
        captured["prompt"] = prompt
        captured["max_tokens"] = max_tokens
        return f"Here is your logo:\n{svg}\nDone."

    monkeypatch.setattr(ai_router, "chat", _fake_chat)
    out = logo_resolver._generate_with_router("BAW", "British Airways", "ignored-key")
    assert out == svg
    assert "British Airways" in captured["prompt"]
    assert captured["max_tokens"] == 4096


def test_generate_with_router_returns_none_on_error(monkeypatch):
    import ai_router

    def _boom(*a, **k):
        raise ai_router.AIRouterError("gateway down")

    monkeypatch.setattr(ai_router, "chat", _boom)
    assert logo_resolver._generate_with_router("XXX", "Test Air", "k") is None


def test_local_provider_is_recognised(monkeypatch, caplog):
    """provider='local' must resolve in the dispatch (not hit the unknown-provider branch)."""
    monkeypatch.setattr(logo_resolver, "_get_existing_logos", lambda: (set(), set()))
    monkeypatch.setattr(logo_resolver, "_load_missing_logos", lambda: {})
    with caplog.at_level(logging.ERROR):
        result = logo_resolver.generate_missing_logos(
            provider="local", api_key="x", airlines_json=[]
        )
    assert result == []  # no candidates -> empty, but provider was recognised
    assert "Unknown AI provider" not in caplog.text
