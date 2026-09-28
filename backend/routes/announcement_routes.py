"""Event announcements."""
from flask import Blueprint, g, jsonify, request

from ..auth import auth_required
from ..database import fetch_all, transaction
from ..realtime import broker
from ..services import notification_service
from ..services.event_service import get_event
from ..utils.errors import Forbidden, ValidationError
from ..utils.validators import clean_text, require_fields

bp = Blueprint("announcements", __name__, url_prefix="/api/events")


def _assert_organizer(event: dict, user: dict) -> None:
    if user["role"] != "ADMIN" and event["organizer_id"] != user["user_id"]:
        raise Forbidden("Only the organizer can post announcements")


@bp.post("/<int:event_id>/announcements")
@auth_required
def create_announcement(event_id: int):
    event = get_event(event_id)
    _assert_organizer(event, g.user)

    data = request.get_json(silent=True) or {}
    require_fields(data, ["title", "message"])
    title = clean_text(data["title"], "title", 200)
    message = clean_text(data["message"], "message", 4000)

    with transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO announcements (event_id, title, message) VALUES (?,?,?)",
            (event_id, title, message),
        )
        announcement_id = cursor.lastrowid
        recipients = notification_service.notify_event_attendees(
            conn, event_id, "ANNOUNCEMENT",
            f"{title}: {message}",
        )

    broker.publish(
        f"event:{event_id}",
        {"type": "ANNOUNCEMENT", "title": title, "message": message},
    )
    return jsonify(
        announcement_id=announcement_id,
        notified=recipients,
        message="Announcement published",
    ), 201


@bp.get("/<int:event_id>/announcements")
@auth_required
def list_announcements(event_id: int):
    get_event(event_id)
    return jsonify(announcements=fetch_all(
        """SELECT announcement_id, title, message, created_at
             FROM announcements WHERE event_id = ?
            ORDER BY created_at DESC""",
        (event_id,),
    )), 200