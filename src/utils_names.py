# src/utils_names.py

# special cases → do NOT format these
SPECIAL_CASES = {
    "fallführende ärzteschaft": "Fallführende Ärzteschaft",
    "fallführende aerzteschaft": "Fallführende Ärzteschaft",
}


def format_single_person(name_raw: str) -> str:

    if not name_raw or not isinstance(name_raw, str):
        return name_raw

    name_clean = name_raw.strip()

    # 🔥 special cases (keep as is)
    if name_clean.lower() in SPECIAL_CASES:
        return SPECIAL_CASES[name_clean.lower()]

    # already formatted (e.g. "B. Lehmann")
    if "." in name_clean and name_clean.split()[0].endswith("."):
        return name_clean

    parts = name_clean.split()

    if len(parts) < 2:
        return name_clean

    # detect format
    if parts[0].islower():
        # lastname firstname
        lastname = parts[0]
        firstname = parts[1]
    else:
        # firstname lastname
        firstname = parts[0]
        lastname = parts[1]

    firstname = firstname.lower()
    lastname = lastname.lower()

    # handle hyphen first names (yok-ai → Y.-A.)
    if "-" in firstname:
        initials = "".join([p[0].upper() + "." for p in firstname.split("-")])
    else:
        initials = firstname[0].upper() + "."

    return f"{initials} {lastname.capitalize()}"


def format_people(name_field: str) -> str:

    if not name_field or not isinstance(name_field, str):
        return name_field

    people = name_field.split("/")

    formatted = [
        format_single_person(p.strip()) for p in people
    ]

    return " / ".join(formatted)
