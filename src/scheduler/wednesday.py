# src/scheduler/wednesday.py

import pandas as pd
from src.config import (
    INTERMEDIATE_ROLES,
    SPAETDIENST,
    TAGDIENST_OA,
    BUERO_FORSCHUNG_OA,
)
from src.selector import pick_person_fair, _extract_lastname


def build_wednesday_schedule(calendar_df, pep_df, topics_df, selector):
    """
    Mittwoch Curriculum — every Wednesday, 14:30–15:15

    LOGIC:
    1. Fair selector picks the person (same rules as always):
         Roles:         INTERMEDIATE_ROLES (SOA, OA_I, OA_II, SFA_II)
         Duty priority: Spätdienst → Büro/Forschung → Tagdienst OA
         Fairness:      selector handles recency + history penalties
    2. Once the person is known, look up THEIR topics in the sheet
       and pick whichever they presented longest ago (oldest
       "Datum letzter Vortrag"). Keeps topic rotation per-person.
    3. If the person has no topics in the sheet, or the sheet is missing,
       fall back to a generic "Mittwochscurriculum" label.
    4. Update that topic's last_date in-memory so it rotates correctly
       across multiple Wednesdays in the same planning run.
    """

    events = []

    if calendar_df is None or calendar_df.empty:
        return pd.DataFrame(events)

    # Build per-person topic lookup once
    topic_map = _build_topic_map(topics_df)

    wednesdays = calendar_df[calendar_df["weekday"] == "Wednesday"]

    for _, row in wednesdays.iterrows():

        d = row["date"]

        # Step 1: selector picks the person fairly
        responsible = pick_person_fair(
            pep_df,
            d,
            roles=INTERMEDIATE_ROLES,
            duty_priority=[SPAETDIENST, BUERO_FORSCHUNG_OA, TAGDIENST_OA],
            selector=selector,
        )

        # Step 2: find their most overdue topic
        topic = _pick_topic_for_person(responsible, topic_map, d)

        events.append({
            "date":        d,
            "time":        "14:30-15:15",
            "event_type":  "Mittwoch_Curriculum",
            "responsible": responsible,
            "topic":       topic,
            "room":        "",
        })

    return pd.DataFrame(events)


# -------------------------
# TOPIC MAP
# -------------------------

def _build_topic_map(topics_df):
    """
    Parse the Mittwoch topic sheet into a dict keyed by lastname.

    Each value is a list of topic dicts (one person can have multiple topics):
      { "thema": str, "last_date": pd.Timestamp }

    The list is mutable — we update last_date in-memory as topics are used,
    so within one planning run the rotation stays correct across months.

    Expected sheet columns (case-insensitive):
      Verantwortlich | Bereich | Thema | Datum (letzter Vortrag) | Rolle | Notizen
    """
    if topics_df is None or topics_df.empty:
        return {}

    df = topics_df.copy()
    df.columns = df.columns.str.lower().str.strip()

    col_thema  = _find_col(df, ["thema", "topic"])
    col_person = _find_col(df, ["verantwortlich", "responsible", "person", "name"])
    col_date   = _find_col(df, [
        "datum (letzter vortrag)", "datum letzter vortrag",
        "letzter vortrag", "last date", "datum",
    ])

    if not col_thema or not col_person:
        return {}

    topic_map = {}  # lastname -> list of { thema, last_date }

    for _, row in df.iterrows():
        thema = str(row.get(col_thema, "") or "").strip()
        if not thema:
            continue

        person_raw = str(row.get(col_person, "") or "").strip()
        if not person_raw:
            continue

        lastname = _extract_lastname(person_raw.lower())
        if not lastname:
            continue

        last_date = pd.Timestamp("1900-01-01")
        if col_date:
            parsed = pd.to_datetime(row.get(col_date), errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                last_date = parsed

        topic_map.setdefault(lastname, []).append({
            "thema":     thema,
            "last_date": last_date,
        })

    return topic_map


def _pick_topic_for_person(responsible, topic_map, date):
    """
    Given the selected person's name (e.g. 'hahn markus' or 'h. hahn'),
    find their most overdue topic (oldest last_date) and mark it as used today.
    Returns the topic string, or a generic fallback if nothing found.
    """
    if not responsible or not topic_map:
        return "Mittwochscurriculum"

    lastname = _extract_lastname(str(responsible).lower())
    topics   = topic_map.get(lastname)

    if not topics:
        return "Mittwochscurriculum"

    # Pick the topic with the oldest last_date (most overdue)
    topics.sort(key=lambda t: t["last_date"])
    chosen = topics[0]

    # Update in-memory so this topic rotates within this run
    chosen["last_date"] = pd.Timestamp(date)

    return chosen["thema"]


def _find_col(df, candidates):
    """Return the first matching column name from candidates list."""
    for c in candidates:
        if c in df.columns:
            return c
    return None
