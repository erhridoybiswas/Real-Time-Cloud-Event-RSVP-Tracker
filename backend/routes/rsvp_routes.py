"""RSVP endpoints + the Server-Sent Events realtime stream."""
import json
import queue

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from ..auth import auth_required, auth_required_query
from ..config import Config
from ..realtime import KEEPALIVE_SECONDS, broker, sse_format
from ..services import rsvp_service
from ..utils.errors import Forbidden

bp = Blueprint("rsvp", __name__, url_prefix="/api")


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------
@bp.post("/events/<int:event_id>/rsvp")
@auth_required
def create_rsvp(event_id: int):
    data = request.get_json(silent=True) or {}
    result = rsvp_service.set_rsvp(event_id, g.user, data.get("status", "GOING"))
    status_code = 201
    result["message"] = (
        "Event is full - you have been added to the waitlist."
        if result["waitlisted"] else "Your RSVP has been recorded."
    )
    return jsonify(result), status_code


@bp.put("/events/<int:event_id>/rsvp")
@auth_required
def update_rsvp(event_id: int):
    data = request.get_json(silent=True) or {}
    result = rsvp_service.set_rsvp(event_id, g.user, data.get("status", "GOING"))
    result["message"] = (
        "Event is full - you have been added to the waitlist."
        if result["waitlisted"] else "Your RSVP has been updated."
    )
    return jsonify(result), 200


@bp.delete("/events/<int:event_id>/rsvp")
@auth_required
def delete_rsvp(event_id: int):
    result = rsvp_service.cancel_rsvp(event_id, g.user)
    result["message"] = "Your RSVP has been cancelled."
    return jsonify(result), 200


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------
@bp.get("/events/<int:event_id>/rsvps")
@auth_required
def event_rsvps(event_id: int):
    from ..services.event_service import get_event
    event = get_event(event_id)
    if g.user["role"] != "ADMIN" and event["organizer_id"] != g.user["user_id"]:
        raise Forbidden("Only the organizer can view the attendee list")
    return jsonify(
        rsvps=rsvp_service.get_event_rsvps(event_id),
        waitlist=rsvp_service.get_waitlist(event_id),
    ), 200


@bp.get("/events/<int:event_id>/counts")
@auth_required
def event_counts(event_id: int):
    return jsonify(counts=rsvp_service.get_event_counts(event_id)), 200


@bp.get("/rsvps/me")
@auth_required
def my_rsvps():
    return jsonify(rsvps=rsvp_service.get_my_rsvps(g.user["user_id"])), 200


# --------------------------------------------------------------------------
# Realtime: Server-Sent Events
# --------------------------------------------------------------------------
@bp.get("/events/<int:event_id>/stream")
@auth_required_query
def stream(event_id: int):
    """
    Long-lived SSE stream. Emits the current counts immediately, then every
    subsequent RSVP_UPDATED payload for this event.

    Production note: with more than one API worker, `broker` must be backed by
    Redis Pub/Sub (or replaced with Firestore/Supabase realtime listeners) so
    that a publish from worker A reaches subscribers on worker B.
    """
    channel = f"event:{event_id}"
    snapshot = rsvp_service.get_event_counts(event_id)

    def event_generator():
        subscriber = broker.subscribe(channel)
        try:
            yield sse_format(json.dumps(
                {"type": "SNAPSHOT", "counts": snapshot}, default=str
            ))
            while True:
                try:
                    message = subscriber.get(timeout=KEEPALIVE_SECONDS)
                    yield sse_format(message)
                except queue.Empty:
                    # Comment frame keeps proxies from closing an idle stream.
                    yield ": keep-alive\n\n"
        except GeneratorExit:
            return
        finally:
            broker.unsubscribe(channel, subscriber)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",   # disable Nginx buffering
    }
    return Response(stream_with_context(event_generator()), headers=headers)