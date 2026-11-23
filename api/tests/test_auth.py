import time

from tests.conftest import ORIGIN, identity, signup


def test_signup_requires_valid_invite(anon, make_invite):
    assert signup(anon, code="NOPE-NOPE").status_code == 422
    make_invite("WXYZ-2345", max_uses=1)
    r = signup(anon, code="wxyz2345")                       # case/dash-insensitive
    assert r.status_code == 201 and r.json()["role"] == "user"
    assert anon.get("/api/auth/me").json()["email"] == "me@example.com"
    anon.cookies.clear()
    anon.headers["X-CSRF-Token"] = anon.get("/api/auth/csrf").json()["csrf_token"]
    assert signup(anon, email="two@example.com", code="WXYZ-2345").status_code == 422  # single use


def test_signup_validation(anon, make_invite):
    make_invite(max_uses=5)
    assert signup(anon, password="short").status_code == 422
    assert signup(anon, password="password123").status_code == 422
    assert signup(anon, email="not-an-email").status_code == 422
    assert signup(anon, email="Me@Example.com").status_code == 201
    anon.cookies.clear()
    anon.headers["X-CSRF-Token"] = anon.get("/api/auth/csrf").json()["csrf_token"]
    assert signup(anon, email="me@example.com").status_code == 409  # emails are case-insensitive


def test_invite_role_and_expiry(anon, make_invite):
    from db import utcnow
    from datetime import timedelta
    make_invite("OLDD-CODE", expires_at=utcnow() - timedelta(days=1))
    assert signup(anon, code="OLDD-CODE").status_code == 422
    make_invite("ADMN-CODE", role="admin")
    assert signup(anon, code="ADMN-CODE").json()["role"] == "admin"


def test_session_cookie_flags(anon, make_invite):
    make_invite()
    r = signup(anon)
    cookies = r.headers.get_list("set-cookie")
    sess = next(c for c in cookies if c.startswith("__Host-aiwazz_session="))
    low = sess.lower()
    assert "httponly" in low and "secure" in low and "samesite=lax" in low and "path=/" in low and "domain" not in low
    csrf = next(c for c in cookies if c.startswith("__Host-aiwazz_csrf="))
    assert "httponly" not in csrf.lower()  # JS must read it to echo it back


def test_login_logout(client):
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "wrong password!!"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "ME@example.com", "password": "correct horse battery"})
    assert r.status_code == 200 and r.json()["email"] == "me@example.com"
    assert client.get("/api/auth/me").status_code == 200


def test_login_rate_limit_per_email(client):
    client.post("/api/auth/logout")
    codes = [client.post("/api/auth/login", json={"email": "me@example.com", "password": f"wrong-{i}-xxxx"}).status_code for i in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429
    r = client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0  # locked even with the right password


def test_csrf_and_origin_required(client):
    token = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/auth/logout").status_code == 403                       # no CSRF header
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token, "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/tts", json={"text": "hi", "voice": "hf_alpha"}, headers={"X-CSRF-Token": token, "Origin": "https://aiwazz.in.evil.example"}).status_code == 403
    assert client.post("/api/auth/logout", headers={"X-CSRF-Token": token, "Origin": ORIGIN}).status_code == 200


def test_tts_requires_auth(anon):
    assert anon.post("/api/tts", json={"text": "hi", "voice": "hf_alpha"}).status_code == 401
    assert anon.get("/api/history").status_code == 401
    assert anon.get("/api/audio/" + "0" * 32).status_code == 401
    assert anon.get("/api/voices").status_code == 200 and anon.get("/api/health").status_code == 200


def test_api_keys_lifecycle(client, anon):
    r = client.post("/api/keys", json={"name": "video pipeline"})
    assert r.status_code == 201
    key = r.json()["key"]
    assert key.startswith("aiw_live_") and r.json()["prefix"] == key[:13]
    listed = client.get("/api/keys").json()["keys"]
    assert len(listed) == 1 and "key" not in listed[0]                        # never shown again

    # A script using the key: no cookies, no CSRF/Origin, works
    h = {"X-API-Key": key}
    with identity(client) as bare:
        assert bare.get("/api/auth/me", headers=h).json()["via"] == "api_key"
        r = bare.post("/api/tts?wait=true", json={"text": "From a script.", "voice": "af_heart"}, headers=h)
        assert r.status_code == 200, r.text
        assert bare.get(r.json()["url"], headers=h).status_code == 200
        assert bare.get("/api/keys", headers=h).status_code == 403            # keys can't manage keys
        assert bare.get("/api/auth/me", headers={"X-API-Key": "aiw_live_wrong"}).status_code == 401
        assert bare.get("/api/history", headers=h).json()["items"][0]["via_api"] is True

    client.delete(f"/api/keys/{listed[0]['id']}")
    with identity(client) as bare:
        assert bare.get("/api/auth/me", headers=h).status_code == 401          # revoked immediately


def test_audio_is_owner_only(client, anon, make_invite):
    r = client.post("/api/tts?wait=true", json={"text": "Private voiceover.", "voice": "bf_emma"})
    url, gid = r.json()["url"], r.json()["id"]
    assert client.get(url).status_code == 200
    hist = client.get("/api/history").json()["items"]
    assert hist[0]["id"] == gid and hist[0]["available"] and hist[0]["text_excerpt"] == "Private voiceover."

    # Another user: same 404 as for a non-existent id
    make_invite("OTHR-USER")
    with identity(client, keep_origin=True) as other:
        other.headers["X-CSRF-Token"] = other.get("/api/auth/csrf").json()["csrf_token"]
        assert signup(other, email="other@example.com", code="OTHR-USER").status_code == 201
        assert other.get(url).status_code == 404
        assert other.get(f"/api/tts/jobs/{gid}").status_code == 404
        assert other.get("/api/history").json()["items"] == []
    assert client.get(url).status_code == 200                                  # owner still fine


def test_expired_audio_is_410(client):
    r = client.post("/api/tts?wait=true", json={"text": "Short lived.", "voice": "af_heart"}).json()
    jm = client.app.state.jobs
    for f in jm.s.audio_dir.glob(f"{r['id']}.*"):
        f.unlink()
    assert client.get(r["url"]).status_code == 410
    assert client.get("/api/history").json()["items"][0]["available"] is False


def test_per_user_pending_limit(client):
    jm = client.app.state.jobs
    jm.engine.ready = True
    orig = jm.engine.synthesize
    jm.engine.synthesize = lambda *a: (time.sleep(0.4), orig(*a))[1]       # slow down the worker
    codes = [client.post("/api/tts", json={"text": f"Line {i}.", "voice": "af_heart"}).status_code for i in range(6)]
    assert 429 in codes and codes[0] == 202


def test_change_password_and_logout_others(client):
    # second device
    with identity(client, keep_origin=True) as other:
        other.headers["X-CSRF-Token"] = other.get("/api/auth/csrf").json()["csrf_token"]
        assert other.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"}).status_code == 200

    assert client.post("/api/auth/password", json={"current_password": "nope-nope-nope", "new_password": "a brand new secret"}).status_code == 422
    assert client.post("/api/auth/password", json={"current_password": "correct horse battery", "new_password": "short"}).status_code == 422
    r = client.post("/api/auth/password", json={"current_password": "correct horse battery", "new_password": "a brand new secret"})
    assert r.status_code == 200 and r.json()["signed_out_sessions"] == 1          # the other device
    assert client.get("/api/auth/me").status_code == 200                          # this one stays

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "a brand new secret"}).status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("__Host-aiwazz_csrf")   # login rotates the CSRF token
    assert client.post("/api/auth/logout-others").json()["signed_out_sessions"] == 0


def test_delete_account(client, make_invite):
    r = client.post("/api/tts?wait=true", json={"text": "Delete me later.", "voice": "af_heart"}).json()
    files = list(client.app.state.jobs.s.audio_dir.glob(f"{r['id']}.*"))
    assert files
    client.post("/api/keys", json={"name": "k"})
    assert client.post("/api/auth/delete-account", json={"password": "correct horse battery", "confirm": "nope"}).status_code == 422
    assert client.post("/api/auth/delete-account", json={"password": "wrong password!", "confirm": "DELETE"}).status_code == 422
    r2 = client.post("/api/auth/delete-account", json={"password": "correct horse battery", "confirm": "DELETE"})
    assert r2.status_code == 200 and r2.json()["deleted_generations"] == 1
    assert not any(f.exists() for f in files)
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "me@example.com", "password": "correct horse battery"}).status_code == 401


def test_last_admin_cannot_delete_self(anon, make_invite):
    make_invite("ADMN-ONLY", role="admin")
    assert signup(anon, code="ADMN-ONLY").json()["role"] == "admin"
    r = anon.post("/api/auth/delete-account", json={"password": "correct horse battery", "confirm": "DELETE"})
    assert r.status_code == 422 and "only admin" in r.json()["detail"]
