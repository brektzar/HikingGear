"""Bug reporting and conversation module."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from core.activity_log import log_activity
from core.auth import is_admin
from core.db import get_collection, utc_now
from .base import AppModule

BUG_STATUS = {
    "new": "Ny",
    "read": "Läst",
    "in_progress": "Påbörjad",
    "resolved": "Avklarad",
    "cancelled": "Avbruten",
}


def _normalize_text(value: str) -> str:
    return " ".join(str(value).strip().split())


def _create_bug(current_user: str, title: str, description: str, affected_module: str) -> None:
    bugs = get_collection("bug_reports")
    now = utc_now()
    bug_id = f"bug-{uuid4().hex[:8]}"
    bugs.insert_one(
        {
            "bug_id": bug_id,
            "reporter": current_user,
            "title": _normalize_text(title),
            "description": str(description).strip(),
            "affected_module": _normalize_text(affected_module),
            "status": "new",
            "messages": [
                {
                    "message_id": f"msg-{uuid4().hex[:10]}",
                    "author": current_user,
                    "text": str(description).strip(),
                    "is_admin": bool(is_admin(current_user)),
                    "created_at": now,
                }
            ],
            "created_at": now,
            "updated_at": now,
            "last_actor": current_user,
        }
    )
    log_activity(
        current_user,
        "create_bug_report",
        module="bug_tracker",
        target=bug_id,
        details={"title": _normalize_text(title)},
    )


def render(current_user: str) -> None:
    """Render bug reporting and follow-up UI."""
    bugs = get_collection("bug_reports")
    current_user_is_admin = is_admin(current_user)
    from .registry import load_modules

    available_modules = load_modules()
    module_options = [
        module.name
        for module in available_modules
        if current_user_is_admin or module.key != "admin"
    ]
    if "Övrigt" not in module_options:
        module_options.append("Övrigt")

    if current_user_is_admin:
        report_tab, my_bugs_tab, admin_tab = st.tabs(["Rapportera", "Mina buggrapporter", "Adminhantering"])
    else:
        report_tab, my_bugs_tab = st.tabs(["Rapportera", "Mina buggrapporter"])

    with report_tab:
        with st.form("create_bug_report", clear_on_submit=True):
            st.subheader("Rapportera buggar")
            title = st.text_input("Kort rubrik", placeholder="Ex: Fel vid spara checklista")
            affected_module = st.selectbox("Berörd modul", module_options, index=0)
            description = st.text_area("Beskriv buggen", height=140)
            submitted = st.form_submit_button("Skicka buggrapport")

        if submitted:
            normalized_title = _normalize_text(title)
            normalized_description = str(description).strip()
            if len(normalized_title) < 4:
                st.error("Rubriken behöver vara minst 4 tecken.")
            elif len(normalized_description) < 8:
                st.error("Beskrivningen behöver vara minst 8 tecken.")
            else:
                _create_bug(current_user, normalized_title, normalized_description, affected_module)
                st.success("Buggrapport skickad.")
                st.rerun()

    with my_bugs_tab:
        st.subheader("Mina buggrapporter")
        status_filter = st.selectbox(
            "Filtrera status",
            ["all"] + list(BUG_STATUS.keys()),
            format_func=lambda value: "Alla statusar" if value == "all" else BUG_STATUS[value],
            key="bug_tracker_status_filter",
        )
        query: dict[str, str] = {} if current_user_is_admin else {"reporter": current_user}
        if status_filter != "all":
            query["status"] = status_filter

        docs = list(bugs.find(query).sort("updated_at", -1))
        if not docs:
            st.info("Inga buggrapporter hittades.")
        else:
            for bug in docs:
                reporter = str(bug.get("reporter", "okänd"))
                title_text = str(bug.get("title", "Utan titel"))
                status_key = str(bug.get("status", "new"))
                headline = f"{title_text} | {BUG_STATUS.get(status_key, status_key)} | {reporter}"
                with st.expander(headline):
                    st.caption(f"Bug-ID: {bug.get('bug_id', 'saknas')}")
                    st.write(f"**Rapporterad av:** {reporter}")
                    affected_module = str(bug.get("affected_module", "")).strip()
                    if affected_module:
                        st.write(f"**Berörd modul:** {affected_module}")
                    st.write(f"**Status:** {BUG_STATUS.get(status_key, status_key)}")
                    st.write(str(bug.get("description", "")))

                    messages = list(bug.get("messages", []))
                    if messages:
                        st.markdown("**Konversation**")
                        for message in messages:
                            role = "Admin" if bool(message.get("is_admin", False)) else "Användare"
                            author = str(message.get("author", "okänd"))
                            created_at = message.get("created_at")
                            if hasattr(created_at, "strftime"):
                                when = created_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                when = str(created_at or "-")
                            st.write(f"- [{when}] {role} ({author}): {str(message.get('text', ''))}")

                    can_reply = current_user_is_admin or reporter == current_user
                    if can_reply:
                        reply = st.text_area(
                            "Svara i tråden",
                            key=f"bug_reply_{bug.get('_id')}",
                            placeholder="Skriv ditt svar här...",
                        )
                        if st.button("Skicka svar", key=f"bug_reply_btn_{bug.get('_id')}"):
                            reply_text = str(reply).strip()
                            if not reply_text:
                                st.info("Skriv ett meddelande först.")
                            else:
                                new_message = {
                                    "message_id": f"msg-{uuid4().hex[:10]}",
                                    "author": current_user,
                                    "text": reply_text,
                                    "is_admin": current_user_is_admin,
                                    "created_at": utc_now(),
                                }
                                bugs.update_one(
                                    {"_id": bug["_id"]},
                                    {
                                        "$push": {"messages": new_message},
                                        "$set": {"updated_at": utc_now(), "last_actor": current_user},
                                    },
                                )
                                log_activity(
                                    current_user,
                                    "reply_bug_report",
                                    module="bug_tracker",
                                    target=str(bug.get("bug_id", "")),
                                )
                                st.success("Svar skickat.")
                                st.rerun()

    if current_user_is_admin:
        with admin_tab:
            st.subheader("Adminhantering av buggar")
            admin_status_options = ["all", "new", "read", "in_progress", "resolved", "cancelled"]
            selected_bug_status = st.selectbox(
                "Filtrera status",
                admin_status_options,
                format_func=lambda value: "Alla statusar" if value == "all" else BUG_STATUS.get(value, value),
                key="bug_tracker_admin_status_filter",
            )
            bug_query: dict[str, str] = {}
            if selected_bug_status != "all":
                bug_query["status"] = selected_bug_status
            bug_docs = list(bugs.find(bug_query).sort("updated_at", -1))
            if not bug_docs:
                st.info("Inga buggrapporter hittades.")
            else:
                for bug in bug_docs:
                    bug_id = str(bug.get("bug_id", "saknas"))
                    reporter = str(bug.get("reporter", "okänd"))
                    title_text = str(bug.get("title", "Utan titel"))
                    current_status = str(bug.get("status", "new"))
                    header = f"{title_text} | {BUG_STATUS.get(current_status, current_status)} | {reporter}"
                    with st.expander(header):
                        new_status = st.selectbox(
                            "Ändra status",
                            admin_status_options[1:],
                            index=(
                                admin_status_options[1:].index(current_status)
                                if current_status in admin_status_options[1:]
                                else 0
                            ),
                            format_func=lambda value: BUG_STATUS.get(value, value),
                            key=f"bug_tracker_admin_status_{bug.get('_id')}",
                        )
                        if st.button("Spara status", key=f"bug_tracker_admin_status_btn_{bug.get('_id')}"):
                            bugs.update_one(
                                {"_id": bug["_id"]},
                                {"$set": {"status": new_status, "updated_at": utc_now(), "last_actor": current_user}},
                            )
                            log_activity(
                                current_user,
                                "update_bug_status",
                                module="bug_tracker",
                                target=bug_id,
                                details={"status": new_status},
                            )
                            st.success("Bugstatus uppdaterad.")
                            st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="bug_tracker",
        name="Bugtracker",
        description="Rapportera buggar och följ status i dialog med admin.",
        render=render,
    )
