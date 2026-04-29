"""MongoDB connection and collection helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import PyMongoError


def utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def _require_secret(key: str) -> str:
    """Fetch a required top-level secret or raise a user-friendly error."""
    try:
        value = st.secrets.get(key)
    except StreamlitSecretNotFoundError as exc:
        raise RuntimeError(
            "Missing `.streamlit/secrets.toml`. Copy `.streamlit/secrets.toml.example` "
            "to `.streamlit/secrets.toml` and fill in MONGO_URI + MONGO_DB_NAME."
        ) from exc
    if not value:
        raise RuntimeError(f"Missing Streamlit secret: '{key}'.")
    text = str(value).strip()
    if key == "MONGO_URI" and ("<db_user>" in text or "<db_password>" in text):
        raise RuntimeError(
            "MONGO_URI still has placeholders. Replace <db_user> and <db_password> "
            "in `.streamlit/secrets.toml` with real Atlas credentials."
        )
    return text


def _build_mongo_uri() -> str:
    """Build URI from split secrets when provided, otherwise use MONGO_URI."""
    host = str(st.secrets.get("MONGO_HOST", "")).strip()
    user = str(st.secrets.get("MONGO_USER", "")).strip()
    password = str(st.secrets.get("MONGO_PASSWORD", "")).strip()
    options = str(st.secrets.get("MONGO_OPTIONS", "retryWrites=true&w=majority")).strip()

    if host and user and password:
        encoded_user = quote_plus(user)
        encoded_password = quote_plus(password)
        return f"mongodb+srv://{encoded_user}:{encoded_password}@{host}/?{options}"

    return _require_secret("MONGO_URI")


@st.cache_resource(show_spinner=False)
def get_client() -> MongoClient:
    """Return cached MongoDB client."""
    mongo_uri = _build_mongo_uri()
    return MongoClient(mongo_uri, serverSelectionTimeoutMS=4000)


@st.cache_resource(show_spinner=False)
def get_database() -> Database:
    """Return app database from configured secret."""
    db_name = _require_secret("MONGO_DB_NAME")
    return get_client()[db_name]


def get_collection(name: str) -> Collection:
    """Get a database collection by name."""
    return get_database()[name]


def ensure_indexes() -> None:
    """Create required indexes for the application."""
    users = get_collection("users")
    users.create_index([("username", ASCENDING)], unique=True)

    for collection_name in (
        "checklists",
        "trails",
        "gear_items",
        "planned_hikes",
        "checklist_item_types",
    ):
        collection = get_collection(collection_name)
        collection.create_index([("owner", ASCENDING)])
        collection.create_index([("created_at", ASCENDING)])
    planned_hikes = get_collection("planned_hikes")
    planned_hikes.create_index([("participants", ASCENDING)])
    gear_items = get_collection("gear_items")
    gear_items.create_index([("item_id", ASCENDING)])
    gear_items.create_index([("owner", ASCENDING), ("item_id", ASCENDING)], unique=True)
    checklist_item_types = get_collection("checklist_item_types")
    checklist_item_types.create_index([("name_normalized", ASCENDING)], unique=True)
    activity_logs = get_collection("activity_logs")
    activity_logs.create_index([("actor", ASCENDING), ("event_at", ASCENDING)])
    activity_logs.create_index([("action", ASCENDING), ("event_at", ASCENDING)])
    bug_reports = get_collection("bug_reports")
    bug_reports.create_index([("reporter", ASCENDING), ("updated_at", ASCENDING)])
    bug_reports.create_index([("status", ASCENDING), ("updated_at", ASCENDING)])
    bug_reports.create_index([("bug_id", ASCENDING)], unique=True)
    planned_hikes.create_index([("status", ASCENDING), ("updated_at", ASCENDING)])


def ping_database() -> tuple[bool, str]:
    """Check if DB connection is healthy."""
    try:
        get_client().admin.command("ping")
        return True, "Connected to MongoDB."
    except (RuntimeError, PyMongoError) as exc:
        return False, f"Database connection failed: {exc}"
