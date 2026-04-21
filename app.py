# app.py

import streamlit as st
import pandas as pd
import datetime

from src.data_loader import (
    load_simulation,
    load_physio,
    load_imc_updates,
    load_teaching_tuesday,
    load_mittwoch,
    load_bedside,
    load_trauma_board,
    load_pep_clean,
    load_tte,
    load_masterclass,
    load_sheet,
    load_angehoerige,
    load_montagscurriculum,
    load_pflegeassistenten,
    load_sitzungen,
    load_diverse,
    load_fokus_intensivpflege,
    load_epic_update,
    load_fachentwicklung,
    load_history,
)

from src.pipeline import generate_full_schedule, generate_full_schedule_aware, generate_sheet_only_schedule
from src.validation import validate_schedule
from src.export_docx import export_to_word
from src.fairness import (
    build_multi_month_schedule,
    compute_fairness_from_schedule,
    build_alternatives,
    RELEVANT_EVENTS,
    normalize_name,
    is_valid_person,
    _find_alternatives_ordered,
    _extract_lastname,
    _get_duty_priority_label,
    EVENT_DUTY_RULES,
)
from src.email_templates import get_email_for_person
from src.data_loader import load_confirmations, save_confirmation, save_finalization
# email_lookup imported inside tab3 to avoid module-level import errors

st.set_page_config(
    page_title="KIM Weiterbildungsplanung",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS  (styles live in src/style.css — edit there, not here)
# ─────────────────────────────────────────────────────────────────────────────
def _load_css(*paths: str):
    """Load CSS from the first path that exists."""
    import os
    for path in paths:
        if os.path.exists(path):
            with open(path) as f:
                st.markdown(f.read(), unsafe_allow_html=True)
            return
    raise FileNotFoundError(f"Could not find CSS file in any of: {paths}")

_load_css("style.css", "src/style.css")


# ─────────────────────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────────────────────
_today = datetime.date.today().strftime("%d.%m.%Y")

_hcol, _ = st.columns([14, 1])
with _hcol:
    st.markdown(
        "<div class=\"kim-bar\">"
        "<div class=\"kim-bar-left\">"

        # ── Text-based Inselspital logo mark ──────────────────────────────
        "<div class=\"kim-logoblock\">"
        "<div class=\"kim-logo-words\">"
        "<span class=\"kim-logo-insel\">INSEL</span>"
        "<span class=\"kim-logo-spital\">SPITAL</span>"
        "</div>"
        "</div>"

        "<div class=\"kim-bar-divider\"></div>"

        # ── App name + department ──────────────────────────────────────────
        "<div class=\"kim-title\">"
        "Weiterbildungsplanung"
        "<span class=\"kim-subtitle\">"
        "Universitätsklinik f&uuml;r Intensivmedizin &nbsp;&middot;&nbsp; Inselspital Bern"
        "</span>"
        "</div>"
        "</div>"

        "<div class=\"kim-bar-right\">"
        "<div class=\"kim-meta-date\">" + _today + "</div>"
        "<div class=\"kim-meta-contact\">DEMO &nbsp;&middot;&nbsp; " + _today + " &nbsp;&middot;&nbsp; kim.backoffice1@gmail.com</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _banner(text, kind="info"):
    """Render a compact status banner (replaces st.info/success/warning/error)."""
    cls = {"info": "b-info", "ok": "b-ok", "warn": "b-warn", "err": "b-err"}.get(kind, "b-info")
    st.markdown(f'<div class="banner {cls}">{text}</div>', unsafe_allow_html=True)

def _sec(label, first=False):
    """Render a section label (replaces st.subheader/st.title)."""
    extra = " sec-first" if first else ""
    st.markdown(f'<div class="sec{extra}">{label}</div>', unsafe_allow_html=True)

def _loading(label, expanded=False):
    """Show a compact doctor-animation loader, then run as st.status context."""
    return st.status(label, expanded=expanded)

def _doc_loader(label: str):
    """Render the cute inline doctor-animation loader (non-blocking display)."""
    st.markdown(f"""
<div class="kim-loader-wrap">
  <svg class="kim-doc" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg"
       style="animation: doc-bob 1.4s ease-in-out infinite;">
    <!-- Doctor head -->
    <circle cx="16" cy="9" r="5" fill="#e8f4f1" stroke="#0b7b6b" stroke-width="1.2"/>
    <!-- Cap -->
    <rect x="11" y="5.5" width="10" height="2.2" rx="1" fill="#0b7b6b"/>
    <rect x="14.5" y="3.5" width="3" height="2.5" rx=".8" fill="#0b7b6b"/>
    <!-- Cross on cap -->
    <rect x="15.6" y="4" width=".8" height="1.8" fill="white"/>
    <rect x="15" y="4.6" width="2" height=".8" fill="white"/>
    <!-- Body / coat -->
    <rect x="11" y="14" width="10" height="11" rx="2" fill="white" stroke="#0b7b6b" stroke-width="1.1"/>
    <!-- Stethoscope -->
    <path d="M14 16 Q13 19 15 20 Q17 21 18 19" fill="none" stroke="#0b7b6b" stroke-width="1" stroke-linecap="round"/>
    <circle cx="18.2" cy="18.8" r="1.1" fill="#0b7b6b" opacity=".7"
            style="animation: doc-heartbeat 1.4s ease-in-out infinite;"/>
    <!-- Writing arm -->
    <g style="transform-origin: 21px 18px; animation: doc-arm 0.7s ease-in-out infinite;">
      <rect x="20" y="17" width="2" height="6" rx="1" fill="#e8f4f1" stroke="#0b7b6b" stroke-width="1"/>
      <!-- Pen -->
      <line x1="21" y1="23" x2="21" y2="26" stroke="#0d1b2e" stroke-width="1.2" stroke-linecap="round"/>
      <polygon points="20.4,26 21.6,26 21,27.5" fill="#0d1b2e"/>
    </g>
    <!-- Clipboard lines being written -->
    <rect x="12" y="17" width="5" height=".8" rx=".4" fill="#dce1e9"/>
    <rect x="12" y="19" width="4" height=".8" rx=".4" fill="#dce1e9"/>
    <rect x="12" y="21" width="3" height=".8" rx=".4" fill="#dce1e9"/>
    <!-- Legs -->
    <rect x="12.5" y="24.5" width="2.5" height="5" rx="1" fill="#0d1b2e" opacity=".7"/>
    <rect x="17" y="24.5" width="2.5" height="5" rx="1" fill="#0d1b2e" opacity=".7"/>
  </svg>
  <div>
    <div class="kim-loader-label">{label}</div>
    <div class="kim-dots"><span></span><span></span><span></span></div>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
MONTH_LABELS = {
    1: "Jan 2026", 2: "Feb 2026", 3: "Mär 2026", 4: "Apr 2026",
    5: "Mai 2026", 6: "Jun 2026", 7: "Jul 2026", 8: "Aug 2026",
    9: "Sep 2026", 10: "Okt 2026", 11: "Nov 2026", 12: "Dez 2026",
}
MONTH_MAP_WORD = {
    1: "JANUAR", 2: "FEBRUAR", 3: "MÄRZ", 4: "APRIL",
    5: "MAI", 6: "JUNI", 7: "JULI", 8: "AUGUST",
    9: "SEPTEMBER", 10: "OKTOBER", 11: "NOVEMBER", 12: "DEZEMBER",
}
MONTH_NAMES_DE = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}
WEEKDAY_DE = {
    "Monday": "MO", "Tuesday": "DI", "Wednesday": "MI",
    "Thursday": "DO", "Friday": "FR", "Saturday": "SA", "Sunday": "SO",
}

def _fmt_date_de(ts):
    wd = WEEKDAY_DE.get(ts.strftime("%A"), "")
    return f"{wd} {ts.strftime('%d.%m.%Y')}"


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING  (unchanged logic)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_all_data():
    """
    Load all Google Sheets. Each sheet is loaded individually with error
    handling so a single quota/permissions error doesn't crash the whole load.
    The data_loader.py enforces a 1.2s delay between calls to stay under
    the 60 reads/min API quota.
    """
    SHEET_LOADERS = [
        ("sim",               load_simulation,           "SIM_URL"),
        ("physio",            load_physio,               "PHYSIO_URL"),
        ("imc",               load_imc_updates,          "IMC_URL"),
        ("teaching",          load_teaching_tuesday,     "TEACHING_URL"),
        ("mittwoch",          load_mittwoch,             "MITTWOCH_URL"),
        ("bedside",           load_bedside,              "BEDSIDE_URL"),
        ("trauma",            load_trauma_board,         "TRAUMA_URL"),
        ("tte",               load_tte,                  "TTE_URL"),
        ("masterclass",       load_masterclass,          "MASTERCLASS_URL"),
        ("basale",            load_sheet,                "BASALE_URL"),
        ("kinae",             load_sheet,                "KINAESTHETIK_URL"),
        ("pep",               load_pep_clean,            "PEP_URL"),
        ("nds",               load_sheet,                "NDS_URL"),
        ("ofobi",             load_sheet,                "OFOBI_URL"),
        ("history",           load_history,              "HISTORY_URL"),
        ("angehoerige",       load_angehoerige,          "ANGEHOERIGE_URL"),
        ("montagscurriculum", load_montagscurriculum,    "MONTAG_URL"),
        ("pflegeassistenten", load_pflegeassistenten,    "PA_URL"),
        ("sitzungen",         load_sitzungen,            "SITZUNGEN_URL"),
        ("diverse",           load_diverse,              "DIVERSE_URL"),
        ("fokus",             load_fokus_intensivpflege, "FOKUS_URL"),
        ("epic",              load_epic_update,          "EPIC_URL"),
        ("fachentwicklung",   load_fachentwicklung,      "FACHENTWICKLUNG_URL"),
    ]
    data   = {}
    failed = []
    for key, loader, secret_key in SHEET_LOADERS:
        try:
            data[key] = loader(st.secrets[secret_key])
        except Exception as e:
            data[key] = None
            failed.append(f"{key} ({type(e).__name__})")
            print(f"[load_all_data] Failed to load '{key}': {e}")
    if failed:
        _banner(f"{len(failed)} Sheet(s) nicht geladen: {', '.join(failed)}. "
                "Betroffene Ereignisse fehlen im Plan. API-Quota oder Berechtigungen prüfen.",
                "warn")
    return data


def get_pep_months(data):
    pep_df = data.get("pep")
    if pep_df is not None and not pep_df.empty:
        return set(
            pd.to_datetime(pep_df["date"], errors="coerce")
            .dt.month.dropna().astype(int).unique()
        )
    return set()


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULE TABLE HELPER
# ─────────────────────────────────────────────────────────────────────────────
def _show_schedule(sched):
    """Render schedule — compact columns, no fixed height, all visible."""
    disp = sched.copy()
    disp["responsible"] = disp["responsible"].fillna("— TBD —")
    # Compact date: "MI 01.04." on one line, time separate
    disp["Datum"] = disp["date"].apply(
        lambda d: WEEKDAY_DE.get(d.strftime("%A"), "") + " " + d.strftime("%d.%m.")
    )
    disp["Zeit"] = disp["time"].astype(str)
    disp = disp.rename(columns={
        "responsible": "Verantwortliche",
        "topic":       "Thema",
        "room":        "Ort",
    })
    cols = [c for c in ["Datum", "Zeit", "Verantwortliche", "Thema", "Ort"] if c in disp.columns]
    st.dataframe(
        disp[cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Datum":          st.column_config.TextColumn("Datum",          width="small"),
            "Zeit":           st.column_config.TextColumn("Zeit",           width="small"),
            "Verantwortliche":st.column_config.TextColumn("Verantwortliche",width="medium"),
            "Thema":          st.column_config.TextColumn("Thema",          width="large"),
            "Ort":            st.column_config.TextColumn("Ort",            width="small"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# MASTER PASSWORD GATE — nothing renders below until correct
# After correct PW: auto-load all data + assign personnel for all months
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

if not st.session_state.get("_auth_plan", False):
    _pw_col, _ = st.columns([1, 2])
    with _pw_col:
        _pre_pw = st.text_input("Zugangscode", type="password", key="tab1_pw",
                                placeholder="Zugangscode eingeben …",
                                label_visibility="collapsed")
    if _pre_pw:
        if _pre_pw == st.secrets.get("app_password", ""):
            st.session_state["_auth_plan"] = True
            st.session_state["_trigger_autoload"] = True
            st.rerun()
        else:
            st.session_state["_auth_plan"] = False
            _banner("Falscher Zugangscode.", "err")
    else:
        _banner("Bitte Zugangscode eingeben.", "info")
    st.stop()  # ← nothing below renders until master pw is correct

# ── Auto-load: runs once right after successful PW entry ─────────────────────
if st.session_state.pop("_trigger_autoload", False):
    _year_al = 2026
    _load_placeholder = st.empty()
    with _load_placeholder.container():
        _doc_loader("Planungsdaten aus Sheets werden geladen …")
    st.cache_data.clear()
    _data_al = load_all_data()
    st.session_state["data"]       = _data_al
    st.session_state["pep_months"] = get_pep_months(_data_al)
    _pep_months_al = st.session_state["pep_months"]

    with _load_placeholder.container():
        _doc_loader("Kalender wird generiert …")
    # Generate placeholder schedule for all months
    for _m_al in range(1, 13):
        _ph_al = generate_sheet_only_schedule(_year_al, _m_al, _data_al)
        st.session_state[f"placeholder_{_m_al}"] = _ph_al

    with _load_placeholder.container():
        _doc_loader("Personal wird zugewiesen …")
    # Assign personnel for all months
    for _m_al in range(1, 13):
        try:
            if _m_al in _pep_months_al:
                _sched_al = generate_full_schedule_aware(_year_al, _m_al, _data_al)
                _has_pep_al = True
            else:
                _sched_al = generate_sheet_only_schedule(_year_al, _m_al, _data_al)
                _has_pep_al = False
            st.session_state[f"generated_{_m_al}"]  = _sched_al
            st.session_state[f"has_pep_{_m_al}"]    = _has_pep_al
            st.session_state[f"placeholder_{_m_al}"] = _sched_al
        except Exception as _e_al:
            print(f"[autoload] Failed month {_m_al}: {_e_al}")

    _load_placeholder.empty()
    st.session_state["_autoload_done"] = True
    st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# TABS  (only rendered after master pw is correct)
# ─────────────────────────────────────────────────────────────────────────────
_t1_ready = st.session_state.get("_auth_plan",   False)
_t2_ready = st.session_state.get("_auth_analyse", False)
_t4_ready = st.session_state.get("_auth_best",    False)

tab1, tab2, tab3, tab4 = st.tabs(["Plan", "Analyse", "Bestätigung", "Benachrichtigung"])

_active_page = "plan"  # kept for compatibility

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLAN
# ═════════════════════════════════════════════════════════════════════════════
with tab1:

    _t1_ok = True  # master pw already verified above

    year = 2026
    _current_month = datetime.date.today().month
    _default_index = (_current_month - 1) if 1 <= _current_month <= 12 else 3

    # ── Quick-start guide (only when authenticated) ───────────────────────────
    if _t1_ok:
     with st.expander("Hilfe & Kurzanleitung", expanded=False):
        st.markdown("""
<div class="guide">

<div class="guide-step">
<div class="guide-num">1</div>
<div class="guide-body">
<b>Wie funktioniert die App?</b><br>
Die Weiterbildungsplanung basiert auf zwei Datenquellen: dem <b>PEP</b> (Dienstplanung) und mehreren <b>Google Sheets</b>, in denen wiederkehrende Veranstaltungen gepflegt werden. Die App liest diese Daten automatisch ein und erstellt daraus einen vollständigen Monatsplan.
</div>
</div>

<div class="guide-step">
<div class="guide-num">2</div>
<div class="guide-body">
<b>Plan ansehen (Tab «Plan»)</b><br>
Der Tab «Plan» zeigt alle Veranstaltungen in einer Übersichtstabelle, sortiert nach Datum. Über das Dropdown kann auf einen einzelnen Monat gewechselt werden. Die Tabelle zeigt Datum, Uhrzeit, Verantwortliche Person, Thema und Raum.<br><br>
Der Plan kann als <b>CSV</b> oder als <b>Word-Datei</b> heruntergeladen werden — die Word-Datei ist nach der KIM-Formatierungsvorlage gestaltet.<br><br>
Vergangene Monate können eingesehen werden, zeigen aber einen Hinweis, die definitive Dienstplanung zu konsultieren. Monate ohne geladene PEP-Daten zeigen einen Hinweis, dass nur terminbasierte Veranstaltungen sichtbar sind.
</div>
</div>

<div class="guide-step">
<div class="guide-num">3</div>
<div class="guide-body">
<b>Fairness-Analyse (Tab «Analyse»)</b><br>
Der Tab «Analyse» ist für die Planung gedacht. Er zeigt, wer in den kommenden Monaten wie oft für algorithmisch zugewiesene Veranstaltungen eingeplant wurde — und ob die Belastung gleichmässig verteilt ist. Für überlastete Einträge werden geeignete Alternativen aus dem PEP vorgeschlagen.
</div>
</div>

<div class="guide-step">
<div class="guide-num">4</div>
<div class="guide-body">
<b>Bestätigung &amp; Freigabe (Tab «Bestätigung»)</b><br>
Der Tab «Bestätigung» hat drei Rollen:<br><br>
<b>Rolle A</b> kann den Monatsplan prüfen und Personenzuweisungen anpassen:
<ul>
<li>Bei <b>algorithmisch zugewiesenen Veranstaltungen</b> (z.B. Mittwochscurriculum, Journal Club, COD, PEER) kann Rolle A die verantwortliche Person direkt ersetzen. Geeignete Alternativen werden automatisch aus dem PEP vorgeschlagen (nach Rolle und Dienstart). Nach dem Anpassen <b>«Plan aktualisieren»</b> klicken.</li>
<li>Bei <b>Sheet-basierten Veranstaltungen</b> (z.B. Teaching Tuesday, TTE Curriculum, Bedside Infektiologie) ist die verantwortliche Person direkt im jeweiligen Google Sheet hinterlegt — bitte dort anpassen.</li>
</ul>
<b>Rolle B</b> prüft den Plan und bestätigt.<br><br>
<b>Rolle C (Admin)</b> prüft, bestätigt und finalisiert den Plan, sobald alle drei Rollen bestätigt haben. Der finalisierte Plan wird als CSV exportiert — dies dient der Fairness-Auswertung für künftige Monate.
</div>
</div>

<div class="guide-step">
<div class="guide-num">5</div>
<div class="guide-body">
<b>Benachrichtigungen (Tab «Benachrichtigung»)</b><br>
Aktuell als Demo / Konzept: Im Tab «Benachrichtigung» können vorbereitete E-Mails an die verantwortlichen Personen als Mailto-Links geöffnet werden (öffnet Outlook mit vorausgefülltem Text).
</div>
</div>

<div class="guide-tips">
<b>Wichtige Hinweise</b>
<ul>
<li>Die Grunddaten (Veranstaltungsserien, Themen, Referenten) werden in <b>Google Sheets</b> gepflegt. Bei Änderungsbedarf bitte das jeweilige Google Sheet direkt bearbeiten oder <a href="mailto:kim.backoffice1@gmail.com">kim.backoffice1@gmail.com</a> kontaktieren.</li>
<li>Der <b>Fairness-Algorithmus</b> (Tab «Analyse») zeigt, wer in den kommenden Monaten zu oft eingeplant wurde.</li>
<li>Finalisierte Monate sind gesperrt — eine Neuzuweisung ist dann nicht mehr möglich.</li>
<li>Bei technischen Fragen oder Problemen mit der App: <a href="mailto:kim.backoffice1@gmail.com">kim.backoffice1@gmail.com</a></li>
</ul>
</div>

</div>
""", unsafe_allow_html=True)

    # ── Controls ──────────────────────────────────────────────────────────────
    if _t1_ready:
        _sec("Monat & Aktionen", first=True)
        _c1, _ = st.columns([2, 6])
    else:
        _c1 = None

    # View mode: "Alle" or individual month
    VIEW_OPTIONS = {"alle": "Alle Monate"} | {k: v for k, v in MONTH_LABELS.items()}

    view_mode = "alle"
    month = list(MONTH_LABELS.keys())[_default_index]  # safe default

    if _t1_ready:
        with _c1:
            view_mode = st.selectbox(
                "Ansicht",
                list(VIEW_OPTIONS.keys()),
                index=0,
                format_func=lambda x: VIEW_OPTIONS[x],
                label_visibility="collapsed",
                key="view_mode_select",
            )
            if view_mode != "alle":
                month = view_mode

    generated_key   = f"generated_{month}"
    placeholder_key = f"placeholder_{month}"
    finalized_months = st.session_state.get("finalized_months", set())

    # ── YEAR VIEW (Alle Monate) — one flat continuous table ──────────────────
    if _t1_ready and view_mode == "alle":
        _months_ordered = list(range(_current_month, 13))
        _all_scheds = []
        for _mv in _months_ordered:
            _gen_key = f"generated_{_mv}"
            _ph_key  = f"placeholder_{_mv}"
            _sched_mv = st.session_state.get(_gen_key)
            if _sched_mv is None:
                _sched_mv = st.session_state.get(_ph_key)
            if _sched_mv is not None and not _sched_mv.empty:
                _all_scheds.append(_sched_mv)

        if _all_scheds:
            _combined = pd.concat(_all_scheds, ignore_index=True)
            _combined = _combined.sort_values("date").reset_index(drop=True)
            _disp_all = _combined.copy()
            _disp_all["responsible"] = _disp_all["responsible"].fillna("— TBD —")
            _disp_all["Datum"] = _disp_all["date"].apply(
                lambda d: WEEKDAY_DE.get(d.strftime("%A"), "") + " " + d.strftime("%d.%m.%Y")
            )
            _disp_all["Zeit"] = _disp_all["time"].astype(str)
            _disp_all = _disp_all.rename(columns={
                "responsible": "Verantwortliche",
                "topic":       "Thema",
                "room":        "Ort",
            })
            _cols_all = [c for c in ["Datum", "Zeit", "Verantwortliche", "Thema", "Ort"] if c in _disp_all.columns]
            st.dataframe(
                _disp_all[_cols_all],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Datum":           st.column_config.TextColumn("Datum",           width="small"),
                    "Zeit":            st.column_config.TextColumn("Zeit",            width="small"),
                    "Verantwortliche": st.column_config.TextColumn("Verantwortliche", width="medium"),
                    "Thema":           st.column_config.TextColumn("Thema",           width="large"),
                    "Ort":             st.column_config.TextColumn("Ort",             width="small"),
                },
            )
        else:
            st.markdown("<p style='color:var(--muted);font-size:13px;padding:4px 0'>Noch keine Daten geladen.</p>", unsafe_allow_html=True)

    # ── SINGLE MONTH VIEW ────────────────────────────────────────────────────
    elif _t1_ready and view_mode != "alle":
        _month_is_past = (month < _current_month)

        if generated_key in st.session_state:
            schedule = st.session_state[generated_key]
            has_pep  = st.session_state.get(f"has_pep_{month}", False)
            data     = st.session_state.get("data", {})

            _sec("Plan")
            if _month_is_past:
                _banner(
                    f"{MONTH_LABELS[month]} liegt in der Vergangenheit — "
                    "bitte die definitive PEP-Planung für diesen Monat konsultieren.",
                    "warn",
                )
            elif has_pep:
                _banner(f"Plan generiert — {MONTH_LABELS[month]}", "ok")
            else:
                _banner(f"Kein PEP für {MONTH_LABELS[month]} — Platzhalter für algorithmische Slots.", "info")

            _show_schedule(schedule)

            if has_pep and not _month_is_past:
                with st.expander("Validierung", expanded=False):
                    issues = validate_schedule(schedule, data.get("history"))
                    if not issues.empty:
                        _banner("Validierungsprobleme gefunden.", "warn")
                        st.dataframe(issues, use_container_width=True, hide_index=True)
                    else:
                        _banner("Keine Validierungsprobleme.", "ok")

            _sec("Export")
            _dc, _wc, _ = st.columns([1.3, 1.3, 5])
            with _dc:
                csv = schedule.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "↓  CSV", csv,
                    file_name=f"weiterbildungsplan_{year}_{month}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with _wc:
                month_label_word = f"{MONTH_MAP_WORD[month]} {year}"
                word_key = f"word_file_{month}"
                if word_key not in st.session_state:
                    with st.spinner("Word wird erstellt …"):
                        file_path = export_to_word(
                            schedule,
                            template_path="src/Bildung_Vorlage_ICU_month.docx",
                            month_label=month_label_word,
                        )
                    st.session_state[word_key] = file_path
                with open(st.session_state[word_key], "rb") as f:
                    st.download_button(
                        "↓  Word", f,
                        file_name=st.session_state[word_key],
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )

        elif placeholder_key in st.session_state:
            _sec("Plan")
            if month in st.session_state.get("finalized_months", set()):
                _banner(f"{MONTH_LABELS[month]} — Finalisiert — Alle Reviewer haben bestätigt.", "ok")
            elif _month_is_past:
                _banner(
                    f"{MONTH_LABELS[month]} liegt in der Vergangenheit — "
                    "bitte die definitive PEP-Planung für diesen Monat konsultieren.",
                    "warn",
                )
            else:
                _banner(f"Kein PEP für {MONTH_LABELS[month]} — Platzhalter für algorithmische Slots.", "info")
            _show_schedule(st.session_state[placeholder_key])

        else:
            st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
            _banner("Zuerst «Termine laden», dann «Personen zuweisen».", "info")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — ANALYSE
# ═════════════════════════════════════════════════════════════════════════════
with tab2:

    # ── Access gate ───────────────────────────────────────────────────────────
    _gc2, _ = st.columns([1, 2])
    with _gc2:
        fairness_pw = st.text_input("Zugangscode Analyse", type="password", key="fairness_pw",
                                    placeholder="Zugangscode eingeben …",
                                    label_visibility="collapsed")
    if fairness_pw:
        _auth_ok = (fairness_pw == st.secrets.get("fairness_password", ""))
        st.session_state["_auth_analyse"] = _auth_ok
        if not _auth_ok:
            _banner("Falscher Zugangscode.", "err")
    elif "_auth_analyse" not in st.session_state:
        st.session_state["_auth_analyse"] = False

    _t2_ok = st.session_state.get("_auth_analyse", False)
    if fairness_pw and _t2_ok:
        _banner("Zugangscode korrekt ✓", "ok")
    elif not _t2_ok and not fairness_pw:
        _banner("Bitte Zugangscode eingeben.", "info")

    if _t2_ok:
        _sec("Fairness-Analyse", first=True)

    if _t2_ok:
        # ── Load data if not already in session ───────────────────────────────
        if "data" not in st.session_state:
            with st.spinner("Google Sheets werden geladen … (ca. 30–60 Sek.)"):
                try:
                    st.session_state["data"]       = load_all_data()
                    st.session_state["pep_months"] = get_pep_months(st.session_state["data"])
                except Exception as _e:
                    _banner(f"Fehler beim Laden der Daten: {_e}", "err")
                    st.stop()
        data       = st.session_state["data"]
        pep_months = st.session_state.get("pep_months", set())
        # Only consider months from NEXT month onwards
        _next_month = datetime.date.today().month + 1
        if _next_month > 12:
            _next_month = 12
        fairness_months = sorted(m for m in pep_months if m >= _next_month) if pep_months else []
        if not fairness_months:
            fairness_months = list(range(_next_month, 13))[:3]
        month_label_str = ", ".join(MONTH_LABELS[m] for m in fairness_months if m in MONTH_LABELS)

        if not pep_months:
            _banner("Keine PEP-Daten gefunden — bitte zuerst im Plan-Tab «Termine laden» klicken.", "warn")
        else:
            _banner(f"Auswertung ab {MONTH_LABELS.get(_next_month, str(_next_month))}: {month_label_str}", "info")

        _cached_months = st.session_state.get("schedule_all_months")
        if _cached_months != tuple(fairness_months):
            st.session_state.pop("schedule_all", None)
        if "schedule_all" not in st.session_state:
            with st.spinner("Mehrmonatiger Gesamtplan wird berechnet …"):
                try:
                    schedules = []
                    for _m in fairness_months:
                        _sched = generate_full_schedule_aware(year=2026, month=_m, data=data)
                        if _sched is not None and not _sched.empty:
                            _sched["month"] = _m
                            schedules.append(_sched)
                    schedule_all = pd.concat(schedules, ignore_index=True) if schedules else pd.DataFrame()
                    st.session_state["schedule_all"] = schedule_all
                    st.session_state["schedule_all_months"] = tuple(fairness_months)
                except Exception as _e:
                    _banner(f"Fehler beim Berechnen des Gesamtplans: {_e}", "err")
                    st.stop()
        schedule_all = st.session_state["schedule_all"]

        if schedule_all.empty:
            _banner("Gesamtplan ist leer — keine Daten verfügbar.", "warn")
            st.stop()

        _sec("Gesamtplan")
        st.dataframe(schedule_all, use_container_width=True, hide_index=True)

        history_df = data.get("history")
        fairness = compute_fairness_from_schedule(schedule_all, history_df=history_df)

        _sec("Fairness-Tabelle")
        st.dataframe(fairness, use_container_width=True, hide_index=True)

        _sec("Fairness Score")
        st.bar_chart(fairness.set_index("person")["fairness_score"])

        _sec("Überlastete Personen — Alternativkandidaten")
        st.caption(
            "Personen mit mehr Zuweisungen als erwartet. "
            "Alternativen = gleiche Rolle, in Dienst an dem Tag, sortiert nach Dienstpriorität."
        )

        threshold = st.slider(
            "Nur Personen mit Fairness-Score über:",
            min_value=0.0,
            max_value=float(fairness["fairness_score"].max()),
            value=0.0,
            step=0.1,
        )

        pep_df_raw = data.get("pep")

        if pep_df_raw is not None and not pep_df_raw.empty:
            alternatives_df = build_alternatives(schedule_all, pep_df_raw, fairness, threshold=threshold)

            if alternatives_df.empty:
                _banner("Keine überlasteten Personen über diesem Schwellwert.", "ok")
            else:
                for person in alternatives_df["person"].unique():
                    person_rows = alternatives_df[alternatives_df["person"] == person]
                    score_vals  = fairness.loc[fairness["person"] == person, "fairness_score"].values
                    score_str   = f" · Score +{score_vals[0]:.2f}" if len(score_vals) else ""

                    st.markdown(
                        f'<div style="font-size:14px;font-weight:600;color:var(--navy);margin:20px 0 6px">'
                        f'{person.title()}'
                        f'<span style="font-weight:400;color:var(--muted);font-size:12px">{score_str}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    for _, r in person_rows.iterrows():
                        alts = r["alternatives"]
                        if alts:
                            tiers = {}
                            for a in alts:
                                tiers.setdefault(a["priority_tier"], []).append(a)
                            alt_parts = []
                            for tier in sorted(tiers):
                                tier_names = ", ".join(
                                    f"{a['name']} ({a['role']}, {a['duty_label']})"
                                    for a in tiers[tier]
                                )
                                prefix = "Empfohlen: " if tier == 1 else f"Tier {tier}: "
                                alt_parts.append(f"{prefix}{tier_names}")
                            alt_str = " | ".join(alt_parts)
                        else:
                            alt_str = "— keine geeigneten Alternativen in definierten Dienstgruppen"

                        st.markdown(
                            f'<div style="font-size:12px;color:var(--muted);padding:5px 0 5px 12px;'
                            f'border-left:3px solid var(--border);margin-bottom:4px">'
                            f'{r["weekday"]} {r["date"]} &nbsp;·&nbsp; '
                            f'<code>{r["event_type"]}</code> &nbsp;·&nbsp; {r["topic"]}<br>'
                            f'Rolle: <code>{r["role"]}</code> {r["duty_label"]}<br>'
                            f'<b>Alternativen:</b> {alt_str}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                    st.markdown("<hr>", unsafe_allow_html=True)
        else:
            _banner("PEP-Daten nicht verfügbar.", "warn")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — BESTÄTIGUNG
# Three reviewers (A, B, C) confirm independently; Admin (C) finalises.
# ═════════════════════════════════════════════════════════════════════════════
with tab3:

    # ── Access gate ───────────────────────────────────────────────────────────
    _gc4, _ = st.columns([1, 2])
    with _gc4:
        confirm_pw = st.text_input("Zugangscode Bestätigung", type="password", key="confirm_pw",
                                   placeholder="Zugangscode eingeben …",
                                   label_visibility="collapsed")
    if confirm_pw:
        _ok4 = (confirm_pw == st.secrets.get("confirm_password", ""))
        st.session_state["_auth_best"] = _ok4
        if not _ok4:
            _banner("Falscher Zugangscode.", "err")
    elif "_auth_best" not in st.session_state:
        st.session_state["_auth_best"] = False

    _t4_ok = st.session_state.get("_auth_best", False)
    if confirm_pw and _t4_ok:
        _banner("Zugangscode korrekt ✓", "ok")
    elif not _t4_ok and not confirm_pw:
        _banner("Bitte Zugangscode eingeben.", "info")

    if _t4_ok:
        _sec("Programm-Bestätigung & Finalisierung", first=True)

        REVIEWERS      = {"A": "A", "B": "B", "C": "C"}
        ADMIN_REVIEWER = "C"

        # Load persistent state once per session
        if "confirmations_loaded" not in st.session_state:
            try:
                confs, fins = load_confirmations(year=2026)
                st.session_state["confirmations"]    = confs
                st.session_state["finalized_months"] = fins
            except Exception as e:
                _banner(f"Konnte Bestätigungsstatus nicht laden: {e}", "warn")
                st.session_state["confirmations"]    = {}
                st.session_state["finalized_months"] = set()
            st.session_state["confirmations_loaded"] = True

        _r1, _r2, _ = st.columns([1.5, 1.5, 4])
        with _r1:
            reviewer_id = st.selectbox(
                "Ich bin",
                list(REVIEWERS.keys()),
                format_func=lambda k: f"{REVIEWERS[k]} ({k})",
                key="reviewer_id",
            )
        with _r2:
            confirm_month = st.selectbox(
                "Monat",
                list(MONTH_LABELS.keys()),
                index=3,
                format_func=lambda x: MONTH_LABELS[x],
                key="confirm_month",
            )

        is_admin       = (reviewer_id == ADMIN_REVIEWER)
        is_finalized   = confirm_month in st.session_state["finalized_months"]
        month_confirms = st.session_state["confirmations"].get(confirm_month, {})
        all_confirmed  = all(month_confirms.get(r, False) for r in REVIEWERS)
        n_confirmed    = sum(month_confirms.get(r, False) for r in REVIEWERS)

        if is_finalized:
            _banner(f"{MONTH_LABELS[confirm_month]} ist finalisiert und gesperrt.", "ok")
        elif all_confirmed:
            _banner("Alle drei haben bestätigt — bereit zur Finalisierung.", "ok")
        elif n_confirmed == 0:
            _banner(f"Noch keine Bestätigungen für {MONTH_LABELS[confirm_month]}.", "warn")
        else:
            _banner(f"{n_confirmed}/3 bestätigt — warte auf weitere.", "warn")

        # ── Schedule preview ──────────────────────────────────────────────────
        sc = None
        if "data" not in st.session_state:
            _banner("Bitte zuerst im Plan-Tab Daten laden.", "info")
        else:
            data_c       = st.session_state["data"]
            pep_months_c = st.session_state.get("pep_months", set())
            cache_key_c  = f"confirm_schedule_{confirm_month}"
            if cache_key_c not in st.session_state:
                if confirm_month in pep_months_c:
                    sc_new = generate_full_schedule_aware(2026, confirm_month, data_c)
                else:
                    sc_new = generate_sheet_only_schedule(2026, confirm_month, data_c)
                st.session_state[cache_key_c] = sc_new
            sc = st.session_state[cache_key_c].copy()

        if sc is not None:
            with st.expander("Monatsplan " + MONTH_LABELS.get(confirm_month, ""), expanded=not is_finalized):
                disp = sc.copy()
                disp["responsible"] = disp["responsible"].fillna("— TBD —")
                disp["Datum"]       = disp["date"].apply(_fmt_date_de)
                st.dataframe(
                    disp[["Datum", "time", "event_type", "responsible", "topic", "room"]].rename(
                        columns={"time": "Zeit", "event_type": "Veranstaltung",
                                 "responsible": "Verantwortlich", "topic": "Thema", "room": "Raum"}
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Datum":          st.column_config.TextColumn("Datum",          width="medium"),
                        "Zeit":           st.column_config.TextColumn("Zeit",           width="small"),
                        "Veranstaltung":  st.column_config.TextColumn("Veranstaltung",  width="medium"),
                        "Verantwortlich": st.column_config.TextColumn("Verantwortlich", width="medium"),
                        "Thema":          st.column_config.TextColumn("Thema",          width="large"),
                        "Raum":           st.column_config.TextColumn("Raum",           width="small"),
                    },
                )

        # ── Editable person assignment (Role A — algorithmic events) ──────────
        if sc is not None and not is_finalized and reviewer_id == "A":
            _sec("Personenzuweisung bearbeiten")

            _data_a   = st.session_state.get("data", {})
            _pep_raw  = _data_a.get("pep")

            # Prepare normalised PEP lookup (date → day_pep slice) once per month
            _pep_cache_key = f"_pep_norm_{confirm_month}"
            if _pep_cache_key not in st.session_state and _pep_raw is not None:
                import pandas as _pd2
                _pep_n = _pep_raw.copy()
                _pep_n["date"]       = _pd2.to_datetime(_pep_n["date"], errors="coerce").dt.normalize()
                _pep_n["name_clean"] = _pep_n["name_clean"].astype(str).str.strip().str.lower()
                _pep_n["lastname"]   = _pep_n["name_clean"].apply(_extract_lastname)
                _pep_n["duty_code"]  = _pd2.to_numeric(_pep_n["duty_code"], errors="coerce")
                _pep_n["role_code"]  = _pep_n["role_code"].astype(str).str.strip()
                st.session_state[_pep_cache_key] = _pep_n
            _pep_norm = st.session_state.get(_pep_cache_key)

            def _build_row_alternatives(row, slot_idx=0):
                """
                Return ordered alternative list for one assigned slot on a given event row.
                slot_idx: 0 = first person (Intermediate/OA slot), 1 = second (AA slot) for Journal_Club.
                """
                if _pep_norm is None:
                    return []
                evt = row.get("event_type", "")
                rules = EVENT_DUTY_RULES.get(evt)
                if not rules or slot_idx >= len(rules):
                    return []
                role_pool, duty_priority = rules[slot_idx]
                d = pd.Timestamp(row["date"]).normalize()
                day_pep = _pep_norm[_pep_norm["date"] == d]
                if day_pep.empty:
                    return []
                # exclude ALL currently assigned people for this event row
                responsible_raw = str(row.get("responsible", "") or "")
                assigned_lns = [_extract_lastname(p.strip()) for p in responsible_raw.split("/")]
                return _find_alternatives_ordered(day_pep, role_pool, duty_priority, assigned_lns)

            def _name_clean_to_display(raw_n):
                """
                Convert PEP name_clean (lastname firstname, e.g. "bertschi daniela")
                to display format "D. Bertschi" (firstname initial + lastname capitalised).
                """
                parts = raw_n.strip().split()
                if len(parts) >= 2:
                    # PEP format: lastname first, firstname(s) after
                    lastname   = " ".join(p.capitalize() for p in parts[:-1])
                    first_init = parts[-1][0].upper() + "."
                    return f"{first_init} {lastname}"
                return raw_n.title()

            def _format_alt_opts(alt_list, current_name):
                """
                Convert alt_list (from _find_alternatives_ordered) into labelled dropdown options.
                Returns (list of option strings, mapping dict option→display_name).
                name_clean in PEP is "lastname firstname", so we convert to "F. Lastname".
                """
                opts     = []
                name_map = {}  # option_label → display name (for saving)
                tier_labels = {1: "Prio I", 2: "Prio II", 3: "Prio III"}

                for alt in alt_list:
                    tier      = alt["priority_tier"]
                    label     = tier_labels.get(tier, f"Prio {tier}")
                    role      = alt["role"]
                    duty      = alt["duty_label"]
                    disp_name = _name_clean_to_display(alt["name"])
                    option    = f"{label}: {disp_name} ({role}, {duty})"
                    opts.append(option)
                    name_map[option] = disp_name

                return opts, name_map

            # Session state for edits (supports two slots per row for Journal_Club)
            _edits_key = f"_person_edits_{confirm_month}"
            if _edits_key not in st.session_state:
                st.session_state[_edits_key] = {}

            # Filter to algorithmic / relevant events only
            _sc_rel = sc[sc["event_type"].isin(RELEVANT_EVENTS)].copy()

            if _sc_rel.empty:
                _banner("Keine algorithmischen Veranstaltungen in diesem Monat.", "info")
            else:
                _OTHER_LABEL = "Andere (Freitext) …"

                # ── Helper: apply pending edits → schedule DataFrame ──────────
                def _apply_edits_to_sched(base_sc, edits):
                    edited = base_sc.copy()
                    for eidx, eval_ in edits.items():
                        if isinstance(eidx, str) and "_" in str(eidx):
                            try:
                                parts_ = str(eidx).rsplit("_", 1)
                                bidx, slot_ = int(parts_[0]), int(parts_[1])
                                if bidx in edited.index:
                                    cur = str(edited.at[bidx, "responsible"] or "")
                                    cps = [p.strip() for p in cur.split("/")]
                                    while len(cps) <= slot_:
                                        cps.append("— TBD —")
                                    cps[slot_] = eval_
                                    edited.at[bidx, "responsible"] = " / ".join(cps)
                            except (ValueError, KeyError):
                                pass
                        elif eidx in edited.index:
                            edited.at[eidx, "responsible"] = eval_
                    return edited

                def _count_pending(base_sc, edits):
                    n = 0
                    for eidx, eval_ in edits.items():
                        try:
                            if isinstance(eidx, str) and "_" in str(eidx):
                                parts_ = str(eidx).rsplit("_", 1)
                                bidx, slot_ = int(parts_[0]), int(parts_[1])
                                if bidx in base_sc.index:
                                    cur = str(base_sc.at[bidx, "responsible"] or "")
                                    cps = [p.strip() for p in cur.split("/")]
                                    orig = cps[slot_] if slot_ < len(cps) else "— TBD —"
                                    if orig.strip() != eval_.strip():
                                        n += 1
                            elif eidx in base_sc.index:
                                orig = str(base_sc.at[eidx, "responsible"] or "")
                                if orig.strip() != eval_.strip():
                                    n += 1
                        except (ValueError, KeyError):
                            pass
                    return n

                # Pending edits (not yet committed to schedule)
                _pending_key = f"_pending_edits_{confirm_month}"
                if _pending_key not in st.session_state:
                    st.session_state[_pending_key] = {}
                # Work on a fresh copy each rerun so writes are visible immediately
                _pending = dict(st.session_state[_pending_key])
                _base_sc = st.session_state.get(f"confirm_schedule_{confirm_month}")

                # ── nmap cache: maps full option label → clean display name ───
                # Built during the row loop, used for name resolution
                _nmap_cache = {}  # key f"{_idx}" or f"{_idx}_0/1" → nmap dict

                # ── Table: Datum + Verantwortlich only ────────────────────────
                _th1, _th2 = st.columns([1, 2])
                with _th1:
                    st.markdown("<p style='font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 3px'>Datum · Veranstaltung</p>", unsafe_allow_html=True)
                with _th2:
                    st.markdown("<p style='font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:0 0 3px'>Verantwortlich — Alternativ auswählen</p>", unsafe_allow_html=True)
                st.markdown("<div style='height:1px;background:var(--border);margin-bottom:4px'></div>", unsafe_allow_html=True)

                for _idx, _row in _sc_rel.iterrows():
                    _evt_type  = str(_row.get("event_type", ""))
                    _is_jc     = (_evt_type == "Journal_Club")
                    _orig_name = _row.get("responsible", "")
                    if not isinstance(_orig_name, str) or not _orig_name.strip():
                        _orig_name = "— TBD —"

                    if _is_jc:
                        _parts   = [p.strip() for p in _orig_name.split("/")]
                        _orig_p1 = _parts[0] if len(_parts) > 0 else "— TBD —"
                        _orig_p2 = _parts[1] if len(_parts) > 1 else "— TBD —"
                        _pend_p1 = _pending.get(f"{_idx}_0", _orig_p1)
                        _pend_p2 = _pending.get(f"{_idx}_1", _orig_p2)
                        _row_changed = (_pend_p1 != _orig_p1 or _pend_p2 != _orig_p2)
                    else:
                        _orig_p1     = _orig_name
                        _pend_p1     = _pending.get(_idx, _orig_name)
                        _row_changed = (_pend_p1 != _orig_name)

                    _date_str = WEEKDAY_DE.get(_row["date"].strftime("%A"), "") + " " + _row["date"].strftime("%d.%m.")
                    _time_str = str(_row.get("time", ""))
                    _evt_str  = _evt_type.replace("_", " ")
                    _accent   = "border-left:3px solid var(--teal);" if _row_changed else "border-left:3px solid transparent;"

                    _cl, _cr = st.columns([1, 2])
                    with _cl:
                        st.markdown(
                            f"<div style='{_accent}padding:6px 0 4px 6px'>"
                            f"<span style='font-size:12px;font-weight:600;color:var(--navy)'>{_date_str}</span> "
                            f"<span style='font-size:11px;color:var(--muted)'>{_time_str}</span><br>"
                            f"<span style='font-size:11px;color:var(--teal)'>{_evt_str}</span>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                    with _cr:
                        if _is_jc:
                            # Build opts — always use _pend_p1 as current (display name, not label)
                            _alts1, _nmap1 = _format_alt_opts(_build_row_alternatives(_row, slot_idx=0), _pend_p1)
                            _nmap_cache[f"{_idx}_0"] = _nmap1
                            # Only include alt options where the resolved name != current
                            _opts1 = [_pend_p1] + [o for o in _alts1 if _nmap1.get(o, o) != _pend_p1] + [_OTHER_LABEL]
                            st.markdown("<span style='font-size:10px;color:var(--muted)'>OA / Intermediate</span>", unsafe_allow_html=True)
                            _sel1 = st.selectbox("OA", _opts1, index=0, label_visibility="collapsed",
                                                 key=f"sel_{confirm_month}_{_idx}_0")
                            if _sel1 == _OTHER_LABEL:
                                _free1 = st.text_input("Name", key=f"free_{confirm_month}_{_idx}_0",
                                                        placeholder="V. Nachname", label_visibility="collapsed")
                                if _free1.strip():
                                    _pending[f"{_idx}_0"] = _free1.strip()
                            else:
                                # _nmap1 maps label→display_name; if not found, sel is already display_name
                                _pending[f"{_idx}_0"] = _nmap1.get(_sel1, _sel1)

                            _alts2, _nmap2 = _format_alt_opts(_build_row_alternatives(_row, slot_idx=1), _pend_p2)
                            _nmap_cache[f"{_idx}_1"] = _nmap2
                            _opts2 = [_pend_p2] + [o for o in _alts2 if _nmap2.get(o, o) != _pend_p2] + [_OTHER_LABEL]
                            st.markdown("<span style='font-size:10px;color:var(--muted)'>AA</span>", unsafe_allow_html=True)
                            _sel2 = st.selectbox("AA", _opts2, index=0, label_visibility="collapsed",
                                                 key=f"sel_{confirm_month}_{_idx}_1")
                            if _sel2 == _OTHER_LABEL:
                                _free2 = st.text_input("Name", key=f"free_{confirm_month}_{_idx}_1",
                                                        placeholder="V. Nachname", label_visibility="collapsed")
                                if _free2.strip():
                                    _pending[f"{_idx}_1"] = _free2.strip()
                            else:
                                _pending[f"{_idx}_1"] = _nmap2.get(_sel2, _sel2)
                        else:
                            _alts, _nmap = _format_alt_opts(_build_row_alternatives(_row, slot_idx=0), _pend_p1)
                            _nmap_cache[str(_idx)] = _nmap
                            _opts = [_pend_p1] + [o for o in _alts if _nmap.get(o, o) != _pend_p1] + [_OTHER_LABEL]
                            st.markdown("<span style='font-size:10px;color:var(--muted)'>Verantwortlich</span>", unsafe_allow_html=True)
                            _sel = st.selectbox("Verantwortlich", _opts, index=0, label_visibility="collapsed",
                                                key=f"sel_{confirm_month}_{_idx}")
                            if _sel == _OTHER_LABEL:
                                _free = st.text_input("Name", key=f"free_{confirm_month}_{_idx}",
                                                       placeholder="V. Nachname", label_visibility="collapsed")
                                if _free.strip():
                                    _pending[_idx] = _free.strip()
                            else:
                                _pending[_idx] = _nmap.get(_sel, _sel)

                    st.markdown("<div style='height:1px;background:var(--border);opacity:.35;margin:0'></div>", unsafe_allow_html=True)

                # Persist updated pending dict after all rows are processed
                st.session_state[_pending_key] = _pending

                # ── Plan aktualisieren button — shown AFTER rows so count is current ──
                _n_pending = _count_pending(_base_sc, _pending)
                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                _ua_col, _info_col = st.columns([2, 5])
                with _ua_col:
                    _update_clicked = st.button(
                        "Plan aktualisieren",
                        type="primary" if _n_pending > 0 else "secondary",
                        disabled=(_n_pending == 0),
                        key=f"update_plan_{confirm_month}",
                        use_container_width=True,
                    )
                with _info_col:
                    if _n_pending > 0:
                        _banner(f"{_n_pending} Änderung(en) ausstehend.", "warn")
                    else:
                        _banner("Keine ausstehenden Änderungen.", "info")

                if _update_clicked and _n_pending > 0:
                    _new_sc = _apply_edits_to_sched(_base_sc, _pending)
                    st.session_state[f"confirm_schedule_{confirm_month}"] = _new_sc
                    st.session_state[f"generated_{confirm_month}"]        = _new_sc
                    st.session_state.pop("schedule_all", None)
                    st.session_state.pop(f"notify_schedule_{confirm_month}", None)
                    st.session_state.pop(f"word_file_{confirm_month}", None)
                    st.session_state[_pending_key] = {}
                    _banner("Plan aktualisiert.", "ok")
                    st.rerun()

        if sc is not None:
            st.markdown("<hr>", unsafe_allow_html=True)

        if sc is not None and not is_finalized:
            _sec("Meine Bestätigung")
            my_current = month_confirms.get(reviewer_id, False)
            my_new = st.checkbox(
                f"Ich, **{REVIEWERS[reviewer_id]}**, bestätige dass ich den Plan für "
                f"**{MONTH_LABELS[confirm_month]}** geprüft habe und er korrekt ist.",
                value=my_current,
                key=f"my_confirm_{confirm_month}_{reviewer_id}",
            )

            if my_new != my_current:
                try:
                    _doc_loader("Speichern …")
                    save_confirmation(2026, confirm_month, reviewer_id, my_new)
                    month_confirms = st.session_state["confirmations"].setdefault(confirm_month, {})
                    month_confirms[reviewer_id] = my_new
                    st.session_state["confirmations"][confirm_month] = month_confirms
                    action = "bestätigt ✅" if my_new else "Bestätigung zurückgezogen ⬜"
                    _banner(f"{REVIEWERS[reviewer_id]}: {action}", "ok")
                    st.rerun()
                except Exception as e:
                    _banner(f"Konnte nicht speichern: {e}", "err")

            _sec("Status aller Reviewer")
            month_confirms = st.session_state["confirmations"].get(confirm_month, {})
            cols = st.columns(3)
            for i, (rid, rname) in enumerate(REVIEWERS.items()):
                confirmed = month_confirms.get(rid, False)
                with cols[i]:
                    cls   = "rcard done" if confirmed else "rcard"
                    icon  = "✅" if confirmed else "◻"
                    label = "Bestätigt" if confirmed else "Ausstehend"
                    st.markdown(
                        f'<div class="{cls}">' +
                        f'<div class="rcard-icon">{icon}</div>' +
                        f'<div class="rcard-name">{rname} ({rid})</div>' +
                        f'<div class="rcard-sub">{label}</div></div>',
                        unsafe_allow_html=True,
                    )

            all_confirmed = all(
                st.session_state["confirmations"].get(confirm_month, {}).get(r, False)
                for r in REVIEWERS
            )
            st.markdown("<hr>", unsafe_allow_html=True)

            if is_admin:
                _sec("Finalisierung (Admin)")
                if not all_confirmed:
                    _banner("Die Schaltfläche «Finalisieren» erscheint sobald alle drei Reviewer bestätigt haben.", "info")
                else:
                    _banner("Alle Bestätigungen vorhanden — Finalisierung möglich.", "ok")
                    admin_note = st.text_input(
                        "Admin-Notiz (z.B. «Versand an Team 01.04.2026»)",
                        key=f"admin_note_{confirm_month}",
                    )
                    if st.button(
                        f"🔒 Finalisieren & Sperren — {MONTH_LABELS[confirm_month]}",
                        type="primary",
                        key=f"finalize_{confirm_month}",
                    ):
                        try:
                            _doc_loader("Finalisierung wird gespeichert …")
                            save_finalization(2026, confirm_month, admin_note)
                            st.session_state["finalized_months"].add(confirm_month)
                            history_rows = []
                            for _, row in sc.iterrows():
                                resp = row.get("responsible")
                                if pd.notna(resp) and str(resp).strip() not in ("", "— TBD —"):
                                    history_rows.append({
                                        "date":              row["date"].strftime("%d.%m.%Y") if pd.notna(row.get("date")) else "",
                                        "datetime":          f"{row['date'].strftime('%d.%m.%Y')} {row.get('time', '')}",
                                        "event_type":        row.get("event_type", ""),
                                        "responsible":       resp,
                                        "responsible_clean": str(resp).lower().strip(),
                                        "topic":             row.get("topic", ""),
                                        "room":              row.get("room", ""),
                                        "finalized_at":      pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                                        "admin_note":        admin_note,
                                        "month":             confirm_month,
                                        "year":              2026,
                                    })
                            hist_df  = pd.DataFrame(history_rows)
                            csv_hist = hist_df.to_csv(index=False).encode("utf-8")
                            _banner(f"{MONTH_LABELS[confirm_month]} finalisiert! {len(history_rows)} Einträge bereit.", "ok")
                            st.download_button(
                                "⬇️ Finalisierten Plan herunterladen (→ Historical_Assignment hochladen)",
                                csv_hist,
                                file_name=f"finalisiert_{MONTH_LABELS[confirm_month].replace(' ', '_')}.csv",
                                mime="text/csv",
                                key=f"dl_hist_{confirm_month}",
                            )
                            _banner("Bitte die heruntergeladene CSV in das Google Sheet «Historical_Assignment» hochladen.", "info")
                        except Exception as e:
                            _banner(f"Finalisierung fehlgeschlagen: {e}", "err")
            else:
                _banner("Die Finalisierung wird von Admin (C) durchgeführt, sobald alle drei Reviewer bestätigt haben.", "info")

        if sc is not None and is_finalized and is_admin:
            _sec("Finalisierten Plan herunterladen")
            hist2 = []
            for _, row in sc.iterrows():
                resp = row.get("responsible")
                if pd.notna(resp) and str(resp).strip() not in ("", "— TBD —"):
                    hist2.append({
                        "date":              row["date"].strftime("%d.%m.%Y") if pd.notna(row.get("date")) else "",
                        "datetime":          f"{row['date'].strftime('%d.%m.%Y')} {row.get('time', '')}",
                        "event_type":        row.get("event_type", ""),
                        "responsible":       resp,
                        "responsible_clean": str(resp).lower().strip(),
                        "topic":             row.get("topic", ""),
                        "room":              row.get("room", ""),
                    })
            if hist2:
                csv2 = pd.DataFrame(hist2).to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Finalisierten Plan nochmals herunterladen",
                    csv2,
                    file_name=f"finalisiert_{MONTH_LABELS[confirm_month].replace(' ', '_')}.csv",
                    mime="text/csv",
                    key=f"dl_hist2_{confirm_month}",
                )

        # ── Overview all months ───────────────────────────────────────────────
        st.markdown("<hr>", unsafe_allow_html=True)
        _sec("Übersicht aller Monate")
        _rf, _ = st.columns([2, 8])
        with _rf:
            if st.button("↺  Aktualisieren", key="refresh_confirmations"):
                try:
                    confs, fins = load_confirmations(year=2026)
                    st.session_state["confirmations"]    = confs
                    st.session_state["finalized_months"] = fins
                    st.rerun()
                except Exception as e:
                    _banner(f"Fehler: {e}", "err")

        overview_rows = []
        for m in range(1, 13):
            mc  = st.session_state["confirmations"].get(m, {})
            fin = m in st.session_state["finalized_months"]
            overview_rows.append({
                "Monat":  MONTH_LABELS[m],
                "A":      "✅" if mc.get("A") else "⬜",
                "B":      "✅" if mc.get("B") else "⬜",
                "C":      "✅" if mc.get("C") else "⬜",
                "Status": "🔒 Gesperrt" if fin else (
                    "✅ Bereit" if all(mc.get(r) for r in REVIEWERS)
                    else f"⏳ {sum(mc.get(r, False) for r in REVIEWERS)}/3"
                ),
            })
        st.dataframe(
            pd.DataFrame(overview_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Monat":  st.column_config.TextColumn("Monat",  width="medium"),
                "A":      st.column_config.TextColumn("A",      width="small"),
                "B":      st.column_config.TextColumn("B",      width="small"),
                "C":      st.column_config.TextColumn("C",      width="small"),
                "Status": st.column_config.TextColumn("Status", width="medium"),
            },
        )

# TAB 4 — BENACHRICHTIGUNG (position 4)
# ═════════════════════════════════════════════════════════════════════════════
with tab4:

    # ── Access gate ───────────────────────────────────────────────────────────
    _gc_ben, _ = st.columns([1, 2])
    with _gc_ben:
        ben_pw = st.text_input("Zugangscode Benachrichtigung", type="password", key="ben_pw",
                               placeholder="Zugangscode eingeben …",
                               label_visibility="collapsed")
    if ben_pw:
        _auth_ok_ben = (ben_pw == st.secrets.get("ben_password", ""))
        st.session_state["_auth_ben"] = _auth_ok_ben
        if not _auth_ok_ben:
            _banner("Falscher Zugangscode.", "err")
    elif "_auth_ben" not in st.session_state:
        st.session_state["_auth_ben"] = False

    _t3_ok = st.session_state.get("_auth_ben", False)
    if ben_pw and _t3_ok:
        _banner("Zugangscode korrekt ✓", "ok")
    elif not _t3_ok and not ben_pw:
        _banner("Bitte Zugangscode eingeben.", "info")

    if _t3_ok:
        _sec("Benachrichtigung", first=True)
        st.caption("Monat wählen → Zeilen anwählen → Vorschau prüfen → Senden.")

        if "data" not in st.session_state:
            _banner("Bitte zuerst im Plan-Tab Daten laden.", "info")

        if "data" in st.session_state:
            data       = st.session_state["data"]
            pep_months = st.session_state.get("pep_months", set())

            _mc, _ = st.columns([2, 5])
            with _mc:
                notify_month = st.selectbox(
                    "Monat",
                    list(MONTH_LABELS.keys()),
                    index=3,
                    format_func=lambda x: MONTH_LABELS[x],
                    key="notify_month",
                )

            cache_key = f"notify_schedule_{notify_month}"
            if cache_key not in st.session_state:
                if notify_month in pep_months:
                    sched = generate_full_schedule_aware(2026, notify_month, data)
                else:
                    sched = generate_sheet_only_schedule(2026, notify_month, data)
                st.session_state[cache_key] = sched

            sched = st.session_state[cache_key].copy()

            notify_df = sched[
                sched["responsible"].notna() &
                (sched["responsible"] != "") &
                (sched["responsible"] != "— TBD —")
            ].copy()

            notify_df["date_fmt"] = notify_df["date"].apply(_fmt_date_de)
            notify_df.insert(0, "✉️", False)

            notify_df["datum_only"] = notify_df["date"].apply(lambda d: d.strftime("%d.%m."))
            notify_df["weekday"]    = notify_df["date"].apply(lambda d: WEEKDAY_DE.get(d.strftime("%A"), ""))
            notify_df["datum_2l"]   = notify_df["weekday"] + "\n" + notify_df["datum_only"]
            display_cols = ["✉️", "datum_2l", "time", "responsible", "topic"]
            notify_df_display = notify_df[display_cols].rename(columns={
                "datum_2l": "Datum", "time": "Zeit", "responsible": "Person", "topic": "Thema"
            })

            _sec("Empfänger auswählen")
            st.caption("Checkbox in der ersten Spalte anwählen um eine Person in den Versand aufzunehmen.")

            edited = st.data_editor(
                notify_df_display,
                column_config={
                    "✉️":     st.column_config.CheckboxColumn("", default=False, width="small"),
                    "Datum":  st.column_config.TextColumn("Datum",  width="small"),
                    "Zeit":   st.column_config.TextColumn("Zeit",   width="small"),
                    "Person": st.column_config.TextColumn("Person", width="medium"),
                    "Thema":  st.column_config.TextColumn("Thema",  width="medium"),
                },
                disabled=[c for c in display_cols if c != "✉️"],
                hide_index=True,
                use_container_width=True,
                key=f"notify_editor_{notify_month}",
            )

            selected = edited[edited["✉️"] == True]

            st.markdown("<hr>", unsafe_allow_html=True)
            send_mode = "Vorschau / Mailto-Links"  # always mailto
            my_email  = st.secrets.get("TEST_EMAIL", "sarah.deckarm@insel.ch")

            if selected.empty:
                _banner(f"{len(selected)} Zeilen ausgewählt — bitte Zeilen anwählen.", "info")
            if not selected.empty:
                _banner(f"{len(selected)} Zeile(n) ausgewählt.", "ok")

            month_label = f"{MONTH_NAMES_DE[notify_month]} 2026"

            # ── Build firstname lookup from PEP ───────────────────────────────
            # PEP has first_name + last_name columns. Build lastname→firstname map
            # so emails say "Liebe/r Yoel" not "Liebe/r Y."
            from src.fairness import _extract_lastname as _el
            _pep_fn_lookup: dict = {}
            _pep_raw_ben = data.get("pep")
            if _pep_raw_ben is not None and not _pep_raw_ben.empty:
                for _, _pr in _pep_raw_ben.drop_duplicates("name_clean").iterrows():
                    _ln = _extract_lastname(str(_pr.get("name_clean", "") or ""))
                    _fn = str(_pr.get("first_name", "") or "").strip().capitalize()
                    if _ln and _fn:
                        _pep_fn_lookup[_ln] = _fn

            # ── Build email list ──────────────────────────────────────────────
            # Each selected row may have multiple people (e.g. Journal Club "Y. Berger / M.E. Jaquier").
            # We send one email per individual person, with only their own rows.
            kim_email     = "kim.backoffice1@gmail.com"
            emails_to_send = []
            selected_orig  = notify_df.loc[selected.index]

            # Expand: build a flat list of (individual_name, row) pairs
            individual_rows: dict = {}  # name → list of rows
            for _, row in selected_orig.iterrows():
                responsible = str(row.get("responsible", "") or "")
                names = [n.strip() for n in responsible.split("/") if n.strip()]
                for name in names:
                    if name and name != "— TBD —":
                        individual_rows.setdefault(name, []).append(row)

            import pandas as _pd_mail
            for person, rows in individual_rows.items():
                # Resolve firstname: PEP lookup by lastname → fallback to [FIRST NAME]
                _person_ln   = _extract_lastname(person.lower().strip())
                _person_fn   = _pep_fn_lookup.get(_person_ln, "[FIRST NAME]")
                person_rows_orig = _pd_mail.DataFrame(rows)
                subject, body = get_email_for_person(
                    person=person,
                    firstname=_person_fn,
                    person_rows=person_rows_orig,
                    month_label=month_label,
                )
                emails_to_send.append({
                    "person":  person,
                    "display": person.title().strip(),
                    "to_addr": kim_email,
                    "subject": subject,
                    "body":    body,
                })

            # ── Previews ──────────────────────────────────────────────────────
            _sec("Vorschau")
            for e in emails_to_send:
                with st.expander(f"{e['display']}  →  {e['to_addr']}", expanded=True):
                    e["subject"] = st.text_input(
                        "Betreff", value=e["subject"],
                        key=f"subj_{e['display']}_{notify_month}",
                    )
                    e["body"] = st.text_area(
                        "E-Mail Text", value=e["body"], height=320,
                        key=f"body_{e['display']}_{notify_month}",
                    )

            st.markdown("<hr>", unsafe_allow_html=True)

            # ── Send / mailto links ────────────────────────────────────────────
            if send_mode == "Vorschau / Mailto-Links":
                _sec("E-Mails versenden")
                st.caption("Jeder Link öffnet deinen E-Mail-Client (Outlook etc.) mit dem vorbereiteten Text.")
                for e in emails_to_send:
                    to  = e["to_addr"]
                    sub = e["subject"].replace(" ", "%20")
                    bod = e["body"].replace("\n", "%0A").replace(" ", "%20")
                    st.markdown(
                        f'<a href="mailto:{to}?subject={sub}&body={bod}" style="' +
                        'display:inline-flex;align-items:center;gap:8px;padding:10px 20px;' +
                        'border:1.5px solid var(--teal);border-radius:var(--radius);' +
                        'color:var(--teal);font-size:13px;font-weight:600;text-decoration:none;' +
                        f'background:#fff;margin-bottom:10px;width:100%;max-width:520px">' +
                        f'{e["display"]} — In Outlook öffnen</a>',
                        unsafe_allow_html=True,
                    )
            else:
                _banner("Zeilen auswählen um Emails zu senden.", "info")
