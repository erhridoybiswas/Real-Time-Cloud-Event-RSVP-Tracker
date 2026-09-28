"""Event CRUD, lifecycle and ownership rules."""
import datetime as dt

from ..database import fetch_all, fetch_one, transaction
from ..utils.errors import Conflict, Forbidden, NotFound, ValidationError
from ..utils.validators import (
    clean_capacity, clean_date, clean_datetime_or_none, clean_event_status,
    clean_text, clean_time, require_fields,
)

REQUIRED_CREATE_FIELDS = [
    "event_name", "event_date", "start_time", "end_time", "maximum_capacity",
]

UPDATABLE_FIELDS = [
    "event_name", "description", "event_type", "event_date", "start_time",
    "end_time", "venue", "online_link", "maximum_capacity",
    "registration_deadline", "status",
]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def _validate_event_payload(data: dict, partial: bool = False) -> dict:
    clean: dict = {}

    if not partial:
        require_fields(data, REQUIRED_CREATE_FIELDS)

    if "event_name" in data:
        name = clean_text(data.get("event_name"), "event_name", 200)
        if not name:
            raise ValidationError("event_name is required")
        clean["event_name"] = name

    for field in ("description", "event_type", "venue", "online_link"):
        if field in data:
            clean[field] = clean_text(data.get(field), field)

    if "event_date" in data:
        clean["event_date"] = clean_date(data["event_date"])
    if "start_time" in data:
        clean["start_time"] = clean_time(data["start_time"])
    if "end_time" in data:
        clean["end_time"] = clean_time(data["end_time"])
    if "maximum_capacity" in data:
        clean["maximum_capacity"] = clean_capacity(data["maximum_capacity"])
    if "registration_deadline" in data:
        clean["registration_deadline"] = clean_datetime_or_none(
            data.get("registration_deadline")
        )
    if "status" in data:
        clean["status"] = clean_event_status(data["status"])

    # cross-field rules
    start = clean.get("start_time", data.get("start_time"))
    end = clean.get("end_time", data.get("end_time"))
    if start and end and str(end) <= str(start):
        raise ValidationError("end_time must be after start_time")

    deadline = clean.get("registration_deadline", data.get("registration_deadline"))
    event_date = clean.get("event_date", data.get("event_date"))
    if deadline and event_date and str(deadline)[:10] > str(event_date):
        raise ValidationError("registration_deadline cannot be after the event date")

    return clean


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
def get_event(event_id: int) -> dict:
    event = fetch_one(
        """SELECT e.*, u.full_name AS organizer_name, u.email AS organizer_email
             FROM events e
             JOIN users u ON u.user_id = e.organizer_id
            WHERE e.event_id = ?""",
        (event_id,),
    )
    if not event:
        raise NotFound(f"Event {event_id} not found")
    return event


def list_events(status: str | None = None, search: str | None = None,
                organizer_id: int | None = None) -> list[dict]:
    sql = """SELECT e.*, u.full_name AS organizer_name,
                    (SELECT COUNT(*) FROM rsvps r
                      WHERE r.event_id = e.event_id AND r.status = 'GOING') AS going_count,
                    (SELECT COUNT(*) FROM rsvps r
                      WHERE r.event_id = e.event_id) AS response_count
               FROM events e
               JOIN users u ON u.user_id = e.organizer_id
              WHERE 1 = 1"""
    params: list = []

    if status:
        sql += " AND e.status = ?"
        params.append(clean_event_status(status))
    if organizer_id:
        sql += " AND e.organizer_id = ?"
        params.append(organizer_id)
    if search:
        sql += " AND (e.event_name LIKE ? OR e.description LIKE ?)"
        like = f"%{search}%"
        params += [like, like]

    sql += " ORDER BY e.event_date ASC, e.start_time ASC"
    return fetch_all(sql, tuple(params))


def get_upcoming_events(limit: int = 50) -> list[dict]:
    today = dt.date.today().isoformat()
    return fetch_all(
        """SELECT e.*, u.full_name AS organizer_name,
                  (SELECT COUNT(*) FROM rsvps r
                    WHERE r.event_id = e.event_id AND r.status = 'GOING') AS going_count
             FROM events e
             JOIN users u ON u.user_id = e.organizer_id
            WHERE e.event_date >= ?
              AND e.status IN ('PUBLISHED','FULL')
            ORDER BY e.event_date ASC, e.start_time ASC
            LIMIT ?""",
        (today, limit),
    )


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------
def create_event(organizer: dict, data: dict) -> dict:
    clean = _validate_event_payload(data, partial=False)

    with transaction() as conn:
        cursor = conn.execute(
            """INSERT INTO events
                 (organizer_id, event_name, description, event_type, event_date,
                  start_time, end_time, venue, online_link, maximum_capacity,
                  registration_deadline, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                organizer["user_id"],
                clean["event_name"],
                clean.get("description", ""),
                clean.get("event_type", "GENERAL"),
                clean["event_date"],
                clean["start_time"],
                clean["end_time"],
                clean.get("venue", ""),
                clean.get("online_link", ""),
                clean["maximum_capacity"],
                clean.get("registration_deadline"),
                clean.get("status", "PUBLISHED"),
            ),
        )
        event_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (organizer["user_id"], "EVENT_CREATED", f"event_id={event_id}"),
        )

    return get_event(event_id)


def _assert_can_manage(event: dict, user: dict) -> None:
    if user["role"] == "ADMIN":
        return
    if event["organizer_id"] != user["user_id"]:
        raise Forbidden("You may only manage events that you organize")


def update_event(event_id: int, user: dict, data: dict) -> dict:
    event = get_event(event_id)
    _assert_can_manage(event, user)

    if event["status"] == "CANCELLED" and data.get("status") != "CANCELLED":
        raise Conflict("A cancelled event cannot be modified")

    clean = _validate_event_payload(data, partial=True)
    if not clean:
        raise ValidationError("No updatable fields supplied")

    assignments = ", ".join(f"{field} = ?" for field in clean)
    params = list(clean.values()) + [event_id]

    with transaction() as conn:
        conn.execute(
            f"UPDATE events SET {assignments}, updated_at = datetime('now') "
            f"WHERE event_id = ?",
            tuple(params),
        )
        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (user["user_id"], "EVENT_UPDATED", f"event_id={event_id}"),
        )

    return get_event(event_id)


def cancel_event(event_id: int, user: dict, reason: str = "") -> dict:
    event = get_event(event_id)
    _assert_can_manage(event, user)
    if event["status"] == "CANCELLED":
        raise Conflict("Event is already cancelled")

    message = f"Event '{event['event_name']}' has been cancelled."
    if reason:
        message += f" Reason: {reason}"

    with transaction() as conn:
        conn.execute(
            "UPDATE events SET status = 'CANCELLED', updated_at = datetime('now') "
            "WHERE event_id = ?",
            (event_id,),
        )
        rows = conn.execute(
            "SELECT user_id FROM rsvps WHERE event_id = ? AND status IN ('GOING','MAYBE')",
            (event_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                """INSERT INTO notifications (user_id, event_id, type, message)
                   VALUES (?,?,?,?)""",
                (row["user_id"], event_id, "EVENT_CANCELLED", message),
            )
        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (user["user_id"], "EVENT_CANCELLED", f"event_id={event_id}"),
        )

    return get_event(event_id)


def delete_event(event_id: int, user: dict) -> None:
    event = get_event(event_id)
    _assert_can_manage(event, user)

    with transaction() as conn:
        conn.execute("DELETE FROM events WHERE event_id = ?", (event_id,))
        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (user["user_id"], "EVENT_DELETED", f"event_id={event_id}"),
        )


# --------------------------------------------------------------------------
# Invites
# --------------------------------------------------------------------------
def invite_attendee(event_id: int, user: dict, attendee_email: str) -> dict:
    event = get_event(event_id)
    _assert_can_manage(event, user)

    attendee = fetch_one(
        "SELECT user_id, email, full_name FROM users WHERE email = ?",
        (attendee_email.strip().lower(),),
    )
    if not attendee:
        raise NotFound(f"No registered user with email {attendee_email}")

    with transaction() as conn:
        existing = conn.execute(
            "SELECT 1 FROM invites WHERE event_id = ? AND user_id = ?",
            (event_id, attendee["user_id"]),
        ).fetchone()
        if existing:
            raise Conflict("User is already invited to this event")

        conn.execute(
            "INSERT INTO invites (event_id, user_id) VALUES (?,?)",
            (event_id, attendee["user_id"]),
        )
        conn.execute(
            """INSERT INTO notifications (user_id, event_id, type, message)
               VALUES (?,?,?,?)""",
            (attendee["user_id"], event_id, "INVITE",
             f"You have been invited to '{event['event_name']}'."),
        )
    return attendee


def list_invites(event_id: int, user: dict) -> list[dict]:
    event = get_event(event_id)
    _assert_can_manage(event, user)
    return fetch_all(
        """SELECT i.invite_id, i.created_at, u.user_id, u.full_name, u.email,
                  r.status AS rsvp_status
             FROM invites i
             JOIN users u ON u.user_id = i.user_id
             LEFT JOIN rsvps r ON r.event_id = i.event_id AND r.user_id = i.user_id
            WHERE i.event_id = ?
            ORDER BY i.created_at ASC""",
        (event_id,),
    )