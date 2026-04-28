"""Authentication service backed by MongoDB users collection."""

from __future__ import annotations

from dataclasses import dataclass

from pymongo.errors import DuplicateKeyError

from .db import get_collection, utc_now
from .security import hash_password, verify_password


@dataclass(frozen=True)
class AuthResult:
    """Simple result object for auth actions."""

    ok: bool
    message: str


def register_user(username: str, password: str) -> AuthResult:
    """Register a user with hashed password."""
    username = username.strip().lower()
    if len(username) < 3:
        return AuthResult(False, "Användarnamn måste vara minst 3 tecken.")
    if len(password) < 8:
        return AuthResult(False, "Lösenord måste vara minst 8 tecken.")

    users = get_collection("users")
    doc = {
        "username": username,
        "password_hash": hash_password(password),
        "is_admin": False,
        "created_at": utc_now(),
    }
    try:
        users.insert_one(doc)
        return AuthResult(True, "Konto skapat.")
    except DuplicateKeyError:
        return AuthResult(False, "Användarnamnet finns redan.")


def authenticate_user(username: str, password: str) -> AuthResult:
    """Validate credentials against stored hash."""
    username = username.strip().lower()
    users = get_collection("users")
    doc = users.find_one({"username": username})
    if not doc:
        return AuthResult(False, "Fel användarnamn eller lösenord.")

    stored_hash = doc.get("password_hash", "")
    if not verify_password(password, stored_hash):
        return AuthResult(False, "Fel användarnamn eller lösenord.")
    return AuthResult(True, "Inloggning lyckades.")


def list_usernames() -> list[str]:
    """Return usernames sorted alphabetically."""
    users = get_collection("users")
    return [user["username"] for user in users.find({}, {"username": 1}).sort("username", 1)]


def is_admin(username: str) -> bool:
    """Return True if user has admin role."""
    users = get_collection("users")
    doc = users.find_one(
        {"username": username.strip().lower()},
        {"is_admin": 1, "role": 1},
    )
    if not doc:
        return False
    if bool(doc.get("is_admin", False)):
        return True
    return str(doc.get("role", "")).strip().lower() == "admin"


def is_registration_enabled() -> bool:
    """Return whether self-registration is enabled for the site."""
    settings = get_collection("app_settings")
    doc = settings.find_one({"_id": "auth"}, {"registration_enabled": 1})
    if doc is None:
        return True
    return bool(doc.get("registration_enabled", True))
