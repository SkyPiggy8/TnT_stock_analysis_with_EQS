"""Tests for TRADINGAGENTS_* env-var overlay onto DEFAULT_CONFIG."""

from __future__ import annotations

import importlib

import pytest

import tradingagents.default_config as default_config_module


@pytest.fixture(autouse=True)
def _restore_default_config_module(monkeypatch):
    yield
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(default_config_module._DATA_VENDOR_ALL_ENV, raising=False)
    for key in list(default_config_module._DATA_VENDOR_ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(default_config_module)


def _reload_with_env(monkeypatch, **overrides):
    """Set/clear env vars then reload default_config to re-evaluate DEFAULT_CONFIG."""
    for key in list(default_config_module._ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv(default_config_module._DATA_VENDOR_ALL_ENV, raising=False)
    for key in list(default_config_module._DATA_VENDOR_ENV_OVERRIDES):
        monkeypatch.delenv(key, raising=False)
    for key, val in overrides.items():
        monkeypatch.setenv(key, val)
    return importlib.reload(default_config_module)


def test_no_env_uses_built_in_defaults(monkeypatch):
    dc = _reload_with_env(monkeypatch)
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gpt-5.5"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gpt-5.4-mini"
    assert dc.DEFAULT_CONFIG["backend_url"] is None
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is False
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "tushare,akshare,yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "tushare,akshare,yfinance"
    assert dc.DEFAULT_CONFIG["data_vendors"]["news_data"] == "akshare_news,yfinance"


def test_string_overrides(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="google",
        TRADINGAGENTS_DEEP_THINK_LLM="gemini-3-pro-preview",
        TRADINGAGENTS_QUICK_THINK_LLM="gemini-3-flash-preview",
        TRADINGAGENTS_LLM_BACKEND_URL="https://example.invalid/v1",
        TRADINGAGENTS_OUTPUT_LANGUAGE="Chinese",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "google"
    assert dc.DEFAULT_CONFIG["deep_think_llm"] == "gemini-3-pro-preview"
    assert dc.DEFAULT_CONFIG["quick_think_llm"] == "gemini-3-flash-preview"
    assert dc.DEFAULT_CONFIG["backend_url"] == "https://example.invalid/v1"
    assert dc.DEFAULT_CONFIG["output_language"] == "Chinese"


def test_int_coercion(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="3",
        TRADINGAGENTS_MAX_RISK_ROUNDS="2",
        TRADINGAGENTS_LLM_MAX_RETRIES="5",
    )
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 3
    assert isinstance(dc.DEFAULT_CONFIG["max_debate_rounds"], int)
    assert dc.DEFAULT_CONFIG["max_risk_discuss_rounds"] == 2
    assert isinstance(dc.DEFAULT_CONFIG["max_risk_discuss_rounds"], int)
    assert dc.DEFAULT_CONFIG["llm_max_retries"] == 5
    assert isinstance(dc.DEFAULT_CONFIG["llm_max_retries"], int)


def test_float_coercion(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_LLM_TIMEOUT="180.5")
    assert dc.DEFAULT_CONFIG["llm_timeout"] == 180.5
    assert isinstance(dc.DEFAULT_CONFIG["llm_timeout"], float)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("true", True), ("True", True), ("1", True), ("yes", True), ("on", True),
        ("false", False), ("False", False), ("0", False), ("no", False), ("off", False),
    ],
)
def test_bool_coercion(monkeypatch, raw, expected):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_CHECKPOINT_ENABLED=raw)
    assert dc.DEFAULT_CONFIG["checkpoint_enabled"] is expected


def test_llm_trust_env_bool_coercion(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_LLM_TRUST_ENV="false")
    assert dc.DEFAULT_CONFIG["llm_trust_env"] is False


def test_akshare_trust_env_bool_coercion(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_AKSHARE_TRUST_ENV="true")
    assert dc.DEFAULT_CONFIG["akshare_trust_env"] is True


def test_empty_env_value_is_passthrough(monkeypatch):
    """Empty TRADINGAGENTS_* values must not clobber the built-in default."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_LLM_PROVIDER="",
        TRADINGAGENTS_MAX_DEBATE_ROUNDS="",
    )
    assert dc.DEFAULT_CONFIG["llm_provider"] == "openai"
    assert dc.DEFAULT_CONFIG["max_debate_rounds"] == 1


def test_invalid_int_raises(monkeypatch):
    """Garbage int values should surface a ValueError at import, not silently misconfigure."""
    monkeypatch.setenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "not-a-number")
    with pytest.raises(ValueError):
        importlib.reload(default_config_module)
    # Restore module state for subsequent tests in this process
    monkeypatch.delenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", raising=False)
    importlib.reload(default_config_module)


def test_unknown_env_var_is_ignored(monkeypatch):
    """Env vars outside _ENV_OVERRIDES must not bleed into DEFAULT_CONFIG."""
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_NONEXISTENT_KEY="oops",
    )
    assert "nonexistent_key" not in dc.DEFAULT_CONFIG


def test_data_vendor_all_override(monkeypatch):
    dc = _reload_with_env(monkeypatch, TRADINGAGENTS_DATA_VENDOR="alpha_vantage")
    assert dc.DEFAULT_CONFIG["data_vendors"] == {
        "core_stock_apis": "alpha_vantage",
        "technical_indicators": "alpha_vantage",
        "fundamental_data": "alpha_vantage",
        "news_data": "alpha_vantage",
    }


def test_data_vendor_category_override_wins(monkeypatch):
    dc = _reload_with_env(
        monkeypatch,
        TRADINGAGENTS_DATA_VENDOR="alpha_vantage",
        TRADINGAGENTS_NEWS_DATA_VENDOR="yfinance",
    )
    assert dc.DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "alpha_vantage"
    assert dc.DEFAULT_CONFIG["data_vendors"]["technical_indicators"] == "alpha_vantage"
    assert dc.DEFAULT_CONFIG["data_vendors"]["fundamental_data"] == "alpha_vantage"
    assert dc.DEFAULT_CONFIG["data_vendors"]["news_data"] == "yfinance"
