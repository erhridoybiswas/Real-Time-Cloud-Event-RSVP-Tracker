"""Event and organizer analytics."""
from ..database import fetch_all, fetch_one
from ..utils.errors import NotFound


def _safe_pct(numerator: float, denominator: float) -> float:
    return round((numerator / denominator) * 100, 2) if denominator else 0.0


def event_analytics(event_id: int) -> dict:
    event = fetch_one(
        """SELECT e.*, u.full_name AS organizer_name
             FROM events e JOIN users u ON u.user_id = e.organizer_id
            WHERE e.event_id = ?""",
        (event_id,),
    )
    if not event:
        raise NotFound(f"Event {event_id} not found")

    rows = fetch_all(
        "SELECT status, COUNT(*) AS c FROM rsvps WHERE event_id = ? GROUP BY status",
        (event_id,),
    )
    counts = {"GOING": 0, "MAYBE": 0, "NOT_GOING": 0}
    for row in rows:
        counts[row["status"]] = row["c"]

    invited = fetch_one(
        "SELECT COUNT(*) AS c FROM invites WHERE event_id = ?", (event_id,)
    )["c"]
    waitlist = fetch_one(
        "SELECT COUNT(*) AS c FROM waitlist WHERE event_id = ? AND status = 'WAITING'",
        (event_id,),
    )["c"]

    responded = sum(counts.values())
    capacity = event["maximum_capacity"]

    # Denominator for the response rate: explicit invites, or everyone with
    # an account if the organizer never sent targeted invites.
    total_audience = invited if invited else fetch_one(
        "SELECT COUNT(*) AS c FROM users WHERE role = 'ATTENDEE'"
    )["c"]
    total_audience = max(total_audience, responded, 1)

    growth = fetch_all(
        """SELECT date(responded_at) AS day,
                  SUM(CASE WHEN status = 'GOING'     THEN 1 ELSE 0 END) AS going,
                  SUM(CASE WHEN status = 'MAYBE'     THEN 1 ELSE 0 END) AS maybe,
                  SUM(CASE WHEN status = 'NOT_GOING' THEN 1 ELSE 0 END) AS not_going
             FROM rsvps
            WHERE event_id = ?
            GROUP BY date(responded_at)
            ORDER BY day ASC""",
        (event_id,),
    )

    timeline = fetch_all(
        """SELECT strftime('%Y-%m-%d %H:00', responded_at) AS bucket,
                  COUNT(*) AS responses
             FROM rsvps
            WHERE event_id = ?
            GROUP BY bucket
            ORDER BY bucket ASC
            LIMIT 200""",
        (event_id,),
    )

    return {
        "event": {
            "event_id": event["event_id"],
            "event_name": event["event_name"],
            "status": event["status"],
            "event_date": event["event_date"],
            "start_time": event["start_time"],
            "maximum_capacity": capacity,
            "organizer_name": event["organizer_name"],
        },
        "totals": {
            "invited": invited,
            "responded": responded,
            "going": counts["GOING"],
            "maybe": counts["MAYBE"],
            "not_going": counts["NOT_GOING"],
            "waitlist": waitlist,
        },
        "metrics": {
            "response_rate": _safe_pct(responded, total_audience),
            "capacity_utilization": _safe_pct(counts["GOING"], capacity),
            "available_seats": max(capacity - counts["GOING"], 0),
            "rsvp_conversion_rate": _safe_pct(counts["GOING"], responded),
            "maybe_rate": _safe_pct(counts["MAYBE"], responded),
            "no_show_risk": _safe_pct(counts["MAYBE"], counts["GOING"] + counts["MAYBE"]),
        },
        "charts": {
            "status_distribution": [
                {"label": "Going", "value": counts["GOING"]},
                {"label": "Maybe", "value": counts["MAYBE"]},
                {"label": "Not Going", "value": counts["NOT_GOING"]},
            ],
            "growth_over_time": growth,
            "capacity_utilization": {
                "used": counts["GOING"],
                "available": max(capacity - counts["GOING"], 0),
                "capacity": capacity,
            },
            "rsvp_timeline": timeline,
        },
    }


def organizer_overview(organizer_id: int) -> dict:
    events = fetch_all(
        """SELECT e.event_id, e.event_name, e.event_date, e.status, e.maximum_capacity,
                  (SELECT COUNT(*) FROM rsvps r
                    WHERE r.event_id = e.event_id AND r.status='GOING')     AS going,
                  (SELECT COUNT(*) FROM rsvps r
                    WHERE r.event_id = e.event_id AND r.status='MAYBE')     AS maybe,
                  (SELECT COUNT(*) FROM rsvps r
                    WHERE r.event_id = e.event_id AND r.status='NOT_GOING') AS not_going,
                  (SELECT COUNT(*) FROM waitlist w
                    WHERE w.event_id = e.event_id AND w.status='WAITING')   AS waitlist
             FROM events e
            WHERE e.organizer_id = ?
            ORDER BY e.event_date DESC""",
        (organizer_id,),
    )

    totals = {
        "total_events": len(events),
        "published": sum(1 for e in events if e["status"] == "PUBLISHED"),
        "full": sum(1 for e in events if e["status"] == "FULL"),
        "cancelled": sum(1 for e in events if e["status"] == "CANCELLED"),
        "going": sum(e["going"] for e in events),
        "maybe": sum(e["maybe"] for e in events),
        "not_going": sum(e["not_going"] for e in events),
        "waitlist": sum(e["waitlist"] for e in events),
        "total_capacity": sum(e["maximum_capacity"] for e in events),
    }
    totals["responses"] = totals["going"] + totals["maybe"] + totals["not_going"]
    totals["response_rate"] = _safe_pct(totals["responses"], max(totals["total_capacity"], 1))

    return {"totals": totals, "events": events}