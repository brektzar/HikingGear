"""Statistics module with personal and collaborative overview."""

from __future__ import annotations

from datetime import datetime
import math

import pandas as pd
import plotly.express as px
import streamlit as st

from core.auth import is_admin
from core.db import get_collection
from .base import AppModule


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in kilometers between two coordinates."""
    earth_radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_km * c


def _line_paths(geometry: dict) -> list[list[tuple[float, float]]]:
    """Extract LineString-like paths as [(lon, lat), ...]."""
    geom_type = str((geometry or {}).get("type", ""))
    coords = (geometry or {}).get("coordinates")
    if geom_type == "LineString" and isinstance(coords, list):
        path = [
            (float(point[0]), float(point[1]))
            for point in coords
            if isinstance(point, (list, tuple)) and len(point) >= 2
        ]
        return [path] if len(path) >= 2 else []
    if geom_type == "MultiLineString" and isinstance(coords, list):
        paths: list[list[tuple[float, float]]] = []
        for line in coords:
            if not isinstance(line, list):
                continue
            path = [
                (float(point[0]), float(point[1]))
                for point in line
                if isinstance(point, (list, tuple)) and len(point) >= 2
            ]
            if len(path) >= 2:
                paths.append(path)
        return paths
    return []


def _line_length_km(path: list[tuple[float, float]]) -> float:
    """Compute total distance for one path."""
    length_km = 0.0
    for index in range(1, len(path)):
        prev_lon, prev_lat = path[index - 1]
        curr_lon, curr_lat = path[index]
        length_km += _haversine_km(prev_lat, prev_lon, curr_lat, curr_lon)
    return length_km


def _per_trail_lengths_km(geojson_data: dict) -> dict[str, float]:
    """Return per-trail lengths from GeoJSON by feature title."""
    features = (
        list(geojson_data.get("features", []))
        if isinstance(geojson_data.get("features"), list)
        else []
    )
    result: dict[str, float] = {}
    unnamed_index = 1
    for feature in features:
        geometry = (feature or {}).get("geometry") or {}
        paths = _line_paths(geometry)
        if not paths:
            continue
        props = (feature or {}).get("properties") or {}
        title = str(props.get("title", "")).strip()
        if not title:
            title = f"Led utan namn {unnamed_index}"
            unnamed_index += 1
        trail_km = sum(_line_length_km(path) for path in paths)
        if trail_km > 0:
            result[title] = result.get(title, 0.0) + trail_km
    return result


def _safe_parse_date(value: str) -> datetime | None:
    """Parse ISO date-like string to datetime, else None."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _metric_card(label: str, value: str, caption: str = "") -> None:
    """Render one bordered metric card."""
    with st.container(border=True):
        st.metric(label, value)
        if caption:
            st.caption(caption)


def render(current_user: str) -> None:
    """Render extended statistics for the logged-in user."""
    users_col = get_collection("users")
    checklists_col = get_collection("checklists")
    trails_col = get_collection("trails")
    gear_col = get_collection("gear_items")
    planned_hikes_col = get_collection("planned_hikes")
    logs_col = get_collection("activity_logs")
    bugs_col = get_collection("bug_reports")

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

    st.divider()
    st.markdown("### Vandringsutfall")
    all_hikes = list(
        planned_hikes_col.find(
            {},
            {
                "status": 1,
                "created_at": 1,
                "updated_at": 1,
                "participants": 1,
                "participant_checks": 1,
                "linked_checklist": 1,
                "gear_assignments": 1,
                "route_geojson": 1,
                "main_route_titles": 1,
            },
        )
    )
    planned_count = len([h for h in all_hikes if str(h.get("status", "planned")) != "completed"])
    completed_count = len([h for h in all_hikes if str(h.get("status", "planned")) == "completed"])
    total_hikes_count = len(all_hikes)
    completion_rate = (completed_count / total_hikes_count * 100) if total_hikes_count else 0.0

    completion_days: list[float] = []
    for hike in all_hikes:
        created_at = hike.get("created_at")
        updated_at = hike.get("updated_at")
        if str(hike.get("status", "planned")) == "completed" and isinstance(created_at, datetime) and isinstance(updated_at, datetime):
            completion_days.append(max(0.0, (updated_at - created_at).total_seconds() / 86400))
    avg_days_to_complete = sum(completion_days) / len(completion_days) if completion_days else 0.0

    # Build per-hike dataset for configurable charts.
    hike_records: list[dict] = []
    for index, hike in enumerate(all_hikes, start=1):
        status = str(hike.get("status", "planned"))
        per_trail_km = _per_trail_lengths_km(hike.get("route_geojson") or {})
        selected_titles = [str(title) for title in hike.get("main_route_titles", []) if str(title) in per_trail_km]
        selected_main_km = sum(per_trail_km.get(title, 0.0) for title in selected_titles)
        start_date_text = str(hike.get("planned_start_date") or hike.get("planned_date") or "")
        end_date_text = str(
            hike.get("planned_end_date") or hike.get("planned_start_date") or hike.get("planned_date") or ""
        )
        start_dt = _safe_parse_date(start_date_text)
        end_dt = _safe_parse_date(end_date_text)
        duration_days = ((end_dt - start_dt).days + 1) if (start_dt and end_dt and end_dt >= start_dt) else 0
        assignments = list(hike.get("gear_assignments", []) or [])
        borrowed_qty = sum(
            int(entry.get("quantity", 0) or 0)
            for entry in assignments
            if str(entry.get("assignment_type", "")).strip().lower() == "borrowed"
        )
        shared_qty = sum(
            int(entry.get("quantity", 0) or 0)
            for entry in assignments
            if str(entry.get("assignment_type", "")).strip().lower() == "shared"
        )
        owned_qty = sum(
            int(entry.get("quantity", 0) or 0)
            for entry in assignments
            if str(entry.get("assignment_type", "")).strip().lower() not in {"borrowed", "shared"}
        )
        hike_records.append(
            {
                "hike_index": index,
                "hike_title": str(hike.get("title", "")).strip() or f"Vandring {index}",
                "owner": str(hike.get("owner", "")),
                "status": status,
                "participants_count": len(list(hike.get("participants", []) or [])),
                "assignments_count": len(list(hike.get("gear_assignments", []) or [])),
                "duration_days": duration_days,
                "main_route_km": round(float(selected_main_km), 3),
                "borrowed_qty": borrowed_qty,
                "shared_qty": shared_qty,
                "owned_qty": owned_qty,
                "pending_requests_count": len(
                    [
                        req
                        for req in list(hike.get("borrow_requests", []) or [])
                        if str(req.get("status", "")).strip().lower() == "pending"
                    ]
                ),
                "start_date": start_date_text or "-",
                "end_date": end_date_text or "-",
                "created_year": (hike.get("created_at").year if isinstance(hike.get("created_at"), datetime) else 0),
            }
        )

    out_col1, out_col2, out_col3, out_col4 = st.columns(4)
    with out_col1:
        _metric_card("Planerade", str(planned_count))
    with out_col2:
        _metric_card("Genomförda", str(completed_count))
    with out_col3:
        _metric_card("Genomförandegrad", f"{completion_rate:.1f}%")
    with out_col4:
        _metric_card("Snitt dagar till genomförd", f"{avg_days_to_complete:.1f}")

    st.markdown("### Distansstatistik")
    completed_with_route = [h for h in all_hikes if str(h.get("status", "planned")) == "completed" and h.get("route_geojson")]
    selected_lengths: list[float] = []
    for hike in completed_with_route:
        per_trail_km = _per_trail_lengths_km(hike.get("route_geojson") or {})
        selected_titles = [str(title) for title in hike.get("main_route_titles", []) if str(title) in per_trail_km]
        if selected_titles:
            selected_lengths.append(sum(per_trail_km.get(title, 0.0) for title in selected_titles))
    total_completed_km = sum(selected_lengths)
    avg_completed_km = (total_completed_km / len(selected_lengths)) if selected_lengths else 0.0
    max_completed_km = max(selected_lengths) if selected_lengths else 0.0
    min_completed_km = min(selected_lengths) if selected_lengths else 0.0
    dist_col1, dist_col2, dist_col3, dist_col4 = st.columns(4)
    with dist_col1:
        _metric_card("Total km (genomförda huvudleder)", f"{total_completed_km:.1f}")
    with dist_col2:
        _metric_card("Snitt km per vandring", f"{avg_completed_km:.1f}")
    with dist_col3:
        _metric_card("Längsta huvudled", f"{max_completed_km:.1f}")
    with dist_col4:
        _metric_card("Kortaste huvudled", f"{min_completed_km:.1f}")

    st.markdown("### Packningskvalitet")
    total_req_slots = 0
    total_done_slots = 0
    missing_requirement_counts: dict[str, int] = {}
    for hike in all_hikes:
        participants = list(hike.get("participants", []) or [])
        linked = hike.get("linked_checklist") or {}
        requirements = list(linked.get("item_types", []) or [])
        if not participants or not requirements:
            continue
        checks = list(hike.get("participant_checks", []) or [])
        checks_by_key = {
            (str(entry.get("participant", "")), str(entry.get("requirement_id", ""))): bool(entry.get("done", False))
            for entry in checks
        }
        for requirement in requirements:
            req_name = str(requirement.get("name", "Okänd")).strip() or "Okänd"
            req_id = f"type:{req_name.lower()}"
            for participant in participants:
                total_req_slots += 1
                if checks_by_key.get((participant, req_id), False):
                    total_done_slots += 1
                else:
                    missing_requirement_counts[req_name] = missing_requirement_counts.get(req_name, 0) + 1
    pack_rate = (total_done_slots / total_req_slots * 100) if total_req_slots else 0.0
    pack_col1, pack_col2 = st.columns(2)
    with pack_col1:
        _metric_card("Packningsgrad (alla markeringar)", f"{pack_rate:.1f}%")
    top_missing = sorted(missing_requirement_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    if top_missing:
        pack_col2.markdown("**Vanligaste saknade krav**")
        for name, count in top_missing:
            pack_col2.write(f"- {name}: {count}")
    else:
        pack_col2.caption("Inga saknade krav registrerade.")

    st.markdown("### Utrustningssamarbete")
    lend_counts: dict[str, int] = {}
    borrow_counts: dict[str, int] = {}
    shared_category_counts: dict[str, int] = {}
    total_owned_qty = 0
    total_borrowed_qty = 0
    total_shared_qty = 0
    for hike in all_hikes:
        for assignment in hike.get("gear_assignments", []) or []:
            mode = str(assignment.get("assignment_type", "")).strip().lower()
            qty = int(assignment.get("quantity", 0) or 0)
            lender = str(assignment.get("lender", "")).strip()
            borrower = str(assignment.get("borrower", "")).strip()
            if mode == "borrowed":
                total_borrowed_qty += qty
            elif mode == "shared":
                total_shared_qty += qty
                category = str(assignment.get("item_category", "Övrigt")).strip() or "Övrigt"
                shared_category_counts[category] = shared_category_counts.get(category, 0) + qty
            else:
                total_owned_qty += qty
            if lender:
                lend_counts[lender] = lend_counts.get(lender, 0) + qty
            if borrower:
                borrow_counts[borrower] = borrow_counts.get(borrower, 0) + qty
    top_lender = max(lend_counts.items(), key=lambda item: item[1])[0] if lend_counts else "-"
    top_borrower = max(borrow_counts.items(), key=lambda item: item[1])[0] if borrow_counts else "-"
    top_shared_category = max(shared_category_counts.items(), key=lambda item: item[1])[0] if shared_category_counts else "-"
    collab_col1, collab_col2, collab_col3, collab_col4 = st.columns(4)
    with collab_col1:
        _metric_card("Eget antal", str(total_owned_qty))
    with collab_col2:
        _metric_card("Lånat antal", str(total_borrowed_qty))
    with collab_col3:
        _metric_card("Delat antal", str(total_shared_qty))
    with collab_col4:
        _metric_card("Mest delad kategori", top_shared_category)
    st.caption(f"Lånar ut mest: {top_lender} | Lånar mest: {top_borrower}")

    st.markdown("### Ledåteranvändning")
    clone_events = list(logs_col.find({"action": "clone_hike_for_replan"}, {"actor": 1, "target": 1, "event_at": 1}))
    clone_count = len(clone_events)
    unique_routes_reused = len({str(event.get("target", "")).strip() for event in clone_events if str(event.get("target", "")).strip()})
    reuse_rate = (clone_count / completed_count * 100) if completed_count else 0.0
    reused_by_user: dict[str, int] = {}
    for event in clone_events:
        actor = str(event.get("actor", "")).strip()
        if actor:
            reused_by_user[actor] = reused_by_user.get(actor, 0) + 1
    top_reuser = max(reused_by_user.items(), key=lambda item: item[1])[0] if reused_by_user else "-"
    reuse_col1, reuse_col2, reuse_col3, reuse_col4 = st.columns(4)
    with reuse_col1:
        _metric_card("Kopieringar till planering", str(clone_count))
    with reuse_col2:
        _metric_card("Unika återanvända leder", str(unique_routes_reused))
    with reuse_col3:
        _metric_card("Återanvändningsgrad", f"{reuse_rate:.1f}%")
    with reuse_col4:
        _metric_card("Mest återanvändare", top_reuser)

    st.markdown("### Grafanalys")
    if hike_records:
        chart_df = pd.DataFrame(hike_records)
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
        available_metrics = {
            "Huvudled km": "main_route_km",
            "Vandringsdagar": "duration_days",
            "Antal deltagare": "participants_count",
            "Antal tilldelningar": "assignments_count",
            "Lånat antal": "borrowed_qty",
            "Delat antal": "shared_qty",
            "Eget antal": "owned_qty",
            "Väntande förfrågningar": "pending_requests_count",
        }
        with ctrl_col1:
            selected_metric_labels = st.multiselect(
                "Välj datapunkter",
                list(available_metrics.keys()),
                default=["Huvudled km", "Vandringsdagar"],
                key="stats_chart_metrics",
            )
        with ctrl_col2:
            x_axis = st.selectbox(
                "X-axel",
                ["hike_title", "status", "owner", "hike_index"],
                format_func=lambda value: {
                    "hike_title": "Vandring",
                    "status": "Status",
                    "owner": "Ägare",
                    "hike_index": "Index",
                }[value],
                key="stats_chart_x_axis",
            )
        with ctrl_col3:
            chart_type = st.selectbox(
                "Graftyp",
                ["Bar", "Line", "Scatter"],
                key="stats_chart_type",
            )

        selected_metrics = [available_metrics[label] for label in selected_metric_labels]
        if selected_metrics:
            id_vars = [
                x_axis,
                "hike_title",
                "status",
                "owner",
                "participants_count",
                "duration_days",
                "start_date",
                "end_date",
            ]
            unique_id_vars = list(dict.fromkeys(id_vars))
            long_df = chart_df.melt(
                id_vars=unique_id_vars,
                value_vars=selected_metrics,
                var_name="metric",
                value_name="value",
            )
            metric_name_map = {value: key for key, value in available_metrics.items()}
            long_df["metric"] = long_df["metric"].map(metric_name_map)
            long_df["status_label"] = long_df["status"].map(
                {"planned": "Planerad", "completed": "Genomförd"}
            ).fillna(long_df["status"])
            if chart_type == "Line":
                grouped_df = (
                    long_df.groupby([x_axis, "metric"], as_index=False)["value"].sum().sort_values([x_axis, "metric"])
                )
            else:
                grouped_df = long_df
            if chart_type == "Line":
                fig = px.line(
                    grouped_df,
                    x=x_axis,
                    y="value",
                    color="metric",
                    markers=True,
                )
                fig.update_traces(mode="lines+markers")
            elif chart_type == "Scatter":
                fig = px.scatter(grouped_df, x=x_axis, y="value", color="metric")
            else:
                fig = px.bar(grouped_df, x=x_axis, y="value", color="metric", barmode="group")
            fig.update_traces(
                customdata=(
                    long_df[
                        [
                            "hike_title",
                            "status_label",
                            "owner",
                            "participants_count",
                            "duration_days",
                            "start_date",
                            "end_date",
                        ]
                    ].to_numpy()
                    if chart_type != "Line"
                    else None
                )
            )
            if chart_type != "Line":
                fig.update_traces(
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        + "Status: %{customdata[1]}<br>"
                        + "Ägare: %{customdata[2]}<br>"
                        + "Deltagare: %{customdata[3]}<br>"
                        + "Vandringsdagar: %{customdata[4]}<br>"
                        + "Start: %{customdata[5]}<br>"
                        + "Slut: %{customdata[6]}<br>"
                        + "Värde: %{y}<extra></extra>"
                    )
                )
            fig.update_layout(margin=dict(l=12, r=12, t=34, b=12))
            status_fig = px.pie(
                chart_df,
                names="status",
                title="Statusfördelning vandringar",
                color="status",
                color_discrete_map={"planned": "#C9B24D", "completed": "#5E6E4A"},
            )
            status_fig.update_layout(margin=dict(l=12, r=12, t=36, b=12))
            chart_col, status_col = st.columns([2, 1])
            with chart_col:
                st.plotly_chart(
                    fig,
                    use_container_width=True,
                    config={
                        "displaylogo": False,
                        "toImageButtonOptions": {"format": "png", "filename": "hiking_stats_chart"},
                    },
                )
            with status_col:
                st.plotly_chart(
                    status_fig,
                    use_container_width=True,
                    config={
                        "displaylogo": False,
                        "toImageButtonOptions": {"format": "png", "filename": "hiking_status_distribution"},
                    },
                )

    if is_admin(current_user):
        st.markdown("### Bugtracker hälsa (Admin)")
        bug_docs = list(
            bugs_col.find(
                {},
                {"status": 1, "messages": 1, "created_at": 1, "updated_at": 1},
            )
        )
        total_bugs = len(bug_docs)
        status_counts: dict[str, int] = {}
        first_response_hours: list[float] = []
        resolve_hours: list[float] = []
        for bug in bug_docs:
            status = str(bug.get("status", "new"))
            status_counts[status] = status_counts.get(status, 0) + 1
            created_at = bug.get("created_at")
            updated_at = bug.get("updated_at")
            messages = list(bug.get("messages", []) or [])
            if isinstance(created_at, datetime):
                first_admin_message = next(
                    (
                        message
                        for message in messages
                        if bool(message.get("is_admin", False)) and isinstance(message.get("created_at"), datetime)
                    ),
                    None,
                )
                if first_admin_message:
                    first_response_hours.append(
                        max(0.0, (first_admin_message["created_at"] - created_at).total_seconds() / 3600)
                    )
                if status == "resolved" and isinstance(updated_at, datetime):
                    resolve_hours.append(max(0.0, (updated_at - created_at).total_seconds() / 3600))
        avg_first_response_hours = (
            sum(first_response_hours) / len(first_response_hours) if first_response_hours else 0.0
        )
        avg_resolve_hours = sum(resolve_hours) / len(resolve_hours) if resolve_hours else 0.0
        bug_col1, bug_col2, bug_col3, bug_col4 = st.columns(4)
        with bug_col1:
            _metric_card("Totala buggar", str(total_bugs))
        with bug_col2:
            _metric_card("Nya", str(status_counts.get("new", 0)))
        with bug_col3:
            _metric_card("Snitt tid till första adminsvar", f"{avg_first_response_hours:.1f} h")
        with bug_col4:
            _metric_card("Snitt tid till avklarad", f"{avg_resolve_hours:.1f} h")
        st.caption(
            "Statusfördelning: "
            + ", ".join(
                [
                    f"{label}: {status_counts.get(key, 0)}"
                    for key, label in [
                        ("read", "Läst"),
                        ("in_progress", "Påbörjad"),
                        ("resolved", "Avklarad"),
                        ("cancelled", "Avbruten"),
                    ]
                ]
            )
        )


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="stats",
        name="Statistik",
        description="Statistik för checklistor, utrustning, leder och vandringar.",
        render=render,
    )
