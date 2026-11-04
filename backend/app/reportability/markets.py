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

import re
from dataclasses import dataclass, field
from functools import lru_cache

from backend.app.reportability import deadlines, rules
from backend.app.standards import STARTER_MARK, version_words

# The label every signed record and document made in a free trial carries (T-B5).
PRACTICE_LABEL = "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record."

YES, NO, UNKNOWN, NOT_APPLICABLE = "YES", "NO", "UNKNOWN", "NOT_APPLICABLE"
ANSWERS = (YES, NO, UNKNOWN, NOT_APPLICABLE)
ANSWER_LABELS = {YES: "Yes", NO: "No", UNKNOWN: "Unknown", NOT_APPLICABLE: "Not applicable"}

US, EU_NI, GB, IN, CA = "US", "EU_NI", "GB", "IN", "CA"
# Canada (0.10.76, Release C part C4) comes last, so every earlier market keeps its place on the screens.
MARKETS = (US, EU_NI, GB, IN, CA)
MARKET_LABELS = {
    US: "United States (FDA)",
    EU_NI: "EU and Northern Ireland (EU MDR)",
    GB: "Great Britain (MHRA)",
    IN: "India (CDSCO)",
    CA: "Canada (Health Canada)",
}
# The countries of each market, as complaint and window fields name them (rules.normalize compares them).
MARKET_COUNTRIES = {
    US: rules._US,
    EU_NI: [*rules._EU, "Northern Ireland", "NI"],
    GB: rules._GB,
    IN: rules._IN,
    CA: rules._CA,
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
    # Canada, Medical Devices Regulations SOR/98-282 s. 60(1) (calendar days; the awareness day is day zero).
    "CA_10_DAY": ReportType(
        "Death or serious deterioration: preliminary report in 10 days (SOR/98-282 s. 60(1)(a)(i))", 10
    ),
    "CA_30_DAY": ReportType(
        "Could lead to death or serious deterioration if it recurred: preliminary report in 30 days (SOR/98-282 "
        "s. 60(1)(a)(ii))",
        30,
    ),
    "CA_FOREIGN": ReportType(
        "Incident outside Canada: preliminary report as soon as possible after the corrective action decision "
        "(SOR/98-282 s. 60(1)(b))",
        None,
    ),
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
    # False when a customer's guide version of 0.10.59-0.10.63 reworded it (T-G15; locked from 0.10.64); an extra
    # question is the customer's own: recorded and printed with the answer, never part of the conclusion and never
    # required.
    starter: bool = True
    extra: bool = False
    # The organization's own explanation and examples beside the locked wording (0.10.64).
    explanation: str = ""
    examples: str = ""

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
            "explanation": self.explanation or None,
            "examples": self.examples or None,
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
# Canada (0.10.76, C4): Medical Devices Regulations SOR/98-282 ss. 59-61.1, current to 2026-10-19 (laws-lois.justice.
# gc.ca, read 3 Nov 2026), and Health Canada's "Incident reporting for medical devices: Guidance document" (2021).
_CA_LAW = "SOR/98-282"
_CA_SERIOUS = (
    "Serious deterioration in the state of health (SOR/98-282 s. 1, starter paraphrase): a life-threatening disease, "
    "disorder or abnormal physical state, the permanent impairment of a body function or permanent damage to a body "
    "structure, or a condition that needs an unexpected medical or surgical intervention to prevent them."
)
CA_SET = QuestionSet(
    CA,
    "CA-starter-1",
    "Canada mandatory problem reporting (Medical Devices Regulations s. 59-61.1)",
    (
        Question(
            "CA1",
            "Is the device sold in Canada?",
            "The duty to report applies to a device sold in Canada.",
            f"{_CA_LAW} s. 59(1)(a)",
            ("CA_MDR",),
        ),
        Question(
            "CA2",
            "Is the incident related to a failure of the device, a deterioration in its effectiveness, or an "
            "inadequacy in its labelling or in its directions for use?",
            "An incident is reportable only when it is related to one of these.",
            f"{_CA_LAW} s. 59(1)(b)(i)",
            ("CA_MDR",),
        ),
        Question(
            "CA3",
            "Did it lead to the death or a serious deterioration in the state of health of a patient, user or other "
            "person?",
            _CA_SERIOUS,
            f"{_CA_LAW} s. 59(1)(b)(ii); s. 60(1)(a)(i) (10 days)",
            ("CA_MDR",),
            serious=True,
        ),
        Question(
            "CA4",
            "Could it lead to death or a serious deterioration in the state of health, were it to recur?",
            _CA_SERIOUS,
            f"{_CA_LAW} s. 59(1)(b)(ii); s. 60(1)(a)(ii) (30 days)",
            ("CA_MDR",),
            serious=True,
        ),
        Question(
            "CA5",
            "Did the incident occur in Canada?",
            "An incident in Canada is reported in 10 or 30 days after you become aware of it. An incident outside "
            "Canada is reported only as question 6 says.",
            f"{_CA_LAW} s. 59(1) and (1.1)",
            ("CA_MDR",),
        ),
        Question(
            "CA6",
            "For an incident outside Canada: is it a Class I device, and has the manufacturer told the regulator of "
            "that country that it intends to take corrective action, or has that regulator required it?",
            "A foreign incident is reported for a Class I device, and only once corrective action is intended or "
            "required; then as soon as possible (Health Canada's guidance: within 48 hours of the decision). Class II "
            "to IV foreign issues come under s. 61.2 (serious risk of injury), not this tree. Answer Not applicable "
            "for an incident in Canada.",
            f"{_CA_LAW} s. 59(1.1) and (2); s. 60(1)(b)",
            ("CA_MDR",),
        ),
    ),
    note="Calendar days, the awareness day is day zero (Health Canada's guidance). The manufacturer and the importer "
    "each report, or the importer reports for both (s. 61.1). A final report follows on the timetable the "
    "preliminary report gives (s. 61).",
    basis=("CA_MDR",),
)
QUESTION_SETS = {question_set.market: question_set for question_set in (US_SET, EU_SET, GB_SET, IN_SET, CA_SET)}


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


MDCG = "MDCG 2023-3"


def _shorter(question: str, shorter: str, longer: str, cite: str | None = None) -> str:
    """The note of an Unknown that keeps the shorter report (0.10.81): which answer would lengthen it."""
    why = f" ({cite}: report within the period even when uncertain)" if cite else ""
    return (
        f"{question} is Unknown: until it is answered, {shorter} applies{why}. A No can lengthen it to {longer}. "
        "Starter rule, for your consultant to confirm."
    )


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
        # Unknown takes the shortest category the facts do not yet exclude (0.10.81, starter).
        kind = "US_30_DAY" if five_day is False else "US_5_WORK_DAY"
        if reportable and five_day is None:
            notes.append(_shorter("Question 6", "the 5-work-day report (21 CFR 803.53)", "30 days (21 CFR 803.50)"))
        elif reportable and five_day is False:
            notes.append("Question 6 is No, so not the 5-work-day report (803.53).")
    elif market in (EU_NI, GB):
        p = "EU" if market == EU_NI else "GB"
        limbs = [v(f"{p}3{letter}") for letter in "ABCDEF"]
        reportable = _all(v(f"{p}1"), _any(v(f"{p}2"), *limbs, v(f"{p}4")), v(f"{p}5"))
        # Unknown takes the shortest category the facts do not yet exclude (MDCG 2023-3: report within the period
        # even when uncertain; 0.10.81, starter).
        threat, death, unanticipated = v(f"{p}4"), v(f"{p}2"), v(f"{p}6")
        deterioration = _any(*limbs)
        if threat is not False:
            kind = f"{p}_2_DAY"
            if reportable and threat is None:
                notes.append(
                    _shorter("Question 4 (serious public health threat)", "the 2-day report", "10 or 15 days", MDCG)
                )
        elif death is not False or (deterioration is not False and unanticipated is not False):
            kind = f"{p}_10_DAY"
            if reportable and death is None:
                notes.append(_shorter("Question 2 (death)", "the 10-day report", "15 days", MDCG))
            elif reportable and not death and unanticipated is None:
                notes.append(_shorter("Question 6 (unanticipated)", "the 10-day report", "15 days", MDCG))
        else:
            kind = f"{p}_15_DAY"
    elif market == IN:
        reportable = _all(v("IN1"), _any(*(v(f"IN2{letter}") for letter in "ABCDEF")))
        kind = "IN_SERIOUS_ADVERSE_EVENT"
        if reportable and v("IN3"):
            notes.append("Serious and unexpected: a suspected unexpected serious adverse event.")
    elif market == CA:
        reportable = _all(v("CA1"), v("CA2"), _any(v("CA3"), v("CA4")), _any(v("CA5"), v("CA6")))
        if v("CA5") is False:
            kind = "CA_FOREIGN"
        elif v("CA3") is False:
            kind = "CA_30_DAY"
        else:
            # Conservative (starter): while question 3 is Unknown, the shorter 10-day report.
            kind = "CA_10_DAY"
            if reportable and v("CA3") is None:
                notes.append("Question 3 is Unknown: until it is answered, the shorter 10-day report applies.")
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
        "not_asked": not_asked(market, answers),
    }


def not_asked(market: str, answers: dict) -> dict[str, str]:
    """The questions earlier answers make unnecessary, each with why (0.10.83, D2): their answer can no longer change
    the conclusion, the report type or the form. Only a Yes, No or Not applicable folds a question away; an Unknown or
    a missing answer never does. A folded question is not required to sign."""
    v = lambda question_id: _value(answers, question_id)  # noqa: E731
    found: dict[str, str] = {}

    def fold(ids, why: str) -> None:
        for question_id in ids:
            found.setdefault(question_id, why)

    if market == US:
        if v("US1") is False and _any(v("US2A"), v("US2B"), v("US2C")) is False:
            fold(["US3"], "Not asked: no death and no serious injury")
        if v("US4") is False:
            fold(["US5"], "Not asked: no malfunction")
        harm = _all(_any(v("US1"), v("US2A"), v("US2B"), v("US2C")), v("US3"))
        if _any(harm, _all(v("US4"), v("US5"))) is False:
            fold(["US6"], "Not needed: not reportable on the answers above")
    elif market in (EU_NI, GB):
        p = "EU" if market == EU_NI else "GB"
        limbs = [f"{p}3{letter}" for letter in "ABCDEF"]
        if v(f"{p}1") is False:
            fold([f"{p}2", *limbs, f"{p}4", f"{p}5", f"{p}6"], "Not asked: not an incident")
        serious = _any(v(f"{p}2"), *(v(item) for item in limbs), v(f"{p}4"))
        if serious is False:
            fold([f"{p}5"], "Not asked: no death, serious deterioration or public health threat")
        if v(f"{p}5") is False or serious is False:
            fold([f"{p}6"], "Not needed: not reportable on the answers above")
        elif v(f"{p}4") is True:
            fold([f"{p}6"], "Not needed: a serious public health threat takes the 2-day report")
        elif v(f"{p}2") is True:
            fold([f"{p}6"], "Not needed: a death takes the 10-day report")
        elif _any(*(v(item) for item in limbs)) is False:
            fold([f"{p}6"], "Not needed: no serious deterioration in health")
    elif market == IN:
        criteria = [f"IN2{letter}" for letter in "ABCDEF"]
        if v("IN1") is False:
            fold([*criteria, "IN3"], "Not asked: not an adverse event suspected to be associated with the device")
        elif _any(*(v(item) for item in criteria)) is False:
            fold(["IN3"], "Not needed: not serious on the answers above")
    elif market == CA:
        rest = ["CA2", "CA3", "CA4", "CA5", "CA6"]
        if v("CA1") is False:
            fold(rest, "Not asked: the device is not sold in Canada")
        elif v("CA2") is False:
            fold(rest[1:], "Not asked: not related to a failure, a deterioration or the labelling")
        if v("CA3") is True:
            fold(["CA4"], "Not needed: it already led to death or a serious deterioration")
        if v("CA5") is True:
            fold(["CA6"], "Not asked: the incident occurred in Canada")
    return found


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
    """Why the answers cannot be saved (``complete=False``) or signed (``complete=True``), or None. A question earlier
    answers make unnecessary (``not_asked``) is not required."""
    folded = not_asked(question_set.market, answers) if complete else {}
    for question in question_set.questions:
        item = answers.get(question.id)
        if question.id in folded:
            continue
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


# --------------------------------------------------------------------------------------------- facts from the record

# Release B (0.10.72), B1: the factual questions a complaint's own record answers, for the person to confirm or
# correct. Never causation, recurrence, remedial action, "unexpected" or the conclusion: those stay the person's
# judgement. A field the record leaves empty (Unknown) suggests nothing: it is never read as No.
# 0.10.83 (D2): "serious injury" is a judgement under the regulation's definition (21 CFR 803.3(w); India's serious
# criteria alike), never pre-filled: the record's words are shown beside it (``record_notes``).
_DEATH_QUESTIONS = ("US1", "IN2A")
_INJURY_QUESTIONS = ("US2A", "US2B", "US2C", "IN2B", "IN2D", "IN2F")
_MALFUNCTION_QUESTIONS = ("US4",)
JUDGEMENT_QUESTIONS = ("US3", "US5", "US6", "IN1", "IN2C", "IN2E", "IN3", *_INJURY_QUESTIONS)
CONFIRMED, CORRECTED, ENTERED = "CONFIRMED", "CORRECTED", "ENTERED"


def suggestions(question_set: QuestionSet, record: dict) -> dict[str, dict]:
    """The factual answers the complaint's record states, each with its source, for the questions of this set."""
    death, malfunction = record.get("death"), record.get("malfunction")
    found: dict[str, dict] = {}

    def suggest(ids, answer, source, evidence):
        for question_id in ids:
            found[question_id] = {
                "answer": answer,
                "source": f"From the complaint record: {source}",
                "evidence": evidence,
            }

    if death is not None:
        suggest(
            _DEATH_QUESTIONS,
            YES if death else NO,
            "a death was reported" if death else "no death was reported",
            "Patient outcome fields",
        )
    if malfunction is not None:
        suggest(
            _MALFUNCTION_QUESTIONS,
            YES if malfunction else NO,
            "a malfunction was reported" if malfunction else "no malfunction was reported",
            "Malfunction field",
        )
    asked = {question.id for question in question_set.questions if not question.extra}
    return {key: value for key, value in found.items() if key in asked}


def record_notes(question_set: QuestionSet, record: dict) -> dict[str, str]:
    """What the record says beside each serious-injury question, never as its answer (0.10.83, D2): the person judges
    it against the regulation's definition."""
    injury = record.get("serious_injury")
    said = {
        True: "The record says a serious injury was reported",
        False: "The record says no serious injury was reported",
        None: "The record does not say whether there was a serious injury",
    }[injury if injury in (True, False) else None]
    severity = " ".join(str(record.get("severity") or "").split())
    text = f"{said}{f' · severity “{severity}”' if severity else ''}."
    asked = {question.id for question in question_set.questions if not question.extra}
    return {question_id: text for question_id in _INJURY_QUESTIONS if question_id in asked}


def mark_origins(answers: dict, suggested: dict[str, dict], confirmed: set[str]) -> dict:
    """Each answer's origin, kept on the answer: a suggestion the person confirmed, one they corrected, or entered."""
    for question_id, item in answers.items():
        offer = suggested.get(question_id)
        if item.get("answer") is None:
            continue
        if offer and item["answer"] != offer["answer"]:
            item.update(origin=CORRECTED, suggested=offer["answer"], source=offer["source"])
        elif offer and question_id in confirmed:
            item.update(origin=CONFIRMED, suggested=offer["answer"], source=offer["source"])
        else:
            item["origin"] = ENTERED
    return answers


def origins(answers: dict) -> dict[str, str]:
    return {key: item["origin"] for key, item in (answers or {}).items() if item.get("origin")}


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
THRESHOLDS = {US: SERIOUS, EU_NI: SERIOUS, GB: SERIOUS, IN: SERIOUS, CA: SERIOUS}
THRESHOLD_LABELS = {
    US: "US serious injury",
    EU_NI: "EU/NI serious deterioration",
    GB: "GB serious deterioration",
    IN: "India serious adverse event",
    CA: "Canada serious deterioration",
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


def _market_of_one(name: str) -> str | None:
    for market in MARKETS:
        if name in _country_names(market):
            return market
    return None


@lru_cache(maxsize=None)
def _country_names(market: str) -> frozenset[str]:
    """A market's country names, normalized once (0.10.88: they were normalized again for every complaint)."""
    return frozenset(rules.normalize(item) for item in MARKET_COUNTRIES[market])


def markets_of(country: object) -> list[str]:
    """The markets of an event's country cell, in the order it names them: one country, or several separated by a
    comma, semicolon, slash, "&" or "and" ("India, Germany": India's, then the EU's) (J41)."""
    whole = _market_of_one(rules.normalize(country))
    if whole:
        return [whole]
    found: list[str] = []
    for part in rules.countries(country):
        market = _market_of_one(rules.normalize(part))
        if market and market not in found:
            found.append(market)
    return found


def market_of(country: object) -> str | None:
    """The market of an event's country, or None; of a cell naming several countries, the first one's (the event's own
    market; ``markets_of`` gives them all)."""
    name = rules.normalize(country)
    if not name:
        return None
    return next(iter(markets_of(country)), None)


# Words that mark an in-vitro diagnostic in a product's name, family, GMDN term or description: its EU clocks cite the
# IVDR. shortcut: a word list, until products carry a device category (an owner decision, stage 4).
IVD_WORDS = re.compile(r"(?i)\b(ivds?|in[- ]vitro|reagents?|assays?|test strips?|diagnostic kits?|rapid tests?)\b")


def is_ivd(*texts) -> bool:
    """Whether a product's words mark it as an in-vitro diagnostic (``IVD_WORDS``)."""
    return any(IVD_WORDS.search(str(text or "")) for text in texts)


def product_is_ivd(product) -> bool:
    """Whether a product (a Product row, or None) is an in-vitro diagnostic, read the same way on the watch and in
    triage: its device category when set (IVD or not), else the words of its name, family, GMDN term or description."""
    if product is None:
        return False
    if getattr(product, "device_category", None):
        return product.device_category == "IVD"
    return is_ivd(product.name, product.product_family, product.gmdn_term, product.description)


def window_markets(window: dict) -> set[str]:
    """The markets a reporting window covers (a window without markets covers every market)."""
    if not window.get("markets"):
        return set(MARKETS)
    names = {rules.normalize(item) for item in window["markets"]}
    return {market for market in MARKETS if names & _country_names(market)}


def enabled_markets(windows: list[dict]) -> list[str]:
    """The markets the organization enabled: those it entered a reporting window for."""
    covered = set().union(*(window_markets(window) for window in windows)) if windows else set()
    return [market for market in MARKETS if market in covered]


def _clock(
    name: str,
    days: int,
    day_basis: str,
    aware,
    now,
    source: str,
    market: str | None = None,
    org_zone: str | None = None,
) -> dict:
    due = deadlines.count(aware, days, day_basis, market, org_zone)
    return {"window": name, "days": days, "day_basis": day_basis, **deadlines.view(due, now, days), "source": source}


def market_clock(
    market: str,
    state: str | None,
    report_type: str | None,
    windows: list[dict],
    aware,
    now,
    org_zone: str | None = None,
) -> dict | None:
    """A market's clock, by its counting rule (deadlines.py). Reportable: the organization's window of the report
    type's period for that market, or the regulation's period when none matches. Pending, or not yet assessed: the
    shortest window the organization set for that market, still counting. Not reportable: none."""
    if aware is None or state == NOT_REPORTABLE:
        return None
    mine = [window for window in windows if market in window_markets(window)]
    clocks = [_clock(w["name"], w["days"], w["day_basis"], aware, now, "WINDOW", market, org_zone) for w in mine]
    kind = REPORT_TYPES.get(report_type or "")
    if state == REPORTABLE and kind and kind.days:
        exact = [
            clock
            for window, clock in zip(mine, clocks)
            if window["days"] == kind.days and window["day_basis"] == kind.day_basis
        ]
        if exact:
            return min(exact, key=lambda clock: clock["due_at"])
        return _clock(kind.label, kind.days, kind.day_basis, aware, now, "REGULATION", market, org_zone)
    return min(clocks, key=lambda clock: clock["due_at"]) if clocks else None


def signature_meaning(ref: str, market: str, version: str, conclusion: str) -> str:
    return (
        f"I have assessed {ref} for {MARKET_LABELS[market]} with its questions, {version_words(version)}, and the "
        f"harm-severity scale, {version_words(SCALE_VERSION)}, and conclude: {CONCLUSION_LABELS[conclusion].lower()}."
    )
