"""In-app notification endpoints."""
from flask import Blueprint, g, jsonify

from ..auth import auth_required
from ..services import notification_service
from ..utils.errors import NotFound

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@bp.get("")
@auth_required
def list_notifications():
    return jsonify(
        notifications=notification_service.list_notifications(g.user["user_id"]),
        unread=notification_service.unread_count(g.user["user_id"]),
    ), 200


@bp.put("/<int:notification_id>/read")
@auth_required
def mark_read(notification_id: int):
    if not notification_service.mark_read(notification_id, g.user["user_id"]):
        raise NotFound("Notification not found")
    return jsonify(message="Marked as read"), 200


@bp.put("/read-all")
@auth_required
def mark_all_read():
    updated = notification_service.mark_all_read(g.user["user_id"])
    return jsonify(updated=updated, message="All notifications marked as read"), 200