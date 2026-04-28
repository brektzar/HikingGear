"""Checklist management module."""

from __future__ import annotations

from typing import Any

import streamlit as st

from core.auth import is_admin, list_usernames
from core.db import get_collection, utc_now
from .base import AppModule
from .checklist_item_types import seed_default_item_types


def _owner_filter(current_user: str, key: str) -> str:
    owners = ["all"] + list_usernames()
    default_index = owners.index(current_user) if current_user in owners else 0
    selected = st.selectbox(
        "Visa listor från",
        owners,
        index=default_index,
        format_func=lambda value: "Alla användare" if value == "all" else value,
        key=key,
    )
    return selected


def _normalize_type_name(value: str) -> str:
    return " ".join(value.strip().split())


def _sorted_item_types(item_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        item_types,
        key=lambda item: (
            not bool(item.get("essential", False)),
            str(item.get("name", "")).lower(),
        ),
    )


def render(current_user: str) -> None:
    """Render checklist CRUD interface."""
    collection = get_collection("checklists")
    item_types_collection = get_collection("checklist_item_types")
    trails_collection = get_collection("trails")
    seed_default_item_types(current_user)
    current_user_is_admin = is_admin(current_user)
    item_types = _sorted_item_types(
        list(item_types_collection.find({}, {"name": 1, "essential": 1}))
    )
    essential_item_types = [item_type for item_type in item_types if bool(item_type.get("essential", False))]
    if not item_types:
        st.info(
            "Inga utrustningskategorier finns än. Öppna 'Utrustningskategorier' för att lägga till kategorier."
        )

    user_trails = list(
        trails_collection.find(
            {"owner": current_user},
            {"name": 1, "location": 1, "status": 1},
        ).sort("name", 1)
    )
    trail_options = {
        f"{trail['name']} ({trail.get('location', 'Unknown')})": trail for trail in user_trails
    }

    with st.form("create_checklist", clear_on_submit=True):
        st.subheader("Skapa checklista")
        title = st.text_input("Titel", placeholder="Basutrustning inför vandring")
        st.markdown("**1) Välj obligatoriska kategorier till checklistan**")
        select_all_essentials = st.checkbox("Välj alla obligatoriska", key="select_all_essentials")
        essential_labels_to_type = {
            str(item_type.get("name", "Unnamed")): item_type for item_type in essential_item_types
        }
        selected_essential_labels = st.multiselect(
            "Obligatoriska artiklar",
            list(essential_labels_to_type.keys()),
            default=list(essential_labels_to_type.keys()) if select_all_essentials else [],
        )

        st.markdown("**2) Saknas kategori? Lägg till här**")
        new_type_name = st.text_input("Namn på ny kategori", placeholder="Kastrull")
        new_type_essential = st.checkbox("Ny kategori är obligatorisk", key="new_type_essential")

        selected_trail_labels = st.multiselect(
            "Koppla checklistan till dina leder",
            list(trail_options.keys()),
        )
        notes = st.text_area("Anteckningar (valfritt)")
        submitted = st.form_submit_button("Spara checklista")

    if submitted:
        if not title.strip():
            st.error("Ange en titel för checklistan.")
        else:
            selected_types = [
                essential_labels_to_type[label]
                for label in selected_essential_labels
                if label in essential_labels_to_type
            ]
            normalized_new_type_name = _normalize_type_name(new_type_name)
            if normalized_new_type_name:
                existing_type = item_types_collection.find_one(
                    {"name_normalized": normalized_new_type_name.lower()}
                )
                if existing_type:
                    selected_types.append(existing_type)
                else:
                    created_type = {
                        "name": normalized_new_type_name,
                        "name_normalized": normalized_new_type_name.lower(),
                        "essential": bool(new_type_essential),
                        "created_by": current_user,
                        "created_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                    inserted = item_types_collection.insert_one(created_type)
                    selected_types.append({**created_type, "_id": inserted.inserted_id})

            if not selected_types:
                st.error("Välj minst en kategori eller lägg till en ny.")
                return

            unique_types_by_name: dict[str, dict[str, Any]] = {}
            for item_type in selected_types:
                normalized_name = str(item_type.get("name", "")).strip().lower()
                if not normalized_name:
                    continue
                if normalized_name not in unique_types_by_name:
                    unique_types_by_name[normalized_name] = {
                        "type_id": str(item_type.get("_id", "")),
                        "name": str(item_type.get("name", "")).strip(),
                        "essential": bool(item_type.get("essential", False)),
                    }

            checklist_item_types = list(unique_types_by_name.values())
            checklist_items = [
                {"text": item_type["name"], "done": False} for item_type in checklist_item_types
            ]
            linked_trails = [
                {
                    "trail_id": str(trail_options[label].get("_id")),
                    "name": trail_options[label].get("name"),
                    "location": trail_options[label].get("location"),
                    "status": trail_options[label].get("status"),
                }
                for label in selected_trail_labels
            ]
            collection.insert_one(
                {
                    "owner": current_user,
                    "title": title.strip(),
                    "item_types": checklist_item_types,
                    "items": checklist_items,
                    "attached_gear": [],
                    "linked_trails": linked_trails,
                    "notes": notes.strip(),
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            st.success("Checklista sparad.")

    st.divider()
    st.subheader("Bläddra checklistor")
    selected_owner = _owner_filter(current_user, "owner_filter_checklists")
    query = {} if selected_owner == "all" else {"owner": selected_owner}
    docs = list(collection.find(query).sort("updated_at", -1))

    if not docs:
        st.info("Inga checklistor hittades för detta filter.")
        return

    for doc in docs:
        owner = doc["owner"]
        item_count = len(doc.get("items", []))
        done_count = len([item for item in doc.get("items", []) if item.get("done")])
        title = f"{doc.get('title', 'Utan titel')} ({owner})"
        with st.expander(title):
            if item_count > 0:
                st.progress(done_count / item_count)

            for index, item in enumerate(doc.get("items", [])):
                can_manage = owner == current_user or current_user_is_admin
                checked = st.checkbox(
                    item.get("text", ""),
                    value=bool(item.get("done", False)),
                    key=f"check_{doc['_id']}_{index}",
                    disabled=not can_manage,
                )
                if can_manage and checked != bool(item.get("done", False)):
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                f"items.{index}.done": checked,
                                "updated_at": utc_now(),
                            }
                        },
                    )
                    st.rerun()

            checklist_item_types = doc.get("item_types", [])
            if checklist_item_types:
                st.markdown("**Utrustningskategorier**")
                for item_type in checklist_item_types:
                    suffix = " (obligatorisk)" if item_type.get("essential") else ""
                    st.write(f"- {item_type.get('name', 'Unnamed')}{suffix}")

            linked_trails = doc.get("linked_trails", [])
            if linked_trails:
                st.markdown("**Kopplade leder**")
                for trail in linked_trails:
                    st.write(
                        f"- {trail.get('name', 'Unnamed')} "
                        f"({trail.get('location', 'Okänd plats')})"
                    )

            notes = doc.get("notes")
            if notes:
                st.caption(notes)

            if can_manage:
                edited_title = st.text_input(
                    "Redigera titel",
                    value=doc.get("title", ""),
                    key=f"edit_checklist_title_{doc['_id']}",
                )
                edited_notes = st.text_area(
                    "Redigera anteckningar",
                    value=doc.get("notes", ""),
                    key=f"edit_checklist_notes_{doc['_id']}",
                )
                if st.button("Spara ändringar", key=f"save_checklist_{doc['_id']}"):
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"title": edited_title.strip(), "notes": edited_notes.strip(), "updated_at": utc_now()}},
                    )
                    st.success("Checklista uppdaterad.")
                    st.rerun()

            if can_manage and st.button(
                "Radera checklista",
                key=f"delete_checklist_{doc['_id']}",
                type="primary",
            ):
                collection.delete_one({"_id": doc["_id"]})
                st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="checklists",
        name="Checklistor",
        description="Skapa och hantera checklistmallar för vandringar.",
        render=render,
    )
