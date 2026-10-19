import logging
import time

import pytest
from fastapi.testclient import TestClient

import apply_agent
from app_backend import user_store
from app_backend.auth_config import load_auth_settings
from app_backend.main import app
from app_backend.secrets_provider import Secret
from app_backend.security import UserContext, create_access_token, decode_access_token, hash_password
from core.errors import AuthenticationError, AuthorizationError, ConfigurationError
from core.logging_config import configure_logging, redact_mapping, redact_text

SECRET = "x" * 40
PASSWORD = "correct horse battery"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "iss")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "aud")
    monkeypatch.setenv("AUTH_LOGIN_USERNAME", "alice")
    monkeypatch.setenv("AUTH_LOGIN_PASSWORD_HASH", hash_password(PASSWORD, iterations=1000))
    monkeypatch.setenv("USER_DATA_DIR", str(tmp_path / "users"))
    monkeypatch.setattr(apply_agent, "APPLICATION_DB_FILE", tmp_path / "db.sqlite3")
    return tmp_path


@pytest.fixture
def client(env):
    with TestClient(app) as c:
        yield c


def token_for(user, role="user", **overrides):
    settings = load_auth_settings()
    return create_access_token(settings, user, role, **overrides)


def auth(token):
    return {"Authorization": "Bearer " + token}


def test_startup_fails_fast_with_actionable_error(monkeypatch, env):
    monkeypatch.delenv("AUTH_JWT_SECRET")
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "none")
    with pytest.raises(ConfigurationError) as exc:
        with TestClient(app):
            pass
    assert "AUTH_JWT_SECRET" in str(exc.value) and "AUTH_JWT_ALGORITHM" in str(exc.value)


def test_short_secret_rejected(monkeypatch, env):
    monkeypatch.setenv("AUTH_JWT_SECRET", "short")
    with pytest.raises(ConfigurationError):
        load_auth_settings()


def test_login_and_authenticated_flow(client):
    assert client.post("/auth/login", json={"username": "alice", "password": "bad"}).status_code == 401
    assert client.post("/auth/login", json={"username": "bob", "password": PASSWORD}).status_code == 401
    resp = client.post("/auth/login", json={"username": "alice", "password": PASSWORD})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = client.get("/auth/me", headers=auth(token)).json()
    assert me["user_id"] == "alice" and me["role"] == "user"


def test_protected_routes_require_token(client):
    for method, path in (("get", "/applications"), ("get", "/profile"), ("get", "/auth/me")):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"] == "Bearer"
    assert client.post("/jobs/apply", json={"job_url": "u", "resume_path": "r"}).status_code == 401
    assert client.get("/health").status_code == 200


def test_invalid_tokens_rejected(client, env):
    settings = load_auth_settings()
    assert client.get("/auth/me", headers=auth("garbage")).status_code == 401
    expired = token_for("alice", now=time.time() - 7200)
    assert client.get("/auth/me", headers=auth(expired)).status_code == 401
    import jwt

    claims = {"sub": "alice", "iss": "iss", "aud": "aud", "iat": 1, "exp": int(time.time()) + 100}
    assert client.get("/auth/me", headers=auth(jwt.encode(claims, "y" * 40, algorithm="HS256"))).status_code == 401
    assert client.get("/auth/me", headers=auth(jwt.encode(claims, SECRET, algorithm="HS512"))).status_code == 401
    wrong_aud = dict(claims, aud="other")
    assert client.get("/auth/me", headers=auth(jwt.encode(wrong_aud, SECRET, algorithm="HS256"))).status_code == 401
    wrong_iss = dict(claims, iss="other")
    assert client.get("/auth/me", headers=auth(jwt.encode(wrong_iss, SECRET, algorithm="HS256"))).status_code == 401
    no_sub = {k: v for k, v in claims.items() if k != "sub"}
    assert client.get("/auth/me", headers=auth(jwt.encode(no_sub, SECRET, algorithm="HS256"))).status_code == 401
    traversal = dict(claims, sub="../evil")
    assert client.get("/auth/me", headers=auth(jwt.encode(traversal, SECRET, algorithm="HS256"))).status_code == 401
    unsigned = jwt.encode(claims, None, algorithm="none")
    assert client.get("/auth/me", headers=auth(unsigned)).status_code == 401
    with pytest.raises(AuthenticationError):
        decode_access_token(settings, "")


def test_rbac_forbidden_for_unknown_role(client):
    resp = client.get("/applications", headers=auth(token_for("alice", role="guest")))
    assert resp.status_code == 403
    assert resp.json()["category"] == "authorization"
    admin = UserContext("a", "admin")
    assert admin.has_permission("users:manage") and not UserContext("a").has_permission("users:manage")


def test_profile_isolated_per_user(client):
    alice, bob = auth(token_for("alice")), auth(token_for("bob"))
    assert client.put("/profile", json={"first_name": "Alice"}, headers=alice).status_code == 200
    assert client.get("/profile", headers=alice).json()["profile"] == {"first_name": "Alice"}
    assert client.get("/profile", headers=bob).json()["profile"] == {}
    assert client.put("/profile", json={"bogus": "x"}, headers=bob).status_code == 422


def test_service_layer_blocks_cross_user_access(env):
    alice = UserContext("alice")
    with pytest.raises(AuthorizationError):
        user_store.load_profile(alice, "bob")
    with pytest.raises(AuthorizationError):
        user_store.save_profile(alice, {"first_name": "x"}, "bob")
    with pytest.raises(AuthenticationError):
        user_store.user_dir("../bob")


def test_applications_scoped_to_user(client):
    apply_agent.record_application_event({"url": "https://a"}, "success", artifacts={}, user_id="alice")
    apply_agent.record_application_event({"url": "https://b"}, "failed", artifacts={}, user_id="bob")
    items = client.get("/applications", headers=auth(token_for("alice"))).json()["items"]
    assert [i["url"] for i in items] == ["https://a"]
    assert len(apply_agent.list_recent_application_events()) == 2


def test_secret_never_exposed_in_repr_or_logs(env, capsys):
    settings = load_auth_settings()
    assert SECRET not in repr(settings) and SECRET not in str(settings.jwt_secret)
    assert repr(Secret("abc")) == "Secret([REDACTED])"
    token = token_for("alice")
    logger = configure_logging(fmt="kv")
    logger.info("Authorization: Bearer " + "%s", token)
    logger.info("jwt %s", token)
    err = capsys.readouterr().err
    assert token not in err and "Bearer " + token not in err


def test_redaction_of_auth_keys():
    masked = redact_mapping({"access_token": "t", "Authorization": "******", "jwt_secret": "s", "cookie": "c"})
    assert set(masked.values()) == {"[REDACTED]"}
    assert "abc" not in redact_text("header ******")
