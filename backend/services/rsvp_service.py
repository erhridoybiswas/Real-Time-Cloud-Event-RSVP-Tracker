"""
RSVP lifecycle: create / update / cancel, capacity enforcement, waitlist.

CONCURRENCY CONTRACT
--------------------
Every state-changing operation runs inside `transaction()` which issues
`BEGIN IMMEDIATE`. SQLite grants only ONE RESERVED lock at a time, so the
sequence

    read going_count  ->  compare with capacity  ->  write rsvp

is atomic with respect to all other writers. Two users racing for the last
seat cannot both win: the second transaction blocks until the first commits,
then re-reads the updated count and is correctly rejected / waitlisted.
"""
from ..database import fetch_all, fetch_one, transaction
from ..realtime import broker
from ..utils.errors import Conflict, NotFound, ValidationError
from ..utils.validators import clean_rsvp_status

ZERO_COUNTS = {"GOING": 0, "MAYBE": 0, "NOT_GOING": 0}


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------
def _counts(conn, event_id: int) -> dict:
    """Compute the live RSVP aggregate using an existing connection."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS c FROM rsvps WHERE event_id = ? GROUP BY status",
        (event_id,),
    ).fetchall()
    counts = dict(ZERO_COUNTS)
    for row in rows:
        counts[row["status"]] = row["c"]

    event = conn.execute(
        "SELECT maximum_capacity, status FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    capacity = event["maximum_capacity"] if event else 0

    waitlist_row = conn.execute(
        "SELECT COUNT(*) AS c FROM waitlist WHERE event_id = ? AND status = 'WAITING'",
        (event_id,),
    ).fetchone()

    counts.update(
        event_id=event_id,
        capacity=capacity,
        available=max(capacity - counts["GOING"], 0),
        waitlist=waitlist_row["c"] if waitlist_row else 0,
        event_status=event["status"] if event else None,
        total_responses=sum(counts[s] for s in ZERO_COUNTS),
    )
    return counts


def get_event_counts(event_id: int) -> dict:
    """Public read-only snapshot (used by the SSE handshake and /counts)."""
    conn = fetch_one("SELECT event_id FROM events WHERE event_id = ?", (event_id,))
    if not conn:
        raise NotFound(f"Event {event_id} not found")
    return _event_counts_readonly(event_id)


def _event_counts_readonly(event_id: int) -> dict:
    rows = fetch_all(
        "SELECT status, COUNT(*) AS c FROM rsvps WHERE event_id = ? GROUP BY status",
        (event_id,),
    )
    counts = dict(ZERO_COUNTS)
    for row in rows:
        counts[row["status"]] = row["c"]

    event = fetch_one(
        "SELECT maximum_capacity, status FROM events WHERE event_id = ?", (event_id,)
    )
    capacity = event["maximum_capacity"] if event else 0
    waitlist = fetch_one(
        "SELECT COUNT(*) AS c FROM waitlist WHERE event_id = ? AND status = 'WAITING'",
        (event_id,),
    )

    counts.update(
        event_id=event_id,
        capacity=capacity,
        available=max(capacity - counts["GOING"], 0),
        waitlist=waitlist["c"] if waitlist else 0,
        event_status=event["status"] if event else None,
        total_responses=sum(counts[s] for s in ZERO_COUNTS),
    )
    return counts


def _publish(event_id: int, counts: dict, reason: str) -> None:
    """Publish AFTER the transaction commits — clients must never see rolled-back state."""
    broker.publish(
        f"event:{event_id}",
        {"type": "RSVP_UPDATED", "reason": reason, "counts": counts},
    )


# --------------------------------------------------------------------------
# Waitlist
# --------------------------------------------------------------------------
def _promote_from_waitlist(conn, event_id: int, capacity: int) -> list[int]:
    """Promote FIFO waitlisted users while seats remain. Returns promoted user ids."""
    promoted: list[int] = []
    going = conn.execute(
        "SELECT COUNT(*) AS c FROM rsvps WHERE event_id = ? AND status = 'GOING'",
        (event_id,),
    ).fetchone()["c"]

    while going < capacity:
        row = conn.execute(
            """SELECT * FROM waitlist
                WHERE event_id = ? AND status = 'WAITING'
                ORDER BY joined_at ASC, waitlist_id ASC
                LIMIT 1""",
            (event_id,),
        ).fetchone()
        if not row:
            break

        conn.execute(
            "UPDATE waitlist SET status = 'PROMOTED' WHERE waitlist_id = ?",
            (row["waitlist_id"],),
        )
        conn.execute(
            """INSERT INTO rsvps (event_id, user_id, status)
               VALUES (?, ?, 'GOING')
               ON CONFLICT(event_id, user_id)
               DO UPDATE SET status = 'GOING', updated_at = datetime('now')""",
            (event_id, row["user_id"]),
        )
        conn.execute(
            """INSERT INTO notifications (user_id, event_id, type, message)
               VALUES (?,?,?,?)""",
            (row["user_id"], event_id, "WAITLIST_PROMOTED",
             "Good news! A seat opened up and you have been moved from the "
             "waitlist to GOING."),
        )
        promoted.append(row["user_id"])
        going += 1

    return promoted


def _sync_event_status(conn, event_id: int, counts: dict) -> None:
    """Flip PUBLISHED <-> FULL based on the live going count."""
    current = conn.execute(
        "SELECT status FROM events WHERE event_id = ?", (event_id,)
    ).fetchone()
    if not current:
        return
    status = current["status"]
    if status in ("CANCELLED", "COMPLETED", "DRAFT"):
        return

    if counts["GOING"] >= counts["capacity"] and status != "FULL":
        conn.execute(
            "UPDATE events SET status = 'FULL', updated_at = datetime('now') "
            "WHERE event_id = ?",
            (event_id,),
        )
    elif counts["GOING"] < counts["capacity"] and status == "FULL":
        conn.execute(
            "UPDATE events SET status = 'PUBLISHED', updated_at = datetime('now') "
            "WHERE event_id = ?",
            (event_id,),
        )


# --------------------------------------------------------------------------
# Core write path
# --------------------------------------------------------------------------
def set_rsvp(event_id: int, user: dict, status: str, allow_waitlist: bool = True) -> dict:
    """
    Create or update the caller's RSVP for an event. Idempotent and race-safe.

    Returns a dict with the new counts plus metadata about waitlisting /
    promotion so the API layer can build a precise response.
    """
    status = clean_rsvp_status(status)
    user_id = user["user_id"]
    waitlisted = False
    promoted: list[int] = []

    with transaction() as conn:
        event = conn.execute(
            "SELECT * FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if not event:
            raise NotFound(f"Event {event_id} not found")

        if event["status"] == "CANCELLED":
            raise Conflict("This event has been cancelled")
        if event["status"] == "COMPLETED":
            raise Conflict("This event has already completed")

        # --- registration deadline (GOING / MAYBE only) --------------------
        if status in ("GOING", "MAYBE") and event["registration_deadline"]:
            from datetime import datetime, timezone
            deadline = str(event["registration_deadline"]).replace("Z", "")
            try:
                deadline_dt = datetime.fromisoformat(deadline)
                if deadline_dt.tzinfo is None:
                    deadline_dt = deadline_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > deadline_dt:
                    raise Conflict("The registration deadline has passed")
            except ValueError:
                pass  # malformed deadline -> do not block the user

        previous = conn.execute(
            "SELECT status FROM rsvps WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        ).fetchone()
        previous_status = previous["status"] if previous else None

        # --- capacity check (the critical section) -------------------------
        if status == "GOING":
            going_others = conn.execute(
                """SELECT COUNT(*) AS c FROM rsvps
                    WHERE event_id = ? AND status = 'GOING' AND user_id <> ?""",
                (event_id, user_id),
            ).fetchone()["c"]

            if going_others >= event["maximum_capacity"]:
                if not allow_waitlist:
                    raise Conflict("Event is full")

                conn.execute(
                    """INSERT INTO waitlist (event_id, user_id, status)
                       VALUES (?, ?, 'WAITING')
                       ON CONFLICT(event_id, user_id)
                       DO UPDATE SET status = 'WAITING', joined_at = datetime('now')""",
                    (event_id, user_id),
                )
                waitlisted = True
            else:
                # A seat is available — make sure we are not stuck on the waitlist.
                conn.execute(
                    """UPDATE waitlist SET status = 'CANCELLED'
                        WHERE event_id = ? AND user_id = ? AND status = 'WAITING'""",
                    (event_id, user_id),
                )

        # --- upsert the RSVP ----------------------------------------------
        if not waitlisted:
            conn.execute(
                """INSERT INTO rsvps (event_id, user_id, status)
                   VALUES (?, ?, ?)
                   ON CONFLICT(event_id, user_id)
                   DO UPDATE SET status = excluded.status,
                                 updated_at = datetime('now')""",
                (event_id, user_id, status),
            )

            if status == "GOING" and previous_status != "GOING":
                conn.execute(
                    """INSERT INTO notifications (user_id, event_id, type, message)
                       VALUES (?,?,?,?)""",
                    (user_id, event_id, "RSVP_CONFIRMED",
                     f"Your RSVP for '{event['event_name']}' is confirmed as GOING."),
                )

        # --- free a seat? promote from the waitlist ------------------------
        if previous_status == "GOING" and status != "GOING":
            promoted = _promote_from_waitlist(conn, event_id, event["maximum_capacity"])

        counts = _counts(conn, event_id)
        _sync_event_status(conn, event_id, counts)
        counts = _counts(conn, event_id)  # refresh after a possible status flip

        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (user_id, "RSVP_SET", f"event_id={event_id} status={status} waitlisted={waitlisted}"),
        )

    _publish(event_id, counts, reason="RSVP_SET")

    return {
        "counts": counts,
        "waitlisted": waitlisted,
        "promoted_user_ids": promoted,
        "status": "WAITLISTED" if waitlisted else status,
    }


def cancel_rsvp(event_id: int, user: dict) -> dict:
    """Delete the caller's RSVP and promote the next waitlisted user."""
    user_id = user["user_id"]

    with transaction() as conn:
        event = conn.execute(
            "SELECT maximum_capacity FROM events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if not event:
            raise NotFound(f"Event {event_id} not found")

        previous = conn.execute(
            "SELECT status FROM rsvps WHERE event_id = ? AND user_id = ?",
            (event_id, user_id),
        ).fetchone()
        if not previous:
            raise NotFound("You have no RSVP for this event")

        conn.execute(
            "DELETE FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, user_id)
        )
        conn.execute(
            """UPDATE waitlist SET status = 'CANCELLED'
                WHERE event_id = ? AND user_id = ? AND status = 'WAITING'""",
            (event_id, user_id),
        )

        promoted = []
        if previous["status"] == "GOING":
            promoted = _promote_from_waitlist(conn, event_id, event["maximum_capacity"])

        counts = _counts(conn, event_id)
        _sync_event_status(conn, event_id, counts)
        counts = _counts(conn, event_id)

    _publish(event_id, counts, reason="RSVP_CANCELLED")
    return {"counts": counts, "promoted_user_ids": promoted}


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
def get_my_rsvps(user_id: int) -> list[dict]:
    return fetch_all(
        """SELECT r.rsvp_id, r.event_id, r.status, r.responded_at, r.updated_at,
                  e.event_name, e.event_date, e.start_time, e.end_time,
                  e.venue, e.online_link, e.status AS event_status,
                  e.maximum_capacity
             FROM rsvps r
             JOIN events e ON e.event_id = r.event_id
            WHERE r.user_id = ?
            ORDER BY e.event_date DESC, e.start_time DESC""",
        (user_id,),
    )


def get_event_rsvps(event_id: int) -> list[dict]:
    return fetch_all(
        """SELECT r.rsvp_id, r.status, r.responded_at, r.updated_at,
                  u.user_id, u.full_name, u.email
             FROM rsvps r
             JOIN users u ON u.user_id = r.user_id
            WHERE r.event_id = ?
            ORDER BY r.updated_at DESC""",
        (event_id,),
    )


def get_waitlist(event_id: int) -> list[dict]:
    return fetch_all(
        """SELECT w.waitlist_id, w.joined_at, w.status,
                  u.user_id, u.full_name, u.email
             FROM waitlist w
             JOIN users u ON u.user_id = w.user_id
            WHERE w.event_id = ?
            ORDER BY w.joined_at ASC, w.waitlist_id ASC""",
        (event_id,),
    )