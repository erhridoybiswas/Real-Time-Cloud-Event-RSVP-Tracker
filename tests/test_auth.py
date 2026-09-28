"""Authentication and authorization tests."""
from tests.conftest import auth_header, login, register


def test_01_user_registration(client):
    resp = register(client, "new@test.com")
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["token"]
    assert body["user"]["email"] == "new@test.com"
    assert body["user"]["role"] == "ATTENDEE"


def test_02_duplicate_registration_rejected(client):
    register(client, "dup@test.com")
    resp = register(client, "dup@test.com")
    assert resp.status_code == 409
    assert "already exists" in resp.get_json()["error"]


def test_03_login_success_and_failure(client):
    register(client, "log@test.com")
    ok = login(client, "log@test.com")
    assert ok.status_code == 200 and ok.get_json()["token"]

    bad = login(client, "log@test.com", password="WrongPassword1")
    assert bad.status_code == 401


def test_04_weak_password_rejected(client):
    resp = register(client, "weak@test.com", password="123")
    assert resp.status_code == 422


def test_05_invalid_email_rejected(client):
    resp = register(client, "not-an-email")
    assert resp.status_code == 422


def test_06_protected_route_requires_token(client):
    assert client.get("/api/rsvps/me").status_code == 401


def test_07_invalid_token_rejected(client):
    resp = client.get("/api/rsvps/me", headers=auth_header("garbage.token.value"))
    assert resp.status_code == 401


def test_08_me_endpoint(client, attendee):
    resp = client.get("/api/me", headers=attendee["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "att@test.com"


def test_09_logout_writes_audit_log(client, attendee):
    assert client.post("/api/logout", headers=attendee["headers"]).status_code == 200