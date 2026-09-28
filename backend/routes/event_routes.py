"""Event management endpoints."""
from flask import Blueprint, g, jsonify, request

from ..auth import auth_required, optional_auth, roles_required
from ..services import event_service
from ..utils.errors import Forbidden

bp = Blueprint("events", __name__, url_prefix="/api/events")


@bp.post("")
@roles_required("ORGANIZER", "ADMIN")
def create_event():
    data = request.get_json(silent=True) or {}
    event = event_service.create_event(g.user, data)
    return jsonify(event=event), 201


@bp.get("")
@optional_auth
def list_events():
    status = request.args.get("status")
    search = request.args.get("q")
    mine = request.args.get("mine")
    organizer_id = None
    if mine == "true" and g.user:
        organizer_id = g.user["user_id"]
    return jsonify(events=event_service.list_events(status, search, organizer_id)), 200


@bp.get("/upcoming")
@optional_auth
def upcoming():
    return jsonify(events=event_service.get_upcoming_events()), 200


@bp.get("/<int:event_id>")
@optional_auth
def get_event(event_id: int):
    return jsonify(event=event_service.get_event(event_id)), 200


@bp.put("/<int:event_id>")
@auth_required
def update_event(event_id: int):
    data = request.get_json(silent=True) or {}
    return jsonify(event=event_service.update_event(event_id, g.user, data)), 200


@bp.delete("/<int:event_id>")
@auth_required
def delete_event(event_id: int):
    event_service.delete_event(event_id, g.user)
    return jsonify(message="Event deleted"), 200


@bp.post("/<int:event_id>/cancel")
@auth_required
def cancel_event(event_id: int):
    data = request.get_json(silent=True) or {}
    event = event_service.cancel_event(event_id, g.user, data.get("reason", ""))
    return jsonify(event=event, message="Event cancelled and attendees notified"), 200


@bp.post("/<int:event_id>/invite")
@auth_required
def invite(event_id: int):
    data = request.get_json(silent=True) or {}
    attendee = event_service.invite_attendee(event_id, g.user, data.get("email", ""))
    return jsonify(invitee=attendee, message="Invitation sent"), 201


@bp.get("/<int:event_id>/invites")
@auth_required
def list_invites(event_id: int):
    return jsonify(invites=event_service.list_invites(event_id, g.user)), 200