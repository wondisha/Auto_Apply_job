# App Backend Scaffold

This folder is a scaffold for a more serious app version of the project.

## Goals

- move from a local operator script to an API-driven service
- support login and user-specific state
- run discovery, prep, and apply workflows through background jobs
- centralize browser-session and application tracking

## Current status

- `main.py` boots a minimal FastAPI app
- `routers/auth.py` contains a placeholder login endpoint
- `routers/applications.py` exposes recent tracked applications
- `routers/jobs.py` exposes discovery and preview handoff endpoints

## Next production steps

- replace placeholder auth with real session or token-based authentication
- move live apply runs into background worker processes
- add browser-session persistence and reconnect support
- separate candidate profiles by user instead of hardcoding them in `apply_agent.py`
- add RBAC and encrypted secret storage for API keys and resume paths
