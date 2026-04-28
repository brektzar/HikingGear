"""Statistics module with personal and collaborative overview."""

from __future__ import annotations

import streamlit as st

from core.db import get_collection
from .base import AppModule


def render(current_user: str) -> None:
    """Render extended statistics for the logged-in user."""
    users_col = get_collection("users")
    checklists_col = get_collection("checklists")
    trails_col = get_collection("trails")
    gear_col = get_collection("gear_items")
    planned_hikes_col = get_collection("planned_hikes")

    my_checklists = checklists_col.count_documents({"owner": current_user})
    trails_done = trails_col.count_documents({"owner": current_user, "status": "done"})
    trails_want = trails_col.count_documents({"owner": current_user, "status": "want_to_do"})
    my_gear_items = gear_col.count_documents({"owner": current_user})
    planned_hikes_joined = planned_hikes_col.count_documents({"participants": current_user})
    planned_hikes_owned = planned_hikes_col.count_documents({"owner": current_user})

    all_hikes = list(
        planned_hikes_col.find(
            {"participants": current_user},
            {"gear_assignments": 1, "borrow_requests": 1, "participants": 1},
        )
    )
    total_assignments = 0
    borrowed_assignments = 0
    shared_assignments = 0
    pending_my_requests = 0
    total_participant_slots = 0
    for hike in all_hikes:
        participants = hike.get("participants", []) or []
        total_participant_slots += len(participants)
        for assignment in hike.get("gear_assignments", []) or []:
            total_assignments += 1
            assignment_type = str(assignment.get("assignment_type", "owned")).strip().lower()
            if assignment_type == "borrowed":
                borrowed_assignments += 1
            elif assignment_type == "shared":
                shared_assignments += 1
        for request in hike.get("borrow_requests", []) or []:
            if request.get("requester") == current_user and request.get("status") == "pending":
                pending_my_requests += 1

    avg_participants_per_hike = (
        round(total_participant_slots / planned_hikes_joined, 1) if planned_hikes_joined else 0.0
    )

    st.caption(f"Inloggad som: {current_user}")
    row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
    row1_col1.metric("Mina checklistor", my_checklists)
    row1_col2.metric("Klara leder", trails_done)
    row1_col3.metric("Planerade leder", trails_want)
    row1_col4.metric("Mina utrustningsartiklar", my_gear_items)

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
    row2_col1.metric("Vandringar jag deltar i", planned_hikes_joined)
    row2_col2.metric("Vandringar jag skapat", planned_hikes_owned)
    row2_col3.metric("Tilldelade utrustningsval", total_assignments)
    row2_col4.metric("Snitt deltagare/vandring", avg_participants_per_hike)

    row3_col1, row3_col2, row3_col3, row3_col4 = st.columns(4)
    row3_col1.metric("Lånade tilldelningar", borrowed_assignments)
    row3_col2.metric("Delade tilldelningar", shared_assignments)
    row3_col3.metric("Mina väntande förfrågningar", pending_my_requests)
    row3_col4.metric("Totala användare", users_col.count_documents({}))


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="stats",
        name="Statistik",
        description="Statistik för checklistor, utrustning, leder och vandringar.",
        render=render,
    )
