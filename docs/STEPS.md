# Steps

## 1. Create the local environment

```powershell
Set-Location D:\Downloads\resume_control
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install browser-use python-dotenv requests pypdf langchain-google-genai
```

Optional PDF generation support:

```powershell
pip install weasyprint
```

## 2. Install and validate Ollama

```powershell
ollama --version
ollama list
ollama pull qwen2.5:3b
```

If `ollama` is not on PATH yet, use:

```powershell
C:\Users\techp\AppData\Local\Programs\Ollama\ollama.exe --version
```

## 3. Prepare configuration

1. Copy `.env.example` to `.env`.
2. Set `GOOGLE_API_KEY` if you want Gemini as the primary model.
3. Keep `FALLBACK_LLM_PROVIDER=ollama` and `FALLBACK_LLM_MODEL=qwen2.5:3b` for free local fallback.
4. Set `RESUME_PATH` to your real resume PDF.
5. Add trusted companies to `VERIFIED_COMPANY_ALLOWLIST`.
6. Tune `PREFERRED_ROLE_KEYWORDS` and `PREFERRED_LOCATION_KEYWORDS` so the top-5 selector matches the jobs you actually want.

## 4. Create the job list

Create `jobs.txt` with one URL per line.

Example:

```text
https://www.linkedin.com/jobs/view/4428723824/
https://www.linkedin.com/jobs/view/1234567890/
```

## 5. Validate before applying

Single posting:

```powershell
python .\apply_agent.py --preflight --job-url "https://www.linkedin.com/jobs/view/4428723824/" --resume "wondi.pdf"
```

## 6. Generate materials only

```powershell
python .\apply_agent.py --generate-docs-only --job-url "https://www.linkedin.com/jobs/view/4428723824/" --resume "wondi.pdf"
```

This creates:

- `job_context.json`
- `tailored_resume.html`
- `interview_prep.md`

## 7. Run batch applications

```powershell
python .\apply_agent.py --job-urls-file ".\jobs.txt" --resume "wondi.pdf"
```

Behavior:

- skips companies that fail verification
- ranks verified jobs before applying
- selects only the top jobs up to the daily target
- prepares per-job docs before applying
- uploads tailored PDF when available, otherwise the original PDF
- stops once `DAILY_APPLICATION_TARGET` is reached

## 8. Review outputs

Artifacts are stored under:

```text
artifacts/YYYY-MM-DD/company-role/
```

Daily application state is stored in:

- `.application_history.json`
- `.agent_status.json`

## 9. Push this project to GitHub

```powershell
git init
git branch -M main
git remote add origin https://github.com/wondisha/Auto_Apply_job.git
git add .
git commit -m "Initial automation workflow"
git push -u origin main
```

Before pushing, confirm that `.env`, resumes, and `artifacts/` are excluded by `.gitignore`.
