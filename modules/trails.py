"""Trail tracking module."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core.auth import is_admin, list_usernames
from core.activity_log import log_activity
from core.db import get_collection, utc_now
from .base import AppModule

STATUS_OPTIONS = {
    "want_to_do": "Vill göra",
    "done": "Klar",
}


def render(current_user: str) -> None:
    """Render trails planner and history list."""
    collection = get_collection("trails")
    current_user_is_admin = is_admin(current_user)

    with st.form("add_trail", clear_on_submit=True):
        st.subheader("Lägg till led")
        name = st.text_input("Namn på led", placeholder="Kungsleden etapp")
        location = st.text_input("Plats")
        distance_km = st.number_input("Distans (km)", min_value=0.0, step=0.5)
        status = st.selectbox("Status", list(STATUS_OPTIONS.keys()), format_func=STATUS_OPTIONS.get)
        hike_date = st.date_input("Datum", value=date.today())
        notes = st.text_area("Anteckningar")
        submitted = st.form_submit_button("Spara led")

    if submitted:
        if not name.strip() or not location.strip():
            st.error("Lednamn och plats är obligatoriska.")
        else:
            collection.insert_one(
                {
                    "owner": current_user,
                    "name": name.strip(),
                    "location": location.strip(),
                    "distance_km": float(distance_km),
                    "status": status,
                    "hike_date": hike_date.isoformat(),
                    "notes": notes.strip(),
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            log_activity(
                current_user,
                "create_trail",
                module="trails",
                target=name.strip(),
                details={"location": location.strip(), "status": status},
            )
            st.success("Led sparad.")

    st.divider()
    st.subheader("Ledbibliotek")
    owners = ["all"] + list_usernames()
    selected_owner = st.selectbox(
        "Visa leder från",
        owners,
        format_func=lambda value: "Alla användare" if value == "all" else value,
        key="owner_filter_trails",
    )
    selected_status = st.selectbox(
        "Filtrera på status",
        ["all"] + list(STATUS_OPTIONS.keys()),
        format_func=lambda value: "Alla statusar" if value == "all" else STATUS_OPTIONS[value],
    )

    query: dict[str, str] = {}
    if selected_owner != "all":
        query["owner"] = selected_owner
    if selected_status != "all":
        query["status"] = selected_status

    docs = list(collection.find(query).sort("hike_date", -1))
    if not docs:
        st.info("Inga leder hittades för detta filter.")
        return

    for doc in docs:
        title = f"{doc['name']} ({doc['owner']})"
        subtitle = f"{doc.get('location', '')} - {doc.get('distance_km', 0)} km - {STATUS_OPTIONS.get(doc.get('status'), '')}"
        with st.expander(title):
            st.write(subtitle)
            st.caption(f"Datum: {doc.get('hike_date', 'N/A')}")
            if doc.get("notes"):
                st.write(doc["notes"])

            can_manage = doc["owner"] == current_user or current_user_is_admin
            if can_manage:
                edit_name = st.text_input(
                    "Redigera lednamn",
                    value=doc.get("name", ""),
                    key=f"edit_trail_name_{doc['_id']}",
                )
                edit_location = st.text_input(
                    "Redigera plats",
                    value=doc.get("location", ""),
                    key=f"edit_trail_location_{doc['_id']}",
                )
                edit_distance = st.number_input(
                    "Redigera distans (km)",
                    min_value=0.0,
                    step=0.5,
                    value=float(doc.get("distance_km", 0.0)),
                    key=f"edit_trail_distance_{doc['_id']}",
                )
                edit_status = st.selectbox(
                    "Redigera status",
                    list(STATUS_OPTIONS.keys()),
                    index=0
                    if doc.get("status") not in STATUS_OPTIONS
                    else list(STATUS_OPTIONS.keys()).index(doc.get("status")),
                    format_func=STATUS_OPTIONS.get,
                    key=f"edit_trail_status_{doc['_id']}",
                )
                if st.button("Spara ändringar", key=f"save_trail_{doc['_id']}"):
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "name": edit_name.strip(),
                                "location": edit_location.strip(),
                                "distance_km": float(edit_distance),
                                "status": edit_status,
                                "updated_at": utc_now(),
                            }
                        },
                    )
                    log_activity(
                        current_user,
                        "update_trail",
                        module="trails",
                        target=edit_name.strip() or str(doc.get("name", "")),
                    )
                    st.success("Led uppdaterad.")
                    st.rerun()

            if can_manage and st.button(
                "Radera led",
                key=f"delete_trail_{doc['_id']}",
                type="primary",
            ):
                collection.delete_one({"_id": doc["_id"]})
                log_activity(
                    current_user,
                    "delete_trail",
                    module="trails",
                    target=str(doc.get("name", "")),
                )
                st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="trails",
        name="Leder",
        description="Spara avklarade leder och leder du vill vandra.",
        render=render,
    )
