"""Authentication endpoints: register, login, logout, me."""
from flask import Blueprint, current_app, g, jsonify, request

from ..auth import auth_required, create_token, hash_password, verify_password
from ..database import fetch_one, transaction
from ..utils.errors import Conflict, Unauthorized, ValidationError
from ..utils.validators import clean_email, clean_name, clean_password, clean_role

bp = Blueprint("auth", __name__, url_prefix="/api")


@bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = clean_email(data.get("email", ""))
    password = clean_password(data.get("password", ""))
    full_name = clean_name(data.get("full_name", ""))
    role = clean_role(data.get("role"))

    # Bootstrap: the very first admin must present the bootstrap key.
    bootstrap_key = request.headers.get("X-Bootstrap-Key")
    if role == "ADMIN":
        if not bootstrap_key or bootstrap_key != current_app.config["BOOTSTRAP_KEY"]:
            raise ValidationError("Admin registration requires a valid X-Bootstrap-Key")

    with transaction() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone()
        if exists:
            raise Conflict("An account with this email already exists")

        # If no admin exists yet and the bootstrap key matches, promote.
        if role == "ORGANIZER":
            pass  # organizers may self-register in this academic build
        admin_exists = conn.execute(
            "SELECT 1 FROM users WHERE role = 'ADMIN'"
        ).fetchone()
        if not admin_exists and bootstrap_key == current_app.config["BOOTSTRAP_KEY"]:
            role = "ADMIN"

        cursor = conn.execute(
            """INSERT INTO users (email, password_hash, full_name, role)
               VALUES (?,?,?,?)""",
            (email, hash_password(password), full_name, role),
        )
        user_id = cursor.lastrowid

    user = fetch_one(
        "SELECT user_id, email, full_name, role, created_at FROM users WHERE user_id = ?",
        (user_id,),
    )
    return jsonify(token=create_token(user), user=user), 201


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = clean_email(data.get("email", ""))
    password = data.get("password", "")

    user = fetch_one("SELECT * FROM users WHERE email = ?", (email,))
    if not user or not verify_password(user["password_hash"], password):
        # Deliberately identical error for unknown user and wrong password.
        raise Unauthorized("Invalid email or password")

    public_user = {
        "user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
    }
    return jsonify(token=create_token(public_user), user=public_user), 200


@bp.post("/logout")
@auth_required
def logout():
    with transaction() as conn:
        conn.execute(
            "INSERT INTO audit_logs (actor_id, action, detail) VALUES (?,?,?)",
            (g.user["user_id"], "LOGOUT", g.user["email"]),
        )
    return jsonify(message="Logged out. Discard the token on the client."), 200


@bp.get("/me")
@auth_required
def me():
    return jsonify(user=g.user), 200