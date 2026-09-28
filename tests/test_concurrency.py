"""
Concurrency / race-condition tests.

These tests prove that two users clicking GOING on the last seat at the same
moment cannot both succeed.
"""
import threading

from tests.conftest import auth_header, make_event, register


def _attendee(client, email):
    resp = register(client, email, role="ATTENDEE", name=email.split("@")[0])
    return auth_header(resp.get_json()["token"])


def test_36_simultaneous_last_seat_requests(client, organizer):
    """
    Capacity = 1. Fire 25 concurrent GOING requests.

    Correct behaviour: exactly ONE user ends up GOING. The other 24 are
    waitlisted (never accepted) because the capacity check and the insert
    happen inside a single BEGIN IMMEDIATE transaction.
    """
    event = make_event(client, organizer, maximum_capacity=1)
    eid = event["event_id"]

    headers_list = [_attendee(client, f"race{i}@test.com") for i in range(25)]
    results: list[tuple[int, dict]] = []
    lock = threading.Lock()

    def attempt(headers):
        resp = client.post(f"/api/events/{eid}/rsvp",
                           json={"status": "GOING"}, headers=headers)
        with lock:
            results.append((resp.status_code, resp.get_json()))

    threads = [threading.Thread(target=attempt, args=(h,)) for h in headers_list]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 25

    accepted = [body for status, body in results
                if status == 201 and not body.get("waitlisted")]
    waitlisted = [body for status, body in results if body.get("waitlisted")]

    assert len(accepted) == 1, f"Expected exactly 1 accepted RSVP, got {len(accepted)}"
    assert len(waitlisted) == 24

    counts = client.get(f"/api/events/{eid}/counts", headers=organizer["headers"]).get_json()["counts"]
    assert counts["GOING"] == 1
    assert counts["GOING"] <= counts["capacity"]
    assert counts["waitlist"] == 24


def test_37_duplicate_concurrent_requests_are_idempotent(client, organizer):
    """One user firing 10 identical requests in parallel still produces ONE row."""
    event = make_event(client, organizer, maximum_capacity=50)
    eid = event["event_id"]
    headers = _attendee(client, "spam@test.com")

    threads = [
        threading.Thread(
            target=lambda: client.post(f"/api/events/{eid}/rsvp",
                                       json={"status": "GOING"}, headers=headers)
        )
        for _ in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    counts = client.get(f"/api/events/{eid}/counts", headers=headers).get_json()["counts"]
    assert counts["GOING"] == 1  # UNIQUE(event_id,user_id) + upsert = idempotent

    rsvps = client.get("/api/rsvps/me", headers=headers).get_json()["rsvps"]
    assert len(rsvps) == 1


def test_38_capacity_never_exceeded_under_mixed_load(client, organizer):
    """Mixed GOING / MAYBE traffic never pushes GOING above capacity."""
    capacity = 5
    event = make_event(client, organizer, maximum_capacity=capacity)
    eid = event["event_id"]

    headers_list = [_attendee(client, f"mix{i}@test.com") for i in range(30)]

    def worker(i, headers):
        status = "GOING" if i % 2 == 0 else "MAYBE"
        client.post(f"/api/events/{eid}/rsvp", json={"status": status}, headers=headers)

    threads = [threading.Thread(target=worker, args=(i, h))
               for i, h in enumerate(headers_list)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    counts = client.get(f"/api/events/{eid}/counts", headers=organizer["headers"]).get_json()["counts"]
    assert counts["GOING"] <= capacity