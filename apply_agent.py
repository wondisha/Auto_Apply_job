import argparse
import asyncio
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse

import requests
from dotenv import load_dotenv
from browser_use import Agent, Browser, ChatGoogle

load_dotenv()

STATUS_FILE = Path(__file__).with_name(".agent_status.json")
APPLICATION_LOG_FILE = Path(__file__).with_name(".application_history.json")
ARTIFACTS_ROOT = Path(__file__).with_name("artifacts")
VERIFIED_MARKERS = (
    "verified company",
    "verified employer",
    "linkedin verified",
    "verified hiring",
)
SUPPORTED_SEARCH_PORTALS = {"linkedin"}


def resolve_ollama_executable():
    env_path = os.getenv("OLLAMA_EXECUTABLE_PATH") or os.getenv("FALLBACK_OLLAMA_EXECUTABLE_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"OLLAMA_EXECUTABLE_PATH does not exist: {candidate}")

    path_executable = shutil.which("ollama")
    if path_executable:
        return path_executable

    candidates = [
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")),
        Path(r"C:\Program Files\Ollama\ollama.exe"),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "Ollama is not installed or not discoverable. Install Ollama, add it to PATH, or set OLLAMA_EXECUTABLE_PATH."
    )


def resolve_browser_executable():
    env_path = os.getenv("BROWSER_EXECUTABLE_PATH")
    if env_path:
        candidate = Path(env_path).expanduser()
        if candidate.is_file():
            return str(candidate)
        raise FileNotFoundError(f"BROWSER_EXECUTABLE_PATH does not exist: {candidate}")

    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe")),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "Application", "msedge.exe")),
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "No supported Chrome/Edge executable was found. Set BROWSER_EXECUTABLE_PATH to a valid browser binary."
    )


def resolve_browser_profile_dir():
    env_dir = os.getenv("BROWSER_USER_DATA_DIR")
    if env_dir:
        profile_dir = Path(env_dir).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        return str(profile_dir), False

    profile_dir = Path(tempfile.mkdtemp(prefix="browser-use-profile-"))
    return str(profile_dir), True


def create_primary_llm():
    if os.getenv("USE_FALLBACK_AS_PRIMARY", "0").strip().lower() in {"1", "true", "yes"}:
        fallback_llm = create_fallback_llm()
        if fallback_llm is None:
            raise ValueError("USE_FALLBACK_AS_PRIMARY is enabled, but no fallback LLM is configured.")
        return fallback_llm

    return ChatGoogle(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "2")),
        retry_base_delay=float(os.getenv("GEMINI_RETRY_BASE_DELAY", "2")),
        retry_max_delay=float(os.getenv("GEMINI_RETRY_MAX_DELAY", "30")),
    )


def create_fallback_llm():
    provider = os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("FALLBACK_PROVIDER", "google")).strip().lower()
    model = os.getenv("FALLBACK_LLM_MODEL", os.getenv("FALLBACK_MODEL", "")).strip()

    if not model:
        return None

    if provider == "google":
        return ChatGoogle(
            model=model,
            api_key=os.getenv("FALLBACK_GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"),
            max_retries=int(os.getenv("FALLBACK_GEMINI_MAX_RETRIES", os.getenv("GEMINI_MAX_RETRIES", "2"))),
            retry_base_delay=float(os.getenv("FALLBACK_GEMINI_RETRY_BASE_DELAY", os.getenv("GEMINI_RETRY_BASE_DELAY", "2"))),
            retry_max_delay=float(os.getenv("FALLBACK_GEMINI_RETRY_MAX_DELAY", os.getenv("GEMINI_RETRY_MAX_DELAY", "30"))),
        )

    if provider == "openai":
        from browser_use import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=os.getenv("FALLBACK_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("FALLBACK_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            max_retries=int(os.getenv("FALLBACK_OPENAI_MAX_RETRIES", "2")),
        )

    if provider == "anthropic":
        from browser_use import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=os.getenv("FALLBACK_ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY"),
        )

    if provider == "groq":
        from browser_use import ChatGroq

        return ChatGroq(
            model=model,
            api_key=os.getenv("FALLBACK_GROQ_API_KEY") or os.getenv("GROQ_API_KEY"),
        )

    if provider == "litellm":
        from browser_use import ChatLiteLLM

        return ChatLiteLLM(
            model=model,
            api_key=os.getenv("FALLBACK_LITELLM_API_KEY") or os.getenv("LITELLM_API_KEY"),
            base_url=os.getenv("FALLBACK_LITELLM_BASE_URL") or os.getenv("LITELLM_BASE_URL"),
        )

    if provider == "ollama":
        from browser_use import ChatOllama

        return ChatOllama(
            model=model,
            host=os.getenv("FALLBACK_OLLAMA_HOST") or os.getenv("OLLAMA_HOST"),
        )

    raise ValueError(
        f"Unsupported FALLBACK_LLM_PROVIDER '{provider}'. Supported values: google, openai, anthropic, groq, litellm, ollama."
    )


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


def read_json_file(path, default_value):
    if not path.exists():
        return default_value

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_value


def write_json_file(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_status_record():
    return read_json_file(STATUS_FILE, {})


def save_status_record(status):
    write_json_file(STATUS_FILE, status)


def clear_status_record():
    try:
        STATUS_FILE.unlink(missing_ok=True)
    except OSError:
        pass


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


def get_candidate_profile():
    return {
        "first_name": "Wondi",
        "last_name": "Wolde",
        "email": "wondenad@gmail.com",
        "phone": "240-505-7107",
        "linkedin_url": "https://linkedin.com/in/wondi",
        "github_url": "https://github.com/wondisha",
        "location": "Garland, Texas",
        "sponsorship_needed": "No",
    }


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


def normalize_text(value):
    return re.sub(r"\s+", " ", value.lower()).strip()


def count_keyword_hits(text, keywords):
    normalized = normalize_text(text)
    hits = []
    for keyword in keywords:
        lowered = normalize_text(keyword)
        if lowered and lowered in normalized:
            hits.append(keyword)
    return hits


def extract_resume_keywords(resume_text):
    candidate_terms = re.findall(r"[a-zA-Z][a-zA-Z0-9\+#\.\-/]{2,}", resume_text.lower())
    stopwords = {
        "with", "from", "that", "this", "have", "your", "will", "team", "role", "years", "using",
        "into", "such", "than", "their", "about", "work", "data", "engineer", "manager", "senior",
    }
    ranked_terms = []
    seen = set()
    for term in candidate_terms:
        if term in stopwords or term in seen:
            continue
        seen.add(term)
        ranked_terms.append(term)
        if len(ranked_terms) >= 40:
            break
    return ranked_terms


def score_job_context(job_context, resume_text, candidate_profile):
    combined_text = "\n".join(
        [job_context["page_title"], job_context["job_title"], job_context["description"], job_context["page_text"][:3000]]
    )
    score = 0
    reasons = []

    role_hits = count_keyword_hits(combined_text, get_preferred_role_keywords())
    if role_hits:
        score += 25 * len(role_hits)
        reasons.append(f"role matches: {', '.join(role_hits[:4])}")

    location_hits = count_keyword_hits(combined_text, get_preferred_location_keywords(candidate_profile))
    if location_hits:
        score += 12 * len(location_hits)
        reasons.append(f"location matches: {', '.join(location_hits[:3])}")

    resume_hits = count_keyword_hits(combined_text, extract_resume_keywords(resume_text))
    if resume_hits:
        score += min(len(resume_hits), 10) * 4
        reasons.append(f"resume overlap: {', '.join(resume_hits[:5])}")

    eligibility_markers = (
        "green card",
        "u.s. citizens",
        "citizens only",
        "no sponsorship",
        "no opt",
    )
    eligibility_hits = count_keyword_hits(combined_text, list(eligibility_markers))
    if candidate_profile["sponsorship_needed"].strip().lower() == "no" and eligibility_hits:
        score += 10
        reasons.append("eligibility aligned")

    if job_context.get("verified"):
        score += 30
        reasons.append(f"verified via {job_context.get('verification_source')}")

    return score, reasons


def get_search_result_limit():
    configured = os.getenv("JOB_SEARCH_RESULT_LIMIT", "25").strip() or "25"
    try:
        limit = int(configured)
    except ValueError as exc:
        raise ValueError(f"JOB_SEARCH_RESULT_LIMIT must be an integer. Got: {configured}") from exc

    if limit <= 0:
        raise ValueError("JOB_SEARCH_RESULT_LIMIT must be greater than zero.")

    return limit


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
        response = requests.get(search_url, headers=headers, timeout=30)
        response.raise_for_status()

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
        raise ValueError(f"Unsupported job search portal '{portal_name}'. Supported values: {supported}")

    if not search_query or not search_query.strip():
        raise ValueError("Job search query is required for automatic discovery.")

    result_limit = max_results or get_search_result_limit()
    if portal_name == "linkedin":
        job_urls = discover_linkedin_job_urls(search_query, search_location or "", result_limit)
    else:
        job_urls = []

    if not job_urls:
        location_text = f" in {search_location}" if search_location else ""
        raise ValueError(f"No job postings were discovered for '{search_query}'{location_text} on {portal_name}.")

    return job_urls


def rank_job_urls(job_urls, resume_path, candidate_profile):
    resume_text = extract_resume_text(Path(resume_path).expanduser())
    ranked_jobs = []

    for job_url in job_urls:
        try:
            job_context = fetch_job_posting_context(job_url)
            verified, verification_source = classify_company_verification(job_context)
            job_context["verified"] = verified
            job_context["verification_source"] = verification_source

            if require_verified_company() and not verified:
                ranked_jobs.append(
                    {
                        "url": job_url,
                        "job_context": job_context,
                        "eligible": False,
                        "score": -1,
                        "reasons": ["company verification not confirmed"],
                    }
                )
                continue

            score, reasons = score_job_context(job_context, resume_text, candidate_profile)
            ranked_jobs.append(
                {
                    "url": job_url,
                    "job_context": job_context,
                    "eligible": True,
                    "score": score,
                    "reasons": reasons,
                }
            )
        except Exception as exc:
            ranked_jobs.append(
                {
                    "url": job_url,
                    "job_context": {"url": job_url, "company_name": "Unknown Company", "job_title": job_url},
                    "eligible": False,
                    "score": -1,
                    "reasons": [f"screening error: {exc}"],
                }
            )

    ranked_jobs.sort(key=lambda item: (item["eligible"], item["score"]), reverse=True)
    return ranked_jobs


def print_ranked_job_summary(ranked_jobs, selection_count):
    print(f"[*] Ranked {len(ranked_jobs)} jobs. Selecting top {selection_count} verified postings.")
    for index, item in enumerate(ranked_jobs[:selection_count], start=1):
        context = item["job_context"]
        reason_text = "; ".join(item["reasons"][:3]) if item["reasons"] else "no scoring reasons"
        print(
            f"[{index}] score={item['score']} | {context.get('company_name')} | {context.get('job_title')} | {reason_text}"
        )


def validate_ollama_runtime(model):
    try:
        ollama_executable = resolve_ollama_executable()
    except FileNotFoundError as exc:
        raise ValueError(
            "Fallback provider 'ollama' is configured, but Ollama is not installed or not discoverable. "
            "Install Ollama, add it to PATH, or set OLLAMA_EXECUTABLE_PATH."
        ) from exc

    try:
        result = subprocess.run(
            [ollama_executable, "list"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Ollama is installed, but 'ollama list' timed out. Make sure the Ollama service is running.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise ValueError(f"Ollama is installed, but model discovery failed: {stderr or exc}") from exc

    installed_models = result.stdout.lower()
    requested_model = model.lower()
    if requested_model not in installed_models:
        raise ValueError(
            f"Ollama fallback model '{model}' is not installed. Run 'ollama pull {model}' first."
        )


def validate_fallback_configuration():
    provider = os.getenv("FALLBACK_LLM_PROVIDER", os.getenv("FALLBACK_PROVIDER", "google")).strip().lower()
    model = os.getenv("FALLBACK_LLM_MODEL", os.getenv("FALLBACK_MODEL", "")).strip()

    if not model:
        return None

    required_by_provider = {
        "google": ["FALLBACK_GOOGLE_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "openai": ["FALLBACK_OPENAI_API_KEY", "OPENAI_API_KEY"],
        "anthropic": ["FALLBACK_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"],
        "groq": ["FALLBACK_GROQ_API_KEY", "GROQ_API_KEY"],
        "litellm": [],
        "ollama": [],
    }

    if provider not in required_by_provider:
        raise ValueError(
            f"Unsupported FALLBACK_LLM_PROVIDER '{provider}'. Supported values: google, openai, anthropic, groq, litellm, ollama."
        )

    required_vars = required_by_provider[provider]
    if required_vars and not any(os.getenv(name) for name in required_vars):
        raise ValueError(
            f"Fallback provider '{provider}' requires one of these environment variables: {', '.join(required_vars)}"
        )

    if provider == "ollama":
        validate_ollama_runtime(model)

    return provider, model


def validate_target_job_url(job_url):
    parsed = urlparse(job_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"TARGET_JOB_URL must be a valid http(s) URL. Got: {job_url}")

    placeholder_hosts = {"example.com", "www.example.com"}
    if parsed.netloc.lower() in placeholder_hosts:
        raise ValueError(
            "TARGET_JOB_URL is still set to the example placeholder. Set it to the real application form URL."
        )


def slugify(value):
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or "job"


def extract_job_identity(title_text):
    stripped_title = title_text.strip()
    if " hiring " in stripped_title and " | LinkedIn" in stripped_title:
        company_name, remainder = stripped_title.split(" hiring ", 1)
        job_title = remainder.rsplit(" | LinkedIn", 1)[0]
        if " in " in job_title:
            job_title = job_title.rsplit(" in ", 1)[0]
        return company_name.strip(), job_title.strip()

    cleaned_title = stripped_title.rsplit("|", 1)[0].strip()
    return "Unknown Company", cleaned_title


def strip_html_tags(html_text):
    without_scripts = re.sub(r"<script.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    without_styles = re.sub(r"<style.*?</style>", " ", without_scripts, flags=re.IGNORECASE | re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", " ", without_styles)
    normalized = html.unescape(re.sub(r"\s+", " ", without_tags)).strip()
    return normalized


def fetch_job_posting_context(job_url):
    response = requests.get(job_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()

    html_text = response.text
    title_match = re.search(r"<title>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    description_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    title_text = html.unescape(title_match.group(1)).strip() if title_match else job_url
    description_text = html.unescape(description_match.group(1)).strip() if description_match else ""
    company_name, job_title = extract_job_identity(title_text)
    page_text = strip_html_tags(html_text)

    return {
        "url": job_url,
        "page_title": title_text,
        "job_title": job_title,
        "company_name": company_name,
        "description": description_text,
        "page_text": page_text[:12000],
        "page_html": html_text[:12000],
    }


def classify_company_verification(job_context):
    allowlist = get_verified_company_allowlist()
    company_name = job_context["company_name"].strip().lower()

    if company_name and company_name in allowlist:
        return True, "allowlist"

    combined_text = f"{job_context['page_title']}\n{job_context['description']}\n{job_context['page_text']}\n{job_context['page_html']}".lower()
    for marker in VERIFIED_MARKERS:
        if marker in combined_text:
            return True, f"marker:{marker}"

    return False, "no verified marker found"


def extract_resume_text(resume_path):
    from pypdf import PdfReader

    reader = PdfReader(str(resume_path))
    extracted_pages = [(page.extract_text() or "").strip() for page in reader.pages]
    resume_text = "\n\n".join(page for page in extracted_pages if page)
    if not resume_text.strip():
        raise ValueError(f"Could not extract text from resume PDF: {resume_path}")
    return resume_text


def get_document_model():
    return os.getenv("DOCUMENT_LLM_MODEL", "").strip() or os.getenv("FALLBACK_LLM_MODEL", "qwen2.5:3b")


def get_document_resume_char_limit():
    return int(os.getenv("DOCUMENT_RESUME_CHAR_LIMIT", "3500"))


def get_document_job_char_limit():
    return int(os.getenv("DOCUMENT_JOB_CHAR_LIMIT", "2000"))


def get_document_max_tokens():
    return int(os.getenv("DOCUMENT_MAX_TOKENS", "450"))


def should_generate_interview_prep_only():
    return os.getenv("INTERVIEW_PREP_ONLY", "0").strip().lower() in {"1", "true", "yes"}


def generate_ollama_text(prompt, model=None):
    model_name = model or get_document_model()
    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    response = requests.post(
        f"{host}/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": get_document_max_tokens()},
        },
        timeout=300,
    )
    response.raise_for_status()
    payload = response.json()
    generated_text = payload.get("response", "").strip()
    if not generated_text:
        raise ValueError("Ollama returned an empty response while generating application materials.")
    return generated_text


def build_contact_html(candidate_profile):
    return (
        "<h2>Contact Information</h2>"
        f"<p>Email: {html.escape(candidate_profile['email'])}<br>"
        f"Phone: {html.escape(candidate_profile['phone'])}<br>"
        f"LinkedIn: {html.escape(candidate_profile['linkedin_url'])}<br>"
        f"GitHub: {html.escape(candidate_profile['github_url'])}<br>"
        f"Location: {html.escape(candidate_profile['location'])}</p>"
    )


def wrap_resume_html(document_title, contact_html, body_html):
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <title>{html.escape(document_title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 28px; color: #111827; line-height: 1.45; }}
    h1 {{ font-size: 24px; margin-bottom: 8px; }}
    h2 {{ font-size: 16px; margin-top: 18px; border-bottom: 1px solid #d1d5db; padding-bottom: 4px; }}
    p, li {{ font-size: 11px; }}
    ul {{ padding-left: 18px; }}
  </style>
</head>
<body>
  <h1>{html.escape(document_title)}</h1>
    {contact_html}
  {body_html}
</body>
</html>
"""


def render_resume_pdf_if_available(html_path):
    try:
        from weasyprint import HTML
    except ImportError:
        return None

    pdf_path = html_path.with_suffix(".pdf")
    HTML(filename=str(html_path)).write_pdf(str(pdf_path))
    return pdf_path


def build_artifact_paths(job_context):
    artifact_dir = ARTIFACTS_ROOT / date.today().isoformat() / slugify(
        f"{job_context['company_name']}-{job_context['job_title']}"
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return {
        "artifact_dir": artifact_dir,
        "job_context_path": artifact_dir / "job_context.json",
        "tailored_resume_html_path": artifact_dir / "tailored_resume.html",
        "interview_prep_path": artifact_dir / "interview_prep.md",
    }


def generate_application_documents(job_context, resume_path, candidate_profile):
    artifact_paths = build_artifact_paths(job_context)
    resume_text = extract_resume_text(resume_path)
    model_name = get_document_model()
    resume_excerpt = resume_text[: get_document_resume_char_limit()]
    job_excerpt = job_context["page_text"][: get_document_job_char_limit()]

    artifact_paths["job_context_path"].write_text(json.dumps(job_context, indent=2), encoding="utf-8")

    resume_prompt = f"""
You are tailoring a resume for a specific job application.
Use only facts that appear in the source resume and candidate profile below.
Do not invent employers, degrees, certifications, dates, metrics, or responsibilities.
Do not include contact information in the response.
Do not name a technology unless it appears verbatim in the source resume text, candidate profile, or job title.
Return only an HTML fragment using h2, p, ul, and li tags. No markdown and no code fences.
Focus the wording toward the posted role while keeping it truthful and ATS-friendly.
Keep the result concise: a short summary plus 6 to 10 bullets total.

Candidate profile:
{json.dumps(candidate_profile, indent=2)}

Job context:
Company: {job_context['company_name']}
Role: {job_context['job_title']}
Description: {job_context['description']}
Page excerpt: {job_excerpt}

Source resume text:
{resume_excerpt}
""".strip()

    interview_prompt = f"""
Create interview preparation notes in markdown for the following application.
Use only the provided company, role, posting details, candidate profile, and resume text.
Do not invent facts about the candidate. If company specifics are missing, say so.
Include these sections:
1. Role snapshot
2. Likely interview focus areas
3. Eight tailored interview questions with suggested talking points
4. Technical topics to review
5. Candidate stories to prepare based on the resume
6. Questions to ask the interviewer
Keep the whole document compact and practical.

Candidate profile:
{json.dumps(candidate_profile, indent=2)}

Job context:
Company: {job_context['company_name']}
Role: {job_context['job_title']}
Description: {job_context['description']}
Page excerpt: {job_excerpt}

Source resume text:
{resume_excerpt}
""".strip()

    interview_prep_markdown = generate_ollama_text(interview_prompt, model=model_name)
    artifact_paths["interview_prep_path"].write_text(interview_prep_markdown, encoding="utf-8")

    tailored_resume_pdf_path = None
    if not should_generate_interview_prep_only():
        resume_fragment = generate_ollama_text(resume_prompt, model=model_name)
        tailored_resume_html = wrap_resume_html(
            f"{job_context['company_name']} - {job_context['job_title']} Tailored Resume",
            build_contact_html(candidate_profile),
            resume_fragment,
        )
        artifact_paths["tailored_resume_html_path"].write_text(tailored_resume_html, encoding="utf-8")
        tailored_resume_pdf_path = render_resume_pdf_if_available(artifact_paths["tailored_resume_html_path"])

    return {
        "artifact_dir": str(artifact_paths["artifact_dir"]),
        "job_context_path": str(artifact_paths["job_context_path"]),
        "tailored_resume_html_path": str(artifact_paths["tailored_resume_html_path"]) if artifact_paths["tailored_resume_html_path"].exists() else None,
        "tailored_resume_pdf_path": str(tailored_resume_pdf_path) if tailored_resume_pdf_path else None,
        "interview_prep_path": str(artifact_paths["interview_prep_path"]),
    }


def load_application_history():
    return read_json_file(APPLICATION_LOG_FILE, {"applications": []})


def record_application_event(job_context, status, reason=None, artifacts=None):
    history = load_application_history()
    history.setdefault("applications", []).append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "reason": reason,
            "url": job_context.get("url"),
            "company_name": job_context.get("company_name"),
            "job_title": job_context.get("job_title"),
            "verified": job_context.get("verified"),
            "verification_source": job_context.get("verification_source"),
            "artifacts": artifacts or {},
        }
    )
    write_json_file(APPLICATION_LOG_FILE, history)


def count_successful_applications_today():
    today = date.today().isoformat()
    history = load_application_history()
    return sum(
        1
        for entry in history.get("applications", [])
        if entry.get("status") == "success" and str(entry.get("timestamp", "")).startswith(today)
    )


def print_daily_progress():
    successes = count_successful_applications_today()
    target = get_daily_application_target()
    print(f"[*] Daily verified application progress: {successes}/{target}")


def run_startup_preflight(job_url, resume_path):
    validate_target_job_url(job_url)

    resume_file = Path(resume_path).expanduser()
    if not resume_file.is_file():
        raise FileNotFoundError(f"Resume file not found: {resume_file}")

    browser_path = resolve_browser_executable()
    fallback_config = validate_fallback_configuration()
    status = load_status_record()
    primary_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    job_context = fetch_job_posting_context(job_url)
    verified, verification_source = classify_company_verification(job_context)

    print(f"[*] Browser executable: {browser_path}")
    print(f"[*] Target job URL: {job_url}")
    print(f"[*] Parsed job: {job_context['company_name']} / {job_context['job_title']}")
    print(f"[*] Primary LLM: google/{primary_model}")
    print(f"[*] Verified-only mode: {'on' if require_verified_company() else 'off'}")

    if fallback_config is None:
        print("[!] No fallback LLM configured. Gemini quota exhaustion will stop the run.")
    else:
        provider, model = fallback_config
        print(f"[*] Fallback LLM ready: {provider}/{model}")
        print(
            f"[*] Agent runtime settings: llm_timeout={get_agent_llm_timeout_seconds()}s, "
            f"step_timeout={get_agent_step_timeout_seconds()}s, use_thinking={'on' if should_use_agent_thinking() else 'off'}, "
            f"use_vision={'on' if should_use_agent_vision() else 'off'}"
        )

    if verified:
        print(f"[*] Company verification accepted via {verification_source}")
    else:
        print(f"[!] Company verification not confirmed: {verification_source}")

    if status.get("daily_quota_exhausted") and status.get("provider") == "google" and status.get("model") == primary_model:
        print(
            "[!] Previous run recorded Gemini daily quota exhaustion for the current primary model. "
            "If quota has not reset yet, the primary model will fail immediately."
        )

    print_daily_progress()
    return fallback_config


def is_quota_error(error_message):
    lowered = error_message.lower()
    quota_markers = (
        "429",
        "resource_exhausted",
        "quota exceeded",
        "quotafailure",
        "rate limit",
        "too many requests",
        "generativelanguage.googleapis.com",
    )
    return any(marker in lowered for marker in quota_markers)


def is_daily_quota_exhausted(error_message):
    lowered = error_message.lower()
    return "requestsperday" in lowered or "perday" in lowered


def extract_retry_delay_seconds(error_message):
    patterns = (
        r"retry in ([\d\.]+)s",
        r"retrydelay['\"]?\s*[:=]\s*['\"]?([\d\.]+)s",
        r"retry delay['\"]?\s*[:=]\s*['\"]?([\d\.]+)s",
    )

    for pattern in patterns:
        match = re.search(pattern, error_message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))

    return None


def summarize_history_errors(history):
    return [error for error in history.errors() if error]


def cleanup_browser(profile_path):
    if os.path.exists(profile_path):
        try:
            shutil.rmtree(profile_path)
            print("[*] Cleaned up stale browser profile.")
        except PermissionError:
            print("[!] Warning: Could not delete profile. Browser might be running.")


def build_agent_task(job_url, candidate_profile, upload_resume_path):
    return (
        f"Navigate to {job_url}. "
        f"Before applying, confirm the employer appears verified on the page. If verification is missing or ambiguous, stop without applying. "
        f"Fill the application using this candidate profile: {candidate_profile}. "
        f"Upload {upload_resume_path}. "
        "Do not invent answers. If any required field cannot be answered from the provided data, stop and report the blocker. "
        "Submit only if the posting is from a verified company and the form is complete."
    )


def should_skip_document_generation_for_apply():
    return os.getenv("SKIP_DOCUMENT_GENERATION_ON_APPLY", "0").strip().lower() in {"1", "true", "yes"}


def prepare_application_package(job_url, resume_path, candidate_profile):
    job_context = fetch_job_posting_context(job_url)
    verified, verification_source = classify_company_verification(job_context)
    job_context["verified"] = verified
    job_context["verification_source"] = verification_source

    if require_verified_company() and not verified:
        return {
            "job_context": job_context,
            "should_apply": False,
            "reason": "Company verification not confirmed.",
            "artifacts": {},
            "upload_resume_path": str(Path(resume_path).expanduser()),
        }

    if should_skip_document_generation_for_apply():
        print("[!] Skipping tailored document generation for live apply. Using the original resume for upload.")
        return {
            "job_context": job_context,
            "should_apply": True,
            "reason": None,
            "artifacts": {},
            "upload_resume_path": str(Path(resume_path).expanduser()),
        }

    artifacts = generate_application_documents(job_context, Path(resume_path).expanduser(), candidate_profile)
    upload_resume_path = artifacts.get("tailored_resume_pdf_path") or str(Path(resume_path).expanduser())
    if not artifacts.get("tailored_resume_pdf_path"):
        print("[!] Tailored resume PDF was not rendered. Using the original PDF for upload; tailored HTML was still generated.")

    return {
        "job_context": job_context,
        "should_apply": True,
        "reason": None,
        "artifacts": artifacts,
        "upload_resume_path": upload_resume_path,
    }


async def run_application_agent(job_url, resume_path):
    candidate_profile = get_candidate_profile()

    run_startup_preflight(job_url, resume_path)
    package = prepare_application_package(job_url, resume_path, candidate_profile)
    job_context = package["job_context"]

    if not package["should_apply"]:
        print(f"[!] Skipping application for {job_context['company_name']}: {package['reason']}")
        record_application_event(job_context, "skipped", reason=package["reason"], artifacts=package["artifacts"])
        return False

    browser_executable = resolve_browser_executable()
    profile_path, cleanup_profile = resolve_browser_profile_dir()

    if not cleanup_profile:
        cleanup_browser(profile_path)

    browser = Browser(
        executable_path=browser_executable,
        headless=os.getenv("BROWSER_HEADLESS", "true").lower() not in {"0", "false", "no"},
        user_data_dir=profile_path,
    )

    try:
        llm = create_primary_llm()
        fallback_llm = create_fallback_llm()
        if fallback_llm is not None:
            print(f"[*] Fallback LLM enabled: provider={fallback_llm.provider}, model={fallback_llm.model}")

        task = build_agent_task(job_url, candidate_profile, os.path.abspath(package["upload_resume_path"]))
        max_retries = int(os.getenv("AGENT_MAX_RETRIES", "3"))
        llm_timeout = get_agent_llm_timeout_seconds()
        step_timeout = get_agent_step_timeout_seconds()
        use_thinking = should_use_agent_thinking()
        use_vision = should_use_agent_vision()

        for attempt in range(max_retries):
            agent = Agent(
                task=task,
                llm=llm,
                fallback_llm=fallback_llm,
                browser=browser,
                llm_timeout=llm_timeout,
                step_timeout=step_timeout,
                use_thinking=use_thinking,
                use_vision=use_vision,
            )
            if not hasattr(agent, "_task_start_time"):
                agent._task_start_time = time.time()
            print(f"[*] Starting agent (Attempt {attempt + 1})")

            try:
                history = await agent.run()
            except Exception as exc:
                error_msg = str(exc)
                if is_quota_error(error_msg) and attempt < max_retries - 1:
                    wait_time = extract_retry_delay_seconds(error_msg)
                    if wait_time is None or wait_time <= 0:
                        wait_time = min(30 * (attempt + 1), 300)
                    print(f"[!] Quota exhausted before completion. Sleeping for {wait_time:.1f} seconds...")
                    await asyncio.sleep(wait_time + 2)
                    continue

                print(f"[!] Unexpected error: {error_msg}")
                record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                return False

            if history.is_successful():
                clear_status_record()
                record_application_event(job_context, "success", artifacts=package["artifacts"])
                print("[+] Application workflow complete!")
                print_daily_progress()
                return True

            history_errors = summarize_history_errors(history)
            if history_errors:
                error_msg = "\n".join(history_errors[-3:])
                if is_quota_error(error_msg):
                    if is_daily_quota_exhausted(error_msg):
                        save_status_record(
                            {
                                "daily_quota_exhausted": True,
                                "provider": "google",
                                "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                                "last_error": error_msg,
                            }
                        )
                        record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                        print("[!] Gemini daily free-tier quota exhausted. Retry tomorrow or switch to a billed API key/model.")
                        return False

                    if attempt < max_retries - 1:
                        wait_time = extract_retry_delay_seconds(error_msg)
                        if wait_time is None or wait_time <= 0:
                            wait_time = min(30 * (attempt + 1), 300)
                        print(f"[!] Gemini rate limit hit. Sleeping for {wait_time:.1f} seconds before retry...")
                        await asyncio.sleep(wait_time + 2)
                        continue

                    print("[!] Gemini quota exhausted and retry budget reached.")
                    save_status_record(
                        {
                            "daily_quota_exhausted": False,
                            "provider": "google",
                            "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                            "last_error": error_msg,
                        }
                    )
                    record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                    return False

                save_status_record({"daily_quota_exhausted": False, "last_error": error_msg})
                record_application_event(job_context, "failed", reason=error_msg, artifacts=package["artifacts"])
                print(f"[!] Agent stopped with errors:\n{error_msg}")
                return False

            message = "Agent stopped without completing the task."
            save_status_record({"daily_quota_exhausted": False, "last_error": message})
            record_application_event(job_context, "failed", reason=message, artifacts=package["artifacts"])
            print(f"[!] {message}")
            return False

        return False
    finally:
        await browser.close()

        if cleanup_profile:
            cleanup_browser(profile_path)


async def smoke_test_browser():
    browser_executable = resolve_browser_executable()
    profile_path, cleanup_profile = resolve_browser_profile_dir()
    browser = Browser(
        executable_path=browser_executable,
        headless=True,
        user_data_dir=profile_path,
    )

    try:
        await browser.start()
        print(f"[+] Browser launch OK with {browser_executable}")
    finally:
        await browser.close()
        if cleanup_profile:
            cleanup_browser(profile_path)


def load_job_urls(job_url, job_urls_file, job_search_query=None, job_search_location=None, job_search_portal=None):
    urls = []
    if job_url:
        urls.append(job_url)

    if job_urls_file:
        job_urls_path = Path(job_urls_file).expanduser()
        if not job_urls_path.is_file():
            raise FileNotFoundError(f"Job URL list file not found: {job_urls_path}")
        file_urls = [line.strip() for line in job_urls_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#")]
        urls.extend(file_urls)

    if job_search_query:
        discovered_urls = discover_job_urls(
            job_search_query,
            job_search_location,
            portal=job_search_portal,
            max_results=get_search_result_limit(),
        )
        print(
            f"[*] Discovered {len(discovered_urls)} {job_search_portal or os.getenv('JOB_SEARCH_PORTAL', 'linkedin')} jobs for "
            f"'{job_search_query}'{f' in {job_search_location}' if job_search_location else ''}."
        )
        urls.extend(discovered_urls)

    deduplicated = []
    seen = set()
    for url in urls:
        if url not in seen:
            deduplicated.append(url)
            seen.add(url)

    if not deduplicated:
        raise ValueError("Provide --job-url or --job-urls-file with at least one real job posting URL.")

    return deduplicated


def preview_ranked_jobs(job_urls, resume_path):
    candidate_profile = get_candidate_profile()
    ranked_jobs = rank_job_urls(job_urls, resume_path, candidate_profile)
    eligible_ranked_jobs = [item for item in ranked_jobs if item["eligible"]]
    target_count = min(get_daily_application_target(), len(eligible_ranked_jobs))

    if not eligible_ranked_jobs:
        print("[!] No verified jobs qualified for application after screening.")
        for item in ranked_jobs:
            context = item["job_context"]
            reason_text = "; ".join(item["reasons"][:3]) if item["reasons"] else "not eligible"
            print(f"[-] {context.get('company_name')} | {context.get('job_title')} | {reason_text}")
        return False

    print_ranked_job_summary(eligible_ranked_jobs, target_count)
    for index, item in enumerate(eligible_ranked_jobs[:target_count], start=1):
        context = item["job_context"]
        print(f"    -> {index}. {context.get('job_title')} at {context.get('company_name')} ({item['url']})")
    return True


def generate_docs_only(job_url, resume_path):
    candidate_profile = get_candidate_profile()
    package = prepare_application_package(job_url, resume_path, candidate_profile)
    if not package["should_apply"]:
        raise ValueError(package["reason"])

    if package["artifacts"].get("tailored_resume_html_path"):
        print(f"[*] Tailored resume HTML: {package['artifacts']['tailored_resume_html_path']}")
    if package["artifacts"].get("tailored_resume_pdf_path"):
        print(f"[*] Tailored resume PDF: {package['artifacts']['tailored_resume_pdf_path']}")
    print(f"[*] Interview prep doc: {package['artifacts']['interview_prep_path']}")
    return True


async def run_job_plan(job_urls, resume_path, docs_only=False):
    if docs_only:
        all_generated = True
        for job_url in job_urls:
            try:
                generate_docs_only(job_url, resume_path)
            except Exception as exc:
                print(f"[!] Failed to prepare documents for {job_url}: {exc}")
                all_generated = False
        return all_generated

    if len(job_urls) == 1:
        return await run_application_agent(job_urls[0], resume_path)

    target = get_daily_application_target()
    starting_successes = count_successful_applications_today()
    remaining_target = max(target - starting_successes, 0)
    print(f"[*] Starting batch run with {len(job_urls)} URLs. Daily target: {target}")

    if starting_successes >= target:
        print("[*] Daily target already met. No new applications will be submitted.")
        return True

    candidate_profile = get_candidate_profile()
    ranked_jobs = rank_job_urls(job_urls, resume_path, candidate_profile)
    eligible_ranked_jobs = [item for item in ranked_jobs if item["eligible"]]

    if not eligible_ranked_jobs:
        print("[!] No verified jobs qualified for application after screening.")
        for item in ranked_jobs:
            context = item["job_context"]
            record_application_event(
                context,
                "skipped",
                reason="; ".join(item["reasons"]) or "job did not qualify during ranking",
                artifacts={},
            )
        return False

    selected_jobs = eligible_ranked_jobs[:remaining_target]
    print_ranked_job_summary(selected_jobs, len(selected_jobs))

    skipped_jobs = [item for item in ranked_jobs if item not in selected_jobs]
    for item in skipped_jobs:
        context = item["job_context"]
        record_application_event(
            context,
            "skipped",
            reason="; ".join(item["reasons"]) or "not selected in top-ranked jobs",
            artifacts={},
        )

    for item in selected_jobs:
        if count_successful_applications_today() >= target:
            break
        await run_application_agent(item["url"], resume_path)

    final_successes = count_successful_applications_today()
    print(f"[*] Batch complete. Daily verified applications: {final_successes}/{target}")
    return final_successes >= target


def run_docs_plan(job_urls, resume_path):
    all_generated = True
    for job_url in job_urls:
        try:
            generate_docs_only(job_url, resume_path)
        except Exception as exc:
            print(f"[!] Failed to prepare documents for {job_url}: {exc}")
            all_generated = False
    return all_generated


def parse_cli_args():
    parser = argparse.ArgumentParser(description="Run the browser-use job application agent.")
    parser.add_argument("--job-url", dest="job_url", help="Real application form URL to open.")
    parser.add_argument("--job-urls-file", dest="job_urls_file", help="Path to a text file with one job URL per line.")
    parser.add_argument("--job-search-query", dest="job_search_query", help="Search job portals for matching roles before ranking.")
    parser.add_argument("--job-search-location", dest="job_search_location", help="Optional location filter for automatic job discovery.")
    parser.add_argument(
        "--job-search-portal",
        dest="job_search_portal",
        default=os.getenv("JOB_SEARCH_PORTAL", "linkedin"),
        help="Portal to search for jobs automatically. Currently supports: linkedin.",
    )
    parser.add_argument("--resume", dest="resume_path", help="Path to the resume PDF to upload.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validate config and prerequisites, then exit without running the agent.",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Launch the browser only, then exit without running the agent.",
    )
    parser.add_argument(
        "--generate-docs-only",
        action="store_true",
        help="Generate the tailored resume/interview prep artifacts but do not submit applications.",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Discover and rank matching jobs but do not generate documents or submit applications.",
    )
    return parser.parse_args()


def has_explicit_job_input(args):
    return any(
        [
            args.job_url,
            args.job_urls_file,
            args.job_search_query,
        ]
    )


if __name__ == "__main__":
    args = parse_cli_args()

    target_job_url = args.job_url or os.getenv("TARGET_JOB_URL", "https://example.com/apply")
    my_tailored_pdf = args.resume_path or os.getenv("RESUME_PATH", "wondi.pdf")

    try:
        job_urls = load_job_urls(
            args.job_url,
            args.job_urls_file,
            job_search_query=args.job_search_query,
            job_search_location=args.job_search_location,
            job_search_portal=args.job_search_portal,
        )
    except (FileNotFoundError, ValueError, requests.RequestException) as exc:
        if has_explicit_job_input(args):
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        job_urls = [target_job_url]

    if args.preflight:
        try:
            for job_url in job_urls:
                run_startup_preflight(job_url, my_tailored_pdf)
            print("[+] Preflight OK")
        except (FileNotFoundError, ValueError, requests.RequestException) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc
        raise SystemExit(0)

    if args.generate_docs_only:
        try:
            success = run_docs_plan(job_urls, my_tailored_pdf)
        except (FileNotFoundError, ValueError, requests.RequestException) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc

        raise SystemExit(0 if success else 1)

    if args.discover_only:
        try:
            success = preview_ranked_jobs(job_urls, my_tailored_pdf)
        except (FileNotFoundError, ValueError, requests.RequestException) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc

        raise SystemExit(0 if success else 1)

    if args.smoke_test or os.getenv("BROWSER_SMOKE_TEST", "0") == "1":
        asyncio.run(smoke_test_browser())
    else:
        try:
            success = asyncio.run(run_job_plan(job_urls, my_tailored_pdf, docs_only=False))
        except (FileNotFoundError, ValueError, requests.RequestException) as exc:
            print(f"[!] Configuration error: {exc}")
            raise SystemExit(1) from exc

        raise SystemExit(0 if success else 1)