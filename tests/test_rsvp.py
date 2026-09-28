"""RSVP workflow, capacity, waitlist, analytics and notification tests."""
from tests.conftest import auth_header, make_event, register


def _attendee(client, email, name="Attendee"):
    resp = register(client, email, role="ATTENDEE", name=name)
    data = resp.get_json()
    return {"token": data["token"], "user": data["user"], "headers": auth_header(data["token"])}


def test_21_valid_rsvp(client, organizer, attendee):
    event = make_event(client, organizer)
    resp = client.post(f"/api/events/{event['event_id']}/rsvp",
                       json={"status": "GOING"}, headers=attendee["headers"])
    assert resp.status_code == 201
    assert resp.get_json()["counts"]["GOING"] == 1


def test_22_duplicate_rsvp_updates_instead_of_duplicating(client, organizer, attendee):
    event = make_event(client, organizer)
    eid = event["event_id"]
    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])
    resp = client.put(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["counts"]["GOING"] == 1  # never 2

    rsvps = client.get(f"/api/events/{eid}/rsvps", headers=organizer["headers"]).get_json()["rsvps"]
    assert len(rsvps) == 1


def test_23_update_going_to_maybe(client, organizer, attendee):
    event = make_event(client, organizer)
    eid = event["event_id"]
    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])
    resp = client.put(f"/api/events/{eid}/rsvp", json={"status": "MAYBE"}, headers=attendee["headers"])
    counts = resp.get_json()["counts"]
    assert counts["GOING"] == 0 and counts["MAYBE"] == 1


def test_24_update_maybe_to_going(client, organizer, attendee):
    event = make_event(client, organizer)
    eid = event["event_id"]
    client.post(f"/api/events/{eid}/rsvp", json={"status": "MAYBE"}, headers=attendee["headers"])
    resp = client.put(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])
    counts = resp.get_json()["counts"]
    assert counts["GOING"] == 1 and counts["MAYBE"] == 0


def test_25_cancel_rsvp(client, organizer, attendee):
    event = make_event(client, organizer)
    eid = event["event_id"]
    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])
    resp = client.delete(f"/api/events/{eid}/rsvp", headers=attendee["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["counts"]["GOING"] == 0


def test_26_registration_deadline_enforced(client, organizer, attendee):
    event = make_event(client, organizer, registration_deadline="2020-01-01T00:00:00")
    resp = client.post(f"/api/events/{event['event_id']}/rsvp",
                       json={"status": "GOING"}, headers=attendee["headers"])
    assert resp.status_code == 409
    assert "deadline" in resp.get_json()["error"].lower()


def test_27_capacity_enforced_and_waitlist_used(client, organizer):
    event = make_event(client, organizer, maximum_capacity=2)
    eid = event["event_id"]

    for i in range(2):
        a = _attendee(client, f"cap{i}@test.com")
        resp = client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=a["headers"])
        assert resp.status_code == 201
        assert resp.get_json()["waitlisted"] is False

    third = _attendee(client, "cap2@test.com")
    resp = client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=third["headers"])
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["waitlisted"] is True
    assert body["status"] == "WAITLISTED"
    assert body["counts"]["GOING"] == 2
    assert body["counts"]["waitlist"] == 1

    ev = client.get(f"/api/events/{eid}", headers=organizer["headers"]).get_json()["event"]
    assert ev["status"] == "FULL"


def test_28_waitlist_promotion_on_cancellation(client, organizer):
    event = make_event(client, organizer, maximum_capacity=1)
    eid = event["event_id"]

    first = _attendee(client, "w1@test.com")
    second = _attendee(client, "w2@test.com")

    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=first["headers"])
    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=second["headers"])

    resp = client.delete(f"/api/events/{eid}/rsvp", headers=first["headers"])
    body = resp.get_json()
    assert body["counts"]["GOING"] == 1
    assert body["counts"]["waitlist"] == 0
    assert second["user"]["user_id"] in body["promoted_user_ids"]

    notifs = client.get("/api/notifications", headers=second["headers"]).get_json()
    assert any(n["type"] == "WAITLIST_PROMOTED" for n in notifs["notifications"])


def test_29_rsvp_confirmation_notification(client, organizer, attendee):
    event = make_event(client, organizer)
    client.post(f"/api/events/{event['event_id']}/rsvp",
                json={"status": "GOING"}, headers=attendee["headers"])
    notifs = client.get("/api/notifications", headers=attendee["headers"]).get_json()
    assert any(n["type"] == "RSVP_CONFIRMED" for n in notifs["notifications"])


def test_30_announcement_creation_and_notification(client, organizer, attendee):
    event = make_event(client, organizer)
    eid = event["event_id"]
    client.post(f"/api/events/{eid}/rsvp", json={"status": "GOING"}, headers=attendee["headers"])

    resp = client.post(f"/api/events/{eid}/announcements",
                       json={"title": "Venue changed", "message": "Now in Hall B."},
                       headers=organizer["headers"])
    assert resp.status_code == 201
    assert resp.get_json()["notified"] >= 1

    listing = client.get(f"/api/events/{eid}/announcements", headers=attendee["headers"]).get_json()
    assert listing["announcements"][0]["title"] == "Venue changed"

    notifs = client.get("/api/notifications", headers=attendee["headers"]).get_json()
    assert any(n["type"] == "ANNOUNCEMENT" for n in notifs["notifications"])


def test_31_attendee_cannot_read_other_peoples_rsvp_list(client, organizer, attendee):
    event = make_event(client, organizer)
    resp = client.get(f"/api/events/{event['event_id']}/rsvps", headers=attendee["headers"])
    assert resp.status_code == 403


def test_32_my_rsvps_endpoint(client, organizer, attendee):
    event = make_event(client, organizer)
    client.post(f"/api/events/{event['event_id']}/rsvp",
                json={"status": "MAYBE"}, headers=attendee["headers"])
    resp = client.get("/api/rsvps/me", headers=attendee["headers"])
    assert resp.status_code == 200
    assert resp.get_json()["rsvps"][0]["status"] == "MAYBE"


def test_33_analytics_calculation(client, organizer):
    event = make_event(client, organizer, maximum_capacity=10)
    eid = event["event_id"]

    statuses = ["GOING", "GOING", "MAYBE", "NOT_GOING"]
    for i, status in enumerate(statuses):
        a = _attendee(client, f"an{i}@test.com")
        client.post("/api/events/%d/invite" % eid, json={"email": f"an{i}@test.com"},
                    headers=organizer["headers"])
        client.post(f"/api/events/{eid}/rsvp", json={"status": status}, headers=a["headers"])

    resp = client.get(f"/api/events/{eid}/analytics", headers=organizer["headers"])
    assert resp.status_code == 200
    a = resp.get_json()

    assert a["totals"]["going"] == 2
    assert a["totals"]["maybe"] == 1
    assert a["totals"]["not_going"] == 1
    assert a["totals"]["responded"] == 4
    assert a["metrics"]["capacity_utilization"] == 20.0
    assert a["metrics"]["available_seats"] == 8
    assert a["metrics"]["rsvp_conversion_rate"] == 50.0
    assert a["metrics"]["response_rate"] == 100.0


def test_34_notification_mark_read(client, organizer, attendee):
    event = make_event(client, organizer)
    client.post(f"/api/events/{event['event_id']}/rsvp",
                json={"status": "GOING"}, headers=attendee["headers"])
    notifs = client.get("/api/notifications", headers=attendee["headers"]).get_json()
    nid = notifs["notifications"][0]["notification_id"]

    assert client.put(f"/api/notifications/{nid}/read",
                      headers=attendee["headers"]).status_code == 200
    after = client.get("/api/notifications", headers=attendee["headers"]).get_json()
    assert all(n["read"] for n in after["notifications"])


def test_35_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"