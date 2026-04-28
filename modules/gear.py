"""Hiking gear inventory module."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from core.auth import is_admin, list_usernames
from core.db import get_collection, utc_now
from .base import AppModule
from .checklist_item_types import seed_default_item_types

DEFAULT_FALLBACK_CATEGORIES = [
    "Skydd (tält/pressening)",
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


def _migration_key(doc: dict) -> tuple[str, str]:
    """Return normalized matching key for shared gear identity."""
    name_normalized = str(doc.get("name_normalized") or doc.get("name", "")).strip().lower()
    category = str(doc.get("category", "Shelter")).strip() or "Shelter"
    return name_normalized, category


def _migrate_legacy_item_ids(collection) -> tuple[int, int]:
    """Assign missing item_id values and normalize names for legacy documents."""
    seeded_docs = collection.find(
        {"item_id": {"$exists": True, "$ne": ""}},
        {"item_id": 1, "name": 1, "name_normalized": 1, "category": 1},
    )
    shared_ids_by_key: dict[tuple[str, str], str] = {}
    for doc in seeded_docs:
        key = _migration_key(doc)
        if key[0] and key not in shared_ids_by_key:
            shared_ids_by_key[key] = str(doc.get("item_id"))

    migrated_count = 0
    generated_count = 0
    legacy_docs = list(
        collection.find(
            {
                "$or": [
                    {"item_id": {"$exists": False}},
                    {"item_id": ""},
                ]
            }
        )
    )
    for doc in legacy_docs:
        key = _migration_key(doc)
        if not key[0]:
            continue

        item_id = shared_ids_by_key.get(key)
        if not item_id:
            item_id = f"item-{uuid4().hex[:10]}"
            shared_ids_by_key[key] = item_id
            generated_count += 1

        collection.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "item_id": item_id,
                    "name_normalized": key[0],
                    "category": key[1],
                    "updated_at": utc_now(),
                }
            },
        )
        migrated_count += 1

    return migrated_count, generated_count


def render(current_user: str) -> None:
    """Render gear create and browse views."""
    collection = get_collection("gear_items")
    checklist_type_collection = get_collection("checklist_item_types")
    current_user_is_admin = is_admin(current_user)
    seed_default_item_types(current_user)
    type_docs = list(checklist_type_collection.find({}, {"name": 1}).sort("name", 1))
    dynamic_categories = [
        str(doc.get("name", "")).strip()
        for doc in type_docs
        if str(doc.get("name", "")).strip()
    ]
    categories = dynamic_categories or DEFAULT_FALLBACK_CATEGORIES

    with st.form("add_gear_item", clear_on_submit=True):
        st.subheader("Lägg till utrustning")
        name = st.text_input("Namn på artikel", placeholder="Ultralätt tält")
        category = st.selectbox("Kategori", categories)
        shelter_is_hammock = False
        if category.strip().lower() in {"shelter", "skydd (tält/pressening)"}:
            shelter_is_hammock = st.toggle(
                "Detta skydd är en hammock",
                help="Hammock kräver att vandringen är markerad som hammockvänlig.",
            )
        weight_g = st.number_input("Vikt (gram)", min_value=0, step=50)
        quantity = st.number_input("Antal", min_value=1, step=1, value=1)
        essential = st.checkbox("Obligatorisk")
        notes = st.text_area("Anteckningar")
        submitted = st.form_submit_button("Spara utrustning")

    if submitted:
        if not name.strip():
            st.error("Artikelnamn är obligatoriskt.")
        elif not category.strip():
            st.error("Kategori är obligatorisk.")
        else:
            item_name = name.strip()
            item_category = category.strip()
            existing_item = collection.find_one(
                {
                    "name_normalized": item_name.lower(),
                    "category": item_category,
                },
                sort=[("created_at", 1)],
            )
            item_id = existing_item["item_id"] if existing_item else f"item-{uuid4().hex[:10]}"
            collection.insert_one(
                {
                    "owner": current_user,
                    "item_id": item_id,
                    "name": item_name,
                    "name_normalized": item_name.lower(),
                    "category": item_category,
                    "weight_g": int(weight_g),
                    "quantity": int(quantity),
                    "essential": essential,
                    "private_use_only": False,
                    "shelter_is_hammock": bool(shelter_is_hammock)
                    if item_category.strip().lower() in {"shelter", "skydd (tält/pressening)"}
                    else False,
                    "notes": notes.strip(),
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            st.success("Utrustning sparad.")

    with st.expander("Underhallsverktyg"):
        st.caption("Kör en gång för att normalisera äldre utrustning utan `item_id`.")
        if st.button("Migrera aldre utrustnings-ID", type="secondary"):
            migrated_count, generated_count = _migrate_legacy_item_ids(collection)
            if migrated_count == 0:
                st.info("Inga äldre artiklar behövde migrering.")
            else:
                st.success(
                    f"Migrerade {migrated_count} artiklar. "
                    f"Skapade {generated_count} nya delade item-ID."
                )
                st.rerun()

    st.divider()
    st.subheader("Utrustningsbibliotek")
    owners = ["all"] + list_usernames()
    selected_owner = st.selectbox(
        "Visa utrustning från",
        owners,
        format_func=lambda value: "Alla användare" if value == "all" else value,
        key="owner_filter_gear",
    )
    selected_category = st.selectbox("Kategorifilter", ["all"] + categories)

    query: dict[str, str] = {}
    if selected_owner != "all":
        query["owner"] = selected_owner
    if selected_category != "all":
        query["category"] = selected_category

    docs = list(collection.find(query).sort("updated_at", -1))
    if not docs:
        st.info("Ingen utrustning hittades för detta filter.")
        return

    total_weight = sum(doc.get("weight_g", 0) * doc.get("quantity", 1) for doc in docs)
    st.metric("Visad total packvikt", f"{total_weight / 1000:.2f} kg")

    for doc in docs:
        title = f"{doc['name']} ({doc['owner']})"
        with st.expander(title):
            owners_count = collection.count_documents({"item_id": doc.get("item_id")})
            st.write(f"Item-ID: {doc.get('item_id', 'N/A')}")
            st.write(f"Ägs av användare: {owners_count}")
            st.write(f"Kategori: {doc.get('category', 'Övrigt')}")
            st.write(f"Vikt: {doc.get('weight_g', 0)} g x {doc.get('quantity', 1)}")
            st.write(f"Obligatorisk: {'Ja' if doc.get('essential') else 'Nej'}")
            is_private = bool(doc.get("private_use_only", False))
            st.write(f"Endast privat bruk: {'Ja' if is_private else 'Nej'}")
            if doc.get("category") == "Shelter":
                is_hammock = bool(doc.get("shelter_is_hammock", False))
                st.write(f"Hammockskydd: {'Ja' if is_hammock else 'Nej'}")
            if doc.get("notes"):
                st.caption(doc["notes"])

            can_manage = doc["owner"] == current_user or current_user_is_admin
            if can_manage:
                edited_name = st.text_input(
                    "Redigera namn",
                    value=doc.get("name", ""),
                    key=f"edit_gear_name_{doc['_id']}",
                )
                edited_category = st.selectbox(
                    "Redigera kategori",
                    categories,
                    index=categories.index(doc.get("category", categories[0]))
                    if doc.get("category", categories[0]) in categories
                    else 0,
                    key=f"edit_gear_category_{doc['_id']}",
                )
                edited_weight = st.number_input(
                    "Redigera vikt (gram)",
                    min_value=0,
                    step=50,
                    value=int(doc.get("weight_g", 0)),
                    key=f"edit_gear_weight_{doc['_id']}",
                )
                edited_qty = st.number_input(
                    "Redigera antal",
                    min_value=1,
                    step=1,
                    value=int(doc.get("quantity", 1)),
                    key=f"edit_gear_qty_{doc['_id']}",
                )
                if st.button("Spara ändringar", key=f"save_gear_{doc['_id']}"):
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "name": edited_name.strip(),
                                "name_normalized": edited_name.strip().lower(),
                                "category": edited_category,
                                "weight_g": int(edited_weight),
                                "quantity": int(edited_qty),
                                "updated_at": utc_now(),
                            }
                        },
                    )
                    st.success("Utrustning uppdaterad.")
                    st.rerun()

                toggle_label = (
                    "Inaktivera endast privat bruk" if is_private else "Markera som endast privat bruk"
                )
                if st.button(toggle_label, key=f"toggle_private_{doc['_id']}"):
                    collection.update_one(
                        {"_id": doc["_id"]},
                        {
                            "$set": {
                                "private_use_only": not is_private,
                                "updated_at": utc_now(),
                            }
                        },
                    )
                    st.rerun()

                if doc.get("category") == "Shelter":
                    is_hammock = bool(doc.get("shelter_is_hammock", False))
                    hammock_label = (
                        "Markera som ej-hammockskydd"
                        if is_hammock
                        else "Markera som hammockskydd"
                    )
                    if st.button(hammock_label, key=f"toggle_hammock_{doc['_id']}"):
                        collection.update_one(
                            {"_id": doc["_id"]},
                            {
                                "$set": {
                                    "shelter_is_hammock": not is_hammock,
                                    "updated_at": utc_now(),
                                }
                            },
                        )
                        st.rerun()

            if doc["owner"] != current_user and st.button(
                "Jag ager den ocksa",
                key=f"claim_gear_{doc['_id']}",
            ):
                already_owned = collection.find_one(
                    {"owner": current_user, "item_id": doc.get("item_id")}
                )
                if already_owned:
                    st.info("Du har redan denna artikel i din utrustning.")
                else:
                    collection.insert_one(
                        {
                            "owner": current_user,
                            "item_id": doc.get("item_id", f"item-{uuid4().hex[:10]}"),
                            "name": doc.get("name", ""),
                            "name_normalized": doc.get("name", "").strip().lower(),
                            "category": doc.get("category", "Shelter"),
                            "weight_g": int(doc.get("weight_g", 0)),
                            "quantity": 1,
                            "essential": bool(doc.get("essential", False)),
                            "private_use_only": False,
                            "shelter_is_hammock": bool(doc.get("shelter_is_hammock", False)),
                            "notes": f"Kopierad från {doc.get('owner', 'annan användare')}",
                            "created_at": utc_now(),
                            "updated_at": utc_now(),
                        }
                    )
                    st.success("Tillagd i din utrustning.")
                    st.rerun()

            if can_manage and st.button(
                "Radera utrustning",
                key=f"delete_gear_{doc['_id']}",
                type="primary",
            ):
                collection.delete_one({"_id": doc["_id"]})
                st.rerun()


def get_module() -> AppModule:
    """Return module metadata and render callable."""
    return AppModule(
        key="gear",
        name="Utrustning",
        description="Spara och visa utrustningslistor per användare.",
        render=render,
    )
