# App Backend Scaffold

This folder is a scaffold for a more serious app version of the project.

## Goals

- move from a local operator script to an API-driven service
- support login and user-specific state
- run discovery, prep, and apply workflows through background jobs
- centralize browser-session and application tracking

## Current status

- `main.py` boots a minimal FastAPI app
- `routers/auth.py` provides `POST /auth/login` (issues a signed JWT) and `GET /auth/me`
- `routers/profile.py` stores per-user profiles under `USER_DATA_DIR/<user_id>/`
- `routers/applications.py` exposes recent tracked applications
- `routers/jobs.py` exposes discovery and preview handoff endpoints

## Next production steps

- move live apply runs into background worker processes
- add browser-session persistence and reconnect support
- migrate `apply_agent.py` CLI flows to the per-user profile store
- add encrypted secret storage (vault-backed `SecretProvider`) and more RBAC roles

## Authentication

All routes except `/health` and `/auth/login` require an `Authorization: Bearer <jwt>` header.
Tokens are HS256/384/512-signed with issuer, audience, `sub` (user id), `role`, `iat` and `exp`
claims, all verified. Missing/invalid tokens return `401`; insufficient role/permission returns `403`.
Application events and profiles are namespaced by the token's `user_id`; the service layer
(`user_store.assert_same_user`) refuses cross-user access.

### Required environment variables

The API refuses to start (with a list of every problem) unless these are valid:

| Variable | Purpose |
| --- | --- |
| `AUTH_JWT_SECRET` | Signing secret, at least 32 chars |
| `AUTH_JWT_ISSUER` / `AUTH_JWT_AUDIENCE` | Expected `iss` / `aud` claims |
| `AUTH_LOGIN_USERNAME` | Login user (also the `user_id`) |
| `AUTH_LOGIN_PASSWORD_HASH` | PBKDF2 hash from `python -m app_backend.security_cli` |

Optional: `AUTH_JWT_ALGORITHM` (default `HS256`), `AUTH_ACCESS_TOKEN_TTL_SECONDS` (default `3600`),
`AUTH_LOGIN_ROLE` (default `user`; `user` and `admin` are defined in `security.ROLE_PERMISSIONS`),
`USER_DATA_DIR` (default `.user_data`).

### Run locally with auth

```bash
export AUTH_JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export AUTH_JWT_ISSUER=auto-apply-job AUTH_JWT_AUDIENCE=auto-apply-job-api AUTH_LOGIN_USERNAME=me
export AUTH_LOGIN_PASSWORD_HASH="$(python -m app_backend.security_cli)"
uvicorn app_backend.main:app --reload

TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"me","password":"<your password>"}' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -H "Authorization: Bearer $TOKEN" localhost:8000/auth/me
curl -X PUT -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"first_name":"Ada"}' localhost:8000/profile
curl -H "Authorization: Bearer $TOKEN" localhost:8000/applications
```

### Security notes

- Secrets are read through `secrets_provider.SecretProvider` (env-backed by default) and wrapped in
  `Secret`, whose `repr` never shows the value. Swap in a vault-backed provider via `set_secret_provider`.
- Logging redacts bearer tokens, JWTs and keys containing `token`, `secret`, `password`, `authorization`, etc.
- Store secrets in a secret manager or untracked `.env`; never commit them. To rotate `AUTH_JWT_SECRET`,
  set a new value and restart: all existing tokens become invalid and users must log in again.
  Rotate the login password by regenerating `AUTH_LOGIN_PASSWORD_HASH`.
- Existing local SQLite rows are migrated with `user_id='local'`.
