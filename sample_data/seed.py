"""
Seed the database with synthetic demo data.

Run:  python -m sample_data.seed
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.auth import hash_password                     # noqa: E402
from backend.database import init_db, transaction           # noqa: E402

DEMO_PASSWORD = "Password123"

ORGANIZERS = [
    ("organizer@demo.com", "Priya Sharma"),
    ("events@techclub.org", "Rahul Verma"),
]

ATTENDEES = [
    ("attendee@demo.com", "Aarav Gupta"),
    ("meera@example.com", "Meera Nair"),
    ("kabir@example.com", "Kabir Singh"),
    ("ananya@example.com", "Ananya Rao"),
    ("vikram@example.com", "Vikram Menon"),
    ("sara@example.com", "Sara Khan"),
    ("dev@example.com", "Dev Patel"),
    ("isha@example.com", "Isha Bose"),
]

EVENTS = [
    {
        "name": "Cloud Computing Workshop",
        "desc": "Hands-on introduction to cloud services, deployment models and real-time apps.",
        "type": "WORKSHOP", "date": "2025-12-15", "start": "10:00", "end": "13:00",
        "venue": "Seminar Hall A", "capacity": 100,
    },
    {
        "name": "Real-Time Systems Webinar",
        "desc": "WebSockets, SSE and event-driven architecture explained with live demos.",
        "type": "WEBINAR", "date": "2025-12-20", "start": "18:00", "end": "19:30",
        "venue": "Online", "capacity": 500,
    },
    {
        "name": "Microservices Meetup",
        "desc": "Community meetup on API gateways, service mesh and observability.",
        "type": "MEETUP", "date": "2026-01-10", "start": "17:00", "end": "20:00",
        "venue": "Innovation Hub, Block C", "capacity": 60,
    },
    {
        "name": "Tiny Capacity Demo (race condition test)",
        "desc": "Capacity of 2 — used to demonstrate concurrency-safe seat allocation.",
        "type": "GENERAL", "date": "2026-01-25", "start": "11:00", "end": "12:00",
        "venue": "Lab 3", "capacity": 2,
    },
]


def seed() -> None:
    init_db()
    rng = random.Random(42)  # deterministic

    with transaction() as conn:
        # ---- users ----
        user_ids: dict[str, int] = {}

        for email, name in ORGANIZERS:
            row = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                user_ids[email] = row["user_id"]; continue
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
                (email, hash_password(DEMO_PASSWORD), name, "ORGANIZER"),
            )
            user_ids[email] = cur.lastrowid

        for email, name in ATTENDEES:
            row = conn.execute("SELECT user_id FROM users WHERE email = ?", (email,)).fetchone()
            if row:
                user_ids[email] = row["user_id"]; continue
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
                (email, hash_password(DEMO_PASSWORD), name, "ATTENDEE"),
            )
            user_ids[email] = cur.lastrowid

        # Admin (uses the bootstrap flow in normal registration)
        admin = conn.execute("SELECT user_id FROM users WHERE role='ADMIN'").fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role) VALUES (?,?,?,?)",
                ("admin@demo.com", hash_password(DEMO_PASSWORD), "Platform Admin", "ADMIN"),
            )

        # ---- events ----
        organizer_ids = [user_ids[e] for e, _ in ORGANIZERS]
        event_ids: list[int] = []

        for idx, ev in enumerate(EVENTS):
            existing = conn.execute(
                "SELECT event_id FROM events WHERE event_name = ?", (ev["name"],)
            ).fetchone()
            if existing:
                event_ids.append(existing["event_id"]); continue

            cur = conn.execute(
                """INSERT INTO events
                     (organizer_id, event_name, description, event_type, event_date,
                      start_time, end_time, venue, online_link, maximum_capacity,
                      registration_deadline, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    organizer_ids[idx % len(organizer_ids)],
                    ev["name"], ev["desc"], ev["type"], ev["date"],
                    ev["start"], ev["end"], ev["venue"],
                    "https://meet.example.com/demo-room" if ev["venue"] == "Online" else "",
                    ev["capacity"], f"{ev['date']}T09:00:00", "PUBLISHED",
                ),
            )
            event_ids.append(cur.lastrowid)

        # ---- invites + RSVPs ----
        attendee_ids = [user_ids[e] for e, _ in ATTENDEES]
        statuses = ["GOING", "GOING", "GOING", "MAYBE", "MAYBE", "NOT_GOING"]

        for event_id in event_ids[:-1]:  # leave the tiny-capacity event clean
            for attendee_id in attendee_ids:
                conn.execute(
                    """INSERT OR IGNORE INTO invites (event_id, user_id) VALUES (?,?)""",
                    (event_id, attendee_id),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO rsvps (event_id, user_id, status)
                       VALUES (?,?,?)""",
                    (event_id, attendee_id, rng.choice(statuses)),
                )

        # ---- announcements ----
        first_event = event_ids[0]
        existing_ann = conn.execute(
            "SELECT 1 FROM announcements WHERE event_id = ?", (first_event,)
        ).fetchone()
        if not existing_ann:
            conn.execute(
                "INSERT INTO announcements (event_id, title, message) VALUES (?,?,?)",
                (first_event, "Venue confirmed",
                 "The workshop will be held in Seminar Hall A. Please arrive 10 minutes early."),
            )

    print("✅ Seed complete.")
    print(f"   Organizer : organizer@demo.com / {DEMO_PASSWORD}")
    print(f"   Attendee  : attendee@demo.com  / {DEMO_PASSWORD}")
    print(f"   Admin     : admin@demo.com     / {DEMO_PASSWORD}")


if __name__ == "__main__":
    seed()