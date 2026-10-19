import os


def get_fallback_provider_name():
    return os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("FALLBACK_PROVIDER", "google")).strip().lower()


def get_agent_llm_timeout_seconds():
    configured = os.getenv("AGENT_LLM_TIMEOUT", "180").strip() or "180"
    try:
        timeout = int(configured)
    except ValueError as exc:
        raise ValueError(f"AGENT_LLM_TIMEOUT must be an integer. Got: {configured}") from exc

    if timeout <= 0:
        raise ValueError("AGENT_LLM_TIMEOUT must be greater than zero.")

    return timeout


def get_agent_step_timeout_seconds():
    configured = os.getenv("AGENT_STEP_TIMEOUT", "240").strip() or "240"
    try:
        timeout = int(configured)
    except ValueError as exc:
        raise ValueError(f"AGENT_STEP_TIMEOUT must be an integer. Got: {configured}") from exc

    if timeout <= 0:
        raise ValueError("AGENT_STEP_TIMEOUT must be greater than zero.")

    return timeout


def should_use_agent_thinking():
    configured = os.getenv("AGENT_USE_THINKING", "").strip().lower()
    if configured:
        return configured not in {"0", "false", "no"}

    return get_fallback_provider_name() != "ollama"


def should_use_agent_vision():
    configured = os.getenv("AGENT_USE_VISION", "").strip().lower()
    if configured:
        return configured not in {"0", "false", "no"}

    provider = get_fallback_provider_name()
    if provider == "ollama":
        return False

    return True


def get_daily_application_target():
    configured = os.getenv("DAILY_APPLICATION_TARGET", "5").strip() or "5"
    try:
        target = int(configured)
    except ValueError as exc:
        raise ValueError(f"DAILY_APPLICATION_TARGET must be an integer. Got: {configured}") from exc

    if target <= 0:
        raise ValueError("DAILY_APPLICATION_TARGET must be greater than zero.")

    return target


def require_verified_company():
    return os.getenv("REQUIRE_VERIFIED_COMPANY", "1").strip().lower() not in {"0", "false", "no"}


def get_verified_company_allowlist():
    allowlist = os.getenv("VERIFIED_COMPANY_ALLOWLIST", "")
    return {entry.strip().lower() for entry in allowlist.split(",") if entry.strip()}


def split_csv_env(name, fallback=""):
    raw_value = os.getenv(name, fallback)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def get_preferred_role_keywords():
    return split_csv_env(
        "PREFERRED_ROLE_KEYWORDS",
        "snowflake,data engineer,database administrator,data platform,cloud data operations,sql server",
    )


def get_preferred_location_keywords(candidate_profile):
    return split_csv_env(
        "PREFERRED_LOCATION_KEYWORDS",
        f"{candidate_profile['location']},Dallas,Texas,Remote,Hybrid",
    )


def get_search_result_limit():
    configured = os.getenv("JOB_SEARCH_RESULT_LIMIT", "25").strip() or "25"
    try:
        limit = int(configured)
    except ValueError as exc:
        raise ValueError(f"JOB_SEARCH_RESULT_LIMIT must be an integer. Got: {configured}") from exc

    if limit <= 0:
        raise ValueError("JOB_SEARCH_RESULT_LIMIT must be greater than zero.")

    return limit
