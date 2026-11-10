"""Version 1 of the five reportability floors as hand-written code, frozen (B4): the oracle the rule register's version 1
is proved against (tests/test_b4_equivalence.py), and the path every rule function takes when the register is switched
off (``MDARIX_RULE_REGISTER=off``). Moved unchanged from ``markets.py`` (0.10.98); never edit it. When a market gets a
version 2, this stays valid for its version 1 only.
"""

from __future__ import annotations

from backend.app.reportability.markets import (
    CA,
    EU_NI,
    GB,
    IN,
    NO,
    NOT_APPLICABLE,
    NOT_REPORTABLE,
    PENDING,
    REPORTABLE,
    US,
    YES,
    QuestionSet,
)


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


_DEATH_QUESTIONS = ("US1", "IN2A")
_INJURY_QUESTIONS = ("US2A", "US2B", "US2C", "IN2B", "IN2D", "IN2F")
_MALFUNCTION_QUESTIONS = ("US4",)


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
