# src/email_templates.py

WEEKDAY_DE = {
    "Monday": "Mo", "Tuesday": "Di", "Wednesday": "Mi",
    "Thursday": "Do", "Friday": "Fr", "Saturday": "Sa", "Sunday": "So"
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _format_date(date_val):
    try:
        wd = WEEKDAY_DE.get(date_val.strftime("%A"), "")
        return f"{wd} {date_val.day}.{date_val.month}."
    except Exception:
        return str(date_val)


def _format_time_range(row):
    """Return e.g. '14:30–15:15' from the time field."""
    t = str(row.get("time", "")).strip()
    return t if t else ""


def _clean_topic(topic, event_type=""):
    """Strip redundant event-type prefixes from topic string."""
    topic = str(topic or "").strip()
    for prefix in [
        "Mittwochscurriculum:", "Physio Teaching:",
        "Journal Club", "Peer-Teaching Session", "Peer Teaching",
        "Case of the Day (COD)", "S - Case of the Day (COD)",
        "Fokus Intensivpflege:", "EPIC Update:",
    ]:
        if topic.startswith(prefix):
            topic = topic[len(prefix):].strip(" –-:")
            break
    return topic


def _assignment_lines(person_rows):
    """
    Build one detail line per row:
      Mi 1.4.   14:30–15:15   Mittwoch Curriculum   Thema   INO E218
    """
    lines = []
    for _, r in person_rows.iterrows():
        date_str  = _format_date(r["date"])
        time_str  = _format_time_range(r)
        evt_str   = str(r.get("event_type", "")).replace("_", " ")
        topic_str = _clean_topic(r.get("topic", ""), r.get("event_type", ""))
        room_str  = str(r.get("room", "") or "").strip()

        parts = [date_str, time_str, evt_str]
        if topic_str:
            parts.append(topic_str)
        if room_str:
            parts.append(room_str)
        lines.append("   ".join(parts))
    return "\n".join(lines)


def _extract_firstname(person: str) -> str:
    """
    Extract the best available firstname for salutation.

    Handles:
      "Julian Lippert"           → "Julian"
      "Anna Messmer"             → "Anna"
      "Marie-Noelle Kronig"      → "Marie-Noelle"
      "J. Prazak"                → "J."   (initial only — no full name available)
      "Y.A. Que"                 → "Y.A." (double initial)
      "N. Annen"                 → "N."
    If the name is initial-format we return the initial so Nadja can correct
    the draft — better than guessing wrong.
    """
    name = person.strip()
    parts = name.split()
    if not parts:
        return name

    first = parts[0]
    # Looks like an initial: "J.", "Y.A.", "M.-E.", "H.P."
    if "." in first:
        return first  # return as-is, e.g. "J."

    # Full first name — may be hyphenated like "Marie-Noelle"
    return first.capitalize()


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ─────────────────────────────────────────────────────────────────────────────

def template_mittwoch(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Mittwochscurriculum {month_label} – Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Hier die Einteilung fürs Mittwochscurriculum {month_label}:

{lines}

Das Mittwochscurriculum findet jeweils mittwochs von 14:30–15:15 Uhr im INO E218 statt.

Falls du zu deinem Thema Fragen hast oder es anpassen möchtest, melde dich gerne bei mir.

Ganz herzlichen Dank und liebe Grüsse
nadja"""
    return subject, body


def template_peer(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Peer-Teaching Session {month_label} – Anfrage/Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Gerne möchte ich Dich für die Peer-Teaching Session einteilen/anfragen:

{lines}

Diese Weiterbildung findet jeweils jeden 2. Dienstag nach dem Röntgenrapport statt und soll ca. 15 Minuten dauern.

Es geht darum dass du etwas Spannendes aus deinem eigenen Fachgebiet präsentierst das eine gewisse Überschneidung mit der Intensivmedizin hat oder für Intensivmediziner spannend oder relevant ist.

Falls du keine Idee hast kannst du dich bei mir melden dann suchen wir zusammen ein Thema oder einen Fall; oder du kannst alternativ einen Physiologie-Talk halten (hierfür kann ich Dir ein Grundlagenpaper zur Verfügung stellen).

Ganz lieber Gruss und merci!
nadja"""
    return subject, body


def template_physio(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Physiologie-Talk {month_label} – Anfrage/Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Gerne möchte ich Dich für den Physiologie-Talk einteilen/anfragen:

{lines}

Er findet jeweils jeden 2. Dienstag nach dem Röntgenrapport statt und soll ca. 15 Minuten dauern.

Falls du keine Idee hast kannst du dich bei mir melden dann suchen wir zusammen ein Thema oder einen Fall; oder du kannst alternativ einen anderen Vortrag halten (hierfür kann ich Dir ein Grundlagenpaper zur Verfügung stellen).

Melde dich ungeniert, falls du Fragen hast – dann schauen wir's zusammen an.

Ganz lieber Gruss und merci!
nadja"""
    return subject, body


def template_cod(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Case of the Day {month_label} – Anfrage/Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Gerne möchte ich Dich für den Case of the Day einteilen/anfragen:

{lines}

Ihr könnt einen Fall aus der näheren Vergangenheit präsentieren der spannend oder eine Herausforderung war und das Therapiekonzept nochmals genauer beleuchten – mit Hilfe des anwesenden BL und des Auditoriums.
Oder auch einen älteren Fall vorstellen der Euch in Erinnerung geblieben ist und anhand dessen Ihr Euren Peers ein bestimmtes Lernziel weitergeben könnt.

Gewünscht ist eine möglichst interaktive Gestaltung.
Und es sollen nicht unbedingt nur Präsentationen von «Kolibris» sein, sondern gerne auch von Fällen mit alltäglicher klinischer Relevanz.

Meldet Euch bei Fragen gerne bei mir.
Ganz herzlichen Dank für Eure Unterstützung
nadja"""
    return subject, body


def template_journal_club(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Journal Club {month_label} – Anfrage/Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Ich möchte Dich gerne für den Journal Club {month_label} anfragen/einteilen.

{lines}

Die Lernziele sind:

• Basics der Literaturrecherche kennenlernen
• Kritische Beurteilung eines wissenschaftlichen Artikels
• Beurteilung der Relevanz für die klinische Arbeit
• Verbesserung statistischer Kenntnisse

Bitte führe die Literaturrecherche selbstständig durch – dein:e Oberärzt:in unterstützt dich bei Bedarf.
Es sollte ein grosses intensivmedizinisches Journal sein oder ein anderes grosses Journal mit intensivmedizinischem Thema (Bsp. NEJM, JAMA oä.). Das Paper sollte nicht älter als 12 Monate sein. Bitte keine Reviews oder Case reports auswählen.
Für statistische und methodologische Fragen ist während des Journal Club ein Leitender Arzt anwesend.

Bitte verschicke den Artikel (via KIM-Administration) genügend früh an die KIM-Ärzt:innen damit sie sich vorbereiten und einbringen können.
Die schon vorgestellten Artikel findest du unter dem Laufwerk L:\\KIM\\Ärzte\\Weiterbildung\\Journal Club

Ganz herzlichen Dank und liebe Grüsse!
nadja"""
    return subject, body


def template_generic(person, person_rows, month_label, firstname=None):
    if not firstname or firstname == "[FIRST NAME]":
        firstname = _extract_firstname(person)
    subject   = f"Weiterbildung {month_label} – Einteilung"
    lines     = _assignment_lines(person_rows)
    body = f"""Liebe/r {firstname}

Hier die Einteilung für {month_label}:

{lines}

[Placeholder]

Ganz herzlichen Dank und liebe Grüsse
nadja"""
    return subject, body


# ─────────────────────────────────────────────────────────────────────────────
# ROUTING
# ─────────────────────────────────────────────────────────────────────────────

EVENT_TEMPLATES = {
    "Mittwoch_Curriculum":   template_mittwoch,
    "PEER":                  template_peer,
    "COD_JUNIOR":            template_cod,
    "COD_SENIOR":            template_cod,
    "PHYSIO":                template_physio,
    "Journal_Club":          template_journal_club,
    "Teaching_Tuesday":      template_peer,
    "Bedside_Infektiologie": template_generic,
    "NDS_Fallbesprechung":   template_generic,
    "Trauma_Board":          template_generic,
    "Therapieplanung":       template_generic,
    "Fokus_Intensivpflege":  template_generic,
    "TTE_Curriculum":        template_generic,
    "Masterclass":           template_generic,
    "KimSim":                template_generic,
}


def get_email(event_type, person, person_rows, month_label, firstname=None):
    template_fn = EVENT_TEMPLATES.get(event_type, template_generic)
    return template_fn(person, person_rows, month_label, firstname=firstname)


def get_email_for_person(person, person_rows, month_label, firstname=None):
    """
    Pick the right template based on event type.
    If a person has multiple different event types in one batch, use generic.

    person     — display name e.g. "J. Prazak" or "Julian Lippert" (used for display)
    firstname  — resolved first name from PEP lookup e.g. "Yoel"; falls back to
                 _extract_firstname(person) if not provided, or "[FIRST NAME]" if
                 that also fails to produce a real name.
    """
    event_types = person_rows["event_type"].unique().tolist()
    if len(event_types) == 1:
        return get_email(event_types[0], person, person_rows, month_label, firstname=firstname)
    return template_generic(person, person_rows, month_label, firstname=firstname)
