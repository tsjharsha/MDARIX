# Regulatory decision tables (DEV-09, 0.10.87)

**What this is.** The rules MDARIX applies today to reportability, deadlines, escalation and signing, written as
tables: each row is one branch, with the outcome the code gives. **These are MDARIX's starter rules. They have not been
reviewed by a regulatory expert yet; that review is an external sign-off still pending.** The tests below prove that
the code does what the tables say. They do not prove that the tables are right in law, and they are not regulatory
qualification or validation.

**How the tables are tested.** A table marked `<!-- table: name -->` is read by
`tests/test_regulatory_decision_tables.py`: every row runs as its own test case, named by the row's ID
(`pytest tests/test_regulatory_decision_tables.py -k US-7`). A row that disagrees with the code fails. Tables marked
`linked` name the behavioural test that covers each row; a test checks that every named test exists. Change a rule,
and its row must change in the same commit.

**Conventions.**

- Answers are Yes, No, Unknown or Not applicable. In the answer tables, a question not listed is answered **No**; a
  question listed under *Not answered* has no answer at all.
- **Unknown is never No.** An Unknown, or a missing answer, that could make the event reportable gives *pending
  information*; "not reportable" cannot be signed while it stands. *Not applicable* counts as No.
- *Type if reportable* is the report type a person gets who concludes reportable (the suggestion's type when the
  suggestion is reportable). While an answer that sets the type is Unknown, the shortest type the facts do not yet
  exclude applies (0.10.81).
- **The market follows the incident's country** (table MARKET). MDARIX never decides: the tables give the suggestion;
  a person confirms or overrides it with a reason, and signs.
- Code: `backend/app/reportability/markets.py` (`evaluate`, `not_asked`, `answers_problem`, `conclusion_problem`),
  `deadlines.py`, `facts.py`, `backend/app/complaint_disposition/rules.py` and `triggers.py`.

## 1. Reportability by market

Question IDs and wording: the starter question sets in `markets.py` (`US-starter-1`, `EU-starter-1`, `GB-starter-1`,
`IN-starter-1`, `CA-starter-1`). A customer's own guide version keeps the core questions and this logic unchanged
(`decision_guides/rules.py`): only the wording beside them and extra questions are theirs.

### US: 21 CFR Part 803

Reportable when (death or serious injury, part a, b or c) and the device caused or contributed (US3); or a
malfunction (US4) that would be likely to cause or contribute to a death or serious injury if it recurred (US5).
US6 Yes gives the 5-work-day report (803.53), otherwise 30 calendar days (803.50).

<!-- table: evaluate -->
| ID | Market | Yes | Unknown | Not applicable | Not answered | Suggested | Type if reportable | Rule |
|---|---|---|---|---|---|---|---|---|
| US-1 | US | US1 US3 | | | | REPORTABLE | US_30_DAY | 803.50(a)(1): a death the device caused or contributed to |
| US-2 | US | US2A US3 | | | | REPORTABLE | US_30_DAY | 803.3(w)(1): life-threatening |
| US-3 | US | US2B US3 | | | | REPORTABLE | US_30_DAY | 803.3(w)(2): permanent impairment |
| US-4 | US | US2C US3 | | | | REPORTABLE | US_30_DAY | 803.3(w)(3): intervention to preclude it |
| US-5 | US | US1 | | | | NOT_REPORTABLE | US_30_DAY | 803.3(c): the device did not cause or contribute |
| US-6 | US | US4 US5 | | | | REPORTABLE | US_30_DAY | 803.50(a)(2): malfunction likely to harm if it recurred |
| US-7 | US | US4 | | | | NOT_REPORTABLE | US_30_DAY | 803.50(a)(2): a recurrence would not be likely to harm |
| US-8 | US | US4 | US5 | | | PENDING | US_30_DAY | Recurrence Unknown: never No |
| US-9 | US | US4 US5 US6 | | | | REPORTABLE | US_5_WORK_DAY | 803.53: remedial action for public health |
| US-10 | US | US4 US5 | US6 | | | REPORTABLE | US_5_WORK_DAY | US6 Unknown: the shorter 5-work-day report |
| US-11 | US | US1 | US3 | | | PENDING | US_30_DAY | Causation Unknown |
| US-12 | US | US3 | US2B | | | PENDING | US_30_DAY | One part of serious injury Unknown |
| US-13 | US | | | | | NOT_REPORTABLE | US_30_DAY | Every answer No |
| US-14 | US | US1 | | | US3 | PENDING | US_30_DAY | A missing answer is Unknown, never No |
| US-15 | US | US1 | | US3 | | NOT_REPORTABLE | US_30_DAY | Not applicable counts as No |
| US-16 | US | | | | US1 US2A US2B US2C US3 US4 US5 US6 | PENDING | US_5_WORK_DAY | Nothing answered |

### EU and Northern Ireland: EU MDR Art. 87 (and Great Britain, UK MDR 2002 Part 4A)

Reportable when it is an incident (1), it led, might have led or might lead to a death (2), a serious deterioration
in health (3A-3F) or a serious public health threat (4), and a causal relationship is established or reasonably
possible (5). The type: a public health threat 2 days (Art. 87(4)); a death, or an unanticipated serious deterioration
(6), 10 days (Art. 87(5)); otherwise 15 days (Art. 87(3)). Great Britain applies the same logic to its own questions.

<!-- table: evaluate -->
| ID | Market | Yes | Unknown | Not applicable | Not answered | Suggested | Type if reportable | Rule |
|---|---|---|---|---|---|---|---|---|
| EU-1 | EU_NI | EU1 EU2 EU5 | | | | REPORTABLE | EU_10_DAY | Art. 87(5): a death |
| EU-2 | EU_NI | EU1 EU4 EU5 | | | | REPORTABLE | EU_2_DAY | Art. 87(4): serious public health threat |
| EU-3 | EU_NI | EU1 EU3A EU5 | | | | REPORTABLE | EU_15_DAY | Art. 87(3): anticipated serious deterioration |
| EU-4 | EU_NI | EU1 EU3C EU5 EU6 | | | | REPORTABLE | EU_10_DAY | Art. 87(5): unanticipated serious deterioration |
| EU-5 | EU_NI | EU1 EU3B EU5 | EU6 | | | REPORTABLE | EU_10_DAY | Unanticipated Unknown: the shorter 10 days (MDCG 2023-3) |
| EU-6 | EU_NI | EU1 EU2 EU5 | EU4 | | | REPORTABLE | EU_2_DAY | Threat Unknown: the shortest, 2 days |
| EU-7 | EU_NI | EU2 EU5 | | | | NOT_REPORTABLE | EU_10_DAY | Not an incident |
| EU-8 | EU_NI | EU1 EU5 | | | | NOT_REPORTABLE | EU_15_DAY | No serious outcome possible |
| EU-9 | EU_NI | EU1 EU2 | | | | NOT_REPORTABLE | EU_10_DAY | No causal relationship possible |
| EU-10 | EU_NI | EU1 EU2 | EU5 | | | PENDING | EU_10_DAY | Causal relationship Unknown |
| EU-11 | EU_NI | EU1 EU5 | EU3A | | | PENDING | EU_15_DAY | Whether health deteriorated is Unknown |
| EU-12 | EU_NI | EU1 EU3D EU5 | | | | REPORTABLE | EU_15_DAY | Criterion (d): intervention |
| EU-13 | EU_NI | EU1 EU3E EU5 | | | | REPORTABLE | EU_15_DAY | Criterion (e): chronic disease |
| EU-14 | EU_NI | EU1 EU3F EU5 | | | | REPORTABLE | EU_15_DAY | Criterion (f): foetal harm |
| EU-15 | EU_NI | EU1 EU3A EU5 | EU2 | | | REPORTABLE | EU_10_DAY | Death Unknown: the shorter 10 days |
| EU-16 | EU_NI | EU2 EU5 | | | EU1 | PENDING | EU_10_DAY | Whether it is an incident is not answered |
| GB-1 | GB | GB1 GB2 GB5 | | | | REPORTABLE | GB_10_DAY | UK MDR 2002: a death |
| GB-2 | GB | GB1 GB4 GB5 | | | | REPORTABLE | GB_2_DAY | Serious public health threat |
| GB-3 | GB | GB1 GB3A GB5 | | | | REPORTABLE | GB_15_DAY | Anticipated serious deterioration |
| GB-4 | GB | GB1 GB3A GB5 GB6 | | | | REPORTABLE | GB_10_DAY | Unanticipated serious deterioration |
| GB-5 | GB | GB1 GB5 | GB3A | | | PENDING | GB_15_DAY | Whether health deteriorated is Unknown |
| GB-6 | GB | GB1 GB5 | | | | NOT_REPORTABLE | GB_15_DAY | No serious outcome possible |

### India: Medical Devices Rules 2017 (MvPI)

Reportable when it is an adverse event suspected to be associated with the device (IN1) and serious by any criterion
(IN2A-IN2F). Unexpected (IN3) adds a note (a suspected unexpected serious adverse event); it does not change the
conclusion. The period is the organization's window for India (starter: 15 days).

<!-- table: evaluate -->
| ID | Market | Yes | Unknown | Not applicable | Not answered | Suggested | Type if reportable | Rule |
|---|---|---|---|---|---|---|---|---|
| IN-1 | IN | IN1 IN2A | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Death |
| IN-2 | IN | IN1 IN2B | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Life-threatening |
| IN-3 | IN | IN1 IN2C | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Hospitalisation |
| IN-4 | IN | IN1 IN2D | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Disability |
| IN-5 | IN | IN1 IN2E | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Congenital anomaly |
| IN-6 | IN | IN1 IN2F | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Intervention to prevent permanent harm |
| IN-7 | IN | IN1 | | | | NOT_REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Not serious |
| IN-8 | IN | IN2A | | | | NOT_REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Not associated with the device |
| IN-9 | IN | IN1 | IN2C | | | PENDING | IN_SERIOUS_ADVERSE_EVENT | A criterion Unknown |
| IN-10 | IN | IN2A | IN1 | | | PENDING | IN_SERIOUS_ADVERSE_EVENT | Association Unknown |
| IN-11 | IN | IN1 IN2B IN3 | | | | REPORTABLE | IN_SERIOUS_ADVERSE_EVENT | Serious and unexpected: same conclusion, with a note |

### Canada: SOR/98-282 ss. 59-61.1

Reportable when the device is sold in Canada (CA1), the incident relates to a failure, a deterioration or the
labelling (CA2), it led to (CA3) or could lead to, if it recurred (CA4), a death or serious deterioration, and it
occurred in Canada (CA5) or, abroad, is a Class I device with corrective action intended or required (CA6). In Canada:
10 days when it led to it, 30 days when it could if it recurred; abroad: as soon as possible.

<!-- table: evaluate -->
| ID | Market | Yes | Unknown | Not applicable | Not answered | Suggested | Type if reportable | Rule |
|---|---|---|---|---|---|---|---|---|
| CA-1 | CA | CA1 CA2 CA3 CA5 | | CA6 | | REPORTABLE | CA_10_DAY | s. 60(1)(a)(i): death or serious deterioration |
| CA-2 | CA | CA1 CA2 CA4 CA5 | | CA6 | | REPORTABLE | CA_30_DAY | s. 60(1)(a)(ii): could, if it recurred |
| CA-3 | CA | CA1 CA2 CA3 CA6 | | | | REPORTABLE | CA_FOREIGN | s. 59(1.1), 60(1)(b): abroad, corrective action |
| CA-4 | CA | CA1 CA2 CA3 | | | | NOT_REPORTABLE | CA_FOREIGN | Abroad, no corrective action |
| CA-5 | CA | CA2 CA3 CA5 | | CA6 | | NOT_REPORTABLE | CA_10_DAY | Not sold in Canada |
| CA-6 | CA | CA1 CA3 CA5 | | CA6 | | NOT_REPORTABLE | CA_10_DAY | Not related to a failure or the labelling |
| CA-7 | CA | CA1 CA2 CA4 CA5 | CA3 | CA6 | | REPORTABLE | CA_10_DAY | CA3 Unknown: the shorter 10 days |
| CA-8 | CA | CA1 CA2 CA5 | CA3 | CA6 | | PENDING | CA_10_DAY | Whether health deteriorated is Unknown |
| CA-9 | CA | CA1 CA2 CA5 | | CA6 | | NOT_REPORTABLE | CA_30_DAY | No serious deterioration possible |
| CA-10 | CA | CA1 CA2 CA3 | CA5 | CA6 | | PENDING | CA_10_DAY | Whether it occurred in Canada is Unknown (see owner decision OD-3) |

### Questions folded away

A question earlier answers make unnecessary is shown as "not asked" and is not required to sign. Only Yes, No or Not
applicable folds a question; Unknown never does. Across every Yes/No answer set of each market, and every set with
one Unknown, a folded question's answer never changes the suggestion or the report type
(`test_folded_questions_never_change_the_outcome`).

**Every combination, not only these rows.** `test_unknown_is_never_no_in_any_combination` runs every Yes/No answer set
of each market with up to one Unknown (EU and GB), two (US and India) or three (Canada): a definite suggestion holds
however the Unknowns resolve, "pending information" means they could still go either way, and the type is the shortest
any resolution gives (Canada: OD-3). A deliberate fault (Unknown read as No) fails 23 rows and all five markets.

<!-- table: fold -->
| ID | Market | Answers | Not asked |
|---|---|---|---|
| FO-1 | US | US1=NO US2A=NO US2B=NO US2C=NO US4=NO | US3 US5 US6 |
| FO-2 | US | US1=YES US3=YES US4=YES US5=YES | |
| FO-3 | US | US1=UNKNOWN US2A=NO US2B=NO US2C=NO US4=NO | US5 |
| FO-4 | EU_NI | EU1=NO | EU2 EU3A EU3B EU3C EU3D EU3E EU3F EU4 EU5 EU6 |
| FO-5 | EU_NI | EU1=YES EU4=YES EU5=YES | EU6 |
| FO-6 | EU_NI | EU1=YES EU2=YES EU5=YES EU4=NO | EU6 |
| FO-7 | IN | IN1=NO | IN2A IN2B IN2C IN2D IN2E IN2F IN3 |
| FO-8 | CA | CA1=YES CA2=YES CA3=YES CA5=YES | CA4 CA6 |
| FO-9 | CA | CA1=NO | CA2 CA3 CA4 CA5 CA6 |

## 2. The market follows the incident's country

<!-- table: market -->
| ID | Country cell | Markets |
|---|---|---|
| MK-1 | US | US |
| MK-2 | U.S.A. | US |
| MK-3 | Germany | EU_NI |
| MK-4 | Northern Ireland | EU_NI |
| MK-5 | United Kingdom | |
| MK-5a | UK | |
| MK-5b | Great Britain | GB |
| MK-6 | India, Germany | IN EU_NI |
| MK-7 | Canada | CA |
| MK-8 | Brazil | |
| MK-9 | | |

MK-5: "United Kingdom" and "UK" name no market by themselves: Great Britain follows UK MDR 2002, Northern Ireland the
EU MDR. The complaint page asks the person to choose Great Britain or Northern Ireland, with the other missing facts,
and every market's shortest clock runs, provisional, until they do (owner decision OD-2, 5 Nov 2026; 0.10.88).

## 3. Signing: missing facts and missing authority block it ("ask, never guess")

### The facts a reporting step needs

A complaint on the reportability watch (harm or a malfunction recorded, or a patient's outcome unknown) needs a known
incident country and an awareness or received date before a market conclusion is signed (`FACT_NEEDED`); until then
its clocks are provisional. A country outside the five markets needs nothing.

<!-- table: facts -->
| ID | Record | Awareness given | Needs |
|---|---|---|---|
| FA-1 | death=YES country= | YES | COUNTRY |
| FA-2 | death=YES country=Atlantis | YES | COUNTRY |
| FA-3 | death=YES country=Germany | NO | AWARENESS_DATE |
| FA-4 | malfunction=YES country=Brazil | YES | |
| FA-5 | patient_involved=YES country= | NO | COUNTRY AWARENESS_DATE |
| FA-6 | patient_involved=YES serious_injury=NO death=NO country= | NO | |

FA-5 changed in 0.10.87: before, a complaint on the watch only because a patient's outcome is unknown needed nothing,
and its conclusion could be signed with no country and with its clock counted from the day MDARIX recorded it.

### Signing a conclusion against the suggestion

<!-- table: conclusion -->
| ID | Suggested | Conclusion | Reason given | Signing |
|---|---|---|---|---|
| SG-1 | PENDING | NOT_REPORTABLE | YES | Refused: Unknown is never No |
| SG-2 | PENDING | REPORTABLE | YES | Allowed |
| SG-3 | PENDING | REPORTABLE | NO | Refused: an override needs its reason |
| SG-4 | REPORTABLE | REPORTABLE | NO | Allowed |
| SG-5 | REPORTABLE | NOT_REPORTABLE | NO | Refused: an override needs its reason |
| SG-6 | REPORTABLE | NOT_REPORTABLE | YES | Allowed |
| SG-7 | NOT_REPORTABLE | NOT_REPORTABLE | NO | Allowed |
| SG-8 | NOT_REPORTABLE | PENDING | YES | Refused: conclude reportable or not reportable |

### Every answer, with its rationale

<!-- table: answers -->
| ID | Market | Answers | Short rationale | Signing |
|---|---|---|---|---|
| AP-1 | US | US1=YES US3=YES US2A=NO US2B=NO US2C=NO US4=NO US6=NO | | Allowed (US5 not asked: no malfunction) |
| AP-2 | US | US1=YES US3=YES US2A=NO US2B=NO US2C=NO US4=YES US6=NO | | Refused: answer question US5 |
| AP-3 | US | US1=NO US2A=NO US2B=NO US2C=NO US3=NO US4=YES US5=NO US6=NO | US5 | Refused: question US5 is No, say why |
| AP-4 | US | US1=YES US3=YES US2A=NO US2B=NO US2C=NO US4=NO US6=UNKNOWN | | Allowed (an Unknown is an answer; the suggestion says pending or the shorter type) |
| AP-5 | IN | IN1=YES IN2A=YES IN2B=NO IN2C=NO IN2D=NO IN2E=NO IN2F=NO IN3=NO | IN2A | Refused: give the rationale |

### Who may sign (linked)

<!-- table: linked -->
| ID | Rule | Test |
|---|---|---|
| AU-1 | Saving or signing needs regulatory review or approve; a viewer is refused (403) | tests/test_market_assessment_api.py::test_a_serious_us_complaint_is_assessed_trained_signed_versioned_and_filed |
| AU-2 | The current password, and the authenticator code when signatures require it | tests/test_market_assessment_api.py::test_signing_needs_the_authenticator_code_when_signatures_require_it |
| AU-3 | In a free trial, the practice training on the current question set and scale first | tests/test_market_assessment_api.py::test_the_practice_training_rule_binds_a_trial_organization_only |
| AU-4 | An administrator never signs a decision | tests/test_custom_role_escalation.py::test_an_administrator_is_refused_a_signature |
| AU-5 | A report is approved by neither its preparer nor the conclusion's signer | tests/test_authority_reports_api.py::test_the_preparer_and_the_conclusion_signer_cannot_approve_and_a_colleague_can |
| AU-6 | A missing country or awareness date blocks signing (FACT_NEEDED) | tests/test_release_0_10_81.py::test_f3_f4_f9_a_missing_country_or_awareness_date_is_asked_for_and_blocks_signing |
| AU-7 | A draft changed since it was read is not signed (DRAFT_CHANGED) | tests/test_market_assessment_api.py::test_a_serious_us_complaint_is_assessed_trained_signed_versioned_and_filed |
| AU-8 | A decision guide is approved by a second person, never an editor or an administrator | tests/test_decision_guides_api.py::test_a_draft_is_edited_tested_and_approved_by_a_second_person |

## 4. Deadlines: time zones, DST and date-only awareness

The latest day counts from awareness: the US, EU and Canada from the day after (awareness is day 0); Great Britain and
India count the awareness day as day 1. A timed awareness takes the earliest of its days in the authority's and the
organization's time zones; a date-only awareness (kept as 12:00 UTC) is that day everywhere. The deadline ends at the
earlier of the end of the latest day in the authority's and the organization's time zones; each zone's offset is the
one in force on that day, so daylight saving is applied. Canada has no authority zone here: the organization's
counts. Work days are Monday to Friday; holidays count as work days (only ever earlier).

<!-- table: deadline -->
| ID | Market | Awareness | Organization zone | Days | Basis | Latest day | Ends (UTC) | Binding zone | Rule |
|---|---|---|---|---|---|---|---|---|---|
| DL-1 | US | 2026-10-02T15:00:00+00:00 | America/Chicago | 30 | CALENDAR | 2026-11-01 | 2026-11-02T04:59:59+00:00 | America/New_York | Ends after US DST ends (1 Nov): EST, UTC-5 |
| DL-2 | US | 2026-09-01T15:00:00+00:00 | America/Chicago | 30 | CALENDAR | 2026-10-01 | 2026-10-02T03:59:59+00:00 | America/New_York | During US DST: EDT, UTC-4 |
| DL-3 | US | 2026-10-02T15:00:00+00:00 | Asia/Kolkata | 30 | CALENDAR | 2026-11-01 | 2026-11-01T18:29:59+00:00 | Asia/Kolkata | The organization's day ends first |
| DL-4 | EU_NI | 2026-10-20T10:00:00+00:00 | Europe/Brussels | 15 | CALENDAR | 2026-11-04 | 2026-11-04T22:59:59+00:00 | Europe/Brussels | After EU DST ends (25 Oct): CET |
| DL-5 | EU_NI | 2026-03-27T23:30:00+00:00 | UTC | 10 | CALENDAR | 2026-04-06 | 2026-04-06T21:59:59+00:00 | Europe/Brussels | Earliest awareness day (UTC 27 Mar); ends in CEST |
| DL-6 | GB | 2026-11-02T09:00:00+00:00 | Europe/London | 15 | CALENDAR | 2026-11-16 | 2026-11-16T23:59:59+00:00 | Europe/London | Awareness day is day 1 |
| DL-7 | IN | 2026-11-02T20:00:00+00:00 | Asia/Kolkata | 15 | CALENDAR | 2026-11-17 | 2026-11-17T18:29:59+00:00 | Asia/Kolkata | Awareness 3 Nov IST is day 1 |
| DL-8 | IN | 2026-11-02T20:00:00+00:00 | UTC | 15 | CALENDAR | 2026-11-16 | 2026-11-16T18:29:59+00:00 | Asia/Kolkata | Earliest day (2 Nov UTC); IST ends first |
| DL-9 | CA | 2026-11-02T12:00:00+00:00 | Pacific/Auckland | 10 | CALENDAR | 2026-11-12 | 2026-11-12T10:59:59+00:00 | Pacific/Auckland | Date-only awareness: 2 Nov everywhere |
| DL-10 | CA | 2026-11-02T12:00:01+00:00 | Pacific/Auckland | 10 | CALENDAR | 2026-11-13 | 2026-11-13T10:59:59+00:00 | Pacific/Auckland | Timed: 3 Nov in Auckland |
| DL-11 | CA | 2026-11-02T20:00:00+00:00 | Asia/Kolkata | 10 | CALENDAR | 2026-11-13 | 2026-11-13T18:29:59+00:00 | Asia/Kolkata | No authority zone: the organization's |
| DL-12 | US | 2026-10-30T15:00:00+00:00 | America/New_York | 5 | WORK | 2026-11-06 | 2026-11-07T04:59:59+00:00 | America/New_York | 5 work days from a Friday |
| DL-13 | US | 2026-11-02 | UTC | 30 | CALENDAR | 2026-12-02 | 2026-12-02T23:59:59+00:00 | UTC | A day without a time |
| DL-14 | GB | 2026-11-02T09:00:00+00:00 | Europe/London | 5 | WORK | 2026-11-09 | 2026-11-09T23:59:59+00:00 | Europe/London | Work days: day 1 is not applied (owner decision OD-1) |

A market's clock (`markets.market_clock`): reportable, the organization's window of the report type's period, else the
regulation's period; pending or not assessed, the shortest window the organization set for that market; not
reportable, none. Linked tests: `tests/test_reporting_capa_rules.py::test_due_dates_in_calendar_and_work_days`,
`tests/test_release_0_10_81.py::test_u06_a_day_only_awareness_counts_from_that_day_everywhere_and_shows_as_a_date`.

## 5. Escalation, recurrence and the routine path

The disposition tree (`disposition-starter-1`): an escalation trigger met escalates and closes the other branches; else
a known issue (an open case with the same product and problem code, or lot); else resolved at service level; else
escalate by choice with a reason.

### The routine path (0.10.87)

The routine path signs "not reportable" for each enabled market on the basis "no death, serious injury or malfunction
recorded; patient outcome known". It is offered only off the watch, with no second-look flag, no trigger, and every fact
of that basis recorded.

<!-- table: routine -->
| ID | Record | Not recorded | Routine path |
|---|---|---|---|
| RT-1 | (nothing recorded) | MALFUNCTION PATIENT | Not offered |
| RT-2 | patient_involved=NO | MALFUNCTION | Not offered |
| RT-3 | malfunction=NO | PATIENT | Not offered |
| RT-4 | malfunction=NO patient_involved=NO | | Offered |
| RT-5 | malfunction=NO death=NO serious_injury=NO | | Offered |
| RT-6 | malfunction=NO death=NO | PATIENT | Not offered |

RT-1 to RT-3 and RT-6 changed in 0.10.87: before, the path was offered and its signature concluded "not reportable" on
facts the record did not give.

### Triggers, recurrence and the branches (linked)

<!-- table: linked -->
| ID | Rule | Test |
|---|---|---|
| ES-1 | SAFETY: death recorded Yes, or a catastrophic harm level | tests/test_complaint_disposition_rules.py::test_the_triggers_read_the_complaint_and_its_market_assessments |
| ES-2 | INJURY: serious injury Yes, or Unknown with a patient involved; a harm level at or above a threshold | tests/test_complaint_disposition_rules.py::test_the_triggers_read_the_complaint_and_its_market_assessments |
| ES-3 | REPORTABLE: a market concluded reportable, US5 Yes, or an earlier "reported" decision | tests/test_complaint_disposition_rules.py::test_the_triggers_read_the_complaint_and_its_market_assessments |
| ES-4 | A met trigger allows only escalation; no trigger refuses it | tests/test_complaint_disposition_rules.py::test_a_met_trigger_allows_only_escalation_and_no_trigger_refuses_it |
| ES-5 | A trigger met since the screen opened refuses the signature; one met after signing is listed | tests/test_complaint_disposition_api.py::test_a_trigger_met_since_the_screen_opened_refuses_the_signature_and_one_met_after_signing_is_listed |
| ES-6 | NEW_FAILURE_MODE: a problem code new on the product, no open case covering it | tests/test_complaint_disposition_api.py::test_the_battery_shutdown_escalates_by_its_trigger_and_stays_on_the_watch |
| RC-1 | RECURRENCE: two service-level closes in 30 days on one product and problem code, no open case | tests/test_complaint_disposition_api.py::test_a_source_value_off_the_list_stays_unknown_and_two_cable_closes_raise_the_recurring_matter |
| RC-2 | A known issue joins the open case as a new scope version | tests/test_complaint_disposition_api.py::test_the_known_issue_joins_the_open_case_through_a_new_scope_version |
| RC-3 | US5: recurrence is presumed; a No needs its own reason | tests/test_market_assessment_api.py::test_question_5_no_needs_its_reason_and_an_answer_against_the_scale_needs_one_listed_on_readiness |
| RT-7 | The routine path's facts, end to end on the sample | tests/test_complaint_disposition_api.py::test_a_complaint_whose_harm_facts_are_not_recorded_is_never_closed_not_reportable_on_the_routine_basis |

## 6. Late evidence, amendments and controlled records (linked)

<!-- table: linked -->
| ID | Rule | Test |
|---|---|---|
| LE-1 | Evidence reaching a decided or closed case asks for one impact assessment per decision and evidence, and never changes the decision | tests/test_decision_followups.py::test_late_evidence_asks_for_one_impact_assessment_and_never_changes_the_decision |
| LE-2 | No impact keeps the decision; a material impact reopens the case | tests/test_decision_followups.py::test_no_impact_keeps_the_decision_and_a_material_impact_reopens_the_case |
| LE-3 | The same evidence arriving again is assessed once | tests/test_decision_followups_unit.py::test_late_evidence_is_assessed_once_per_decision_and_evidence |
| LE-4 | A re-signed shorter report type moves the open report; a submitted one is only flagged | tests/test_release_0_10_81.py::test_f1_a_re_signed_shorter_report_type_moves_the_open_report_and_a_submitted_one_is_only_flagged |
| AM-1 | An amended conclusion is a new version; the prior version stays with its answers, rationale, signer, time and checksum | tests/test_regulatory_records.py::test_an_amended_conclusion_keeps_the_prior_version_with_its_rationale_actor_and_time |
| AM-2 | A later "not reportable" cancels an unsubmitted report with its reason; reportable again reopens it | tests/test_release_c3_0_10_75.py::test_a_not_reportable_re_sign_cancels_the_unsubmitted_report_and_reportable_reopens_it |
| AM-3 | A signed guide version stays as signed; locked wording cannot change | tests/test_decision_guides_api.py::test_the_server_refuses_a_change_to_locked_wording_and_keeps_old_versions_as_signed |
| AM-4 | A changed answer in a guide's test matrix blocks its approval | tests/test_decision_guides_api.py::test_a_changed_answer_in_the_matrix_blocks_the_approval_before_any_password |
| PV-1 | Provenance: complaint record, signed conclusion, report fields with their sources, approved snapshot, PDF | tests/test_regulatory_records.py::test_provenance_runs_from_the_complaint_to_the_conclusion_the_report_and_its_pdf |
| PV-2 | The worksheet PDF matches its snapshot | tests/test_regulatory_records.py::test_the_worksheet_pdf_matches_its_snapshot |
| PV-3 | A receipt is not acceptance; MDARIX never submits | tests/test_authority_reports_api.py::test_a_receipt_is_not_acceptance |
| PV-4 | G2b follow-up after submission: rows 1-4 | tests/test_authority_reports_rules.py::test_the_decision_table_with_the_emdr_defaults |

## 7. Versioned rules, forms and assumptions

Everything a signature relies on carries a version, printed in its meaning: a change is a new version, and records
signed before keep the version they were signed with.

<!-- table: version -->
| ID | What | Version |
|---|---|---|
| VR-1 | US question set | US-starter-1 |
| VR-2 | EU and Northern Ireland question set | EU-starter-1 |
| VR-3 | Great Britain question set | GB-starter-1 |
| VR-4 | India question set | IN-starter-1 |
| VR-5 | Canada question set | CA-starter-1 |
| VR-6 | Harm-severity scale | scale-starter-1 |
| VR-7 | Disposition rules | disposition-starter-2 |
| VR-8 | Classification coding criteria | coding-starter-1 |
| VR-9 | US form | Form FDA 3500A (09/2025) |
| VR-10 | India form | MDAE Reporting Form, Version 1.2 |
| VR-11 | EU form | MIR form 7.3.1 (SB-11154, 06-05-2026) |
| VR-12 | Great Britain form | GB MIR 7.2.1 (04/06/2025) |
| VR-13 | Canada form | HC Pub. 110180 (April 2018) |
| VR-14 | US reportability floor (rule register) | US-floor-1 |
| VR-15 | EU and Northern Ireland reportability floor (rule register) | EU-floor-1 |
| VR-16 | Great Britain reportability floor (rule register) | GB-floor-1 |
| VR-17 | India reportability floor (rule register) | IN-floor-1 |
| VR-18 | Canada reportability floor (rule register) | CA-floor-1 |

Assumptions the deadlines rest on, starter text: the authority time zones (US America/New_York, EU and NI
Europe/Brussels, GB Europe/London, India Asia/Kolkata); day 1 on the awareness day for GB and India; no weekend or
holiday extension; India's period from the organization's window.

**The rule register (0.10.99, B4).** The rows above are held in the rule register (`backend/app/rule_register/data`,
one file per rule version; read-only on Decision trees > Rules). Each market's questions, logic, report types and
periods, counting zone and day-1 rule and triage tiers form its floor (VR-14 to VR-18), version 1 being exactly this
document's logic (`tests/test_b4_equivalence.py`). A market conclusion keeps the floor in force on its awareness day;
a later version never changes a signed record. The owner decisions below (OD-1, OD-3) and the India period are
carried unchanged in version 1, starter, for your consultant to confirm. `MDARIX_RULE_REGISTER=off` returns to the
same logic held in code (`reportability/legacy_v1.py`).

## Owner decisions these tables raise

- **OD-1** Work-day windows in Great Britain and India do not apply "the awareness day is day 1" (DL-14); calendar
  windows do. The starter report types are all calendar days, so only a window an organization enters with work days
  is affected. Unchanged until decided.
- **OD-2** Decided 5 Nov 2026 (0.10.88): "United Kingdom" or "UK" as the incident country is asked, Great Britain or
  Northern Ireland (MK-5); Northern Ireland follows the EU MDR (EU_NI).
- **OD-3** Canada: while "did it occur in Canada" is Unknown, the 10-day type applies (CA-10), though an incident abroad
  is "as soon as possible" (Health Canada's guidance: 48 hours). Unchanged until decided.
- **OD-4** Decided 5 Nov 2026 (0.10.88): re-signing a market conclusion (a new version superseding a signed one)
  needs a change reason, kept with the new version, as re-signing a disposition does.
