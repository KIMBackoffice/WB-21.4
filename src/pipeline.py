# src/pipeline.py

import pandas as pd
from datetime import date, timedelta

# =========================
# IMPORT SCHEDULERS
# =========================

from src.scheduler.kimsim import schedule_kimsim
from src.scheduler.teaching_tuesday import schedule_teaching_tuesday
from src.scheduler.imc_updates import schedule_imc_updates
from src.scheduler.trauma_schockraum import schedule_trauma
from src.scheduler.bedside import schedule_bedside
from src.scheduler.tte import schedule_tte
from src.scheduler.masterclass import schedule_masterclass
from src.scheduler.kinae_bs import schedule_kinae_bs
from src.scheduler.nds_fallbesprechung import schedule_nds
from src.scheduler.ofobi import schedule_ofobi
from src.scheduler.interprof_therapieplanung import schedule_therapy
# NEW
from src.scheduler.angehoerige import schedule_angehoerige
from src.scheduler.montagscurriculum import schedule_montagscurriculum
from src.scheduler.pflegeassistenten import schedule_pflegeassistenten
from src.scheduler.sitzungen import schedule_sitzungen
from src.scheduler.diverse import schedule_diverse
from src.scheduler.fokus_intensivpflege import schedule_fokus_intensivpflege  
from src.scheduler.epic_update import schedule_epic_update
from src.scheduler.fachentwicklung import schedule_fachentwicklung

from src.scheduler.tuesday import build_tuesday_schedule
from src.scheduler.wednesday import build_wednesday_schedule
from src.scheduler.friday import build_friday_schedule

from src.selector import SmartFairSelector
from src.metadata import EVENT_METADATA
from src.feiertage import FEIERTAGE_DATES, get_feiertag_name

from src.utils_names import format_people


# =========================
# GLOBAL DATE PARSER
# =========================

def parse_date(x):
    return pd.to_datetime(x, errors="coerce", dayfirst=True).normalize()


# =========================
# SCHEMA FIXER
# =========================

def ensure_schema(df):

    required = ["date", "time", "event_type", "responsible", "topic", "room"]

    if df is None or df.empty:
        return pd.DataFrame(columns=required)

    df = df.copy()

    for col in required:
        if col not in df.columns:
            df[col] = None

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()

    return df[required]


# =========================
# CALENDAR
# =========================

def generate_calendar(year, month):
    """
    Generate all weekdays in the given month, excluding public holidays
    (Feiertage Kanton Bern). Holidays are skipped so that Tuesday/Wednesday/
    Friday schedulers never produce algorithm-generated events on those days.
    Sheet-driven events are added separately and are unaffected.
    """
    start = date(year, month, 1)
    rows = []
    d = start

    while d.month == month:

        ts = pd.Timestamp(d)

        # skip weekends
        if d.weekday() <= 4:

            # skip public holidays — algorithm events won't be generated
            if ts.normalize() not in FEIERTAGE_DATES:
                rows.append({
                    "date": ts,
                    "weekday": d.strftime("%A"),
                    "weekday_num": d.weekday(),
                    "day": d.day,
                    "week": d.isocalendar()[1]
                })
            else:
                print(
                    f"[Feiertag] Skipped {d.strftime('%A %d.%m.%Y')} "
                    f"({get_feiertag_name(ts)}) from calendar"
                )

        d += timedelta(days=1)

    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)


def add_weekday_position(calendar):

    calendar = calendar.sort_values("date")

    calendar["weekday_position"] = (
        calendar.groupby("weekday").cumcount() + 1
    )

    return calendar


# =========================
# PERSON STATS
# =========================

def build_person_stats(pep_df):

    if pep_df is None or pep_df.empty:
        return {"first_seen": {}}

    first_seen = (
        pep_df.groupby("name_clean")["date"]
        .min()
        .to_dict()
    )

    return {"first_seen": first_seen}


# =========================
# ENRICHMENT
# =========================

def enrich_schedule(df):

    df = df.copy()

    rooms = []
    topics = []

    for _, row in df.iterrows():

        meta = EVENT_METADATA.get(row["event_type"], {})

        room = row.get("room") or meta.get("room", "")
        prefix = meta.get("prefix", "")
        topic = str(row.get("topic", "") or "")

        if prefix:

            if "Case of the Day" in topic:
                topic = prefix

            elif prefix not in topic:
                topic = f"{prefix} {topic}".strip()

        rooms.append(room)
        topics.append(topic)

    df["room"] = rooms
    df["topic"] = topics

    return df


# =========================
# FRIDAY CONFLICT RESOLUTION
# =========================

def resolve_friday_conflicts(df):

    df = df.copy()

    df["weekday"] = df["date"].dt.day_name()

    cleaned = []

    for date, group in df.groupby("date"):

        if group["weekday"].iloc[0] != "Friday":
            cleaned.append(group)
            continue

        has_bedside = (group["event_type"] == "Bedside_Infektiologie").any()

        if has_bedside:
            group = group[group["event_type"] != "Journal_Club"]

        cleaned.append(group)

    return pd.concat(cleaned).drop(columns=["weekday"])


# =========================
# MAIN PIPELINE
# =========================

def generate_full_schedule(year, month, data):

    def get_df(key):
        df = data.get(key)
        return df if df is not None else pd.DataFrame()

    # -------------------------
    # CALENDAR
    # -------------------------
    calendar = add_weekday_position(
        generate_calendar(year, month)
    )

    # -------------------------
    # PEP CLEANING
    # -------------------------
    pep_df = get_df("pep")

    pep_df = pep_df.copy()

    pep_df["date"] = pd.to_datetime(pep_df["date"], errors="coerce").dt.normalize()

    pep_df["duty_code"] = (
        pd.to_numeric(pep_df["duty_code"], errors="coerce")
        .fillna(-1)
        .astype(int)
    )

    pep_df["role_code"] = pep_df["role_code"].astype(str).str.strip()

    pep_df["name_clean"] = pep_df["name_clean"].astype(str).str.strip().str.lower()

    selector = SmartFairSelector(
        person_stats=build_person_stats(pep_df),
        history_df=get_df("history")   # feeds historical assignments into scoring
    )

    # -------------------------
    # SHEET-BASED
    # -------------------------
    bedside    = ensure_schema(schedule_bedside(get_df("bedside")))
    kimsim     = ensure_schema(schedule_kimsim(get_df("sim")))
    teaching   = ensure_schema(schedule_teaching_tuesday(get_df("teaching")))
    imc        = ensure_schema(schedule_imc_updates(get_df("imc")))
    trauma     = ensure_schema(schedule_trauma(get_df("trauma")))
    tte        = ensure_schema(schedule_tte(get_df("tte")))
    master     = ensure_schema(schedule_masterclass(get_df("masterclass")))
    pflege     = ensure_schema(schedule_kinae_bs(
        get_df("basale"),
        get_df("kinae")
    ))
    nds        = ensure_schema(schedule_nds(get_df("nds")))
    ofobi      = ensure_schema(schedule_ofobi(get_df("ofobi")))

    angehoerige       = ensure_schema(schedule_angehoerige(get_df("angehoerige")))
    montagscurriculum = ensure_schema(schedule_montagscurriculum(get_df("montagscurriculum")))
    pflegeassistenten = ensure_schema(schedule_pflegeassistenten(get_df("pflegeassistenten")))
    sitzungen         = ensure_schema(schedule_sitzungen(get_df("sitzungen")))
    diverse           = ensure_schema(schedule_diverse(get_df("diverse")))
    fokus             = ensure_schema(schedule_fokus_intensivpflege(get_df("fokus")))
    epic              = ensure_schema(schedule_epic_update(get_df("epic")))
    fachentwicklung   = ensure_schema(schedule_fachentwicklung(get_df("fachentwicklung")))

    # -------------------------
    # FIXED
    # -------------------------
    therapy = ensure_schema(schedule_therapy(calendar))

    # -------------------------
    # ALGORITHM
    # -------------------------
    tuesday = ensure_schema(build_tuesday_schedule(
        calendar,
        get_df("physio"),
        pep_df,
        selector
    ))

    wednesday = ensure_schema(build_wednesday_schedule(
        calendar,
        pep_df,
        get_df("mittwoch"),
        selector
    ))

    friday = ensure_schema(build_friday_schedule(
        calendar,
        pep_df,
        selector
    ))

    # -------------------------
    # COMBINE
    # -------------------------
    full = pd.concat([
        kimsim,
        teaching,
        imc,
        trauma,
        bedside,
        tte,
        master,
        pflege,
        nds,
        ofobi,
        therapy,
        tuesday,
        wednesday,
        friday, 
        angehoerige,
        montagscurriculum,
        pflegeassistenten,
        sitzungen,
        diverse,
        fokus,
        epic,
        fachentwicklung,
    ], ignore_index=True)

    # -------------------------
    # GLOBAL DATE FIX
    # -------------------------
    full["date"] = pd.to_datetime(full["date"], errors="coerce").dt.normalize()

    # -------------------------
    # FILTER MONTH
    # -------------------------
    full = full[
        (full["date"].dt.year == year) &
        (full["date"].dt.month == month)
    ]

    # -------------------------
    # REMOVE ALGORITHM EVENTS ON FEIERTAGE
    # -------------------------
    # Sheet-driven events (KimSim, Teaching Tuesday, Bedside, etc.) are kept —
    # they were planned deliberately and should appear even on holidays.
    # Only algorithm-generated events (Tuesday/Wednesday/Friday rotation) are removed.

    ALGORITHM_EVENTS = {
        "COD_SENIOR",
        "COD_JUNIOR",
        "PEER",
        "PHYSIO",
        "Mittwoch_Curriculum",
        "Journal_Club",
        "Therapieplanung",   # fixed but auto-generated every Thursday
    }

    def _feiertag_mask(row):
        """True = keep this row."""
        if row["date"] not in FEIERTAGE_DATES:
            return True  # not a holiday → keep
        if row["event_type"] not in ALGORITHM_EVENTS:
            return True  # sheet-driven → keep even on holiday
        return False      # algorithm-generated on holiday → remove

    keep_mask = full.apply(_feiertag_mask, axis=1)
    removed = full[~keep_mask].copy()
    full = full[keep_mask].copy()

    # log removed events for transparency (visible in Streamlit spinner output)
    for _, r in removed.iterrows():
        holiday_name = get_feiertag_name(r["date"])
        print(
            f"[Feiertag] Removed {r['event_type']} on "
            f"{r['date'].strftime('%d.%m.%Y')} ({holiday_name})"
        )

    # -------------------------
    # ENRICH
    # -------------------------
    full = enrich_schedule(full)

    # -------------------------
    # FIX FRIDAY COLLISIONS
    # -------------------------
    full = resolve_friday_conflicts(full)

    # -------------------------
    # SORT
    # -------------------------
    full = full.sort_values(["date", "time"])

    # -------------------------
    # CLEAN NAMES
    # -------------------------
    full["responsible"] = full["responsible"].apply(format_people)

    return full.reset_index(drop=True)


# =========================
# MULTI-MONTH AWARE SCHEDULE
# =========================

def generate_full_schedule_aware(year, month, data, finalized_months=None):
    """
    Generate the schedule for a single month, but with a selector that
    has already processed ALL other PEP months first — in chronological order.

    This fixes two problems:
    1. Single-month blindness: generating April alone means the selector
       doesn't know what it will assign in May/June. Running all months
       through one shared selector fixes this.
    2. History name mismatch: the selector now uses lastname-based lookup
       so history entries like 'h. grogg-trachsel' correctly penalize
       PEP entries like 'grogg-trachsel hanna'.

    Returns only the requested month's schedule.
    """
    def get_df(key):
        df = data.get(key)
        return df if df is not None else pd.DataFrame()

    pep_df_raw = get_df("pep").copy()

    if pep_df_raw.empty:
        return generate_full_schedule(year, month, data)

    pep_df_raw["date"]       = pd.to_datetime(pep_df_raw["date"], errors="coerce").dt.normalize()
    pep_df_raw["duty_code"]  = pd.to_numeric(pep_df_raw["duty_code"], errors="coerce").fillna(-1).astype(int)
    pep_df_raw["role_code"]  = pep_df_raw["role_code"].astype(str).str.strip()
    pep_df_raw["name_clean"] = pep_df_raw["name_clean"].astype(str).str.strip().str.lower()

    all_pep_months = sorted(
        pep_df_raw["date"].dt.month.dropna().astype(int).unique()
    )

    if month not in all_pep_months:
        return generate_sheet_only_schedule(year, month, data)

    finalized_months = finalized_months or set()

    # one shared selector — history already includes finalized months' assignments
    selector = SmartFairSelector(
        person_stats=build_person_stats(pep_df_raw),
        history_df=get_df("history")
    )

    target_schedule = None

    for m in all_pep_months:

        calendar  = add_weekday_position(generate_calendar(year, m))

        # sheet-based (sliced to month in filter step below)
        bedside    = ensure_schema(schedule_bedside(get_df("bedside")))
        kimsim     = ensure_schema(schedule_kimsim(get_df("sim")))
        teaching   = ensure_schema(schedule_teaching_tuesday(get_df("teaching")))
        imc        = ensure_schema(schedule_imc_updates(get_df("imc")))
        trauma     = ensure_schema(schedule_trauma(get_df("trauma")))
        tte        = ensure_schema(schedule_tte(get_df("tte")))
        master     = ensure_schema(schedule_masterclass(get_df("masterclass")))
        pflege     = ensure_schema(schedule_kinae_bs(get_df("basale"), get_df("kinae")))
        nds        = ensure_schema(schedule_nds(get_df("nds")))
        ofobi      = ensure_schema(schedule_ofobi(get_df("ofobi")))
        therapy    = ensure_schema(schedule_therapy(calendar))
        angehoerige       = ensure_schema(schedule_angehoerige(get_df("angehoerige")))
        montagscurriculum = ensure_schema(schedule_montagscurriculum(get_df("montagscurriculum")))
        pflegeassistenten = ensure_schema(schedule_pflegeassistenten(get_df("pflegeassistenten")))
        sitzungen         = ensure_schema(schedule_sitzungen(get_df("sitzungen")))
        diverse           = ensure_schema(schedule_diverse(get_df("diverse")))
        fokus             = ensure_schema(schedule_fokus_intensivpflege(get_df("fokus")))
        epic              = ensure_schema(schedule_epic_update(get_df("epic")))

        # algorithm events — SHARED selector carries memory month-to-month
        tuesday   = ensure_schema(build_tuesday_schedule(calendar, get_df("physio"), pep_df_raw, selector))
        wednesday = ensure_schema(build_wednesday_schedule(calendar, pep_df_raw, get_df("mittwoch"), selector))
        friday    = ensure_schema(build_friday_schedule(calendar, pep_df_raw, selector))

        full = pd.concat([
            kimsim, teaching, imc, trauma, bedside, tte, master,
            pflege, nds, ofobi, therapy,
            angehoerige, montagscurriculum, pflegeassistenten, sitzungen, diverse,
            fokus, epic, tuesday, wednesday, friday,
        ], ignore_index=True)

        full["date"] = pd.to_datetime(full["date"], errors="coerce").dt.normalize()
        full = full[(full["date"].dt.year == year) & (full["date"].dt.month == m)]

        ALGORITHM_EVENTS = {"COD_SENIOR", "COD_JUNIOR", "PEER", "PHYSIO",
                             "Mittwoch_Curriculum", "Journal_Club", "Therapieplanung"}
        full = full[
            ~((full["date"].isin(FEIERTAGE_DATES)) & (full["event_type"].isin(ALGORITHM_EVENTS)))
        ].copy()

        full = enrich_schedule(full)
        full = resolve_friday_conflicts(full)
        full = full.sort_values(["date", "time"])
        full["responsible"] = full["responsible"].apply(format_people)

        if m == month:
            target_schedule = full.reset_index(drop=True)
            # continue running remaining months so selector stays warm

    return target_schedule if target_schedule is not None else pd.DataFrame()

def build_placeholder_schedule(calendar, physio_df):
    """
    Build algorithm-slot events with NO responsible person assigned.
    Used for months without PEP data — slots appear in the calendar so
    planners can see what needs to be filled, but responsible is blank.

    Mirrors the exact slot logic from tuesday.py, wednesday.py, friday.py:
      Tuesday:    COD_SENIOR (pos=1) / PHYSIO (even month pos=2) /
                  PEER / COD_JUNIOR (rotation)
      Wednesday:  Mittwoch_Curriculum (every Wednesday, topic from sheet)
      Friday:     Journal_Club (intermediate slot + AA slot shown as one row)
    """
    events = []

    # -------------------------
    # TUESDAY — same logic as tuesday.py, no assignment
    # -------------------------
    tuesdays = calendar[calendar["weekday"] == "Tuesday"]
    physio_index = 0

    for _, row in tuesdays.iterrows():
        d = row["date"]
        pos = row["weekday_position"]
        is_even_month = (d.month % 2 == 0)

        if pos == 1:
            subtype = "COD_SENIOR"
            topic   = "S - Case of the Day (COD)"

        elif is_even_month:
            if pos == 2:
                subtype = "PHYSIO"
                if physio_df is not None and not physio_df.empty:
                    topic = "Physio Teaching"  # article title used only in emails, not displayed
                else:
                    topic = "Physio Teaching"
                physio_index += 1
            elif pos % 2 == 1:
                subtype = "PEER"
                topic   = "Peer-Teaching Session"
            else:
                subtype = "COD_JUNIOR"
                topic   = "Case of the Day (COD)"

        else:
            if pos % 2 == 0:
                subtype = "PEER"
                topic   = "Peer-Teaching Session"
            else:
                subtype = "COD_JUNIOR"
                topic   = "Case of the Day (COD)"

        events.append({
            "date":       d,
            "time":       "11:30-11:45",
            "event_type": subtype,
            "responsible": None,   # placeholder — no PEP data
            "topic":      topic,
            "room":       "INO E218",
        })

    # -------------------------
    # WEDNESDAY — Mittwoch_Curriculum placeholder
    # -------------------------
    for _, row in calendar[calendar["weekday"] == "Wednesday"].iterrows():
        events.append({
            "date":       row["date"],
            "time":       "14:30-15:15",
            "event_type": "Mittwoch_Curriculum",
            "responsible": None,
            "topic":      "Mittwochscurriculum",
            "room":       "INO E218",
        })

    # -------------------------
    # FRIDAY — Journal Club placeholder (both slots shown as one row)
    # -------------------------
    for _, row in calendar[calendar["weekday"] == "Friday"].iterrows():
        events.append({
            "date":       row["date"],
            "time":       "14:30-15:15",
            "event_type": "Journal_Club",
            "responsible": None,
            "topic":      "Journal Club",
            "room":       "INO E218",
        })

    return pd.DataFrame(events) if events else pd.DataFrame()


# =========================
# SHEET-ONLY + PLACEHOLDER SCHEDULE
# =========================

def generate_sheet_only_schedule(year, month, data):
    """
    Generate a schedule for months without PEP roster data.

    - Sheet-driven events: fully populated (responsible, topic, room from sheet)
    - Algorithm events (COD, PEER, PHYSIO, Mittwoch, Journal Club):
        appear as placeholders with responsible=None so planners can see
        which slots need to be filled manually
    """

    def get_df(key):
        df = data.get(key)
        return df if df is not None else pd.DataFrame()

    # calendar needed for weekday iteration + Feiertage filtering
    calendar = add_weekday_position(
        generate_calendar(year, month)
    )

    # -------------------------
    # SHEET-BASED
    # -------------------------
    bedside    = ensure_schema(schedule_bedside(get_df("bedside")))
    kimsim     = ensure_schema(schedule_kimsim(get_df("sim")))
    teaching   = ensure_schema(schedule_teaching_tuesday(get_df("teaching")))
    imc        = ensure_schema(schedule_imc_updates(get_df("imc")))
    trauma     = ensure_schema(schedule_trauma(get_df("trauma")))
    tte        = ensure_schema(schedule_tte(get_df("tte")))
    master     = ensure_schema(schedule_masterclass(get_df("masterclass")))
    pflege     = ensure_schema(schedule_kinae_bs(
        get_df("basale"),
        get_df("kinae")
    ))
    nds        = ensure_schema(schedule_nds(get_df("nds")))
    ofobi      = ensure_schema(schedule_ofobi(get_df("ofobi")))
    therapy    = ensure_schema(schedule_therapy(calendar))
    angehoerige       = ensure_schema(schedule_angehoerige(get_df("angehoerige")))
    montagscurriculum = ensure_schema(schedule_montagscurriculum(get_df("montagscurriculum")))
    pflegeassistenten = ensure_schema(schedule_pflegeassistenten(get_df("pflegeassistenten")))
    sitzungen         = ensure_schema(schedule_sitzungen(get_df("sitzungen")))
    diverse           = ensure_schema(schedule_diverse(get_df("diverse")))
    fokus             = ensure_schema(schedule_fokus_intensivpflege(get_df("fokus")))
    epic              = ensure_schema(schedule_epic_update(get_df("epic")))

    placeholders = ensure_schema(
        build_placeholder_schedule(calendar, get_df("physio"))
    )

    full = pd.concat([
        kimsim, teaching, imc, trauma, bedside, tte, master,
        pflege, nds, ofobi, therapy,
        angehoerige, montagscurriculum, pflegeassistenten, sitzungen, diverse,
        fokus, epic,
        placeholders,
    ], ignore_index=True)

    full["date"] = pd.to_datetime(full["date"], errors="coerce").dt.normalize()

    # filter to month
    full = full[
        (full["date"].dt.year == year) &
        (full["date"].dt.month == month)
    ]

    # Feiertage: sheet events kept, algorithm placeholders removed
    ALGORITHM_EVENTS = {
        "COD_SENIOR", "COD_JUNIOR", "PEER", "PHYSIO",
        "Mittwoch_Curriculum", "Journal_Club", "Therapieplanung",
    }

    full = full[
        ~((full["date"].isin(FEIERTAGE_DATES)) &
          (full["event_type"].isin(ALGORITHM_EVENTS)))
    ].copy()

    full = enrich_schedule(full)
    full = resolve_friday_conflicts(full)
    full = full.sort_values(["date", "time"])
    full["responsible"] = full["responsible"].apply(format_people)
    full["month"] = month

    return full.reset_index(drop=True)
