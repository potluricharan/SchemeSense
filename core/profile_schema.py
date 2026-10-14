"""Family profile schema.

`profile` is the persisted family document. It has a small family-level section
and a `members[]` list. The rule engine (core.rules) reads exactly these keys.
"""

from __future__ import annotations

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Jammu and Kashmir", "Ladakh", "Delhi", "Puducherry",
]

GENDERS = ["male", "female", "other"]
RELATIONS = ["head", "spouse", "son", "daughter", "parent", "grandparent", "other"]
MARITAL_STATUS = ["unmarried", "married", "widowed", "divorced", "abandoned"]
CASTES = ["general", "obc", "sc", "st"]
STUDY_LEVELS = ["none", "middle", "secondary", "higher_secondary", "degree", "diploma"]

FAMILY_FIELDS = {
    "family_name": {"type": "text", "default": "", "label": "Family / Head name"},
    "mobile": {"type": "text", "default": "", "label": "Registered mobile number (for login)",
               "placeholder": "10-digit mobile number"},
    "state": {"type": "select", "options": STATES, "default": "Maharashtra", "label": "State of residence"},
    "area": {"type": "select", "options": ["rural", "urban"], "default": "rural", "label": "Area"},
    "annual_income": {"type": "number", "default": 150000, "min": 0, "step": 10000,
                      "label": "Annual family income (₹)"},
    "ration_card": {"type": "toggle", "default": False, "label": "Has (Smart) Ration Card"},
    "destitute": {"type": "toggle", "default": False,
                  "label": "Destitute family (no means of subsistence / dependants)"},
    "land_acres": {"type": "number", "default": 0.0, "min": 0.0, "step": 0.5,
                   "label": "Land owned (acres)"},
    "income_taxpayer": {"type": "toggle", "default": False,
                        "label": "Any member is an income-tax payer"},
    "resident_years": {"type": "number", "default": 20, "min": 0, "step": 1,
                       "label": "Years residing in this state"},
}

MEMBER_FIELDS = {
    "name": {"type": "text", "default": "", "label": "Full name"},
    "age": {"type": "number", "default": 30, "min": 0, "step": 1, "label": "Age"},
    "gender": {"type": "select", "options": GENDERS, "default": "male", "label": "Gender"},
    "relation": {"type": "select", "options": RELATIONS, "default": "spouse", "label": "Relationship to head"},
    "marital_status": {"type": "select", "options": MARITAL_STATUS, "default": "married", "label": "Marital status"},
    "caste": {"type": "select", "options": CASTES, "default": "general", "label": "Caste category"},
    "community": {"type": "text", "default": "", "label": "Community (optional, e.g. Brahmin)"},
    "disability_pct": {"type": "number", "default": 0, "min": 0, "max": 100, "step": 5,
                       "label": "Disability percentage (0 if none)"},
    "student": {"type": "toggle", "default": False, "label": "Is a student"},
    "study_level": {"type": "select", "options": STUDY_LEVELS, "default": "none",
                    "label": "Current study level"},
    "technical_degree": {"type": "toggle", "default": False,
                         "label": "Enrolled in a technical (AICTE) degree/diploma course"},
    "agri_student": {"type": "toggle", "default": False,
                     "label": "Studying agriculture / allied sciences"},
    "pregnant": {"type": "toggle", "default": False, "label": "Currently pregnant"},
    "construction_worker": {"type": "toggle", "default": False,
                            "label": "Registered building / construction worker"},
    "old_age_pensioner": {"type": "toggle", "default": False,
                          "label": "Already gets an old-age pension"},
    "tb_cancer": {"type": "toggle", "default": False, "label": "Suffers from TB / Cancer"},
    "orphan": {"type": "toggle", "default": False, "label": "Orphan"},
    "covid_orphan": {"type": "toggle", "default": False, "label": "Parent(s) died of COVID-19"},
    "martyr_ward": {"type": "toggle", "default": False,
                    "label": "Ward of Armed Forces martyr"},
    "street_vendor": {"type": "toggle", "default": False, "label": "Street vendor"},
    "has_vending_cert": {"type": "toggle", "default": False,
                         "label": "Has Certificate of Vending (ULB)"},
}


def blank_member() -> dict:
    m = {}
    for k, cfg in MEMBER_FIELDS.items():
        m[k] = cfg["default"]
    return m


def blank_profile() -> dict:
    p = {}
    for k, cfg in FAMILY_FIELDS.items():
        p[k] = cfg["default"]
    p["members"] = [blank_member()]
    return p


def sample_profile() -> dict:
    """A ready-made demo family so the app demos end-to-end in one click.

    4 members (Ramesh, Geeta, Ananya, Arjun) tuned to be eligible for exactly
    5 verified schemes: IGNOAPS (old-age pension, Ramesh), Chief Minister Ladli
    Behna Yojana (Geeta), AICTE Pragati Scholarship (Geeta), Girl Child
    Protection Scheme (Ananya) and Pre-Matric OBC Scholarship (Arjun).
    """
    return {
        "family_name": "Sharma Family (demo)",
        "mobile": "9876543210",
        "state": "Madhya Pradesh",
        "area": "rural",
        "annual_income": 72000,
        "ration_card": True,
        "destitute": False,
        "land_acres": 4,
        "income_taxpayer": False,
        "resident_years": 25,
        "members": [
            {"name": "Ramesh Sharma", "age": 65, "gender": "male", "relation": "head",
             "marital_status": "married", "caste": "general", "community": "",
             "disability_pct": 0, "student": False, "study_level": "none",
             "technical_degree": False, "agri_student": False, "pregnant": False,
             "construction_worker": False, "old_age_pensioner": True, "tb_cancer": False,
             "orphan": False, "covid_orphan": False, "martyr_ward": False,
             "street_vendor": False, "has_vending_cert": False},
            {"name": "Geeta Sharma", "age": 28, "gender": "female", "relation": "spouse",
             "marital_status": "married", "caste": "general", "community": "",
             "disability_pct": 0, "student": True, "study_level": "degree",
             "technical_degree": True, "agri_student": False, "pregnant": False,
             "construction_worker": False, "old_age_pensioner": False, "tb_cancer": False,
             "orphan": False, "covid_orphan": False, "martyr_ward": False,
             "street_vendor": False, "has_vending_cert": False},
            {"name": "Ananya Sharma", "age": 16, "gender": "female", "relation": "daughter",
             "marital_status": "unmarried", "caste": "general", "community": "",
             "disability_pct": 0, "student": True, "study_level": "secondary",
             "technical_degree": False, "agri_student": False, "pregnant": False,
             "construction_worker": False, "old_age_pensioner": False, "tb_cancer": False,
             "orphan": False, "covid_orphan": False, "martyr_ward": False,
             "street_vendor": False, "has_vending_cert": False},
            {"name": "Arjun Sharma", "age": 12, "gender": "male", "relation": "son",
             "marital_status": "unmarried", "caste": "obc", "community": "",
             "disability_pct": 0, "student": True, "study_level": "middle",
             "technical_degree": False, "agri_student": False, "pregnant": False,
             "construction_worker": False, "old_age_pensioner": False, "tb_cancer": False,
             "orphan": False, "covid_orphan": False, "martyr_ward": False,
             "street_vendor": False, "has_vending_cert": False},
        ],
    }