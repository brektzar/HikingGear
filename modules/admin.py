"""Admin controls for user and data management."""

from __future__ import annotations

import base64

import streamlit as st

from core.auth import is_admin
from core.activity_log import log_activity
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
        log_activity(
            current_user,
            "update_site_settings",
            module="admin",
            target="app_settings.auth",
            details={"registration_enabled": bool(registration_toggle)},
        )
        st.success("Webbplatsinställningar uppdaterade.")
        st.rerun()

    from .registry import load_modules

    all_modules = load_modules()
    module_settings = settings.find_one(
        {"_id": "modules"},
        {"disabled_keys": 1, "admin_required_keys": 1, "module_order_keys": 1},
    ) or {}
    disabled_keys = {str(key) for key in module_settings.get("disabled_keys", [])}
    admin_required_keys = {str(key) for key in module_settings.get("admin_required_keys", [])}
    admin_required_keys.add("admin")
    default_order = [module.key for module in all_modules]
    valid_keys = set(default_order)
    saved_order = [key for key in module_settings.get("module_order_keys", []) if key in valid_keys]
    for key in default_order:
        if key not in saved_order:
            saved_order.append(key)
    order_state_key = "admin_module_order_keys"
    current_state = st.session_state.get(order_state_key)
    if not isinstance(current_state, list) or set(current_state) != valid_keys:
        st.session_state[order_state_key] = list(saved_order)
    ordered_module_keys = list(st.session_state[order_state_key])
    modules_by_key = {module.key: module for module in all_modules}
    module_enabled_by_key: dict[str, bool] = {}
    module_admin_required_by_key: dict[str, bool] = {}

    user_docs = list(users.find({}, {"username": 1, "is_admin": 1, "created_at": 1}).sort("username", 1))
    module_tab, welcome_tab, user_tab, inventory_tab, logs_tab = st.tabs(
        [
            "🧩 Modulhantering",
            "👋 Välkommen-modul",
            "👤 Användarhantering",
            "🎒 Inventarie",
            "🧾 Aktivitetslogg",
        ]
    )

    with module_tab:
        settings_col, order_col = st.columns([1, 1], gap="small")

        with settings_col:
            st.markdown("**Modulval**")
            st.caption("Ställ in om modul ska vara aktiv och om den ska kräva adminbehörighet.")
            for index, module_key in enumerate(ordered_module_keys):
                module = modules_by_key[module_key]
                is_admin_locked = module.key == "admin"
                is_admin_required = bool(module.requires_admin or module.key in admin_required_keys)
                row_col1, row_col2 = st.columns([2, 1], gap="small")
                with row_col1:
                    module_enabled_by_key[module.key] = st.checkbox(
                        f"{module.name}",
                        value=True if is_admin_locked else module.key not in disabled_keys,
                        key=f"toggle_module_{module.key}",
                        disabled=is_admin_locked,
                    )
                with row_col2:
                    module_admin_required_by_key[module.key] = st.checkbox(
                        "Kräv admin",
                        value=True if (module.requires_admin or is_admin_locked) else is_admin_required,
                        key=f"toggle_module_admin_req_{module.key}",
                        disabled=bool(module.requires_admin or is_admin_locked),
                    )
                if is_admin_locked:
                    st.caption("Admin-modulen är alltid aktiv och kan inte stängas av.")
                elif module.requires_admin:
                    st.caption(f"{module.name} kräver alltid adminbehörighet.")
                if index < len(ordered_module_keys) - 1:
                    st.divider()

        with order_col:
            st.markdown("**Modulordning**")
            st.caption("Flytta moduler upp eller ner för att bestämma visningsordning.")
            for index, module_key in enumerate(ordered_module_keys):
                module = modules_by_key[module_key]
                move_col, up_col, down_col = st.columns([3, 1, 1], gap="small")
                move_col.write(f"{index + 1}. {module.name}")
                with up_col:
                    if st.button("Upp", key=f"module_order_up_{module_key}", disabled=index == 0):
                        ordered_module_keys[index - 1], ordered_module_keys[index] = (
                            ordered_module_keys[index],
                            ordered_module_keys[index - 1],
                        )
                        st.session_state[order_state_key] = ordered_module_keys
                        st.rerun()
                if index < len(ordered_module_keys) - 1:
                    st.divider()
                with down_col:
                    if st.button(
                        "Ner",
                        key=f"module_order_down_{module_key}",
                        disabled=index == len(ordered_module_keys) - 1,
                    ):
                        ordered_module_keys[index + 1], ordered_module_keys[index] = (
                            ordered_module_keys[index],
                            ordered_module_keys[index + 1],
                        )
                        st.session_state[order_state_key] = ordered_module_keys
                        st.rerun()
            if st.button("Återställ standardordning", key="reset_module_order"):
                st.session_state[order_state_key] = list(default_order)
                st.rerun()

        if st.button("Spara modulinställningar", key="admin_save_module_settings"):
            new_disabled = [
                module.key
                for module in all_modules
                if module.key != "admin" and not bool(module_enabled_by_key.get(module.key, True))
            ]
            new_admin_required = [
                module.key
                for module in all_modules
                if module.key == "admin"
                or module.requires_admin
                or bool(module_admin_required_by_key.get(module.key, False))
            ]
            settings.update_one(
                {"_id": "modules"},
                {
                    "$set": {
                        "disabled_keys": new_disabled,
                        "admin_required_keys": sorted(set(new_admin_required)),
                        "module_order_keys": list(st.session_state.get(order_state_key, default_order)),
                        "updated_by": current_user,
                        "updated_at": utc_now(),
                    }
                },
                upsert=True,
            )
            log_activity(
                current_user,
                "update_module_settings",
                module="admin",
                target="app_settings.modules",
                details={
                    "disabled_count": len(new_disabled),
                    "admin_required_count": len(set(new_admin_required)),
                },
            )
            st.success("Modulinställningar uppdaterade.")
            st.rerun()

    with welcome_tab:
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
            remove_image = st.checkbox("Ta bort befintlig bild", value=False)
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
            log_activity(
                current_user,
                "update_welcome_content",
                module="admin",
                target="app_settings.welcome_content",
                details={"removed_image": bool(remove_image), "uploaded_image": uploaded_image is not None},
            )
            st.success("Välkommen-modulen uppdaterad.")
            st.rerun()

    with user_tab:
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
                log_activity(
                    current_user,
                    "create_user",
                    module="admin",
                    target=normalized_username,
                    details={"is_admin": bool(create_is_admin)},
                )
                st.success("Användare skapad.")
                st.rerun()

        if not user_docs:
            st.info("Inga användare hittades.")
        else:
            st.markdown("### Systemöversikt")
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            metrics_col1.metric("Användare", users.count_documents({}))
            metrics_col2.metric("Admins", users.count_documents({"is_admin": True}))
            metrics_col3.metric("Registrering", "På" if registration_enabled else "Av")

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
                                    log_activity(
                                        current_user,
                                        "update_user",
                                        module="admin",
                                        target=normalized_username,
                                        details={"is_admin": bool(promote_admin), "password_changed": bool(new_password)},
                                    )
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
                            log_activity(
                                current_user,
                                "delete_user",
                                module="admin",
                                target=username,
                            )
                            st.warning("Användare raderad.")
                            st.rerun()

    with inventory_tab:
        st.caption("Visa och redigera användares utrustning direkt från adminpanelen.")
        gear_items = get_collection("gear_items")
        checklist_type_collection = get_collection("checklist_item_types")
        type_docs = list(checklist_type_collection.find({}, {"name": 1}).sort("name", 1))
        categories = [
            str(doc.get("name", "")).strip()
            for doc in type_docs
            if str(doc.get("name", "")).strip()
        ]
        if not categories:
            categories = ["Övrigt"]

        owner_options = ["all"] + sorted(
            [str(user_doc.get("username", "")).strip() for user_doc in user_docs if user_doc.get("username")]
        )
        selected_owner = st.selectbox(
            "Visa inventarie för",
            owner_options,
            format_func=lambda value: "Alla användare" if value == "all" else value,
            key="admin_inventory_owner_filter",
        )
        selected_category = st.selectbox(
            "Filtrera kategori",
            ["all"] + categories,
            format_func=lambda value: "Alla kategorier" if value == "all" else value,
            key="admin_inventory_category_filter",
        )

        query: dict[str, str] = {}
        if selected_owner != "all":
            query["owner"] = selected_owner
        if selected_category != "all":
            query["category"] = selected_category

        inventory_docs = list(gear_items.find(query).sort("updated_at", -1))
        if not inventory_docs:
            st.info("Ingen inventarie hittades för valt filter.")
        else:
            for item_doc in inventory_docs:
                title = (
                    f"{item_doc.get('name', 'Utan namn')} "
                    f"({item_doc.get('owner', 'okänd användare')})"
                )
                with st.expander(title):
                    st.caption(f"Item-ID: {item_doc.get('item_id', 'saknas')}")
                    edit_name = st.text_input(
                        "Namn",
                        value=str(item_doc.get("name", "")),
                        key=f"admin_inv_name_{item_doc['_id']}",
                    )
                    edit_category = st.selectbox(
                        "Kategori",
                        categories,
                        index=categories.index(item_doc.get("category"))
                        if item_doc.get("category") in categories
                        else 0,
                        key=f"admin_inv_category_{item_doc['_id']}",
                    )
                    col_weight, col_qty = st.columns(2)
                    with col_weight:
                        edit_weight = st.number_input(
                            "Vikt (gram)",
                            min_value=0,
                            step=50,
                            value=int(item_doc.get("weight_g", 0)),
                            key=f"admin_inv_weight_{item_doc['_id']}",
                        )
                    with col_qty:
                        edit_qty = st.number_input(
                            "Antal",
                            min_value=1,
                            step=1,
                            value=int(item_doc.get("quantity", 1)),
                            key=f"admin_inv_qty_{item_doc['_id']}",
                        )

                    edit_essential = st.checkbox(
                        "Obligatorisk",
                        value=bool(item_doc.get("essential", False)),
                        key=f"admin_inv_essential_{item_doc['_id']}",
                    )
                    edit_private = st.checkbox(
                        "Endast privat bruk",
                        value=bool(item_doc.get("private_use_only", False)),
                        key=f"admin_inv_private_{item_doc['_id']}",
                    )
                    edit_notes = st.text_area(
                        "Anteckningar",
                        value=str(item_doc.get("notes", "")),
                        key=f"admin_inv_notes_{item_doc['_id']}",
                    )

                    save_col, delete_col = st.columns(2)
                    with save_col:
                        if st.button("Spara inventarieändringar", key=f"admin_inv_save_{item_doc['_id']}"):
                            if not edit_name.strip():
                                st.error("Namn får inte vara tomt.")
                            else:
                                updates = {
                                    "name": edit_name.strip(),
                                    "name_normalized": edit_name.strip().lower(),
                                    "category": edit_category,
                                    "weight_g": int(edit_weight),
                                    "quantity": int(edit_qty),
                                    "essential": bool(edit_essential),
                                    "private_use_only": bool(edit_private),
                                    "notes": edit_notes.strip(),
                                    "updated_at": utc_now(),
                                }
                                gear_items.update_one({"_id": item_doc["_id"]}, {"$set": updates})
                                log_activity(
                                    current_user,
                                    "update_inventory_item",
                                    module="admin",
                                    target=str(item_doc.get("item_id", "")),
                                    details={"owner": str(item_doc.get("owner", ""))},
                                )
                                st.success("Inventariepost uppdaterad.")
                                st.rerun()
                    with delete_col:
                        if st.button(
                            "Radera inventariepost",
                            key=f"admin_inv_delete_{item_doc['_id']}",
                            type="primary",
                        ):
                            gear_items.delete_one({"_id": item_doc["_id"]})
                            log_activity(
                                current_user,
                                "delete_inventory_item",
                                module="admin",
                                target=str(item_doc.get("item_id", "")),
                                details={"owner": str(item_doc.get("owner", ""))},
                            )
                            st.warning("Inventariepost raderad.")
                            st.rerun()

    with logs_tab:
        st.caption("Visar användaraktiviteter med tid och datum.")
        activity_logs = get_collection("activity_logs")
        log_settings_doc = settings.find_one({"_id": "activity_log_settings"}, {"max_logs_per_user": 1}) or {}
        configured_max_logs = int(log_settings_doc.get("max_logs_per_user", 150))
        configured_max_logs = max(50, min(2000, configured_max_logs))
        log_limit_value = st.number_input(
            "Max loggar per användare (ringbuffer)",
            min_value=50,
            max_value=2000,
            value=configured_max_logs,
            step=10,
            key="admin_log_limit_per_user",
        )
        if st.button("Spara logggräns", key="admin_save_log_limit"):
            settings.update_one(
                {"_id": "activity_log_settings"},
                {
                    "$set": {
                        "max_logs_per_user": int(log_limit_value),
                        "updated_by": current_user,
                        "updated_at": utc_now(),
                    }
                },
                upsert=True,
            )
            log_activity(
                current_user,
                "update_activity_log_limit",
                module="admin",
                target="app_settings.activity_log_settings",
                details={"max_logs_per_user": int(log_limit_value)},
            )
            st.success("Logggräns uppdaterad.")
            st.rerun()

        actor_options = ["alla"] + sorted(
            {str(doc.get("username", "")).strip() for doc in user_docs if str(doc.get("username", "")).strip()}
        )
        selected_actor = st.selectbox("Filtrera användare", actor_options, key="admin_logs_actor_filter")
        action_options = ["alla"] + sorted(
            {
                str(doc.get("action", "")).strip()
                for doc in activity_logs.find({}, {"action": 1})
                if str(doc.get("action", "")).strip()
            }
        )
        selected_action = st.selectbox("Filtrera funktion", action_options, key="admin_logs_action_filter")
        max_rows = st.slider("Antal rader", min_value=20, max_value=500, value=100, step=20)

        log_query: dict[str, str] = {}
        if selected_actor != "alla":
            log_query["actor"] = selected_actor
        if selected_action != "alla":
            log_query["action"] = selected_action

        log_docs = list(activity_logs.find(log_query).sort("event_at", -1).limit(max_rows))
        if not log_docs:
            st.info("Inga logghändelser hittades.")
        else:
            for event in log_docs:
                timestamp = event.get("event_at") or event.get("created_at")
                if hasattr(timestamp, "strftime"):
                    timestamp_text = timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                else:
                    timestamp_text = str(timestamp or "-")
                actor = str(event.get("actor", "okänd"))
                action = str(event.get("action", "okänd händelse"))
                module_name = str(event.get("module", "")).strip()
                target = str(event.get("target", "")).strip()
                details = event.get("details") or {}
                headline = f"{timestamp_text} | {actor} | {action}"
                with st.expander(headline):
                    if module_name:
                        st.write(f"**Modul:** {module_name}")
                    if target:
                        st.write(f"**Mål:** {target}")
                    st.write(f"**Loggslot:** {event.get('slot', '-')}")
                    if details:
                        st.json(details)

def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="admin",
        name="Admin",
        description="Adminverktyg för användare och privilegierade funktioner.",
        render=render,
        requires_admin=True,
    )
