import pytest

from core import ranking

PROFILE = {
    "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com", "phone": "555-0100",
    "location": "Austin", "sponsorship_needed": "No",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("PREFERRED_ROLE_KEYWORDS", "PREFERRED_LOCATION_KEYWORDS"):
        monkeypatch.delenv(name, raising=False)


def make_context(**overrides):
    context = {"page_title": "", "job_title": "", "description": "", "page_text": "", "company_name": "Acme"}
    context.update(overrides)
    return context


def test_normalize_text():
    assert ranking.normalize_text("  Hello\n\tWORLD  ") == "hello world"


def test_count_keyword_hits():
    assert ranking.count_keyword_hits("Snowflake  and SQL Server", ["snowflake", "sql server", "oracle", ""]) == [
        "snowflake", "sql server",
    ]


def test_extract_resume_keywords_dedups_and_drops_stopwords():
    terms = ranking.extract_resume_keywords("Snowflake with snowflake and Python data engineer")
    assert terms == ["snowflake", "and", "python"]


def test_extract_resume_keywords_capped_at_40():
    text = " ".join(f"term{i}" for i in range(100))
    assert len(ranking.extract_resume_keywords(text)) == 40


def test_score_empty_context_is_zero():
    assert ranking.score_job_context(make_context(), "", PROFILE) == (0, [])


def test_score_representative_context_is_deterministic():
    context = make_context(
        job_title="Snowflake Data Engineer",
        description="Remote role. Must be U.S. citizens only.",
        verified=True,
        verification_source="allowlist",
    )
    score, reasons = ranking.score_job_context(context, "snowflake", PROFILE)
    # role: snowflake + data engineer = 50; location: remote = 12; resume: snowflake = 4;
    # eligibility = 10; verified = 30
    assert score == 106
    assert reasons == [
        "role matches: snowflake, data engineer",
        "location matches: Remote",
        "resume overlap: snowflake",
        "eligibility aligned",
        "verified via allowlist",
    ]
    assert ranking.score_job_context(context, "snowflake", PROFILE) == (score, reasons)


def test_eligibility_only_when_sponsorship_not_needed():
    context = make_context(description="no sponsorship available")
    needs = dict(PROFILE, sponsorship_needed="Yes")
    assert ranking.score_job_context(context, "", PROFILE)[0] == 10
    assert ranking.score_job_context(context, "", needs)[0] == 0


def test_unrelated_job_scores_lower_than_relevant_job():
    relevant = make_context(job_title="Database Administrator", description="SQL Server in Austin")
    unrelated = make_context(job_title="Pastry Chef", description="Bake bread")
    assert ranking.score_job_context(relevant, "", PROFILE)[0] > ranking.score_job_context(unrelated, "", PROFILE)[0]


def test_analyze_resume_gaps_shape():
    context = make_context(job_title="Snowflake Engineer", page_text="Snowflake and Airflow with Python snowflake")
    result = ranking.analyze_resume_gaps(context, "snowflake python", PROFILE)
    assert result["readiness"] == "strong"
    assert result["matched_keywords"] == ["snowflake", "python"]
    assert "airflow" in result["missing_keywords"]
    assert result["role_matches"] == ["snowflake"]
    assert result["candidate_location"] == "Austin"
