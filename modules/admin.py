"""Admin controls for user and data management."""

from __future__ import annotations

import streamlit as st

from core.auth import is_admin
from core.db import get_collection, utc_now
from core.security import hash_password
from .base import AppModule


def _normalize_username(value: str) -> str:
    return value.strip().lower()


def render(current_user: str) -> None:
    """Render admin-only tools."""
    if not is_admin(current_user):
        st.error("Admin-behörighet krävs.")
        return

    users = get_collection("users")
    st.subheader("Admincenter")
    st.caption("Hantera användare och privilegierade dataåtgärder.")

    st.markdown("### Användarhantering")
    user_docs = list(users.find({}, {"username": 1, "is_admin": 1, "created_at": 1}).sort("username", 1))
    if not user_docs:
        st.info("Inga användare hittades.")
        return

    for user_doc in user_docs:
        username = user_doc.get("username", "")
        with st.expander(f"Användare: {username}"):
            new_username = st.text_input(
                "Användarnamn",
                value=username,
                key=f"admin_username_{user_doc['_id']}",
            )
            new_password = st.text_input(
                "Sätt nytt lösenord (lämna tomt för att behålla nuvarande)",
                type="password",
                key=f"admin_password_{user_doc['_id']}",
            )
            promote_admin = st.checkbox(
                "Administratörsanvändare",
                value=bool(user_doc.get("is_admin", False)),
                key=f"admin_flag_{user_doc['_id']}",
            )
            save_col, delete_col = st.columns(2)
            with save_col:
                if st.button("Spara användarändringar", key=f"admin_save_user_{user_doc['_id']}"):
                    normalized_username = _normalize_username(new_username)
                    if len(normalized_username) < 3:
                        st.error("Användarnamn måste vara minst 3 tecken.")
                    else:
                        duplicate = users.find_one(
                            {"username": normalized_username, "_id": {"$ne": user_doc["_id"]}},
                            {"_id": 1},
                        )
                        if duplicate:
                            st.error("Användarnamnet finns redan.")
                        else:
                            updates = {
                                "username": normalized_username,
                                "is_admin": bool(promote_admin),
                                "updated_at": utc_now(),
                            }
                            if new_password:
                                if len(new_password) < 8:
                                    st.error("Lösenord måste vara minst 8 tecken.")
                                    return
                                updates["password_hash"] = hash_password(new_password)
                            users.update_one({"_id": user_doc["_id"]}, {"$set": updates})
                            st.success("Användare uppdaterad.")
                            st.rerun()
            with delete_col:
                if st.button(
                    "Radera användare",
                    key=f"admin_delete_user_{user_doc['_id']}",
                    type="primary",
                    disabled=username == current_user,
                ):
                    users.delete_one({"_id": user_doc["_id"]})
                    st.warning("Användare raderad.")
                    st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="admin",
        name="Admin",
        description="Adminverktyg för användare och privilegierade funktioner.",
        render=render,
        requires_admin=True,
    )
