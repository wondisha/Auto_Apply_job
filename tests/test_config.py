import pytest

from core import config

ENV_VARS = [
    "FALLBACK_LLM_PROVIDER", "FALLBACK_PROVIDER", "AGENT_LLM_TIMEOUT", "AGENT_STEP_TIMEOUT",
    "AGENT_USE_THINKING", "AGENT_USE_VISION", "DAILY_APPLICATION_TARGET", "REQUIRE_VERIFIED_COMPANY",
    "VERIFIED_COMPANY_ALLOWLIST", "PREFERRED_ROLE_KEYWORDS", "PREFERRED_LOCATION_KEYWORDS",
    "JOB_SEARCH_RESULT_LIMIT",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    assert config.get_fallback_provider_name() == "google"
    assert config.get_agent_llm_timeout_seconds() == 180
    assert config.get_agent_step_timeout_seconds() == 240
    assert config.get_daily_application_target() == 5
    assert config.get_search_result_limit() == 25
    assert config.require_verified_company() is True
    assert config.should_use_agent_thinking() is True
    assert config.should_use_agent_vision() is True
    assert config.get_verified_company_allowlist() == set()


def test_provider_normalized_and_legacy_fallback(monkeypatch):
    monkeypatch.setenv("FALLBACK_PROVIDER", "  OpenAI ")
    assert config.get_fallback_provider_name() == "openai"
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "Ollama")
    assert config.get_fallback_provider_name() == "ollama"


def test_ollama_disables_thinking_and_vision_by_default(monkeypatch):
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "ollama")
    assert config.should_use_agent_thinking() is False
    assert config.should_use_agent_vision() is False


@pytest.mark.parametrize("value,expected", [("0", False), ("false", False), ("No", False), ("1", True), ("yes", True)])
def test_explicit_flags_override_provider(monkeypatch, value, expected):
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("AGENT_USE_THINKING", value)
    monkeypatch.setenv("AGENT_USE_VISION", value)
    assert config.should_use_agent_thinking() is expected
    assert config.should_use_agent_vision() is expected


@pytest.mark.parametrize("value", ["0", "no", "False"])
def test_require_verified_company_disabled(monkeypatch, value):
    monkeypatch.setenv("REQUIRE_VERIFIED_COMPANY", value)
    assert config.require_verified_company() is False


@pytest.mark.parametrize("env_name,getter", [
    ("AGENT_LLM_TIMEOUT", config.get_agent_llm_timeout_seconds),
    ("AGENT_STEP_TIMEOUT", config.get_agent_step_timeout_seconds),
    ("DAILY_APPLICATION_TARGET", config.get_daily_application_target),
    ("JOB_SEARCH_RESULT_LIMIT", config.get_search_result_limit),
])
def test_integer_settings_validation(monkeypatch, env_name, getter):
    monkeypatch.setenv(env_name, "42")
    assert getter() == 42
    monkeypatch.setenv(env_name, "   ")
    assert getter() > 0  # blank falls back to default
    monkeypatch.setenv(env_name, "abc")
    with pytest.raises(ValueError, match="must be an integer"):
        getter()
    for bad in ("0", "-3"):
        monkeypatch.setenv(env_name, bad)
        with pytest.raises(ValueError, match="greater than zero"):
            getter()


def test_allowlist_and_csv_parsing(monkeypatch):
    monkeypatch.setenv("VERIFIED_COMPANY_ALLOWLIST", " Acme , ,Globex")
    assert config.get_verified_company_allowlist() == {"acme", "globex"}
    monkeypatch.setenv("PREFERRED_ROLE_KEYWORDS", "a, b ,,c")
    assert config.get_preferred_role_keywords() == ["a", "b", "c"]
    assert config.split_csv_env("MISSING_VAR", "x,y") == ["x", "y"]


def test_preferred_location_keywords_default_includes_profile_location():
    keywords = config.get_preferred_location_keywords({"location": "Austin"})
    assert keywords == ["Austin", "Dallas", "Texas", "Remote", "Hybrid"]
