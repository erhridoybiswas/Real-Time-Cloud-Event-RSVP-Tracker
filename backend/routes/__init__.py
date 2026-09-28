"""HTTP route blueprints."""
from .analytics_routes import bp as analytics_bp
from .announcement_routes import bp as announcement_bp
from .auth_routes import bp as auth_bp
from .event_routes import bp as event_bp
from .notification_routes import bp as notification_bp
from .rsvp_routes import bp as rsvp_bp

ALL_BLUEPRINTS = [
    auth_bp, event_bp, rsvp_bp, announcement_bp, notification_bp, analytics_bp,
]