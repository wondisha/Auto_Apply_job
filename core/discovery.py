import os
import re
from urllib.parse import quote_plus

import requests

from core.config import get_search_result_limit
from core.errors import ConfigurationError, DiscoveryError
from core.logging_config import get_logger

logger = get_logger(__name__)

SUPPORTED_SEARCH_PORTALS = {"linkedin"}


def build_linkedin_search_url(search_query, search_location, start=0):
    keyword_value = quote_plus(search_query.strip())
    location_value = quote_plus(search_location.strip()) if search_location.strip() else ""
    url = f"https://www.linkedin.com/jobs/search/?keywords={keyword_value}"
    if location_value:
        url += f"&location={location_value}"
    if start > 0:
        url += f"&start={start}"
    return url


def build_linkedin_guest_search_url(search_query, search_location, start=0):
    keyword_value = quote_plus(search_query.strip())
    location_value = quote_plus(search_location.strip()) if search_location.strip() else ""
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keyword_value}"
    if location_value:
        url += f"&location={location_value}"
    if start > 0:
        url += f"&start={start}"
    return url


def extract_job_urls_from_search_html(html_text):
    matches = re.findall(
        r'https://www\.linkedin\.com/jobs/view/[^\"\'\s?]+|/jobs/view/[^\"\'\s?]+',
        html_text,
        flags=re.IGNORECASE,
    )
    discovered = []
    seen = set()
    for match in matches:
        normalized = match if match.startswith("http") else f"https://www.linkedin.com{match}"
        normalized = normalized.split("?", 1)[0]
        if normalized not in seen:
            discovered.append(normalized)
            seen.add(normalized)
    return discovered


def discover_linkedin_job_urls(search_query, search_location, max_results):
    discovered = []
    seen = set()
    headers = {"User-Agent": "Mozilla/5.0"}

    page_size = 25
    for start in range(0, max_results, page_size):
        search_url = build_linkedin_guest_search_url(search_query, search_location, start=start)
        logger.debug("Fetching LinkedIn search page start=%s", start)
        try:
            response = requests.get(search_url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DiscoveryError(f"LinkedIn job search request failed: {exc}") from exc

        page_urls = extract_job_urls_from_search_html(response.text)
        if not page_urls:
            break

        new_on_page = 0
        for url in page_urls:
            if url in seen:
                continue
            discovered.append(url)
            seen.add(url)
            new_on_page += 1
            if len(discovered) >= max_results:
                return discovered

        if new_on_page == 0:
            break

    return discovered


def discover_job_urls(search_query, search_location, portal=None, max_results=None):
    portal_name = (portal or os.getenv("JOB_SEARCH_PORTAL", "linkedin")).strip().lower()
    if portal_name not in SUPPORTED_SEARCH_PORTALS:
        supported = ", ".join(sorted(SUPPORTED_SEARCH_PORTALS))
        raise ConfigurationError(f"Unsupported job search portal '{portal_name}'. Supported values: {supported}")

    if not search_query or not search_query.strip():
        raise ConfigurationError("Job search query is required for automatic discovery.")

    result_limit = max_results or get_search_result_limit()
    if portal_name == "linkedin":
        job_urls = discover_linkedin_job_urls(search_query, search_location or "", result_limit)
    else:
        job_urls = []

    if not job_urls:
        location_text = f" in {search_location}" if search_location else ""
        raise DiscoveryError(f"No job postings were discovered for '{search_query}'{location_text} on {portal_name}.")

    return job_urls
