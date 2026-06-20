# Auto Apply Job

Automates job-application prep and browser submission with local fallback LLM support.

## What's New

- Automatic LinkedIn job discovery from a search query
- Ranked preview mode with `--discover-only`
- Improved LinkedIn guest result extraction and ranking flow
- Better local-model runtime controls for timeout, thinking, and vision behavior
- Optional interview-prep-only generation and skip-doc-generation apply mode

See [CHANGELOG.md](CHANGELOG.md) for release details.

The project is designed for a single candidate workflow:

- validate a real job posting URL
- reject non-verified companies unless explicitly allowlisted
- generate a tailored resume artifact from the job post
- generate interview preparation notes for each job
- use Gemini as the primary model and automatically fall back to Ollama when Gemini quota is exhausted
- track progress toward a daily application target

## Current capabilities

- Browser preflight for Chrome or Edge
- Native `browser_use.Agent` fallback LLM support
- Local Ollama fallback using `qwen2.5:3b`
- Verified-company policy with allowlist override
- Automatic LinkedIn job discovery from a search query
- Ranking verified jobs and selecting the top 5 by fit
- Batch processing from a job URL list file
- Per-job artifacts:
  - `job_context.json`
  - `tailored_resume.html`
  - `interview_prep.md`

## Repository layout

```text
apply_agent.py              Main automation script
.env.example                Safe environment template
jobs.example.txt            Example batch input file
docs/STEPS.md               Setup and operating steps
artifacts/                  Generated per-job outputs (ignored by git)
```

## Requirements

- Windows with PowerShell
- Python 3.13
- Chrome or Edge installed
- Ollama installed locally
- `qwen2.5:3b` pulled in Ollama
- Optional Gemini API key for primary model

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install browser-use python-dotenv requests pypdf langchain-google-genai
```

Optional if you want tailored resume PDF rendering instead of HTML-only output:

```powershell
pip install weasyprint
```

## Configure

1. Copy `.env.example` to `.env`.
2. Set your real API keys and local paths.
3. Add trusted employers to `VERIFIED_COMPANY_ALLOWLIST` when guest pages do not expose a verification marker.
4. Put your real resume PDF in the working directory or point `RESUME_PATH` to it.

## Typical commands

Preflight one posting:

```powershell
python .\apply_agent.py --preflight --job-url "https://www.linkedin.com/jobs/view/4428723824/" --resume "wondi.pdf"
```

Generate tailored resume and interview-prep documents only:

```powershell
python .\apply_agent.py --generate-docs-only --job-url "https://www.linkedin.com/jobs/view/4428723824/" --resume "wondi.pdf"
```

Apply to one posting:

```powershell
python .\apply_agent.py --job-url "https://www.linkedin.com/jobs/view/4428723824/" --resume "wondi.pdf"
```

Apply in batch from a file:

```powershell
python .\apply_agent.py --job-urls-file ".\jobs.txt" --resume "wondi.pdf"
```

Discover matching jobs from LinkedIn and preview the best fits without applying:

```powershell
python .\apply_agent.py --discover-only --job-search-query "data engineer" --job-search-location "Texas" --resume "wondi.pdf"
```

Discover matching jobs from LinkedIn and feed them directly into the verified top-5 apply flow:

```powershell
python .\apply_agent.py --job-search-query "data engineer" --job-search-location "Texas" --resume "wondi.pdf"
```

In batch mode, the script now:

- screens every URL first
- can auto-discover LinkedIn job URLs from a search query
- filters out non-verified postings when verified-only mode is on
- scores verified postings against preferred roles, locations, and resume overlap
- selects only the highest-ranked jobs up to `DAILY_APPLICATION_TARGET`

## Verified-company policy

The script defaults to `REQUIRE_VERIFIED_COMPANY=1`.

Verification passes when either of these is true:

- the page text exposes a verification marker such as `verified company`
- the parsed employer name is listed in `VERIFIED_COMPANY_ALLOWLIST`

This is intentionally conservative. On many LinkedIn guest pages, the allowlist is the reliable path.

## Daily target behavior

- `DAILY_APPLICATION_TARGET` defaults to `5`
- successful applications are tracked in `.application_history.json`
- batch mode stops once the daily target is met
- batch mode ranks verified jobs first and applies only to the top-scoring set

## Ranking behavior

The ranking step is deterministic and currently uses:

- preferred role keywords from `PREFERRED_ROLE_KEYWORDS`
- preferred location keywords from `PREFERRED_LOCATION_KEYWORDS`
- overlap between the posting text and extracted resume keywords
- eligibility wording such as `green card` or `no sponsorship`
- verification status

If you want better ranking for your search, tune these two settings in `.env`:

- `PREFERRED_ROLE_KEYWORDS`
- `PREFERRED_LOCATION_KEYWORDS`

For automatic discovery, you can also tune:

- `JOB_SEARCH_PORTAL` which currently supports `linkedin`
- `JOB_SEARCH_RESULT_LIMIT` to cap how many public search results are screened before ranking

## Generated artifacts

Per-job outputs are written under:

```text
artifacts/YYYY-MM-DD/company-role/
```

Typical files:

- `job_context.json`
- `tailored_resume.html`
- `tailored_resume.pdf` when `weasyprint` is available
- `interview_prep.md`

## Notes

- `.env`, local resumes, artifacts, and runtime state are ignored by git.
- If `weasyprint` is not importable in the active Python environment, the script falls back to the original PDF for upload and still writes tailored HTML.
- Small local Ollama models can be slow; `DOCUMENT_RESUME_CHAR_LIMIT`, `DOCUMENT_JOB_CHAR_LIMIT`, and `DOCUMENT_MAX_TOKENS` exist to keep local generation bounded.
- LinkedIn guest pages often do not expose a strong verification badge in HTML, so `VERIFIED_COMPANY_ALLOWLIST` is still the most reliable way to approve trusted employers.

## Next operational file

Detailed run steps are in [docs/STEPS.md](docs/STEPS.md).
