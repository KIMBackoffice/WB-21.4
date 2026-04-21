# src/data_loader.py

import time
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials


# =========================
# CONNECTION
# @st.cache_resource = one shared client per session
# Avoids re-authenticating on every sheet load (was 22 OAuth calls per load)
# =========================

@st.cache_resource
def get_gspread_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    return gspread.authorize(creds)


# =========================
# GENERIC SHEET LOADER
# - 1.2s delay between calls → stays under 60 reads/min quota
#   (22 sheets × 1.2s ≈ 26s total — acceptable for a cached one-time load)
# - 429 rate-limit errors: wait 30s before retry
# - Other API errors: exponential backoff (2s, 4s, 8s)
# =========================

_CALL_DELAY  = 0.5   # seconds between every API call (~12s for 23 sheets vs ~27s before)
_MAX_RETRIES = 5


def load_sheet(sheet_url, worksheet=0):
    client     = get_gspread_client()
    last_error = None

    for attempt in range(_MAX_RETRIES):
        try:
            time.sleep(_CALL_DELAY)
            sh   = client.open_by_url(sheet_url)
            ws   = sh.get_worksheet(worksheet)
            data = ws.get_all_values()
            break

        except gspread.exceptions.APIError as e:
            last_error  = e
            resp        = getattr(e, "response", None)
            status_code = resp.status_code if resp else 0

            if status_code == 429:
                wait = 60  # flat 60s — lets the 1-min quota window fully reset
                print(f"[load_sheet] Rate limit (429), waiting {wait}s (attempt {attempt+1}/{_MAX_RETRIES})")
                time.sleep(wait)
            else:
                wait = 2 ** (attempt + 1)
                print(f"[load_sheet] API error {status_code}, retrying in {wait}s")
                time.sleep(wait)
    else:
        raise last_error

    if not data:
        return pd.DataFrame()

    headers = data[0]

    cleaned_headers = []
    valid_indices = []

    for i, h in enumerate(headers):
        h = str(h).strip().lower()

        if not h:
            continue

        if h in cleaned_headers:
            h = f"{h}_{i}"

        cleaned_headers.append(h)
        valid_indices.append(i)

    cleaned_rows = [
        [row[i] if i < len(row) else "" for i in valid_indices]
        for row in data[1:]
    ]

    df = pd.DataFrame(cleaned_rows, columns=cleaned_headers)

    return df


# =========================
# HELPERS
# =========================

def parse_date(df, col="datum"):
    if col in df.columns:
        return pd.to_datetime(df[col], dayfirst=True, errors="coerce")
    return pd.NaT


# =========================
# LOADERS
# =========================

def load_teaching_tuesday(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_imc_updates(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_simulation(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_bedside(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_mittwoch(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_trauma_board(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_physio(url):
    df = load_sheet(url)
    return df


# =========================
# PEP
# =========================

def load_pep_clean(url):
    df = load_sheet(url)

    df["date"] = pd.to_datetime(
        df["datefixed"],
        errors="coerce",
        dayfirst=True
    ).dt.normalize()

    df["name_clean"] = df["name_clean"].str.lower().str.strip()

    df["duty_code"] = pd.to_numeric(df["duty_code"], errors="coerce")

    return df


# =========================
# TTE
# =========================

def load_tte(url):
    df = load_sheet(url)

    df["date"] = pd.to_datetime(df["datum"], dayfirst=True, errors="coerce")

    df = df[df["date"].notna()]

    start = df.get("startzeit", "")
    end = df.get("endzeit", "")

    df["time"] = start.astype(str) + "-" + end.astype(str)

    df["responsible"] = df.get("veranwortlich (vorname nachname)")
    df["topic"] = df.get("thema")
    df["room"] = df.get("raum")

    return df


# =========================
# MASTERCLASS
# =========================

def load_masterclass(url):
    df = load_sheet(url)

    df["date"] = pd.to_datetime(df["datum"], dayfirst=True, errors="coerce")

    df = df[df["date"].notna()]

    start = df.get("startzeit", "")
    end = df.get("endzeit", "")

    df["time"] = start.astype(str) + "-" + end.astype(str)

    df["responsible"] = df.get("veranwortlich (vorname nachname)")
    df["topic"] = df.get("thema")
    df["room"] = df.get("raum")

    return df


# =========================
# PFLEGE FORTBILDUNG — simple loaders (all same header structure)
# =========================

def load_angehoerige(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_montagscurriculum(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_pflegeassistenten(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_sitzungen(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_diverse(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


# =========================
# NEW LOADERS
# =========================

def load_fokus_intensivpflege(url):
    """Fokus Intensivpflege — same header as other Pflege sheets."""
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


def load_epic_update(url):
    """EPIC Update Schulungen — same header as other Pflege sheets."""
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


 
def load_fachentwicklung(url):
    df = load_sheet(url)
    df["date"] = parse_date(df)
    return df


# =========================
# HISTORY LOADER
# Normalises event_type values from old PDF-scraped history
# so both selector.py and fairness.py always receive clean data.
# =========================

# Map old PDF-scraped event_type labels → app event_type values
_HISTORY_EVENT_TYPE_MAP = {
    "Curriculum":          "Mittwoch_Curriculum",
    "curriculum":          "Mittwoch_Curriculum",
    "Mittwochscurriculum": "Mittwoch_Curriculum",
    "Journal Club":        "Journal_Club",
    "journal club":        "Journal_Club",
    "JournalClub":         "Journal_Club",
    "COD":                 "COD_JUNIOR",
    "cod":                 "COD_JUNIOR",
    # PEER / PHYSIO were labelled "Other" — cannot recover, left as-is
}


def load_history(url):
    """
    Load the Historical_Assignment sheet and normalise event_type values.
    This ensures both selector.py (penalty scoring) and fairness.py
    (fairness counts) always see consistent event_type strings.
    """
    df = load_sheet(url)

    if df is None or df.empty:
        return df

    # Normalise event_type
    if "event_type" in df.columns:
        df["event_type"] = (
            df["event_type"]
            .astype(str)
            .str.strip()
            .map(lambda v: _HISTORY_EVENT_TYPE_MAP.get(v, v))
        )

    # Ensure person column exists
    if "person" not in df.columns:
        if "responsible_clean" in df.columns:
            df["person"] = df["responsible_clean"]
        elif "responsible" in df.columns:
            df["person"] = df["responsible"]

    # Parse date if present
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)

    return df


# =========================
# CONFIRMATION PERSISTENCE
# =========================
# Uses a second worksheet "confirmations" in the History Google Sheet.
# Schema: month | year | reviewer | confirmed_at | finalized | finalized_at | admin_note
#
# This survives app restarts, cache clears, and re-deploys.
# =========================

CONFIRMATION_SHEET_URL = "https://docs.google.com/spreadsheets/d/1bFqR0bY7jx6b_sy-z3Tt9eVkUoUo4SMZF-sMRdj9tpg/edit?gid=0#gid=0"
CONFIRMATION_TAB_NAME  = "confirmations"


def _get_or_create_confirmation_tab():
    """Get the confirmations worksheet, creating it if it doesn't exist."""
    client = get_gspread_client()
    sh     = client.open_by_url(CONFIRMATION_SHEET_URL)

    try:
        ws = sh.worksheet(CONFIRMATION_TAB_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(
            title=CONFIRMATION_TAB_NAME,
            rows=200,
            cols=8
        )
        # write header row
        ws.append_row([
            "year", "month", "reviewer",
            "confirmed", "confirmed_at",
            "finalized", "finalized_at", "admin_note"
        ])

    return ws


def load_confirmations(year=2026):
    """
    Load confirmation state from the Google Sheet.
    Returns:
        confirmations: dict  { month: { reviewer: bool } }
        finalized:     set   { month, ... }
    """
    try:
        time.sleep(_CALL_DELAY)
        ws      = _get_or_create_confirmation_tab()
        records = ws.get_all_records()
    except Exception as e:
        print(f"[load_confirmations] Could not read: {e}")
        return {}, set()

    confirmations    = {}
    finalized_months = set()

    for row in records:
        if int(row.get("year", 0)) != year:
            continue
        m        = int(row.get("month", 0))
        reviewer = str(row.get("reviewer", "")).strip()

        if row.get("confirmed") == "TRUE" or row.get("confirmed") is True:
            confirmations.setdefault(m, {})[reviewer] = True

        if row.get("finalized") == "TRUE" or row.get("finalized") is True:
            finalized_months.add(m)

    return confirmations, finalized_months


def save_confirmation(year, month, reviewer, confirmed=True):
    """
    Upsert a reviewer confirmation for a month.
    Adds a new row if none exists, updates if it does.
    """
    try:
        time.sleep(_CALL_DELAY)
        ws      = _get_or_create_confirmation_tab()
        records = ws.get_all_records()

        # find existing row for this year/month/reviewer
        target_row = None
        for i, row in enumerate(records, start=2):  # row 1 = header
            if (int(row.get("year", 0)) == year and
                    int(row.get("month", 0)) == month and
                    str(row.get("reviewer", "")).strip() == reviewer):
                target_row = i
                break

        now_str = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")

        if target_row:
            ws.update(f"D{target_row}:E{target_row}", [["TRUE" if confirmed else "FALSE", now_str]])
        else:
            ws.append_row([year, month, reviewer, "TRUE" if confirmed else "FALSE", now_str, "FALSE", "", ""])

    except Exception as e:
        print(f"[save_confirmation] Could not write: {e}")
        raise


def save_finalization(year, month, admin_note=""):
    """
    Mark a month as finalized in the confirmations sheet.
    Updates all reviewer rows for this month to set finalized=TRUE.
    """
    try:
        time.sleep(_CALL_DELAY)
        ws      = _get_or_create_confirmation_tab()
        records = ws.get_all_records()

        now_str  = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
        updated  = False

        for i, row in enumerate(records, start=2):
            if (int(row.get("year", 0)) == year and
                    int(row.get("month", 0)) == month):
                ws.update(f"F{i}:H{i}", [["TRUE", now_str, admin_note]])
                updated = True

        if not updated:
            # no reviewer rows yet — write a finalization-only row
            ws.append_row([year, month, "ADM", "TRUE", now_str, "TRUE", now_str, admin_note])

    except Exception as e:
        print(f"[save_finalization] Could not write: {e}")
        raise
