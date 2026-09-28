"""Input validation helpers."""
import datetime as dt
import re

from .errors import ValidationError

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

EVENT_STATUSES = {"DRAFT", "PUBLISHED", "FULL", "COMPLETED", "CANCELLED"}
RSVP_STATUSES = {"GOING", "MAYBE", "NOT_GOING"}
ROLES = {"ATTENDEE", "ORGANIZER", "ADMIN"}


def require_fields(data: dict, fields: list[str]) -> None:
    missing = [f for f in fields if data.get(f) in (None, "")]
    if missing:
        raise ValidationError(f"Missing required field(s): {', '.join(missing)}")


def clean_email(email: str) -> str:
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        raise ValidationError("Invalid email address")
    return email.strip().lower()


def clean_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    return password


def clean_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("Full name is required")
    return name.strip()[:120]


def clean_role(role: str | None) -> str:
    if role is None:
        return "ATTENDEE"
    role = str(role).upper()
    if role not in ROLES:
        raise ValidationError(f"Role must be one of {sorted(ROLES)}")
    return role


def clean_date(value: str) -> str:
    try:
        dt.date.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid date '{value}' (expected YYYY-MM-DD)")
    return str(value)


def clean_time(value: str) -> str:
    try:
        dt.time.fromisoformat(str(value))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid time '{value}' (expected HH:MM)")
    return str(value)


def clean_datetime_or_none(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        dt.datetime.fromisoformat(str(value).replace("Z", ""))
    except (ValueError, TypeError):
        raise ValidationError(f"Invalid datetime '{value}' (expected ISO-8601)")
    return str(value)


def clean_capacity(value) -> int:
    try:
        capacity = int(value)
    except (ValueError, TypeError):
        raise ValidationError("maximum_capacity must be an integer")
    if capacity < 1:
        raise ValidationError("maximum_capacity must be at least 1")
    if capacity > 1_000_000:
        raise ValidationError("maximum_capacity is unrealistically large")
    return capacity


def clean_event_status(value: str) -> str:
    value = str(value).upper()
    if value not in EVENT_STATUSES:
        raise ValidationError(f"Status must be one of {sorted(EVENT_STATUSES)}")
    return value


def clean_rsvp_status(value: str) -> str:
    value = str(value).upper()
    if value not in RSVP_STATUSES:
        raise ValidationError(f"RSVP status must be one of {sorted(RSVP_STATUSES)}")
    return value


def clean_text(value, field: str, max_len: int = 5000) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    return value.strip()[:max_len]