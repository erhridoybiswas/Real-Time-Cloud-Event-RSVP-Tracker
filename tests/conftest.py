"""Shared pytest fixtures: isolated temp database + test client."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("BOOTSTRAP_KEY", "test-bootstrap")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """Fresh app + fresh SQLite file for every test."""
    from backend.config import Config
    monkeypatch.setattr(Config, "DATABASE_PATH", str(tmp_path / "test.db"))

    from backend.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Helper factories
# --------------------------------------------------------------------------
def register(client, email, role="ATTENDEE", password="Password123", name="Test User"):
    return client.post("/api/register", json={
        "email": email, "password": password, "full_name": name, "role": role,
    })


def login(client, email, password="Password123"):
    return client.post("/api/login", json={"email": email, "password": password})


def auth_header(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def organizer(client):
    resp = register(client, "org@test.com", role="ORGANIZER", name="Org One")
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    return {"token": data["token"], "user": data["user"], "headers": auth_header(data["token"])}


@pytest.fixture()
def attendee(client):
    resp = register(client, "att@test.com", role="ATTENDEE", name="Att One")
    assert resp.status_code == 201, resp.get_json()
    data = resp.get_json()
    return {"token": data["token"], "user": data["user"], "headers": auth_header(data["token"])}


def make_event(client, organizer, **overrides):
    payload = {
        "event_name": "Test Event",
        "event_date": "2030-01-01",
        "start_time": "10:00",
        "end_time": "12:00",
        "venue": "Room 1",
        "maximum_capacity": 3,
        "status": "PUBLISHED",
    }
    payload.update(overrides)
    resp = client.post("/api/events", json=payload, headers=organizer["headers"])
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["event"]