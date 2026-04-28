"""Planned hikes with collaborative participation and gear lending."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import streamlit as st

from core.auth import is_admin, list_usernames
from core.db import get_collection, utc_now
from .base import AppModule


def _assignment_totals(hike: dict) -> dict[tuple[str, str], int]:
    """Return assigned quantities keyed by (lender, item_id)."""
    totals: dict[tuple[str, str], int] = {}
    for assignment in hike.get("gear_assignments", []):
        lender = assignment.get("lender", "")
        item_id = assignment.get("item_id", "")
        quantity = int(assignment.get("quantity", 0))
        if lender and item_id and quantity > 0:
            key = (lender, item_id)
            totals[key] = totals.get(key, 0) + quantity
    return totals


def _assignment_line(assignment: dict) -> str:
    """Build human-readable assignment text with owned/borrowed/shared marker."""
    lender = assignment.get("lender", "?")
    borrower = assignment.get("borrower", "?")
    item_name = assignment.get("item_name", "Item")
    quantity = int(assignment.get("quantity", 0))
    mode = assignment.get("assignment_type")
    if not mode:
        mode = "owned" if lender == borrower else "borrowed"

    if mode == "shared":
        return f'{borrower} - "{item_name}" x{quantity} - Shares with {lender}'
    if mode == "borrowed":
        return f'{borrower} - "{item_name}" x{quantity} - Borrowed from {lender}'
    return f'{borrower} - "{item_name}" x{quantity}'


def _checklist_requirements(hike: dict) -> list[dict[str, Any]]:
    """Build per-hike requirement rows from linked checklist snapshot."""
    linked = hike.get("linked_checklist") or {}
    requirements: list[dict[str, Any]] = []
    linked_item_types = linked.get("item_types", [])
    for item_type in linked_item_types:
        name = str(item_type.get("name", "Unnamed")).strip()
        if not name:
            continue
        requirements.append(
            {
                "requirement_id": f"type:{name.lower()}",
                "text": name,
                "category": "Checklist",
                "item_id": "",
            }
        )

    if requirements:
        return requirements

    # Legacy fallback for older linked checklist snapshots.
    for gear_item in linked.get("attached_gear", []):
        item_id = str(gear_item.get("item_id", "")).strip()
        name = str(gear_item.get("name", "Unnamed")).strip()
        category = str(gear_item.get("category", "Other")).strip() or "Other"
        requirements.append(
            {
                "requirement_id": f"gear:{item_id or name.lower()}",
                "text": name,
                "category": category,
                "item_id": item_id,
            }
        )

    for item in linked.get("items", []):
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        requirements.append(
            {
                "requirement_id": f"text:{text.lower()}",
                "text": text,
                "category": "Checklist",
                "item_id": "",
            }
        )
    return requirements


def _matches_requirement(assignment: dict, requirement: dict[str, Any]) -> bool:
    """Return True when assignment satisfies a requirement row."""
    req_item_id = str(requirement.get("item_id", "")).strip()
    if req_item_id:
        return str(assignment.get("item_id", "")).strip() == req_item_id
    req_text = str(requirement.get("text", "")).strip().lower()
    item_name = str(assignment.get("item_name", "")).strip().lower()
    item_category = str(assignment.get("item_category", "")).strip().lower()
    return bool(req_text) and req_text in {item_name, item_category}


def _auto_mark_assigned_user_checks(
    hike: dict,
    assignment: dict[str, Any],
    participant_checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mark matching checklist requirements as packed for the assigned user."""
    borrower = str(assignment.get("borrower", "")).strip()
    if not borrower:
        return participant_checks

    updated_checks = list(participant_checks)
    for requirement in _checklist_requirements(hike):
        if not _matches_requirement(assignment, requirement):
            continue
        updated_checks = [
            entry
            for entry in updated_checks
            if not (
                entry.get("participant") == borrower
                and entry.get("requirement_id") == requirement["requirement_id"]
            )
        ]
        updated_checks.append(
            {
                "participant": borrower,
                "requirement_id": requirement["requirement_id"],
                "done": True,
                "updated_at": utc_now(),
            }
        )
    return updated_checks


def _render_borrow_requests(
    hike: dict,
    current_user: str,
    collection,
    current_user_is_admin: bool = False,
) -> None:
    """Render request/approve flow where owners must approve borrowed items."""
    participants = hike.get("participants", [])
    if current_user not in participants:
        return

    gear = get_collection("gear_items")
    totals = _assignment_totals(hike)
    requests = list(hike.get("borrow_requests", []))
    pending_for_me = [
        req
        for req in requests
        if req.get("owner") == current_user and req.get("status") == "pending"
    ]
    my_pending = [
        req
        for req in requests
        if req.get("requester") == current_user and req.get("status") == "pending"
    ]

    st.markdown("**Låneförfrågningar**")
    metric_col1, metric_col2 = st.columns(2)
    metric_col1.metric("Incoming pending approvals", len(pending_for_me))
    metric_col2.metric("My pending requests", len(my_pending))
    other_participants = [user for user in participants if user != current_user]
    requestable_by_label: dict[str, dict] = {}
    for lender in other_participants:
        docs = gear.find({"owner": lender, "private_use_only": {"$ne": True}})
        for doc in docs:
            item_id = str(doc.get("item_id", ""))
            remaining = int(doc.get("quantity", 0)) - totals.get((lender, item_id), 0)
            if remaining <= 0:
                continue
            label = (
                f'{doc.get("category", "Other")}: {lender} - "{doc.get("name", "Unnamed")}" '
                f"(available {remaining})"
            )
            requestable_by_label[label] = {
                "lender": lender,
                "item_id": item_id,
                "item_name": doc.get("name", "Unnamed"),
                "remaining": remaining,
            }

    if requestable_by_label:
        picked_label = st.selectbox(
            "Förfråga om artikel",
            list(requestable_by_label.keys()),
            key=f"borrow_request_item_{hike['_id']}",
        )
        picked = requestable_by_label[picked_label]
        request_type = st.selectbox(
            "Förfrågningstyp",
            ["borrowed", "shared"],
            format_func=lambda value: {
                "borrowed": "Låna",
                "shared": "Dela",
            }[value],
            key=f"request_type_{hike['_id']}",
        )
        req_qty = st.number_input(
            "Efterfragat antal",
            min_value=1,
            max_value=max(1, int(picked["remaining"])),
            value=1,
            step=1,
            key=f"borrow_request_qty_{hike['_id']}",
        )
        request_button_label = (
            "Skicka låneförfrågan" if request_type == "borrowed" else "Skicka delningsförfrågan"
        )
        if st.button(request_button_label, key=f"send_borrow_request_{hike['_id']}"):
            requests.append(
                {
                    "request_id": f"req-{uuid4().hex[:10]}",
                    "requester": current_user,
                    "owner": picked["lender"],
                    "item_id": picked["item_id"],
                    "item_name": picked["item_name"],
                    "quantity": int(req_qty),
                    "request_type": request_type,
                    "status": "pending",
                    "created_at": utc_now(),
                }
            )
            collection.update_one(
                {"_id": hike["_id"]},
                {"$set": {"borrow_requests": requests, "updated_at": utc_now()}},
            )
            if request_type == "shared":
                st.success("Delningsförfrågan skickad.")
            else:
                st.success("Låneförfrågan skickad.")
            st.rerun()
    else:
        st.caption("Inga tillgängliga artiklar att låna från övriga deltagare.")

    if not requests:
        st.caption("Inga låneförfrågningar än.")
        return

    with st.expander("**Status för förfrågningar**", expanded=False):
        for request in requests:
            request_type = str(request.get("request_type", "borrowed"))
            type_label = "delning" if request_type == "shared" else "lån"
            line = (
                f'{request.get("requester", "?")} begärde {type_label} av "{request.get("item_name", "Artikel")}" '
                f'x{int(request.get("quantity", 0))} från {request.get("owner", "?")} '
                f'[{request.get("status", "pending")}]'
            )
            st.write(line)

            is_owner = request.get("owner") == current_user or current_user_is_admin
            if not is_owner or request.get("status") != "pending":
                continue

            approve_col, decline_col = st.columns(2)
            with approve_col:
                if st.button("Godkänn", key=f"approve_req_{hike['_id']}_{request.get('request_id')}"):
                    item_id = str(request.get("item_id", ""))
                    request_owner = str(request.get("owner", "")).strip()
                    remaining = 0
                    owner_item = gear.find_one({"owner": request_owner, "item_id": item_id})
                    if owner_item:
                        remaining = int(owner_item.get("quantity", 0)) - _assignment_totals(hike).get((request_owner, item_id), 0)
                    if remaining < int(request.get("quantity", 0)):
                        st.error("Inte tillräckligt antal kvar för att godkänna förfrågan.")
                    else:
                        assignments = list(hike.get("gear_assignments", []))
                        new_assignment = {
                            "assignment_id": f"asg-{uuid4().hex[:10]}",
                            "item_id": item_id,
                            "item_name": request.get("item_name", ""),
                            "item_category": owner_item.get("category", "") if owner_item else "",
                            "lender": request_owner,
                            "borrower": request.get("requester", ""),
                            "quantity": int(request.get("quantity", 0)),
                            "assignment_type": str(request.get("request_type", "borrowed")),
                        }
                        assignments.append(new_assignment)
                        updated_checks = _auto_mark_assigned_user_checks(
                            hike,
                            new_assignment,
                            list(hike.get("participant_checks", [])),
                        )
                        updated_requests = []
                        for req in requests:
                            if req.get("request_id") == request.get("request_id"):
                                req = {
                                    **req,
                                    "status": "approved",
                                    "reviewed_at": utc_now(),
                                    "reviewed_by": current_user,
                                }
                            updated_requests.append(req)
                        collection.update_one(
                            {"_id": hike["_id"]},
                            {
                                "$set": {
                                    "borrow_requests": updated_requests,
                                    "gear_assignments": assignments,
                                    "participant_checks": updated_checks,
                                    "updated_at": utc_now(),
                                }
                            },
                        )
                        st.success("Forfragan godkand och tilldelning skapad.")
                        st.rerun()
            with decline_col:
                if st.button("Avslå", key=f"decline_req_{hike['_id']}_{request.get('request_id')}"):
                    updated_requests = []
                    for req in requests:
                        if req.get("request_id") == request.get("request_id"):
                            req = {
                                **req,
                                "status": "declined",
                                "reviewed_at": utc_now(),
                                "reviewed_by": current_user,
                            }
                        updated_requests.append(req)
                    collection.update_one(
                        {"_id": hike["_id"]},
                        {"$set": {"borrow_requests": updated_requests, "updated_at": utc_now()}},
                    )
                    st.info("Forfragan avslogs.")
                    st.rerun()


def _render_assignments(
    hike: dict,
    current_user: str,
    collection,
    current_user_is_admin: bool = False,
) -> None:
    """Render owner-only assignment controls and assignment list."""
    participants = hike.get("participants", [])
    if current_user not in participants:
        return

    gear = get_collection("gear_items")
    totals = _assignment_totals(hike)
    my_docs = list(gear.find({"owner": current_user}).sort("name", 1))
    hammock_friendly = bool(hike.get("hammock_friendly", False))
    options: dict[str, dict] = {}
    for doc in my_docs:
        if (
            str(doc.get("category", "")).strip().lower() == "shelter"
            and bool(doc.get("shelter_is_hammock", False))
            and not hammock_friendly
        ):
            continue
        key = (current_user, str(doc.get("item_id", "")))
        remaining = int(doc.get("quantity", 0)) - totals.get(key, 0)
        if remaining <= 0:
            continue
        is_private = bool(doc.get("private_use_only", False))
        allowed_borrowers = [current_user] if is_private else list(participants)
        if not allowed_borrowers:
            continue
        label = (
            f"{doc.get('name', 'Unnamed')} ({doc.get('category', 'Other')}) "
            f"[{doc.get('item_id', 'N/A')}] "
            f"(available {remaining})"
        )
        if is_private:
            label += " (private)"
        options[label] = {
            "doc": doc,
            "remaining": remaining,
            "allowed_borrowers": allowed_borrowers,
        }

    with st.expander("**Tilldela din utrustning (till dig själv eller andra)**", expanded=False):
        if not options:
            st.info("Ingen tilldelningsbar utrustning finns i ditt lager just nu.")
        else:
            selected_label = st.selectbox(
                "Your gear item",
                list(options.keys()),
                key=f"assign_item_{hike['_id']}",
            )
            selected_option = options[selected_label]
            assignment_mode = st.selectbox(
                "Tilldelningslage",
                ["owned", "shared", "borrowed"],
                format_func=lambda mode: {
                    "owned": "Egen (du bär/använder den)",
                    "shared": "Delad med deltagare",
                    "borrowed": "Lanad av deltagare",
                }[mode],
                key=f"assign_mode_{hike['_id']}",
            )
            borrowers = selected_option["allowed_borrowers"]
            if assignment_mode == "owned":
                borrowers = [current_user]
            else:
                borrowers = [user for user in borrowers if user != current_user]
            if not borrowers:
                st.caption("Inga behöriga deltagare för detta tilldelningsläge.")
                borrower = None
            else:
                borrower = st.selectbox(
                    "Tilldela till användare",
                    borrowers,
                    key=f"assign_borrower_{hike['_id']}",
                )
            max_qty = max(1, selected_option["remaining"])
            quantity = st.number_input(
                "Quantity",
                min_value=1,
                max_value=max_qty,
                value=1,
                step=1,
                key=f"assign_qty_{hike['_id']}",
            )
            if borrower and st.button("Tilldela utrustning", key=f"assign_btn_{hike['_id']}"):
                doc = selected_option["doc"]
                assignments = list(hike.get("gear_assignments", []))
                new_assignment = (
                    {
                        "assignment_id": f"asg-{uuid4().hex[:10]}",
                        "item_id": str(doc.get("item_id", "")),
                        "item_name": doc.get("name", ""),
                        "item_category": doc.get("category", ""),
                        "lender": current_user,
                        "borrower": borrower,
                        "quantity": int(quantity),
                        "assignment_type": assignment_mode,
                    }
                )
                assignments.append(new_assignment)
                updated_checks = _auto_mark_assigned_user_checks(
                    hike,
                    new_assignment,
                    list(hike.get("participant_checks", [])),
                )
                collection.update_one(
                    {"_id": hike["_id"]},
                    {
                        "$set": {
                            "gear_assignments": assignments,
                            "participant_checks": updated_checks,
                            "updated_at": utc_now(),
                        }
                    },
                )
                st.success("Utrustning tilldelad.")
                st.rerun()

    with st.expander("**Nuvarande utrustningstilldelningar**", expanded=False):
        assignments = hike.get("gear_assignments", [])
        if not assignments:
            st.caption("Ingen utrustning har tilldelats an.")
            return

        for assignment in assignments:
            line = _assignment_line(assignment)
            can_remove = current_user in {assignment.get("lender"), hike.get("owner")} or current_user_is_admin
            if can_remove:
                check_col, text_col = st.columns([1, 14])
                with check_col:
                    st.checkbox(
                        "Markera tilldelning för borttagning",
                        key=f"remove_pick_{hike['_id']}_{assignment.get('assignment_id')}",
                        label_visibility="collapsed",
                    )
                with text_col:
                    st.write(line)
            else:
                st.write(line)

        removable_assignments = [
            asg
            for asg in assignments
            if current_user in {asg.get("lender"), hike.get("owner")} or current_user_is_admin
        ]
        if removable_assignments:
            if st.button("Ta bort valda tilldelningar", type="primary", key=f"remove_selected_{hike['_id']}"):
                selected_ids = []
                for asg in removable_assignments:
                    is_selected = st.session_state.get(
                        f"remove_pick_{hike['_id']}_{asg.get('assignment_id')}",
                        False,
                    )
                    if is_selected:
                        selected_ids.append(asg.get("assignment_id"))

                if not selected_ids:
                    st.info("Välj minst en tilldelning att ta bort.")
                else:
                    remaining = [
                        asg
                        for asg in assignments
                        if asg.get("assignment_id") not in selected_ids
                    ]
                    collection.update_one(
                        {"_id": hike["_id"]},
                        {"$set": {"gear_assignments": remaining, "updated_at": utc_now()}},
                    )
                    st.success(f"Removed {len(selected_ids)} assignment(s).")
                    st.rerun()


def _render_hike_checklist(hike: dict, current_user: str, collection) -> None:
    """Render shared per-hike checklist with auto-complete and overview."""
    participants = hike.get("participants", [])
    if current_user not in participants:
        return

    requirements = _checklist_requirements(hike)
    if not requirements:
        st.caption("Inga kopplade checklistkrav för denna vandring än.")
        return

    with st.expander("**Vandringens Checklista**", expanded=False):
        st.caption("Använd denna sektion för att följa tilldelade och packade krav.")
        checks = list(hike.get("participant_checks", []))
        checks_by_key = {
            (entry.get("participant"), entry.get("requirement_id")): bool(entry.get("done", False))
            for entry in checks
        }
        total_requirements = len(requirements)

        requirement_entries: list[dict[str, Any]] = []
        completed_items = 0
        total_required_slots = 0
        packed_required_slots = 0
        started_items = 0

        for requirement in requirements:
            matching_assignments = [
                assignment
                for assignment in hike.get("gear_assignments", [])
                if _matches_requirement(assignment, requirement)
            ]
            required_users = list(participants)

            packed_count = sum(
                1
                for participant in required_users
                if checks_by_key.get((participant, requirement["requirement_id"]), False)
            )
            if packed_count == 0:
                status = "saknas"
                status_rank = 0
            elif packed_count == len(required_users):
                status = "klar"
                status_rank = 2
                completed_items += 1
            else:
                status = "påbörjad"
                status_rank = 1
                started_items += 1
            total_required_slots += len(required_users)
            packed_required_slots += packed_count
            requirement_entries.append(
                {
                    "requirement": requirement,
                    "matching_assignments": matching_assignments,
                    "required_users": required_users,
                    "status": status,
                    "status_rank": status_rank,
                }
            )

        requirement_entries.sort(
            key=lambda entry: (
                entry["status_rank"],
                str(entry["requirement"].get("text", "")).lower(),
            )
        )

        card_columns = st.columns(3)
        for req_index, entry in enumerate(requirement_entries):
            requirement = entry["requirement"]
            matching_assignments = entry["matching_assignments"]
            required_users = entry["required_users"]
            status = entry["status"]
            card_col = card_columns[req_index % 3]
            with card_col:
                st.markdown(f'**{requirement.get("text", "Artikel")}**')
                if matching_assignments:
                    for assignment in matching_assignments:
                        st.caption(_assignment_line(assignment))
                else:
                    st.caption("Ingen tilldelning än (alla deltagare förväntas packa denna artikel).")
                user_cols = st.columns(max(1, len(required_users)))
                for idx, participant in enumerate(required_users):
                    checkbox_key = f"packed_{hike['_id']}_{participant}_{requirement['requirement_id']}"
                    checked = user_cols[idx].checkbox(
                        f"{participant} packed",
                        value=checks_by_key.get((participant, requirement["requirement_id"]), False),
                        key=checkbox_key,
                        disabled=participant != current_user,
                    )
                    if checks_by_key.get((participant, requirement["requirement_id"]), False):
                        packed_required_slots += 1
                    if participant == current_user and checked != checks_by_key.get(
                        (participant, requirement["requirement_id"]),
                        False,
                    ):
                        updated_checks = [
                            entry
                            for entry in checks
                            if not (
                                entry.get("participant") == participant
                                and entry.get("requirement_id") == requirement["requirement_id"]
                            )
                        ]
                        updated_checks.append(
                            {
                                "participant": participant,
                                "requirement_id": requirement["requirement_id"],
                                "done": checked,
                                "updated_at": utc_now(),
                            }
                        )
                        collection.update_one(
                            {"_id": hike["_id"]},
                            {"$set": {"participant_checks": updated_checks, "updated_at": utc_now()}},
                        )
                        st.rerun()

                missing_users = [
                    participant
                    for participant in required_users
                    if not checks_by_key.get((participant, requirement["requirement_id"]), False)
                ]
                if status == "klar":
                    st.success("Klar")
                elif status == "påbörjad":
                    st.warning("Påbörjad")
                else:
                    st.error("Saknas: " + ", ".join(missing_users))
    st.markdown("### Packningsöversikt för vandringen")
    checks = list(hike.get("participant_checks", []))
    checks_by_key = {
        (entry.get("participant"), entry.get("requirement_id")): bool(entry.get("done", False))
        for entry in checks
    }
    total_requirements = len(requirements)
    completed_items = 0
    started_items = 0
    total_required_slots = 0
    packed_required_slots = 0
    for requirement in requirements:
        matching_assignments = [
            assignment
            for assignment in hike.get("gear_assignments", [])
            if _matches_requirement(assignment, requirement)
        ]
        required_users = list(participants)
        total_required_slots += len(required_users)
        req_done = True
        for participant in required_users:
            checked = checks_by_key.get((participant, requirement["requirement_id"]), False)
            if checked:
                packed_required_slots += 1
            else:
                req_done = False
        if req_done:
            completed_items += 1
        elif any(checks_by_key.get((participant, requirement["requirement_id"]), False) for participant in required_users):
            started_items += 1

    assignment_stats = {"owned": 0, "borrowed": 0, "shared": 0}
    for assignment in hike.get("gear_assignments", []):
        mode = assignment.get("assignment_type")
        if not mode:
            mode = "owned" if assignment.get("lender") == assignment.get("borrower") else "borrowed"
        assignment_stats[mode] = assignment_stats.get(mode, 0) + int(assignment.get("quantity", 0))

    missing_items = max(0, total_requirements - completed_items)
    missing_slots = max(0, total_required_slots - packed_required_slots)
    overview_cols = st.columns(6)
    overview_cols[0].metric("Klara", completed_items)
    overview_cols[1].metric("Saknas", missing_items)
    overview_cols[2].metric("Lanat antal", assignment_stats.get("borrowed", 0))
    overview_cols[3].metric("Delat antal", assignment_stats.get("shared", 0))
    overview_cols[4].metric("Eget antal", assignment_stats.get("owned", 0))
    overview_cols[5].metric("Påbörjade", started_items)

    st.markdown("**Snabböversikt per användare**")
    for participant in participants:
        done_count = 0
        required_count = 0
        for requirement in requirements:
            matching_assignments = [
                assignment
                for assignment in hike.get("gear_assignments", [])
                if _matches_requirement(assignment, requirement)
            ]
            required_users = list(participants)
            if participant not in required_users:
                continue
            required_count += 1
            if checks_by_key.get((participant, requirement["requirement_id"]), False):
                done_count += 1
        borrowed_qty = sum(
            int(asg.get("quantity", 0))
            for asg in hike.get("gear_assignments", [])
            if asg.get("borrower") == participant
            and (asg.get("assignment_type") or "borrowed") == "borrowed"
        )
        shared_qty = sum(
            int(asg.get("quantity", 0))
            for asg in hike.get("gear_assignments", [])
            if asg.get("borrower") == participant and asg.get("assignment_type") == "shared"
        )
        st.write(
            f"- {participant}: packed {done_count}/{required_count}, "
            f"borrowed qty {borrowed_qty}, shared qty {shared_qty}, "
            f"missing checks {max(0, required_count - done_count)}"
        )

    st.caption(
        f"Packade obligatoriska markeringar: {packed_required_slots}/{total_required_slots} "
        f"(saknade markeringar: {missing_slots})."
    )


def render(current_user: str) -> None:
    """Render planned hikes and collaborative lending flow."""
    collection = get_collection("planned_hikes")
    checklist_collection = get_collection("checklists")
    current_user_is_admin = is_admin(current_user)
    users = [user for user in list_usernames() if user != current_user]
    checklist_query = {} if current_user_is_admin else {"owner": current_user}
    my_checklists = list(checklist_collection.find(checklist_query).sort("updated_at", -1))
    checklist_options = {
        f'{doc.get("title", "Utan titel")} ({doc.get("owner", "?")}, {len(doc.get("items", []))} artiklar)': doc
        for doc in my_checklists
    }
    checklist_labels = ["Ingen"] + list(checklist_options.keys())

    with st.expander("**Planera en ny vandring**", expanded=False):
        with st.form("create_planned_hike", clear_on_submit=True):
            st.subheader("Skapa planerad vandring")
            title = st.text_input("Vandringens titel", placeholder="Helgtur i fjällen")
            location = st.text_input("Plats")
            start_date = st.date_input("Startdatum", value=date.today())
            end_date = st.date_input("Slutdatum", value=start_date)
            hammock_friendly = st.toggle(
                "Hammockvänlig vandring",
                help="Aktivera om träd/poler gör hammock möjlig.",
            )
            notes = st.text_area("Anteckningar")
            invited_users = st.multiselect("Bjud in användare", users)
            selected_checklist_label = st.selectbox(
                "Koppla checklistmall",
                checklist_labels,
                help="Kopplade checklistkrav blir gemensamma packningskontroller för vandringen.",
            )
            submitted = st.form_submit_button("Skapa planerad vandring")

        if submitted:
            if not title.strip() or not location.strip():
                st.error("Titel och plats är obligatoriska.")
            elif end_date < start_date:
                st.error("Slutdatum måste vara samma dag eller senare än startdatum.")
            else:
                participants = sorted(set([current_user] + invited_users))
                linked_checklist = None
                if selected_checklist_label != "Ingen":
                    doc = checklist_options[selected_checklist_label]
                    linked_checklist = {
                        "checklist_id": str(doc.get("_id")),
                        "title": doc.get("title", "Untitled"),
                        "item_types": doc.get("item_types", []),
                        "items": doc.get("items", []),
                        "attached_gear": doc.get("attached_gear", []),
                    }
                collection.insert_one(
                    {
                        "owner": current_user,
                        "title": title.strip(),
                        "location": location.strip(),
                        "planned_start_date": start_date.isoformat(),
                        "planned_end_date": end_date.isoformat(),
                        # Keep legacy field for backward compatibility with older records/views.
                        "planned_date": start_date.isoformat(),
                        "hammock_friendly": bool(hammock_friendly),
                        "notes": notes.strip(),
                        "participants": participants,
                        "linked_checklist": linked_checklist,
                        "gear_assignments": [],
                        "borrow_requests": [],
                        "participant_checks": [],
                        "created_at": utc_now(),
                        "updated_at": utc_now(),
                    }
                )
                st.success("Planerad vandring skapad.")

    st.divider()
    st.markdown("### **Visa Planerade Vandringar**")
    view_mode = st.selectbox(
        "Visa",
        ["all", "joined", "owned"],
        format_func=lambda mode: {
            "all": "Alla vandringar",
            "joined": "Vandringar jag är med i",
            "owned": "Vandringar jag skapade",
        }[mode],
        label_visibility="collapsed",
    )
    if view_mode == "joined":
        query = {"participants": current_user}
    elif view_mode == "owned":
        query = {"owner": current_user}
    else:
        query = {}
    hikes = list(collection.find(query))
    hikes.sort(
        key=lambda hike: (
            hike.get("planned_start_date")
            or hike.get("planned_date")
            or "9999-12-31"
        )
    )
    if not hikes:
        st.info("Inga planerade vandringar hittades för detta filter.")
        return

    for hike in hikes:
        participants = hike.get("participants", [])
        title = f"{hike.get('title', 'Utan titel')} ({hike.get('location', 'Okänd')})"
        with st.expander(title):
            start_value = hike.get("planned_start_date") or hike.get("planned_date")
            end_value = hike.get("planned_end_date")
            if start_value and end_value:
                st.caption(f"Planerade datum: {start_value} till {end_value}")
            elif start_value:
                st.caption(f"Planerat startdatum: {start_value}")
            else:
                st.caption("Planerade datum: N/A")
            st.write(f"Organisatör: {hike.get('owner', 'Okänd')}")
            is_hammock_friendly = bool(hike.get("hammock_friendly", False))
            st.write(
                "Hammockvänlig: "
                + ("Ja (hammock kan tilldelas)" if is_hammock_friendly else "Nej")
            )
            st.write("Deltagare: " + ", ".join(participants))
            linked_checklist = hike.get("linked_checklist")
            if linked_checklist:
                st.write(f'Checklista: {linked_checklist.get("title", "Utan titel")}')
            can_manage_hike = current_user == hike.get("owner") or current_user_is_admin

            with st.expander("**Redigera Vandringsinformation**)", expanded=False):
                if can_manage_hike:
                    edit_title = st.text_input(
                        "Redigera titel",
                        value=hike.get("title", ""),
                        key=f"edit_hike_title_{hike['_id']}",
                    )
                    edit_location = st.text_input(
                        "Redigera plats",
                        value=hike.get("location", ""),
                        key=f"edit_hike_location_{hike['_id']}",
                    )
                    current_start = hike.get("planned_start_date") or hike.get("planned_date")
                    current_end = hike.get("planned_end_date") or current_start
                    edit_start = st.date_input(
                        "Redigera startdatum",
                        value=date.fromisoformat(current_start) if current_start else date.today(),
                        key=f"edit_hike_start_{hike['_id']}",
                    )
                    edit_end = st.date_input(
                        "Redigera slutdatum",
                        value=date.fromisoformat(current_end) if current_end else edit_start,
                        key=f"edit_hike_end_{hike['_id']}",
                    )
                    edit_notes = st.text_area(
                        "Redigera anteckningar",
                        value=hike.get("notes", ""),
                        key=f"edit_hike_notes_{hike['_id']}",
                    )
                    if st.button("Spara ändringar", key=f"save_hike_{hike['_id']}"):
                        if edit_end < edit_start:
                            st.error("Slutdatum måste vara samma dag eller senare än startdatum.")
                        elif not edit_title.strip() or not edit_location.strip():
                            st.error("Titel och plats är obligatoriska.")
                        else:
                            collection.update_one(
                                {"_id": hike["_id"]},
                                {
                                    "$set": {
                                        "title": edit_title.strip(),
                                        "location": edit_location.strip(),
                                        "planned_start_date": edit_start.isoformat(),
                                        "planned_end_date": edit_end.isoformat(),
                                        "planned_date": edit_start.isoformat(),
                                        "notes": edit_notes.strip(),
                                        "updated_at": utc_now(),
                                    }
                                },
                            )
                            st.success("Vandring uppdaterad.")
                            st.rerun()

                    if checklist_options:
                        attach_label = st.selectbox(
                            "Koppla eller byt checklista på denna vandring",
                            list(checklist_options.keys()),
                            key=f"attach_checklist_{hike['_id']}",
                        )
                        button_label = "Koppla checklista" if not linked_checklist else "Byt checklista"
                        if st.button(button_label, key=f"attach_checklist_btn_{hike['_id']}"):
                            doc = checklist_options[attach_label]
                            collection.update_one(
                                {"_id": hike["_id"]},
                                {
                                    "$set": {
                                        "linked_checklist": {
                                            "checklist_id": str(doc.get("_id")),
                                            "title": doc.get("title", "Untitled"),
                                        "item_types": doc.get("item_types", []),
                                            "items": doc.get("items", []),
                                            "attached_gear": doc.get("attached_gear", []),
                                        },
                                        "participant_checks": [],
                                        "updated_at": utc_now(),
                                    }
                                },
                            )
                            st.success("Checklista kopplad till vandringen.")
                            st.rerun()
                    else:
                        st.caption("Skapa en checklista först för att koppla den till vandringen.")

                    if linked_checklist and st.button(
                        "Ta bort kopplad checklista",
                        key=f"remove_linked_checklist_{hike['_id']}",
                        type="primary",
                    ):
                        collection.update_one(
                            {"_id": hike["_id"]},
                            {
                                "$set": {
                                    "linked_checklist": None,
                                    "participant_checks": [],
                                    "updated_at": utc_now(),
                                }
                            },
                        )
                        st.info("Checklista borttagen från vandringen.")
                        st.rerun()
                if hike.get("notes"):
                    st.caption(hike["notes"])

                if can_manage_hike:
                    hammock_button_label = (
                        "Markera som INTE hammockvänlig"
                        if is_hammock_friendly
                        else "Markera som hammockvänlig"
                    )
                    if st.button(hammock_button_label, key=f"toggle_hike_hammock_{hike['_id']}"):
                        collection.update_one(
                            {"_id": hike["_id"]},
                            {
                                "$set": {
                                    "hammock_friendly": not is_hammock_friendly,
                                    "updated_at": utc_now(),
                                }
                            },
                        )
                        st.rerun()

            if current_user not in participants:
                if st.button("Gå med i vandringen", key=f"join_hike_{hike['_id']}"):
                    collection.update_one(
                        {"_id": hike["_id"]},
                        {
                            "$addToSet": {"participants": current_user},
                            "$set": {"updated_at": utc_now()},
                        },
                    )
                    st.success("Du gick med i vandringen.")
                    st.rerun()
                continue

            _render_borrow_requests(hike, current_user, collection, current_user_is_admin)
            _render_assignments(hike, current_user, collection, current_user_is_admin)
            _render_hike_checklist(hike, current_user, collection)

            if can_manage_hike and st.button(
                "Radera planerad vandring",
                key=f"delete_hike_{hike['_id']}",
                type="primary",
            ):
                collection.delete_one({"_id": hike["_id"]})
                st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="planned_hikes",
        name="Planera vandringar",
        description="Skapa gemensamma vandringar och tilldela utrustning mellan deltagare.",
        render=render,
    )
