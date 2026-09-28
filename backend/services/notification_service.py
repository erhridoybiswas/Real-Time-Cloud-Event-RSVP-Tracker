"""Notification creation and retrieval."""
from ..database import fetch_all, fetch_one, transaction


def create_notification(conn, user_id: int, event_id: int | None,
                        ntype: str, message: str) -> int:
    """Insert a notification using an EXISTING transaction connection."""
    cursor = conn.execute(
        """INSERT INTO notifications (user_id, event_id, type, message)
           VALUES (?, ?, ?, ?)""",
        (user_id, event_id, ntype, message),
    )
    return cursor.lastrowid


def notify_event_attendees(conn, event_id: int, ntype: str, message: str,
                           statuses: tuple[str, ...] = ("GOING", "MAYBE")) -> int:
    """Fan a notification out to every attendee with one of `statuses`."""
    placeholders = ",".join("?" for _ in statuses)
    rows = conn.execute(
        f"SELECT user_id FROM rsvps WHERE event_id = ? AND status IN ({placeholders})",
        (event_id, *statuses),
    ).fetchall()
    for row in rows:
        create_notification(conn, row["user_id"], event_id, ntype, message)
    return len(rows)


def list_notifications(user_id: int, limit: int = 100) -> list[dict]:
    return fetch_all(
        """SELECT n.*, e.event_name
             FROM notifications n
             LEFT JOIN events e ON e.event_id = n.event_id
            WHERE n.user_id = ?
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT ?""",
        (user_id, limit),
    )


def unread_count(user_id: int) -> int:
    row = fetch_one(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND read = 0",
        (user_id,),
    )
    return row["c"] if row else 0


def mark_read(notification_id: int, user_id: int) -> bool:
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE notifications SET read = 1 WHERE notification_id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        return cursor.rowcount > 0


def mark_all_read(user_id: int) -> int:
    with transaction() as conn:
        cursor = conn.execute(
            "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
            (user_id,),
        )
        return cursor.rowcount