"""Module for viewing planned/completed hikes and cloning routes."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core.auth import is_admin, list_usernames
from core.activity_log import log_activity
from core.db import get_collection, utc_now
from .base import AppModule
from .planned_hikes import _geojson_trail_lengths_km, _render_geojson_map, _selected_trails_total_km

STATUS_LABELS = {
    "planned": "Planerad",
    "completed": "Genomförd",
}


def _clone_for_replan(source_hike: dict, current_user: str) -> dict:
    """Create a fresh planned-hike copy preserving only route data."""
    today = date.today().isoformat()
    return {
        "owner": current_user,
        "title": "",
        "location": "",
        "planned_start_date": today,
        "planned_end_date": today,
        "planned_date": today,
        "hammock_friendly": False,
        "notes": "",
        "participants": [current_user],
        "linked_checklist": None,
        "gear_assignments": [],
        "borrow_requests": [],
        "participant_checks": [],
        "status": "planned",
        "route_geojson": source_hike.get("route_geojson"),
        "route_geojson_name": source_hike.get("route_geojson_name", ""),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def _render_hike_entry(hike: dict, current_user: str, current_user_is_admin: bool, hikes_col) -> None:
    """Render one hike card with actions."""
    hike_status = str(hike.get("status", "planned"))
    title = str(hike.get("title", "")).strip() or "Utan titel"
    location = str(hike.get("location", "")).strip() or "Okänd plats"
    owner = str(hike.get("owner", "okänd"))
    header = f"{title} ({location}) | {STATUS_LABELS.get(hike_status, hike_status)} | {owner}"
    with st.expander(header):
        st.caption(f"Start: {hike.get('planned_start_date', '-')}, Slut: {hike.get('planned_end_date', '-')}")
        st.write("Deltagare: " + ", ".join(hike.get("participants", [])))
        route_geojson = hike.get("route_geojson")
        if route_geojson:
            per_trail_km = _geojson_trail_lengths_km(route_geojson)
            selected_main_titles = [
                str(route_title)
                for route_title in hike.get("main_route_titles", [])
                if str(route_title) in per_trail_km
            ]
            if selected_main_titles:
                selected_main_km = _selected_trails_total_km(per_trail_km, selected_main_titles)
                st.write(f"Längd: {selected_main_km:.2f} km")
            else:
                st.write("Längd: Okänt")
        else:
            st.write("Längd: Okänt")
        if hike.get("notes"):
            st.write(str(hike.get("notes", "")))

        status_options = ["planned", "completed"]
        status_col, clone_col = st.columns(2)
        with status_col:
            new_status = st.selectbox(
                "Status",
                status_options,
                index=status_options.index(hike_status) if hike_status in status_options else 0,
                format_func=lambda v: STATUS_LABELS[v],
                key=f"completed_hike_status_{hike['_id']}",
            )
            can_manage = current_user_is_admin or owner == current_user
            if can_manage and st.button("Spara status", key=f"completed_hike_save_status_{hike['_id']}"):
                hikes_col.update_one(
                    {"_id": hike["_id"]},
                    {"$set": {"status": new_status, "updated_at": utc_now()}},
                )
                log_activity(
                    current_user,
                    "update_hike_status",
                    module="completed_hikes",
                    target=title,
                    details={"status": new_status},
                )
                st.success("Status uppdaterad.")
                st.rerun()

        with clone_col:
            if st.button("Kopiera till planerade vandringar", key=f"clone_hike_{hike['_id']}"):
                cloned = _clone_for_replan(hike, current_user)
                hikes_col.insert_one(cloned)
                log_activity(
                    current_user,
                    "clone_hike_for_replan",
                    module="completed_hikes",
                    target=title,
                )
                st.success("Kopia skapad i planerade vandringar. Endast kartdata följde med.")
                st.rerun()

        with st.expander("Ledkarta", expanded=False):
            if route_geojson:
                _render_geojson_map(route_geojson, map_key=f"completed_hike_map_{hike['_id']}")
            else:
                st.caption("Ingen GeoJSON-karta kopplad.")


def render(current_user: str) -> None:
    """Render planned/completed hikes with admin/user controls."""
    hikes_col = get_collection("planned_hikes")
    current_user_is_admin = is_admin(current_user)

    owner_filter_options = ["all"] + list_usernames() if current_user_is_admin else [current_user]
    selected_owner = st.selectbox(
        "Visa vandringar för",
        owner_filter_options,
        format_func=lambda v: "Alla användare" if v == "all" else v,
    )

    query: dict[str, str] = {}
    if selected_owner != "all":
        query["owner"] = selected_owner

    hikes = list(hikes_col.find(query).sort("updated_at", -1))
    if not hikes:
        st.info("Inga vandringar hittades.")
        return

    completed_hikes = [hike for hike in hikes if str(hike.get("status", "planned")) == "completed"]
    planned_hikes = [hike for hike in hikes if str(hike.get("status", "planned")) != "completed"]

    completed_col, planned_col = st.columns(2)
    with completed_col:
        with st.expander("Genomförda vandringar", expanded=True):
            if not completed_hikes:
                st.caption("Inga genomförda vandringar.")
            else:
                for hike in completed_hikes:
                    _render_hike_entry(hike, current_user, current_user_is_admin, hikes_col)

    with planned_col:
        with st.expander("Planerade vandringar", expanded=False):
            if not planned_hikes:
                st.caption("Inga planerade vandringar.")
            else:
                for hike in planned_hikes:
                    _render_hike_entry(hike, current_user, current_user_is_admin, hikes_col)


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="completed_hikes",
        name="Genomförda vandringar",
        description="Visa planerade/genomförda vandringar och återanvänd leder.",
        render=render,
    )
