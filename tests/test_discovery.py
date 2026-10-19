import pytest

from core import discovery


def test_build_linkedin_search_url():
    url = discovery.build_linkedin_search_url(" data engineer ", " Dallas, TX ")
    assert url == "https://www.linkedin.com/jobs/search/?keywords=data+engineer&location=Dallas%2C+TX"


def test_build_linkedin_search_url_without_location_and_with_start():
    assert discovery.build_linkedin_search_url("sql", "") == "https://www.linkedin.com/jobs/search/?keywords=sql"
    assert discovery.build_linkedin_search_url("sql", "  ", start=25).endswith("keywords=sql&start=25")


def test_build_linkedin_guest_search_url():
    base = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=sql"
    assert discovery.build_linkedin_guest_search_url("sql", "") == base
    assert discovery.build_linkedin_guest_search_url("sql", "Remote", start=50) == base + "&location=Remote&start=50"


def test_extract_job_urls_dedups_and_normalizes():
    html = (
        '<a href="/jobs/view/data-engineer-123?trk=abc">A</a>'
        '<a href="https://www.linkedin.com/jobs/view/data-engineer-123?refId=1">dup</a>'
        "<a href='https://www.linkedin.com/jobs/view/dba-456'>B</a>"
        '<a href="/jobs/view/data-engineer-123">dup2</a>'
    )
    assert discovery.extract_job_urls_from_search_html(html) == [
        "https://www.linkedin.com/jobs/view/data-engineer-123",
        "https://www.linkedin.com/jobs/view/dba-456",
    ]


def test_extract_job_urls_empty():
    assert discovery.extract_job_urls_from_search_html("<html></html>") == []


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_discover_linkedin_job_urls_uses_mocked_requests(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return FakeResponse('<a href="/jobs/view/a-1"></a><a href="/jobs/view/b-2"></a>')

    monkeypatch.setattr(discovery.requests, "get", fake_get)
    urls = discovery.discover_linkedin_job_urls("sql", "", 50)
    assert urls == ["https://www.linkedin.com/jobs/view/a-1", "https://www.linkedin.com/jobs/view/b-2"]
    assert len(calls) == 2  # second page adds nothing new, so paging stops


def test_discover_linkedin_job_urls_respects_max_results(monkeypatch):
    monkeypatch.setattr(
        discovery.requests, "get",
        lambda *a, **k: FakeResponse('<a href="/jobs/view/a-1"></a><a href="/jobs/view/b-2"></a>'),
    )
    assert discovery.discover_linkedin_job_urls("sql", "", 1) == ["https://www.linkedin.com/jobs/view/a-1"]


def test_discover_job_urls_validation(monkeypatch):
    with pytest.raises(ValueError, match="Unsupported job search portal"):
        discovery.discover_job_urls("sql", "", portal="indeed")
    with pytest.raises(ValueError, match="query is required"):
        discovery.discover_job_urls("  ", "", portal="linkedin")


def test_discover_job_urls_no_results_and_success(monkeypatch):
    monkeypatch.delenv("JOB_SEARCH_PORTAL", raising=False)
    monkeypatch.setattr(discovery, "discover_linkedin_job_urls", lambda *a: [])
    with pytest.raises(ValueError, match="No job postings were discovered for 'sql' in Dallas"):
        discovery.discover_job_urls("sql", "Dallas")
    monkeypatch.setattr(discovery, "discover_linkedin_job_urls", lambda q, l, n: ["u", n])
    assert discovery.discover_job_urls("sql", None, max_results=3) == ["u", 3]
