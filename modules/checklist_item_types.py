"""Checklist item type catalog management."""

from __future__ import annotations

import streamlit as st

from core.auth import is_admin
from core.activity_log import log_activity
from core.db import get_collection, utc_now
from .base import AppModule


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


DEFAULT_ITEM_TYPES = [
    "Sovsäck",
    "Liggunderlag",
    "Ryggsäck",
    "Matlagningsredskap",
    "Kokutrustning",
    "Tändare/tändstickor",
    "Vätskesystem (t.ex. vattenblåsa)",
    "Vattenfilter",
    "Pannlampa",
    "Första hjälpen-kit",
    "Kniv",
    "Kompass",
    "Karta",
    "Nödsignalvisselpipa",
    "Nödfilt",
    "Vandringsstavar",
    "Hygienartiklar",
    "Toalettkit",
    "Solskydd",
    "Insektsmedel",
    "Regnkläder",
    "Värmande lager",
    "Reparationskit",
    "Powerbank",
    "Nödsändare (PLB)",
]
REMOVED_DEFAULT_ITEM_TYPES = [
    "Skydd (tält/pressening)",
]


def seed_default_item_types(current_user: str) -> int:
    """Ensure default locked checklist item types exist."""
    collection = get_collection("checklist_item_types")
    inserted_count = 0
    for name in REMOVED_DEFAULT_ITEM_TYPES:
        normalized = _normalize(name)
        if not normalized:
            continue
        collection.delete_many(
            {
                "name_normalized": normalized.lower(),
                "system_default": True,
            }
        )
    for name in DEFAULT_ITEM_TYPES:
        normalized = _normalize(name)
        if not normalized:
            continue
        exists = collection.find_one({"name_normalized": normalized.lower()}, {"_id": 1})
        if exists:
            continue
        collection.insert_one(
            {
                "name": normalized,
                "name_normalized": normalized.lower(),
                "essential": True,
                "locked": True,
                "system_default": True,
                "created_by": current_user,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
        )
        inserted_count += 1
    return inserted_count


def render(current_user: str) -> None:
    """Create, edit, and delete global checklist item types."""
    collection = get_collection("checklist_item_types")
    inserted_count = seed_default_item_types(current_user)
    current_user_is_admin = is_admin(current_user)
    if inserted_count > 0:
        st.success(f"Lade till {inserted_count} standardkategorier för utrustning.")

    if not current_user_is_admin:
        st.info(
            "Standardtyper är låsta. Endast admins kan redigera eller ta bort låsta typer."
        )

    with st.form("create_item_type", clear_on_submit=True):
        st.subheader("Lägg till utrustningskategori")
        name = st.text_input("Namn på kategori", placeholder="Liggunderlag")
        essential = st.checkbox("Obligatorisk som standard")
        submitted = st.form_submit_button("Spara typ")

    if submitted:
        normalized_name = _normalize(name)
        if not normalized_name:
            st.error("Typnamn krävs.")
        else:
            existing = collection.find_one({"name_normalized": normalized_name.lower()})
            if existing:
                st.info("Den typen finns redan.")
            else:
                collection.insert_one(
                    {
                        "name": normalized_name,
                        "name_normalized": normalized_name.lower(),
                        "essential": bool(essential),
                        "locked": False,
                        "system_default": False,
                        "created_by": current_user,
                        "created_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
                log_activity(
                    current_user,
                    "create_item_type",
                    module="checklist_item_types",
                    target=normalized_name,
                    details={"essential": bool(essential)},
                )
                st.success("Kategori tillagd.")
                st.rerun()

    st.divider()
    st.subheader("Redigera utrustningskategorier")
    docs = list(collection.find({}).sort("name", 1))
    if not docs:
        st.info("Inga utrustningskategorier finns än.")
        return

    for doc in docs:
        title = f"{doc.get('name', 'Unnamed')}"
        with st.expander(title):
            locked = bool(doc.get("locked", False))
            new_name = st.text_input(
                "Namn",
                value=doc.get("name", ""),
                key=f"type_name_{doc['_id']}",
                disabled=locked and not current_user_is_admin,
            )
            new_essential = st.checkbox(
                "Obligatorisk som standard",
                value=bool(doc.get("essential", False)),
                key=f"type_essential_{doc['_id']}",
                disabled=locked and not current_user_is_admin,
            )
            if locked:
                st.caption("Låst standardkategori.")
            save_col, delete_col = st.columns(2)
            with save_col:
                if st.button("Spara ändringar", key=f"save_type_{doc['_id']}"):
                    if locked and not current_user_is_admin:
                        st.error("Endast admins kan redigera låsta standardtyper.")
                        continue
                    normalized_name = _normalize(new_name)
                    if not normalized_name:
                        st.error("Namn får inte vara tomt.")
                    else:
                        duplicate = collection.find_one(
                            {
                                "name_normalized": normalized_name.lower(),
                                "_id": {"$ne": doc["_id"]},
                            }
                        )
                        if duplicate:
                            st.error("En annan kategori använder redan det namnet.")
                        else:
                            collection.update_one(
                                {"_id": doc["_id"]},
                                {
                                    "$set": {
                                        "name": normalized_name,
                                        "name_normalized": normalized_name.lower(),
                                        "essential": bool(new_essential),
                                        "updated_at": utc_now(),
                                    }
                                },
                            )
                            log_activity(
                                current_user,
                                "update_item_type",
                                module="checklist_item_types",
                                target=normalized_name,
                                details={"essential": bool(new_essential)},
                            )
                            st.success("Kategori uppdaterad.")
                            st.rerun()
            with delete_col:
                if st.button("Radera", key=f"delete_type_{doc['_id']}", type="primary"):
                    if locked and not current_user_is_admin:
                        st.error("Endast admins kan radera låsta standardtyper.")
                        continue
                    collection.delete_one({"_id": doc["_id"]})
                    log_activity(
                        current_user,
                        "delete_item_type",
                        module="checklist_item_types",
                        target=str(doc.get("name", "")),
                    )
                    st.info("Kategori borttagen.")
                    st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="checklist_item_types",
        name="Utrustningskategorier",
        description="Hantera återanvändbara utrustningskategorier.",
        render=render,
    )
