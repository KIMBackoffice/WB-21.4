# =========================
# FAIRNESS ANALYSIS
# =========================
import pandas as pd
import re


# -------------------------
# NORMALIZE NAME
# -------------------------
def normalize_name(name):

    if pd.isna(name):
        return None

    name = str(name).lower().strip()

    # remove special chars
    name = re.sub(r"[^a-zäöü.\- ]", "", name)

    # normalize spacing
    name = re.sub(r"\s+", " ", name)

    # normalize compound initials: "m.- e." / "m. e." / "m.e." → "m.e."
    # covers old PDF format "m.- e. jaquier" → "m.e. jaquier"
    name = re.sub(r"([a-zäöü])\.\s*-?\s*([a-zäöü])\.", r"\1.\2.", name)

    # normalize Y.A. Que variations
    name = name.replace("y.- a.", "y.")
    name = name.replace("y.a.", "y.")
    name = name.replace("y. a.", "y.")

    # normalize h.-p. → h.p. style (hyphenated initials without space)
    name = re.sub(r"([a-zäöü])\.-([ a-zäöü])", r"\1.\2", name)

    return name.strip()


# -------------------------
# REMOVE NON-REAL PERSONS
# -------------------------
def is_valid_person(name):

    if name is None:
        return False

    name = name.lower()

    blacklist = [
        "firma",
        "fallführende",
        "uk",
    ]

    for b in blacklist:
        if b in name:
            return False

    # remove date-like
    if re.search(r"\d{2}\.\d{2}\.\d{4}", name):
        return False

    return True


# -------------------------
# SPLIT MULTI-PERSON
# -------------------------
def explode_persons(df):

    df = df.copy()

    df["person"] = df["responsible"].astype(str).str.lower()
    df = df.assign(person=df["person"].str.split("/"))
    df = df.explode("person")

    df["person"] = df["person"].str.strip()

    return df


# -------------------------
# EVENTS THAT COUNT FOR FAIRNESS
# -------------------------
# These are the events used in:
#   1. compute_fairness_from_schedule() — counts planned assignments per person
#   2. compute_fairness_from_schedule() — filters history sheet to same events
#   3. build_alternatives()             — finds over-assigned persons + alternatives
#
# RULES for inclusion:
#   - Must be algorithmically assigned (tuesday.py, wednesday.py, friday.py)
#     → i.e. the selector picks WHO presents, so fairness tracking makes sense
#   - Must NOT be sheet-driven fixed assignments
#     → e.g. Teaching_Tuesday, Bedside_Infektiologie, TTE_Curriculum are excluded
#     → those have a fixed responsible person from the Google Sheet, not rotated
#   - COD_SENIOR excluded here (but included in validation.py)
#     → COD_SENIOR is assigned to senior doctors (CA/SCA/LA/SFA_I) — separate pool
#     → fairness for seniors tracked separately if needed
#
# EVENT          SOURCE FILE     ASSIGNED BY         ROLE POOL
# COD_JUNIOR     tuesday.py      assign_person()     AA
# PEER           tuesday.py      assign_person()     AA
# PHYSIO         tuesday.py      assign_person()     AA
# Journal_Club   friday.py       pick_person_fair()  INTERMEDIATE + AA
# Mittwoch_Curriculum wednesday.py pick_person_fair() INTERMEDIATE
# -------------------------
RELEVANT_EVENTS = {
    "COD_SENIOR",        # tuesday.py — SENIOR role — S-Dienst (823)
    "COD_JUNIOR",        # tuesday.py — AA role — Case of the Day junior
    "PEER",              # tuesday.py — AA role — Peer Teaching session
    "PHYSIO",            # tuesday.py — AA role — Physiologie Talk
    "Journal_Club",      # friday.py  — INTERMEDIATE + AA — Journal Club
    "Mittwoch_Curriculum", # wednesday.py — INTERMEDIATE — Mittwochscurriculum
}


# -------------------------
# BUILD MULTI MONTH PLAN
# -------------------------
def build_multi_month_schedule(year, months, data, generator):

    schedules = []

    for m in months:
        sched = generator(year, m, data)
        sched["month"] = m
        schedules.append(sched)

    return pd.concat(schedules, ignore_index=True)


# -------------------------
# MAIN FAIRNESS FUNCTION
# -------------------------
def compute_fairness_from_schedule(schedule_all, history_df=None):

    df = schedule_all.copy()

    # -------------------------
    # FILTER EVENTS
    # -------------------------
    df = df[df["event_type"].isin(RELEVANT_EVENTS)]

    # -------------------------
    # SPLIT PEOPLE
    # -------------------------
    df = explode_persons(df)

    # -------------------------
    # CLEAN NAMES
    # -------------------------
    df["person"] = df["person"].apply(normalize_name)
    df = df[df["person"].apply(is_valid_person)]

    # -------------------------
    # CURRENT COUNTS
    # -------------------------
    planned_counts = df["person"].value_counts()

    planned = pd.DataFrame({
        "person": planned_counts.index,
        "planned": planned_counts.values
    })

    # -------------------------
    # HISTORY
    # -------------------------
    history = pd.DataFrame(columns=["person", "historical"])  # default: no history

    if history_df is not None and not history_df.empty:
    
        hist = history_df.copy()
    
        # Filter to relevant events only when column exists.
        # If event_type column is missing (older history format without that column),
        # keep ALL rows so history contributions are not silently lost.
        if "event_type" in hist.columns:
            hist = hist[hist["event_type"].isin(RELEVANT_EVENTS)]

        # -------------------------
        # CLEAN PERSON COLUMN
        # -------------------------
        if "responsible_clean" not in hist.columns:
            if "responsible" in hist.columns:
                hist["responsible_clean"] = hist["responsible"]
            else:
                hist = pd.DataFrame()

        if not hist.empty:
            hist["person"] = (
                hist["responsible_clean"]
                .astype(str)
                .str.lower()
                .str.strip()
            )

            # split (IMPORTANT if history has "/")
            hist = hist.assign(person=hist["person"].str.split("/"))
            hist = hist.explode("person")

            hist["person"] = hist["person"].str.strip()

            # normalize + clean
            hist["person"] = hist["person"].apply(normalize_name)
            hist = hist[hist["person"].apply(is_valid_person)]

            # COUNT
            if hist.empty:
                history = pd.DataFrame(columns=["person", "historical"])
            else:
                hist_counts = hist["person"].value_counts()
                history = pd.DataFrame({
                    "person": hist_counts.index,
                    "historical": hist_counts.values
                })
    # -------------------------
    # MERGE
    # -------------------------
    df = planned.merge(history, on="person", how="outer")

    df["planned"] = pd.to_numeric(df["planned"], errors="coerce").fillna(0).astype(float)
    df["historical"] = pd.to_numeric(df["historical"], errors="coerce").fillna(0).astype(float)

    # -------------------------
    # TOTAL LOAD
    # -------------------------
    df["total"] = df["planned"] + df["historical"]

    total = df["total"].sum()
    n = len(df)

    expected = total / n if n > 0 else 0

    df["expected"] = expected

    # -------------------------
    # FAIRNESS SCORE
    # -------------------------
    df["fairness_score"] = df["total"] - expected

    return df.sort_values("fairness_score", ascending=False)


# -------------------------
# LASTNAME EXTRACTOR (used for cross-format name matching)
# -------------------------

def _extract_lastname(name):
    """
    Extract lastname from any name format so we can match across:
      format_people output:  'H. Grogg-Trachsel'  → 'grogg-trachsel'
      fairness person col:   'h. grogg-trachsel'  → 'grogg-trachsel'
      pep name_clean:        'grogg-trachsel hannah' → 'grogg-trachsel'

    Strategy: lower everything, then take the first token that is NOT
    a single initial pattern like 'h.' or 'y.-a.'
    """
    if not name:
        return ""
    name = str(name).lower().strip()
    parts = name.split()
    non_initials = [
        p for p in parts
        if not re.match(r"^[a-zäöü]\.?(-[a-zäöü]\.?)?$", p)
    ]
    if non_initials:
        return non_initials[0]
    return parts[-1] if parts else ""


# -------------------------
# DUTY PRIORITY RULES PER EVENT TYPE
# Mirrors friday.py, wednesday.py, assigner.py exactly.
# NO fallback to "any" — only people in the listed duty sets are shown.
#
# EVENT              ROLE          DUTY PRIORITY (order matters, tier 1 = best)
# COD_JUNIOR         AA            TAGDIENST_AA only
# PEER               AA            TAGDIENST_AA only
# PHYSIO             AA            TAGDIENST_AA only
# Mittwoch_Curriculum INTERMEDIATE SPAETDIENST → BUERO_FORSCHUNG_OA → TAGDIENST_OA
# Journal_Club (int)  INTERMEDIATE SPAETDIENST → BUERO_FORSCHUNG_OA → TAGDIENST_OA
# Journal_Club (AA)   AA           SPAETDIENST → TAGDIENST_AA  (matches friday.py)
# -------------------------

# duty code sets — kept local to fairness.py, mirrored from config.py
_SPAETDIENST        = {102, 271, 166}
_TAGDIENST_AA       = {1072, 113, 719}
_TAGDIENST_OA       = {101, 119, 165}
_BUERO_FORSCHUNG_OA = {117, 705}
_INTERMEDIATE_ROLES = {"SOA", "OA_I", "OA_II", "SFA_II"}
_AA_ROLES           = {"AA"}
_SENIOR_ROLES       = {"CA", "SCA", "LA", "SFA_I"}
_S_DIENST           = {823}

EVENT_DUTY_RULES = {
    # tuesday.py — SENIOR only, S-Dienst (823)
    "COD_SENIOR": [
        (_SENIOR_ROLES, [_S_DIENST]),
    ],

    # tuesday.py / assigner.py — AA only on Tagdienst AA
    "COD_JUNIOR": [
        (_AA_ROLES, [_TAGDIENST_AA]),
    ],
    "PEER": [
        (_AA_ROLES, [_TAGDIENST_AA]),
    ],
    "PHYSIO": [
        (_AA_ROLES, [_TAGDIENST_AA]),
    ],

    # wednesday.py — INTERMEDIATE with full duty priority chain
    "Mittwoch_Curriculum": [
        (_INTERMEDIATE_ROLES, [_SPAETDIENST, _BUERO_FORSCHUNG_OA, _TAGDIENST_OA]),
    ],

    # friday.py — TWO slots with separate rules
    # intermediate: Spätdienst → Büro/Forschung → Tagdienst OA
    # AA:           Spätdienst → Tagdienst AA
    "Journal_Club": [
        (_INTERMEDIATE_ROLES, [_SPAETDIENST, _BUERO_FORSCHUNG_OA, _TAGDIENST_OA]),
        (_AA_ROLES,           [_SPAETDIENST, _TAGDIENST_AA]),   # matches friday.py exactly
    ],
}


def _get_duty_priority_label(duty_code, event_type, role):
    """
    Return a human-readable priority label for a duty code given the event + role context.
    Used in alternative display to show WHY someone is a good alternative.
    """
    if pd.isna(duty_code):
        return "?"

    dc = int(duty_code)

    if dc in _SPAETDIENST:
        return f"Spätdienst ({dc})"
    if dc in _TAGDIENST_AA and role in _AA_ROLES:
        return f"Tagdienst AA ({dc})"
    if dc in _TAGDIENST_OA and role in _INTERMEDIATE_ROLES:
        return f"Tagdienst OA ({dc})"
    if dc in _BUERO_FORSCHUNG_OA:
        return f"Büro/Forschung ({dc})"
    return f"duty {dc}"


def _find_alternatives_ordered(day_pep, role_pool, duty_priority, assigned_lastnames):
    """
    Find eligible alternatives for one slot (role_pool + duty_priority).

    STRICT: only show people who are in one of the defined duty_priority sets.
    NO fallback to "any person with the right role" — if someone is not on duty
    in one of the defined sets they are not a valid alternative.

    Returns list of dicts ordered by duty priority tier (tier 1 = best).
    Each dict: name, role, duty_code, duty_label, priority_tier
    """
    # only consider people in correct role AND one of the duty sets
    all_valid_duties = set().union(*duty_priority)

    eligible = day_pep[
        day_pep["role_code"].isin(role_pool) &
        day_pep["duty_code"].isin(all_valid_duties) &
        ~day_pep["lastname"].isin(assigned_lastnames)
    ].drop_duplicates("lastname")

    if eligible.empty:
        return []

    result = []
    seen = set()

    # iterate duty priority tiers in order — tier 1 is highest priority
    for tier, duty_set in enumerate(duty_priority, start=1):
        tier_candidates = eligible[eligible["duty_code"].isin(duty_set)]
        for _, alt in tier_candidates.iterrows():
            if alt["lastname"] in seen:
                continue
            seen.add(alt["lastname"])
            dc = alt["duty_code"]
            result.append({
                "name":          alt["name_clean"],
                "role":          alt["role_code"],
                "duty_code":     int(dc) if pd.notna(dc) else "?",
                "duty_label":    _get_duty_priority_label(dc, None, alt["role_code"]),
                "priority_tier": tier,
            })

    return result


# -------------------------
# ALTERNATIVES FOR OVER-ASSIGNED PERSONS
# -------------------------

def build_alternatives(schedule_all, pep_df, fairness_df, threshold=0):
    """
    For each person with fairness_score > threshold:
      - Find all their RELEVANT_EVENTS assignments
      - For each event, apply the CORRECT duty priority rules (per event type + role)
        mirroring friday.py, wednesday.py, assigner.py exactly
      - Show alternatives ordered by duty priority (Spätdienst first, etc.)

    Name matching via lastname extraction (handles all three name formats).

    Returns DataFrame with columns:
      person | date | weekday | event_type | topic | role | duty_code |
      duty_label | alternatives (list of ordered dicts)
    """

    if pep_df is None or pep_df.empty:
        return pd.DataFrame()

    # -------------------------
    # WHO IS OVER-EXPECTED
    # -------------------------
    over = fairness_df[fairness_df["fairness_score"] > threshold]["person"].tolist()

    if not over:
        return pd.DataFrame()

    # -------------------------
    # LASTNAME → FAIRNESS PERSON LOOKUP
    # -------------------------
    over_by_lastname = {_extract_lastname(p): p for p in over}

    # -------------------------
    # NORMALIZE PEP
    # -------------------------
    pep = pep_df.copy()
    pep["date"]       = pd.to_datetime(pep["date"], errors="coerce").dt.normalize()
    pep["name_clean"] = pep["name_clean"].astype(str).str.strip().str.lower()
    pep["lastname"]   = pep["name_clean"].apply(_extract_lastname)
    pep["duty_code"]  = pd.to_numeric(pep["duty_code"], errors="coerce")
    pep["role_code"]  = pep["role_code"].astype(str).str.strip()

    # -------------------------
    # FILTER SCHEDULE TO RELEVANT EVENTS
    # -------------------------
    sched = schedule_all[
        schedule_all["event_type"].isin(RELEVANT_EVENTS)
    ].copy()

    rows = []

    for _, row in sched.iterrows():

        event_type = row["event_type"]
        rules = EVENT_DUTY_RULES.get(event_type)

        if not rules:
            continue  # no rule defined → skip

        responsible_raw   = str(row.get("responsible", "") or "")
        assigned_display  = [p.strip() for p in responsible_raw.split("/")]
        assigned_lastnames = [_extract_lastname(p) for p in assigned_display]

        # check if any over-assigned person is in this row
        matches = [
            (ln, over_by_lastname[ln])
            for ln in assigned_lastnames
            if ln in over_by_lastname
        ]
        if not matches:
            continue

        d = pd.Timestamp(row["date"]).normalize()
        day_pep = pep[pep["date"] == d]

        if day_pep.empty:
            continue

        assigned_pep = day_pep[day_pep["lastname"].isin(assigned_lastnames)]

        # -------------------------
        # FOR EACH MATCHED OVER-ASSIGNED PERSON
        # -------------------------
        for lastname, fairness_person in matches:

            person_pep = assigned_pep[assigned_pep["lastname"] == lastname]

            if person_pep.empty:
                continue

            role = person_pep["role_code"].iloc[0]
            dc   = person_pep["duty_code"].iloc[0]
            duty = int(dc) if pd.notna(dc) else "?"

            # -------------------------
            # FIND THE MATCHING RULE FOR THIS PERSON'S ROLE
            # -------------------------
            matching_rule = None
            for role_pool, duty_priority in rules:
                if role in role_pool:
                    matching_rule = (role_pool, duty_priority)
                    break

            if matching_rule is None:
                continue  # person's role doesn't match any slot for this event

            role_pool, duty_priority = matching_rule

            # -------------------------
            # GET ORDERED ALTERNATIVES
            # -------------------------
            alt_list = _find_alternatives_ordered(
                day_pep,
                role_pool,
                duty_priority,
                assigned_lastnames
            )

            rows.append({
                "person":       fairness_person,
                "date":         row["date"].strftime("%d.%m.%Y"),
                "weekday":      row["date"].strftime("%A")[:2].upper(),
                "event_type":   event_type,
                "topic":        row["topic"],
                "role":         role,
                "duty_code":    duty,
                "duty_label":   _get_duty_priority_label(dc, event_type, role),
                "alternatives": alt_list,
            })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


# -------------------------
# FULL PIPELINE (FOR APP)
# -------------------------
def run_fairness_analysis(year, months, data, generator, history_df=None):

    schedule = build_multi_month_schedule(
        year,
        months,
        data,
        generator
    )

    fairness = compute_fairness_from_schedule(
        schedule,
        history_df
    )

    return schedule, fairness
