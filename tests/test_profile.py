import pytest

from core import profile

VALID = {
    "CANDIDATE_FIRST_NAME": "Ada",
    "CANDIDATE_LAST_NAME": "Lovelace",
    "CANDIDATE_EMAIL": "ada@example.com",
    "CANDIDATE_PHONE": "555-0100",
    "CANDIDATE_LINKEDIN_URL": "https://linkedin.com/in/ada",
    "CANDIDATE_GITHUB_URL": "https://github.com/ada",
    "CANDIDATE_LOCATION": "Dallas, TX",
    "CANDIDATE_SPONSORSHIP_NEEDED": "No",
}


@pytest.fixture
def valid_env(monkeypatch):
    for name, value in VALID.items():
        monkeypatch.setenv(name, value)


def test_profile_shape_and_stripping(valid_env, monkeypatch):
    monkeypatch.setenv("CANDIDATE_FIRST_NAME", "  Ada  ")
    result = profile.get_candidate_profile()
    assert set(result) == set(profile.PROFILE_ENV_VARS)
    assert result["first_name"] == "Ada"
    assert result["sponsorship_needed"] == "No"


def test_missing_env_yields_empty_strings(monkeypatch):
    for name in VALID:
        monkeypatch.delenv(name, raising=False)
    assert set(profile.get_candidate_profile().values()) == {""}


def test_validate_success_returns_profile(valid_env):
    result = profile.validate_candidate_profile()
    assert result["email"] == "ada@example.com"


def test_validate_missing_and_blank_lists_variables(valid_env, monkeypatch):
    monkeypatch.delenv("CANDIDATE_EMAIL")
    monkeypatch.setenv("CANDIDATE_PHONE", "   ")
    with pytest.raises(ValueError) as exc:
        profile.validate_candidate_profile()
    assert "CANDIDATE_EMAIL" in str(exc.value)
    assert "CANDIDATE_PHONE" in str(exc.value)
    assert "CANDIDATE_LAST_NAME" not in str(exc.value)


def test_validate_rejects_placeholders(valid_env, monkeypatch):
    monkeypatch.setenv("CANDIDATE_EMAIL", "<your-email>")
    with pytest.raises(ValueError, match="CANDIDATE_EMAIL"):
        profile.validate_candidate_profile()


@pytest.mark.parametrize("value", ["maybe", "true"])
def test_validate_sponsorship_must_be_yes_or_no(valid_env, monkeypatch, value):
    monkeypatch.setenv("CANDIDATE_SPONSORSHIP_NEEDED", value)
    with pytest.raises(ValueError, match="Yes or No"):
        profile.validate_candidate_profile()


def test_validate_accepts_explicit_profile_case_insensitive():
    explicit = {key: "x" for key in profile.PROFILE_ENV_VARS}
    explicit["sponsorship_needed"] = "YES"
    assert profile.validate_candidate_profile(explicit) is explicit
