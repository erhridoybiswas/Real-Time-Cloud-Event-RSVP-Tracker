"""Analytics endpoints."""
from flask import Blueprint, g, jsonify, request

from ..auth import auth_required, roles_required
from ..services import analytics_service
from ..services.event_service import get_event
from ..utils.errors import Forbidden

bp = Blueprint("analytics", __name__, url_prefix="/api")


@bp.get("/events/<int:event_id>/analytics")
@auth_required
def event_analytics(event_id: int):
    event = get_event(event_id)
    if g.user["role"] != "ADMIN" and event["organizer_id"] != g.user["user_id"]:
        raise Forbidden("Only the organizer can view analytics for this event")
    return jsonify(analytics_service.event_analytics(event_id)), 200


@bp.get("/analytics/overview")
@roles_required("ORGANIZER", "ADMIN")
def overview():
    return jsonify(analytics_service.organizer_overview(g.user["user_id"])), 200