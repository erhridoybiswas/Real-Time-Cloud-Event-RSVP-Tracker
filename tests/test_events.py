"""Event CRUD, validation and authorization tests."""
from tests.conftest import make_event


def test_10_organizer_creates_event(client, organizer):
    event = make_event(client, organizer)
    assert event["event_name"] == "Test Event"
    assert event["status"] == "PUBLISHED"
    assert event["maximum_capacity"] == 3


def test_11_attendee_cannot_create_event(client, attendee):
    resp = client.post("/api/events", json={
        "event_name": "Nope", "event_date": "2030-01-01",
        "start_time": "10:00", "end_time": "11:00", "maximum_capacity": 10,
    }, headers=attendee["headers"])
    assert resp.status_code == 403


def test_12_event_retrieval(client, organizer):
    event = make_event(client, organizer)
    resp = client.get(f"/api/events/{event['event_id']}", headers=organizer["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["event"]["event_id"] == event["event_id"]


def test_13_missing_event_returns_404(client, organizer):
    assert client.get("/api/events/999999", headers=organizer["headers"]).status_code == 404


def test_14_end_time_before_start_time_rejected(client, organizer):
    resp = client.post("/api/events", json={
        "event_name": "Bad Times", "event_date": "2030-01-01",
        "start_time": "12:00", "end_time": "10:00", "maximum_capacity": 10,
    }, headers=organizer["headers"])
    assert resp.status_code == 422


def test_15_invalid_capacity_rejected(client, organizer):
    resp = client.post("/api/events", json={
        "event_name": "Bad Cap", "event_date": "2030-01-01",
        "start_time": "10:00", "end_time": "11:00", "maximum_capacity": 0,
    }, headers=organizer["headers"])
    assert resp.status_code == 422


def test_16_organizer_can_update_own_event(client, organizer):
    event = make_event(client, organizer)
    resp = client.put(f"/api/events/{event['event_id']}",
                      json={"event_name": "Renamed"}, headers=organizer["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["event"]["event_name"] == "Renamed"


def test_17_other_organizer_cannot_update_event(client, organizer):
    event = make_event(client, organizer)
    from tests.conftest import register, auth_header
    other = register(client, "other@test.com", role="ORGANIZER")
    headers = auth_header(other.get_json()["token"])
    resp = client.put(f"/api/events/{event['event_id']}",
                      json={"event_name": "Hijacked"}, headers=headers)
    assert resp.status_code == 403


def test_18_event_cancellation_notifies_attendees(client, organizer, attendee):
    event = make_event(client, organizer)
    client.post(f"/api/events/{event['event_id']}/rsvp",
                json={"status": "GOING"}, headers=attendee["headers"])

    resp = client.post(f"/api/events/{event['event_id']}/cancel",
                       json={"reason": "Instructor unavailable"}, headers=organizer["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["event"]["status"] == "CANCELLED"

    notifs = client.get("/api/notifications", headers=attendee["headers"]).get_json()
    assert any(n["type"] == "EVENT_CANCELLED" for n in notifs["notifications"])


def test_19_cancelled_event_rejects_rsvp(client, organizer, attendee):
    event = make_event(client, organizer)
    client.post(f"/api/events/{event['event_id']}/cancel", json={}, headers=organizer["headers"])
    resp = client.post(f"/api/events/{event['event_id']}/rsvp",
                       json={"status": "GOING"}, headers=attendee["headers"])
    assert resp.status_code == 409


def test_20_upcoming_events_listing(client, organizer):
    make_event(client, organizer, event_name="Future Event", event_date="2030-06-01")
    resp = client.get("/api/events/upcoming", headers=organizer["headers"])
    assert resp.status_code == 200
    assert any(e["event_name"] == "Future Event" for e in resp.get_json()["events"])