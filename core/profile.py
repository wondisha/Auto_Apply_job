import os

from core.errors import ConfigurationError

PROFILE_ENV_VARS = {
    "first_name": "CANDIDATE_FIRST_NAME",
    "last_name": "CANDIDATE_LAST_NAME",
    "email": "CANDIDATE_EMAIL",
    "phone": "CANDIDATE_PHONE",
    "linkedin_url": "CANDIDATE_LINKEDIN_URL",
    "github_url": "CANDIDATE_GITHUB_URL",
    "location": "CANDIDATE_LOCATION",
    "sponsorship_needed": "CANDIDATE_SPONSORSHIP_NEEDED",
}


def get_candidate_profile():
    return {profile_key: os.getenv(env_name, "").strip() for profile_key, env_name in PROFILE_ENV_VARS.items()}


def validate_candidate_profile(candidate_profile=None):
    profile = candidate_profile if candidate_profile is not None else get_candidate_profile()
    missing = [
        env_name
        for profile_key, env_name in PROFILE_ENV_VARS.items()
        if not profile.get(profile_key, "").strip()
        or "<" in profile.get(profile_key, "")
        or ">" in profile.get(profile_key, "")
    ]
    if missing:
        variables = ", ".join(missing)
        raise ConfigurationError(
            f"Candidate profile is incomplete. Set {variables} in .env "
            "(copy .env.example to .env) or export them in your environment."
        )

    if profile["sponsorship_needed"].strip().lower() not in {"yes", "no"}:
        raise ConfigurationError(
            "CANDIDATE_SPONSORSHIP_NEEDED must be Yes or No. "
            "Configure it in .env (copy .env.example to .env) or your environment."
        )

    return profile
