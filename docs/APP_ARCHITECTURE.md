# App Architecture

## Current app shape

The project now has two operator surfaces:

- `apply_agent.py` for CLI-first execution
- `streamlit_app.py` for a lightweight dashboard and run controls

It also includes a starter backend scaffold under `app_backend/` for a more serious service-oriented version.

## Recommended production architecture

### Frontend

- Streamlit for single-user operator workflows today
- Later move to React or another SPA if multi-user workflows are needed

### API layer

- FastAPI backend
- endpoints for discovery, ranking, prep-pack generation, run scheduling, history, and question memory

### Background execution

- dedicated worker process for live application runs
- queue-backed job dispatch for discovery, docs-only, and live apply operations
- persistent job status table for polling and resume-after-failure behavior

### Persistence

- SQLite for local single-user mode today
- Postgres for multi-user or hosted mode later
- artifact files stored under dated job folders

### Auth and secrets

- token or session-based login
- encrypted storage for API keys, candidate profiles, and resume locations
- per-user screening-answer memory instead of a single shared file

### Browser orchestration

- one managed browser session per active run
- reconnect metadata persisted to storage
- screenshots and DOM snapshots captured on failures

## Suggested roadmap

1. Keep Streamlit as the operator UI for local use.
2. Move long-running apply jobs into a worker service.
3. Replace hardcoded candidate profile values with editable persisted profiles.
4. Upgrade the backend scaffold to real authenticated APIs.
5. Introduce multi-user storage and hosted deployment only after the worker model is stable.
