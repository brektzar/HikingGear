"""Admin controls for user and data management."""

from __future__ import annotations

import base64

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
    settings = get_collection("app_settings")
    registration_doc = settings.find_one({"_id": "auth"}, {"registration_enabled": 1})
    registration_enabled = True if registration_doc is None else bool(
        registration_doc.get("registration_enabled", True)
    )
    st.subheader("Admincenter")
    st.caption("Hantera användare och privilegierade dataåtgärder.")

    st.markdown("### Webbplatsinställningar")
    registration_toggle = st.checkbox(
        "Tillåt nya användarregistreringar",
        value=registration_enabled,
        key="admin_registration_toggle",
    )
    if st.button("Spara webbplatsinställningar", key="admin_save_site_settings"):
        settings.update_one(
            {"_id": "auth"},
            {
                "$set": {
                    "registration_enabled": bool(registration_toggle),
                    "updated_by": current_user,
                    "updated_at": utc_now(),
                }
            },
            upsert=True,
        )
        st.success("Webbplatsinställningar uppdaterade.")
        st.rerun()

    st.markdown("### Modulhantering")
    from .registry import load_modules

    all_modules = load_modules()
    module_settings = settings.find_one({"_id": "modules"}, {"disabled_keys": 1}) or {}
    disabled_keys = {str(key) for key in module_settings.get("disabled_keys", [])}
    module_enabled_by_key: dict[str, bool] = {}
    for module in all_modules:
        is_admin_module = module.key == "admin"
        module_enabled_by_key[module.key] = st.checkbox(
            f"{module.name}",
            value=True if is_admin_module else module.key not in disabled_keys,
            key=f"toggle_module_{module.key}",
            disabled=is_admin_module,
        )
        if is_admin_module:
            st.caption("Admin-modulen är alltid aktiv och kan inte stängas av.")
    st.caption(
        "Avstängda moduler visas med meddelande för användaren istället för att orsaka fel."
    )
    if st.button("Spara modulinställningar", key="admin_save_module_settings"):
        new_disabled = [
            module.key
            for module in all_modules
            if module.key != "admin" and not bool(module_enabled_by_key.get(module.key, True))
        ]
        settings.update_one(
            {"_id": "modules"},
            {
                "$set": {
                    "disabled_keys": new_disabled,
                    "updated_by": current_user,
                    "updated_at": utc_now(),
                }
            },
            upsert=True,
        )
        st.success("Modulinställningar uppdaterade.")
        st.rerun()

    st.markdown("### Välkommen-modul")
    welcome_doc = settings.find_one(
        {"_id": "welcome_content"},
        {"title": 1, "body": 1, "image_b64": 1, "image_mime": 1},
    ) or {}
    with st.form("admin_welcome_content"):
        welcome_title = st.text_input(
            "Titel",
            value=str(welcome_doc.get("title", "Välkommen")),
        )
        welcome_body = st.text_area(
            "Brödtext",
            value=str(welcome_doc.get("body", "Detta är din arbetsyta för vandringsplanering.")),
            height=120,
        )
        uploaded_image = st.file_uploader(
            "Ladda upp bild (valfritt)",
            type=["png", "jpg", "jpeg", "webp"],
        )
        remove_image = st.checkbox(
            "Ta bort befintlig bild",
            value=False,
        )
        save_welcome = st.form_submit_button("Spara välkommen-innehåll")

    if save_welcome:
        updates = {
            "title": welcome_title.strip() or "Välkommen",
            "body": welcome_body.strip() or "Detta är din arbetsyta för vandringsplanering.",
            "updated_by": current_user,
            "updated_at": utc_now(),
        }
        if remove_image:
            updates["image_b64"] = ""
            updates["image_mime"] = ""
        elif uploaded_image is not None:
            image_bytes = uploaded_image.read()
            if not image_bytes:
                st.error("Uppladdad bild verkar vara tom.")
            else:
                updates["image_b64"] = base64.b64encode(image_bytes).decode("ascii")
                updates["image_mime"] = str(uploaded_image.type or "")
        settings.update_one(
            {"_id": "welcome_content"},
            {"$set": updates},
            upsert=True,
        )
        st.success("Välkommen-modulen uppdaterad.")
        st.rerun()

    st.markdown("### Användarhantering")
    with st.form("admin_create_user", clear_on_submit=True):
        st.markdown("**Skapa ny användare**")
        create_username = st.text_input("Nytt användarnamn")
        create_password = st.text_input("Nytt lösenord", type="password")
        create_is_admin = st.checkbox("Skapa som administratör")
        create_submit = st.form_submit_button("Skapa användare")

    if create_submit:
        normalized_username = _normalize_username(create_username)
        if len(normalized_username) < 3:
            st.error("Användarnamn måste vara minst 3 tecken.")
        elif len(create_password) < 8:
            st.error("Lösenord måste vara minst 8 tecken.")
        elif users.find_one({"username": normalized_username}, {"_id": 1}):
            st.error("Användarnamnet finns redan.")
        else:
            users.insert_one(
                {
                    "username": normalized_username,
                    "password_hash": hash_password(create_password),
                    "is_admin": bool(create_is_admin),
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            st.success("Användare skapad.")
            st.rerun()

    user_docs = list(users.find({}, {"username": 1, "is_admin": 1, "created_at": 1}).sort("username", 1))
    if not user_docs:
        st.info("Inga användare hittades.")
        return

    st.markdown("### Systemöversikt")
    metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
    metrics_col1.metric("Användare", users.count_documents({}))
    metrics_col2.metric("Admins", users.count_documents({"is_admin": True}))
    metrics_col3.metric(
        "Registrering",
        "På" if registration_enabled else "Av",
    )

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
