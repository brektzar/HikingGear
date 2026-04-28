"""Dashboard module with account-level overview."""

from __future__ import annotations

import streamlit as st

from core.db import get_collection
from .base import AppModule


def render(current_user: str) -> None:
    """Render high-level account stats."""
    checklists = get_collection("checklists").count_documents({"owner": current_user})
    trails_done = get_collection("trails").count_documents(
        {"owner": current_user, "status": "done"}
    )
    trails_want = get_collection("trails").count_documents(
        {"owner": current_user, "status": "want_to_do"}
    )
    gear_items = get_collection("gear_items").count_documents({"owner": current_user})
    planned_hikes_joined = get_collection("planned_hikes").count_documents(
        {"participants": current_user}
    )

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Mina checklistor", checklists)
    col2.metric("Klara leder", trails_done)
    col3.metric("Planerade leder", trails_want)
    col4.metric("Utrustningsartiklar", gear_items)
    col5.metric("Anslutna planerade vandringar", planned_hikes_joined)


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="dashboard",
        name="Översikt",
        description="Personlig vandringsöversikt och räknare.",
        render=render,
    )
