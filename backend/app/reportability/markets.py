"""Seriousness and causation, assessed per market (T-G15S), and the fixed harm-severity scale (T-G15H), as plain
functions and code constants.

Each market the organization enabled (it entered a reporting window for it) has a starter question set with a version
string. Every question shows its definition and its clause; the wording paraphrases the regulation's definitions (21 CFR
803.3; EU MDR Art. 2(64)-(66) and MDCG 2023-3; the UK MDR 2002 as amended; India MDR 2017 Rules 3 and 26) and is
starter text until the regulatory consultant confirms it (T-B6). Answers are Yes, No, Unknown or Not applicable, each
with a rationale. The answers point to a suggested conclusion; a person confirms or overrides it with a reason, and
signs. **Unknown is never No:** an Unknown that could make the event reportable gives "pending information", and a
"not reportable" conclusion is refused while it remains. MDARIX never answers a question, never signs and never
submits a report.

The harm-severity scale is fixed in code (``scale-starter-1``): five ISO 14971-style levels, the IMDRF Annex F
health-impact terms mapped to each (paraphrased, as constants; the coded Annex F release arrives with the MVP, G2a),
and each market's "serious" threshold. The scale informs: it never answers a question or changes a conclusion. An
answer that says "not serious" while the level is at or above the market's threshold needs a written reason.

Codes and versions are the MVP's (G15, G18), so the MVP's guide engine replaces these constants without renaming
anything stored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from backend.app.reportability import rules
from backend.app.standards import STARTER_MARK, version_words

# The label every signed record and document made in a free trial carries (T-B5).
PRACTICE_LABEL = "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record."

YES, NO, UNKNOWN, NOT_APPLICABLE = "YES", "NO", "UNKNOWN", "NOT_APPLICABLE"
ANSWERS = (YES, NO, UNKNOWN, NOT_APPLICABLE)
ANSWER_LABELS = {YES: "Yes", NO: "No", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable"}

US, EU_NI, GB, IN = "US", "EU_NI", "GB", "IN"
MARKETS = (US, EU_NI, GB, IN)
MARKET_LABELS = {
    US: "United States (FDA)",
    EU_NI: "EU and Northern Ireland (EU MDR)",
    GB: "Great Britain (MHRA)",
    IN: "India (CDSCO)",
}
# The countries of each market, as complaint and window fields name them (rules.normalize compares them).
MARKET_COUNTRIES = {
    US: rules._US,
    EU_NI: [*rules._EU, "Northern Ireland", "NI"],
    GB: rules._GB,
    IN: rules._IN,
}

REPORTABLE, PENDING, NOT_REPORTABLE = "REPORTABLE", "PENDING_INFORMATION", "NOT_REPORTABLE"
SUGGESTIONS = (REPORTABLE, PENDING, NOT_REPORTABLE)
# What a person signs: pending is a state of a saved assessment, not a conclusion.
CONCLUSIONS = (REPORTABLE, NOT_REPORTABLE)
CONCLUSION_LABELS = {
    REPORTABLE: "Reportable",
    PENDING: "Pending information",
    NOT_REPORTABLE: "Not reportable",
}

REASON_MIN = 10
RATIONALE_MAX = 2000
EVIDENCE_MAX = 10
EVIDENCE_ITEM_MAX = 200


@dataclass(frozen=True)
class ReportType:
    label: str
    days: int | None
    day_basis: str = rules.CALENDAR


REPORT_TYPES = {
    "US_30_DAY": ReportType("30-calendar-day report (21 CFR 803.50)", 30),
    "US_5_WORK_DAY": ReportType("5-work-day report (21 CFR 803.53)", 5, rules.WORK),
    "EU_2_DAY": ReportType("Serious public health threat: 2 days (EU MDR Art. 87(4))", 2),
    "EU_10_DAY": ReportType("Death or unanticipated serious deterioration: 10 days (EU MDR Art. 87(5))", 10),
    "EU_15_DAY": ReportType("Serious incident: 15 days (EU MDR Art. 87(3))", 15),
    "GB_2_DAY": ReportType("Serious public health threat: 2 days (UK MDR 2002 as amended)", 2),
    "GB_10_DAY": ReportType("Death or unanticipated serious deterioration: 10 days (UK MDR 2002 as amended)", 10),
    "GB_15_DAY": ReportType("Serious incident: 15 days (UK MDR 2002 as amended)", 15),
    # The period is the organization's window for India (rules.TEMPLATES, starter text).
    "IN_SERIOUS_ADVERSE_EVENT": ReportType("Serious adverse event (India MDR 2017 Rule 26)", None),
}


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    definition: str
    clause: str
    basis: tuple[str, ...]
    # The answer says whether the harm reaches the market's "serious" threshold (checked against the scale).
    serious: bool = False
    note: str = ""
    # False once a customer's guide version rewords it (T-G15); an extra question is the customer's own: recorded and
    # printed with the answer, never part of the conclusion and never required.
    starter: bool = True
    extra: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "definition": self.definition,
            "clause": self.clause,
            "basis": list(self.basis),
            "serious": self.serious,
            "note": self.note or None,
            "starter": self.starter,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class QuestionSet:
    market: str
    version: str
    title: str
    questions: tuple[Question, ...]
    note: str = ""
    basis: tuple[str, ...] = field(default_factory=tuple)

    def ids(self) -> list[str]:
        return [question.id for question in self.questions]

    def as_dict(self) -> dict:
        return {
            "market": self.market,
            "market_label": MARKET_LABELS[self.market],
            "version": self.version,
            "title": self.title,
            "note": self.note or None,
            "basis": list(self.basis),
            "starter_mark": STARTER_MARK,
            "questions": [question.as_dict() for question in self.questions],
        }


_US_BASIS = ("CFR803_3", "CFR803_50", "CFR803_53")
_US_INJURY = (
    "Serious injury (21 CFR 803.3(w)) is an injury or illness that is life-threatening, results in permanent impairment "
    "of a body function or permanent damage to a body structure, or needs medical or surgical intervention to preclude "
    "such permanent impairment or damage. Permanent means irreversible, excluding trivial impairment or damage. Answer "
    "each part on its own."
)
US_SET = QuestionSet(
    US,
    "US-starter-1",
    "US medical device reporting (21 CFR Part 803)",
    (
        Question(
            "US1",
            "Did a death occur?",
            "A death of a patient, user or other person that the information reasonably suggests.",
            "21 CFR 803.50(a)(1)",
            ("CFR803_50",),
            serious=True,
        ),
        Question(
            "US2A",
            "Serious injury, part (a): is the injury or illness life-threatening?",
            _US_INJURY,
            "21 CFR 803.3(w)(1)",
            ("CFR803_3",),
            serious=True,
        ),
        Question(
            "US2B",
            "Serious injury, part (b): does it result in permanent impairment of a body function or permanent damage to "
            "a body structure?",
            _US_INJURY,
            "21 CFR 803.3(w)(2)",
            ("CFR803_3",),
            serious=True,
        ),
        Question(
            "US2C",
            "Serious injury, part (c): does it need medical or surgical intervention to preclude permanent impairment "
            "of a body function or permanent damage to a body structure?",
            _US_INJURY,
            "21 CFR 803.3(w)(3)",
            ("CFR803_3",),
            serious=True,
        ),
        Question(
            "US3",
            "Did the device cause or contribute to the death or serious injury?",
            "Caused or contributed (21 CFR 803.3(c)): the death or serious injury was, or may have been, attributed to "
            "the device, including through its failure, malfunction, improper or inadequate design, manufacture or "
            "labelling, or user error.",
            "21 CFR 803.3(c)",
            ("CFR803_3",),
        ),
        Question(
            "US4",
            "Did the device malfunction?",
            "Malfunction (21 CFR 803.3(k)): the device failed to meet its performance specifications or otherwise "
            "perform as intended.",
            "21 CFR 803.3(k)",
            ("CFR803_3",),
        ),
        Question(
            "US5",
            "Would the malfunction be likely to cause or contribute to a death or serious injury if it were to recur?",
            "A malfunction is reportable when the device, or a similar device you market, would be likely to cause or "
            "contribute to a death or serious injury if the malfunction were to recur.",
            "21 CFR 803.50(a)(2)",
            ("CFR803_50",),
            note="Recurrence is presumed: answer what would follow if it recurred, not whether it will recur. A No "
            "needs its reason.",
        ),
        Question(
            "US6",
            "Is remedial action needed to prevent an unreasonable risk of substantial harm to the public health, or has "
            "FDA asked in writing for a 5-day report?",
            "Remedial action (21 CFR 803.3(v)) is any action other than routine maintenance or servicing of a device "
            "where such action is necessary to prevent recurrence of a reportable event. Yes gives the 5-work-day "
            "report (803.53); otherwise a reportable event gets the 30-calendar-day report (803.50).",
            "21 CFR 803.53(a), (b); 803.3(v)",
            ("CFR803_53", "CFR803_3"),
        ),
    ),
    basis=_US_BASIS,
)


def _vigilance_set(market: str, version: str, title: str, prefix: str, law: str, clause: str, basis, report_note):
    """The EU/NI and GB question sets: the same pattern, each in its own law's words and clauses."""
    deterioration = (
        f"A serious deterioration in the state of health ({law}; MDCG 2023-3) includes a life-threatening illness or "
        "injury, permanent impairment of a body structure or function, hospitalisation or its prolongation, medical "
        "or surgical intervention to prevent either, chronic disease, and foetal distress, foetal death or a "
        "congenital impairment. Answer each criterion on its own: led to, might have led to, or might lead to."
    )
    limbs = (
        ("A", "a life-threatening illness or injury?"),
        ("B", "permanent impairment of a body structure or a body function?"),
        ("C", "hospitalisation, or prolonged hospitalisation, of a patient?"),
        (
            "D",
            "medical or surgical intervention to prevent a life-threatening illness or injury, or a permanent "
            "impairment?",
        ),
        ("E", "a chronic disease?"),
        ("F", "foetal distress, foetal death, or a congenital physical or mental impairment or birth defect?"),
    )
    return QuestionSet(
        market,
        version,
        title,
        (
            Question(
                f"{prefix}1",
                "Is it an incident?",
                f"Incident ({law}): any malfunction or deterioration in the characteristics or performance of a device "
                "made available on the market, including use error due to ergonomic features, any inadequacy in the "
                "information supplied by the manufacturer, and any undesirable side-effect.",
                f"{clause} (incident)",
                basis,
            ),
            Question(
                f"{prefix}2",
                "Did it directly or indirectly lead, might it have led, or might it lead to the death of a patient, "
                "user or other person?",
                f"Serious incident ({law}): an incident that directly or indirectly led, might have led or might lead "
                "to a death, a temporary or permanent serious deterioration in health, or a serious public health "
                "threat.",
                f"{clause} (serious incident)",
                basis,
                serious=True,
            ),
            *(
                Question(
                    f"{prefix}3{letter}",
                    f"Serious deterioration in health, criterion ({letter.lower()}): did it lead, might it have led, or "
                    f"might it lead to {text}",
                    deterioration,
                    f"{clause} (serious incident); MDCG 2023-3",
                    (*basis, "MDCG_2023_3") if market == EU_NI else basis,
                    serious=True,
                )
                for letter, text in limbs
            ),
            Question(
                f"{prefix}4",
                "Did it lead, might it have led, or might it lead to a serious public health threat?",
                f"Serious public health threat ({law}): an event that could result in imminent risk of death, serious "
                "deterioration in health or serious illness, that may require prompt remedial action and may cause "
                "significant morbidity or mortality, or that is unusual or unexpected for the place and time.",
                f"{clause} (serious public health threat)",
                basis,
                serious=True,
            ),
            Question(
                f"{prefix}5",
                "Is a causal relationship between the device and the event established, or reasonably possible?",
                "A causal relationship is established, or cannot be excluded on the information you have. When you "
                "cannot tell, it is reasonably possible.",
                f"{report_note}; MDCG 2023-3" if market == EU_NI else report_note,
                (*basis, "MDCG_2023_3") if market == EU_NI else basis,
            ),
            Question(
                f"{prefix}6",
                "Was a serious deterioration in health unanticipated?",
                "Asked for the 10-day report: a serious deterioration that was not anticipated (for example not in the "
                "risk analysis or the information supplied with the device).",
                report_note,
                basis,
            ),
        ),
        note="Report when unsure: if you cannot tell whether the event is a serious incident, report it within the "
        "period (MDCG 2023-3).",
        basis=tuple(basis),
    )


EU_SET = _vigilance_set(
    EU_NI,
    "EU-starter-1",
    "EU and Northern Ireland vigilance (EU MDR Art. 87)",
    "EU",
    "EU MDR Art. 2(64)–(66)",
    "EU MDR Art. 2(64)–(66)",
    ("MDR_2", "MDR_87"),
    "EU MDR Art. 87",
)
GB_SET = _vigilance_set(
    GB,
    "GB-starter-1",
    "Great Britain vigilance (UK MDR 2002 as amended by SI 2024/1368)",
    "GB",
    "UK MDR 2002 as amended by SI 2024/1368",
    "UK MDR 2002 Part 4A, as amended by SI 2024/1368",
    ("UK_MDR",),
    "UK MDR 2002 Part 4A, as amended by SI 2024/1368 (reporting)",
)
_IN_CLAUSE = "India MDR 2017 Rules 3 and 26"
_IN_SERIOUS = (
    "A serious adverse event (India MDR 2017, starter text: criteria to confirm against the Rules and the MDAE form) "
    "results in death, is life-threatening, needs in-patient hospitalisation or prolongs it, results in persistent or "
    "significant disability or incapacity, is a congenital anomaly or birth defect, or needs an intervention to "
    "prevent permanent impairment or damage. Answer each criterion on its own."
)
IN_SET = QuestionSet(
    IN,
    "IN-starter-1",
    "India adverse event reporting (Medical Devices Rules 2017)",
    (
        Question(
            "IN1",
            "Is it an adverse event suspected to be associated with the device?",
            "An adverse event: an untoward occurrence in a patient, user or other person where the device is "
            "suspected to have caused or contributed to it.",
            _IN_CLAUSE,
            ("IN_MDR",),
        ),
        *(
            Question(
                f"IN2{letter}",
                f"Serious, criterion ({letter.lower()}): {text}",
                _IN_SERIOUS,
                _IN_CLAUSE,
                ("IN_MDR",),
                True,
            )
            for letter, text in (
                ("A", "did it result in death?"),
                ("B", "is it life-threatening?"),
                ("C", "did it need in-patient hospitalisation, or prolong it?"),
                ("D", "did it result in persistent or significant disability or incapacity?"),
                ("E", "is it a congenital anomaly or birth defect?"),
                ("F", "did it need an intervention to prevent permanent impairment or damage?"),
            )
        ),
        Question(
            "IN3",
            "Is it unexpected?",
            "Unexpected: its nature or severity is not consistent with the device's labelling or the risks known for "
            "it. A serious and unexpected event is a suspected unexpected serious adverse event.",
            _IN_CLAUSE,
            ("IN_MDR",),
        ),
    ),
    basis=("IN_MDR",),
)
QUESTION_SETS = {question_set.market: question_set for question_set in (US_SET, EU_SET, GB_SET, IN_SET)}


# --------------------------------------------------------------------------------------------- answers to a result


def _value(answers: dict, question_id: str) -> bool | None:
    """Yes is True; No and Not applicable are False; Unknown, or no answer, is None (never False)."""
    answer = (answers.get(question_id) or {}).get("answer")
    if answer == YES:
        return True
    if answer in (NO, NOT_APPLICABLE):
        return False
    return None


def _any(*values: bool | None) -> bool | None:
    if True in values:
        return True
    return None if None in values else False


def _all(*values: bool | None) -> bool | None:
    if False in values:
        return False
    return None if None in values else True


def _suggestion(reportable: bool | None) -> str:
    return {True: REPORTABLE, None: PENDING, False: NOT_REPORTABLE}[reportable]


def evaluate(market: str, answers: dict) -> dict:
    """The suggested conclusion of a market's answers, the report type, and the notes that explain it.
    ``report_type`` is set when the suggestion is reportable; ``report_type_if_reportable`` is the type a person who
    concludes reportable against the suggestion gets."""
    v = lambda question_id: _value(answers, question_id)  # noqa: E731
    notes: list[str] = []
    if market == US:
        injury = _any(v("US2A"), v("US2B"), v("US2C"))
        harm = _all(_any(v("US1"), injury), v("US3"))
        malfunction = _all(v("US4"), v("US5"))
        reportable = _any(harm, malfunction)
        five_day = v("US6")
        kind = "US_5_WORK_DAY" if five_day else "US_30_DAY"
        if reportable and five_day is None:
            notes.append("Question 6 is Unknown: a Yes makes it the 5-work-day report (803.53).")
        elif reportable and five_day is False:
            notes.append("Question 6 is No, so not the 5-work-day report (803.53).")
    elif market in (EU_NI, GB):
        p = "EU" if market == EU_NI else "GB"
        limbs = [v(f"{p}3{letter}") for letter in "ABCDEF"]
        reportable = _all(v(f"{p}1"), _any(v(f"{p}2"), *limbs, v(f"{p}4")), v(f"{p}5"))
        if v(f"{p}4"):
            kind = f"{p}_2_DAY"
        elif v(f"{p}2") or (_any(*limbs) and v(f"{p}6")):
            kind = f"{p}_10_DAY"
        else:
            kind = f"{p}_15_DAY"
            if reportable and _any(*limbs) and v(f"{p}6") is None:
                notes.append("Question 6 is Unknown: an unanticipated serious deterioration is the 10-day report.")
    elif market == IN:
        reportable = _all(v("IN1"), _any(*(v(f"IN2{letter}") for letter in "ABCDEF")))
        kind = "IN_SERIOUS_ADVERSE_EVENT"
        if reportable and v("IN3"):
            notes.append("Serious and unexpected: a suspected unexpected serious adverse event.")
    else:
        raise ValueError(f"unknown market {market}")
    suggested = _suggestion(reportable)
    if suggested == PENDING:
        notes.append(
            "An Unknown answer could make the event reportable: the suggestion stays pending information, and "
            '"not reportable" cannot be concluded until it is answered.'
        )
    return {
        "suggested": suggested,
        "report_type": kind if reportable else None,
        "report_type_if_reportable": kind,
        "notes": notes,
    }


def clean_answers(question_set: QuestionSet, raw: dict | None) -> dict:
    """The answers as stored: only the set's questions; each answer, its rationale tidied, evidence tidied."""
    found = {}
    for question_id in question_set.ids():
        item = (raw or {}).get(question_id)
        if not isinstance(item, dict):
            continue
        answer = str(item.get("answer") or "").strip().upper() or None
        rationale = " ".join(str(item.get("rationale") or "").split())
        evidence = []
        for entry in item.get("evidence") or []:
            text = " ".join(str(entry or "").split())[:EVIDENCE_ITEM_MAX]
            if text and text not in evidence:
                evidence.append(text)
        if answer or rationale or evidence:
            found[question_id] = {"answer": answer, "rationale": rationale, "evidence": evidence[:EVIDENCE_MAX]}
    return found


def answers_problem(question_set: QuestionSet, answers: dict, *, complete: bool) -> str | None:
    """Why the answers cannot be saved (``complete=False``) or signed (``complete=True``), or None."""
    for question in question_set.questions:
        item = answers.get(question.id)
        if question.extra:
            if item is not None and item["answer"] is not None and item["answer"] not in ANSWERS:
                return f"Question {question.id}: answer Yes, No, Unknown or Not applicable"
            if item is not None and len(item["rationale"]) > RATIONALE_MAX:
                return f"Question {question.id}: keep the rationale under {RATIONALE_MAX} characters"
            continue
        if item is None:
            if complete:
                return f"Answer question {question.id}: {question.text}"
            continue
        if item["answer"] is not None and item["answer"] not in ANSWERS:
            return f"Question {question.id}: answer Yes, No, Unknown or Not applicable"
        if len(item["rationale"]) > RATIONALE_MAX:
            return f"Question {question.id}: keep the rationale under {RATIONALE_MAX} characters"
        if complete and item["answer"] is None:
            return f"Answer question {question.id}: {question.text}"
        if complete and len(item["rationale"]) < REASON_MIN:
            if question.id == "US5" and item["answer"] == NO:
                return "Question US5 is No: say in your own words why a recurrence would not be likely to cause harm"
            return f"Question {question.id}: give the rationale for the answer in at least {REASON_MIN} characters"
    return None


# --------------------------------------------------------------------------------------------- the harm scale

SCALE_VERSION = "scale-starter-1"
NEGLIGIBLE, MINOR, SERIOUS, CRITICAL, CATASTROPHIC = "NEGLIGIBLE", "MINOR", "SERIOUS", "CRITICAL", "CATASTROPHIC"
LEVELS = (NEGLIGIBLE, MINOR, SERIOUS, CRITICAL, CATASTROPHIC)
LEVEL_LABELS = {
    NEGLIGIBLE: "Negligible",
    MINOR: "Minor",
    SERIOUS: "Serious",
    CRITICAL: "Critical",
    CATASTROPHIC: "Catastrophic",
}
# IMDRF Annex F health-impact terms (paraphrased, starter text): term -> (label, level, cannot be lowered).
TERMS = {
    "NO_HEALTH_CONSEQUENCE": ("No health consequences or impact", NEGLIGIBLE, False),
    "TEMPORARY_DISCOMFORT": ("Inconvenience or temporary discomfort, no injury", NEGLIGIBLE, False),
    "MINOR_INJURY": ("Minor injury or illness, no medical intervention", MINOR, False),
    "TEMPORARY_IMPAIRMENT": ("Temporary impairment, resolved without intervention", MINOR, False),
    "MEDICAL_INTERVENTION": ("Injury or illness needing medical or surgical intervention", SERIOUS, False),
    "HOSPITALISATION": ("Hospitalisation, or prolonged hospitalisation", SERIOUS, False),
    "LIFE_THREATENING": ("Life-threatening illness or injury", CRITICAL, True),
    "PERMANENT_IMPAIRMENT": ("Permanent impairment of a body function or damage to a body structure", CRITICAL, True),
    "DEATH": ("Death", CATASTROPHIC, True),
}
# The lowest level that meets each market's "serious" threshold.
THRESHOLDS = {US: SERIOUS, EU_NI: SERIOUS, GB: SERIOUS, IN: SERIOUS}
THRESHOLD_LABELS = {
    US: "US serious injury",
    EU_NI: "EU/NI serious deterioration",
    GB: "GB serious deterioration",
    IN: "India serious adverse event",
}
# The complaint's severity text from the QMS, lower case, to a level (a fixed table; anything else is not mapped).
QMS_SEVERITY = {
    "negligible": NEGLIGIBLE,
    "none": NEGLIGIBLE,
    "minor": MINOR,
    "low": MINOR,
    "moderate": SERIOUS,
    "medium": SERIOUS,
    "major": SERIOUS,
    "serious": SERIOUS,
    "high": CRITICAL,
    "critical": CRITICAL,
    "catastrophic": CATASTROPHIC,
    "fatal": CATASTROPHIC,
}
PROTECTED_NOTE = (
    "Death, life-threatening harm and permanent impairment sit at or above every market's threshold and cannot be "
    "lowered."
)


def rank(level: str | None) -> int:
    return LEVELS.index(level) if level in LEVELS else -1


def level_of_severity(severity: object) -> str | None:
    """The level the complaint's QMS severity maps to, or None ("not mapped: choose a level")."""
    return QMS_SEVERITY.get(" ".join(str(severity or "").split()).lower())


def scale() -> dict:
    """The scale as a screen and a training document show it."""
    return {
        "version": SCALE_VERSION,
        "starter_mark": STARTER_MARK,
        "protected_note": PROTECTED_NOTE,
        "levels": [
            {
                "code": level,
                "label": LEVEL_LABELS[level],
                "terms": [{"code": code, "label": label} for code, (label, at, _) in TERMS.items() if at == level],
                "thresholds": [
                    {"market": market, "label": THRESHOLD_LABELS[market]}
                    for market in MARKETS
                    if THRESHOLDS[market] == level
                ],
            }
            for level in LEVELS
        ],
        "terms": [
            {"code": code, "label": label, "level": level, "protected": protected}
            for code, (label, level, protected) in TERMS.items()
        ],
    }


def harm_problem(level: str | None, term: str | None, reason: str, severity: object, *, complete: bool) -> str | None:
    """Why the harm level cannot be kept: a protected term may not be lowered, and a level that differs from the
    term's (or from the QMS severity's, without a term) needs a reason. Signing needs a level."""
    if level is not None and level not in LEVELS:
        return "Choose a level of the harm-severity scale"
    if term is not None and term not in TERMS:
        return "Choose a health-impact term of the scale"
    if level is None:
        return "Choose the harm level: the complaint's severity is not mapped" if complete else None
    expected = TERMS[term][1] if term else level_of_severity(severity)
    if term and TERMS[term][2] and rank(level) < rank(expected):
        return f"{TERMS[term][0]} sits at {LEVEL_LABELS[expected]} or above and cannot be lowered"
    if expected is not None and level != expected and len(reason) < REASON_MIN:
        return (
            f"The scale maps this to {LEVEL_LABELS[expected]}: say in at least {REASON_MIN} characters why you chose "
            f"{LEVEL_LABELS[level]}"
        )
    return None


def disagreement(market: str, answers: dict, level: str | None) -> str | None:
    """An answer that disagrees with the scale: the level is at or above the market's threshold, yet every seriousness
    question is answered No or Not applicable. Unknown never disagrees: it is not a No."""
    if rank(level) < rank(THRESHOLDS[market]):
        return None
    serious = [question.id for question in QUESTION_SETS[market].questions if question.serious]
    if serious and all(_value(answers, question_id) is False for question_id in serious):
        return (
            f"The harm level {LEVEL_LABELS[level]} is at or above the {THRESHOLD_LABELS[market]} threshold, yet every "
            "seriousness question is answered No or Not applicable"
        )
    return None


def conclusion_problem(suggested: str, conclusion: str, reason: str) -> str | None:
    """Why a conclusion cannot be signed against the suggestion: an override needs a reason, and "not reportable" is
    refused while an Unknown could make the event reportable."""
    if conclusion not in CONCLUSIONS:
        return "Conclude reportable or not reportable"
    if conclusion == NOT_REPORTABLE and suggested == PENDING:
        return (
            'An Unknown answer could make the event reportable: "not reportable" cannot be concluded until it is '
            "answered (Unknown is never No)"
        )
    if conclusion != suggested and len(reason) < REASON_MIN:
        return f"You override the suggestion: say in at least {REASON_MIN} characters why"
    return None


# --------------------------------------------------------------------------------------------- markets and clocks


def market_of(country: object) -> str | None:
    """The market of an event's country, or None."""
    name = rules.normalize(country)
    if not name:
        return None
    for market in MARKETS:
        if name in {rules.normalize(item) for item in MARKET_COUNTRIES[market]}:
            return market
    return None


def window_markets(window: dict) -> set[str]:
    """The markets a reporting window covers (a window without markets covers every market)."""
    if not window.get("markets"):
        return set(MARKETS)
    names = {rules.normalize(item) for item in window["markets"]}
    return {market for market in MARKETS if names & {rules.normalize(item) for item in MARKET_COUNTRIES[market]}}


def enabled_markets(windows: list[dict]) -> list[str]:
    """The markets the organization enabled: those it entered a reporting window for."""
    covered = set().union(*(window_markets(window) for window in windows)) if windows else set()
    return [market for market in MARKETS if market in covered]


def _clock(name: str, days: int, day_basis: str, aware: date, today: date, source: str) -> dict:
    due = rules.due_date(aware, {"days": days, "day_basis": day_basis})
    return {
        "window": name,
        "days": days,
        "day_basis": day_basis,
        "due_date": due.isoformat(),
        "days_left": (due - today).days,
        "state": rules.clock_state(due, today, days),
        "source": source,
    }


def market_clock(
    market: str, state: str | None, report_type: str | None, windows: list[dict], aware: date | None, today: date
) -> dict | None:
    """A market's clock. Reportable: the organization's window of the report type's period for that market, or the
    regulation's period when none matches. Pending, or not yet assessed: the shortest window the organization set for
    that market, still counting. Not reportable: none."""
    if aware is None or state == NOT_REPORTABLE:
        return None
    mine = [window for window in windows if market in window_markets(window)]
    clocks = [_clock(w["name"], w["days"], w["day_basis"], aware, today, "WINDOW") for w in mine]
    kind = REPORT_TYPES.get(report_type or "")
    if state == REPORTABLE and kind and kind.days:
        exact = [
            clock
            for window, clock in zip(mine, clocks)
            if window["days"] == kind.days and window["day_basis"] == kind.day_basis
        ]
        if exact:
            return min(exact, key=lambda clock: clock["due_date"])
        return _clock(kind.label, kind.days, kind.day_basis, aware, today, "REGULATION")
    return min(clocks, key=lambda clock: clock["due_date"]) if clocks else None


def signature_meaning(ref: str, market: str, version: str, conclusion: str) -> str:
    return (
        f"I have assessed {ref} for {MARKET_LABELS[market]} with its questions, {version_words(version)}, and the "
        f"harm-severity scale, {version_words(SCALE_VERSION)}, and conclude: {CONCLUSION_LABELS[conclusion].lower()}."
    )
