# MDARIX scenario register

Started 7 Nov 2026 (product direction approved by the owner). This is one shared list of scenarios. Each backlog item's spec takes its scenarios from here as acceptance criteria. The same definitions will later drive the rules, the automated tests and the AI evaluation.

**Status values:**
- **NOT RUN:** the default.
- **PASS:** run, with the result as expected.
- **FAIL:** run, with a wrong result.
- **BLOCKED:** could not be run.
- **REQUIRES HUMAN DECISION:** the outcome needs a regulatory or owner judgement first.

A blocked or unexecuted scenario is never counted as a pass. "Status" holds exactly one of the five values; run notes, partial results (for example "API-tested; E2E NOT RUN", recorded as NOT RUN) and measurements are in "Notes" (normalised 12 Nov 2026, B6b B2). The validation-pack generator (`scripts/validation_pack.py`) reads "Status" only. Nothing here claims a scenario is implemented today.

A scenario whose Notes start with "future: <item>" describes a feature not built yet (owner, 12 Nov 2026): it stays NOT RUN, is not a scripted OQ step and is never counted as verification; the generator lists it in the RTM column "future".

A status recorded here before the first release pack under MDX-VAL-001 is a development result, not validation evidence. The validation evidence for a release is the set of results kept in its release folder (`docs/validation/releases/<version>/`).

## Scenario definition: every scenario, when specified in full, contains
1. The starting state and the user persona.
2. The initial information and its source.
3. Missing, conflicting and contradictory facts.
4. The expected workflow route.
5. Permitted and prohibited AI suggestions (for 2027).
6. The expected regulatory or risk outcome, where it applies.
7. The required permissions and approvals (human).
8. Audit events and evidence.
9. The expected final state.
10. The recovery path when a step fails.

## Sources merged in
- The external product-direction review of 7 Nov: IN, RG, IV, CP below.
- The call-intake deep dive (`call-intake-deep-dive/gap-report.md`): its 28-row edge-case table, merged as CI-01 to CI-28 by the B2 spec (`b2-case-design/spec.md`, 7 Nov 2026), plus CI-29 to CI-44 added by that spec.
- The triage deep dive (`triage-deep-dive/gap-report.md`): its scenario table (TR-01 to TR-24) and the matrix rows not already covered (TR-25 to TR-41), merged by the B2 spec.
- The authority-forms spec (`authority-forms-spec/spec.md`): report types and follow-up rules. To be merged as RP-xx in the B3, B8 and B9 specs.
- An external QA/RA expert's routine path and the combinations matrix (expert feedback, 7 Nov 2026). To be merged as RT-xx in the B7 spec.
- The decision-tree deep dive (`decision-tree-deep-dive/report.md`, 7 Nov 2026): configuration and safety cases for customer-configurable questionnaires per market, as DT-01 to DT-38.
- The W1 spec (`w1-product-supplier-360/spec.md`, 7 Nov 2026): Product 360 and Supplier 360 in the trial, as P360-01 to P360-14 and S360-01 to S360-16.

## Intake (IN) → backlog B2 (and B7 for e-mail and bulk)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| IN-01 | Complete complaint with all facts | Register and route | B2 | NOT RUN | |
| IN-02 | No harm, service requested | Keep the complaint allegation; one record covers service and complaint | B2 | NOT RUN | |
| IN-03 | Service request, no deficiency alleged | Service only; rationale kept | B2 | NOT RUN | |
| IN-04 | Customer alleges poor performance but says it's "not a complaint" | Complaint assessment applies; the customer's label is not relied on | B2 | NOT RUN | |
| IN-05 | Death or serious injury | Immediate fast-track escalation | B2 | NOT RUN | |
| IN-06 | Unknown serial number or product | Provisional Case plus information request; unknown kept as typed and flagged | B2 | NOT RUN | |
| IN-07 | Missing event date | Recorded as unknown; never invented | B2 | NOT RUN | |
| IN-08 | Missing awareness date | Provisional clock plus a clarification task | B2 | NOT RUN | |
| IN-09 | Awareness earlier than the event date | Inconsistency flagged; no unsupported conclusion | B2 | NOT RUN | |
| IN-10 | Event date in the future | Flagged; correction or documented explanation required | B2 | NOT RUN | |
| IN-11 | Several products in one event | Each affected product linked separately | B2 | NOT RUN | |
| IN-12 | The same problem from several customers | Possible duplicates detected; nothing deleted automatically | B2 | NOT RUN | |
| IN-13 | Complaint imported from ERP or CRM | Source-system ID and provenance kept (MDARIX Connect) | B2 | NOT RUN | |
| IN-14 | Duplicate external identifier | No duplicate; a controlled reconciliation instead | B2 | NOT RUN | |
| IN-15 | Complaint in a foreign language | Original kept, plus a reviewed translation | B7 | NOT RUN | |
| IN-16 | Unstructured service call or e-mail | Draft extraction for a person to confirm (rule-based now; AI in 2027) | B7 | NOT RUN | |
| IN-17 | Caller and technician disagree | Both assertions shown, with their sources | B2 | NOT RUN | |
| IN-18 | Customer withdraws the allegation | Withdrawal kept; assess whether investigation is still needed | B2 | NOT RUN | |
| IN-19 | Customer unreachable | Open information request plus escalation | B2 | NOT RUN | |
| IN-20 | Personal data in an uploaded file | Privacy rules applied before any processing | B2 / B7 | NOT RUN | |
| IN-21 | General enquiry; installation help; maintenance without alleged deficiency | Service only | B2 | NOT RUN | |
| IN-22 | Device deficiency with no patient involved | Complaint assessment; never dismissed automatically | B2 | NOT RUN | |
| IN-23 | Product returned with no description | Intake investigation plus follow-up | B2 | NOT RUN | |
| IN-24 | Complaint about an obsolete product | Historical product and lot traceability | B2 | NOT RUN | |

## Regulatory (RG) → backlog B3, B4, B8, B9
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| RG-01 | Clearly non-reportable on confirmed facts | Signed conclusion with a rule reference | B3 / B4 | NOT RUN | |
| RG-02 | Death | Market-specific assessment | B3 | NOT RUN | |
| RG-03 | Serious injury | Assessed independently by market | B3 | NOT RUN | |
| RG-04 | Malfunction that could cause serious harm if repeated | Malfunction criteria applied (RV-11) | B3 | NOT RUN | |
| RG-05 | Unknown whether remedial action is needed | Uncertainty kept; conservative handling as configured | B3 | NOT RUN | |
| RG-06 | Unknown country | No signed market conclusion until resolved | B2 / B3 | NOT RUN | |
| RG-07 | Device distributed to several markets | A separate assessment per relevant jurisdiction | B3 | NOT RUN | |
| RG-08 | Sold in one market, incident in another | Jurisdiction and distribution facts evaluated | B3 | NOT RUN | |
| RG-09 | Distributor aware before the manufacturer | Event, receipt and awareness chronology kept | B2 | NOT RUN | |
| RG-10 | Weekend or public holiday | The market's own calendar and rule | B3 / B4 | NOT RUN | future: market holiday calendar (public holidays count as work days today); not verification until built |
| RG-11 | Deadline crosses a daylight-saving change | Correct local calculation | B4 | NOT RUN | |
| RG-12 | Rule changes after the incident | The applicable historical version kept (rule register) | B4 | NOT RUN | |
| RG-13 | Reportable in one market, not in another | Separate signed conclusions | B3 | NOT RUN | |
| RG-14 | Follow-up information changes seriousness | Reassessment, audit, reporting impact | B3 | NOT RUN | |
| RG-15 | Report already submitted | The submitted record is never overwritten | B3 | NOT RUN | |
| RG-16 | Authority asks for more information | Response deadline plus a versioned response | B3 / B8 | NOT RUN | |
| RG-17 | Authority rejects a submission | Correction and resubmission workflow | B3 / B8 | NOT RUN | |
| RG-18 | No acknowledgement received | Escalation; submission evidence kept | B3 / B8 | NOT RUN | |
| RG-19 | Wrong product code or IMDRF code | Validated against the controlled code list | B3 | NOT RUN | |
| RG-20 | AI suggests reportable, a person concludes otherwise | Difference and reasoning recorded; never silently overridden (2027) | Later | NOT RUN | |

## Investigation (IV) → backlog B4, B5
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| IV-01 | One clear failure mode | Evidence-supported hypothesis | B5 | NOT RUN | |
| IV-02 | Several plausible failure modes | Competing hypotheses | B5 | NOT RUN | |
| IV-03 | Evidence supports one cause | Supporting evidence shown | B5 | NOT RUN | |
| IV-04 | Evidence contradicts the proposed cause | Unsupported root-cause conclusion blocked | B5 | NOT RUN | |
| IV-05 | No evidence available | Evidence requests created | B5 | NOT RUN | |
| IV-06 | Late evidence after the decision | Impact assessment reopened | B5 | NOT RUN | |
| IV-07 | New evidence changes severity | Risk and reportability reassessed | B5 | NOT RUN | |
| IV-08 | Investigators disagree | Disagreement kept; review routed | B5 | NOT RUN | |
| IV-09 | Supplier denies responsibility | Kept as an assertion, not proof | B4 / B5 | NOT RUN | |
| IV-10 | Evidence file contains hidden AI instructions | Treated as untrusted evidence | B5 / Later | NOT RUN | |
| IV-11 | Same evidence attached twice | Duplicate detected; provenance kept | B4 | NOT RUN | |
| IV-12 | Evidence corrupted or unreadable | Blocked as validated evidence | B4 | NOT RUN | |
| IV-13 | Product change before the incident | Historical effective dates correlated | B4 | NOT RUN | |
| IV-14 | Product change after the incident | Not attributed to earlier events | B4 | NOT RUN | |
| IV-15 | Closing with critical unknowns open | Blocked, or an authorised exception with rationale | B5 | NOT RUN | |
| IV-16 | Changing a signed conclusion | A superseding version; history never edited | B5 | NOT RUN | |

## CAPA, field action, trends (CP) → backlog B4, B5, later
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| CP-01 | Isolated event, no systemic issue | CAPA decision and rationale documented (no automatic CAPA) | B5 | NOT RUN | |
| CP-02 | Repeated failure across lots | Trend plus systemic risk assessment | B4 | NOT RUN | |
| CP-03 | Same problem across versions | Cross-version signal analysis | B4 | NOT RUN | |
| CP-04 | Supplier-related failure across products | Supplier and component impact assessment | B4 | NOT RUN | |
| CP-05 | CAPA action assigned | Owner, due date, approval | Later (native CAPA) | NOT RUN | |
| CP-06 | CAPA overdue | Escalation | Later | NOT RUN | |
| CP-07 | CAPA implemented but ineffective | Reopen, revise or escalate (loop back to investigation) | B5 | NOT RUN | |
| CP-08 | Effectiveness sample too small | No unsupported "effective" declaration | B5 | NOT RUN | |
| CP-09 | Complaints rise after the CAPA | Reassessment triggered | B5 | NOT RUN | |
| CP-10 | New version removes the trend | Verified over an appropriate observation window | B5 | NOT RUN | |
| CP-11 | Recall indicated | A separate authorised field-action decision | Later (FSCA) | NOT RUN | |
| CP-12 | Recall across several countries | Market-by-market action plan | Later | NOT RUN | |
| CP-13 | Product retired with complaints open | Obligations and traceability kept | Later | NOT RUN | |
| CP-14 | Duplicate signals from different sources | Analytical events de-duplicated; sources never deleted | B4 | NOT RUN | |
| CP-15 | Similar-looking records but no real signal | Exposure, observation window and data completeness considered before calling a signal | B4 | NOT RUN | |

## Call intake (CI) → backlog B2 (merged from the call-intake deep dive by `b2-case-design/spec.md`, 7 Nov 2026)
CI-01 to CI-28 are the deep dive's edge cases, in its order. CI-29 to CI-44 are added by the B2 spec. Expected behaviour in full: the spec, section 8.2.

| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| CI-01 | Several devices in one call | Split into one Case per device, linked as one event, one awareness | B2 | NOT RUN | |
| CI-02 | Several patients in one call | "Patients involved: Several"; split per patient where each may be its own report | B2 | NOT RUN | |
| CI-03 | Unknown product, or no lot or serial | Kept as typed, flagged, asked at follow-up | B2 | NOT RUN | |
| CI-04 | Anonymous reporter | Allowed; "No contact" flag; Pending never waits for ever | B2 | NOT RUN | |
| CI-05 | Foreign incident | Incident and reporter's country kept apart; the incident market's clock first | B2 | NOT RUN | |
| CI-06 | Same event by two channels | Market-based duplicate match; earliest awareness wins once linked | B2 | NOT RUN | |
| CI-07 | Caller withdraws or changes the story | Addendum; the classification stands; a change needs a new signed version | B2 | NOT RUN | |
| CI-08 | Case logged days late | First knowledge asked; a reason past 1 working day | B2 | NOT RUN | |
| CI-09 | After-hours entry, zones, weekend | Times with zones; routine targets on the calendar; fast track in clock hours | B2 | NOT RUN | |
| CI-10 | Product not in master data | Typed, resolved later by "Correct a fact" | B2 | NOT RUN | |
| CI-11 | Attachment with patient data | Scan and mask before any processing | B7 | NOT RUN | |
| CI-12 | Literature or social-media report | Its own channel; awareness = when found; the same check | B2 | NOT RUN | |
| CI-13 | Death by phone (urgent) | Complaint at once; fast track; clock kept until a signed conclusion (out-of-app notice B7) | B2 | NOT RUN | future: fix C2 (the provisional deadline leaves Oversight after triage; strict xfail today); not verification until built |
| CI-14 | Trial with no QMS | Case → Complaint → report with no QMS step | B2 | NOT RUN | |
| CI-15 | Imported complaint matches an earlier Case | Proposed link; a QMS ID match merges into the escalated complaint | B2 | NOT RUN | |
| CI-16 | Case left pending past its due time | Re-sign task; escalation after 2 working days | B2 | NOT RUN | |
| CI-17 | Reviewer is also the signer | Trial allowed and labelled; refused outside the trial | B2 | NOT RUN | |
| CI-18 | Sample clock and Cases | Non-sample rows never move; Case work stops the clock | B2 | NOT RUN | |
| CI-19 | Confirmed "no deficiency" | "Not a complaint" with a reason and a QA review | B2 | NOT RUN | |
| CI-20 | Service record showing a possible deficiency | "Check as a case"; a fault word sends the review within 24 h | B2 | NOT RUN | |
| CI-21 | Troubleshooting fixed it on the call | Still a complaint when a deficiency was alleged | B2 | NOT RUN | |
| CI-22 | No fault found later | NFF never undoes "Complaint" | B2 / B7 | NOT RUN | |
| CI-23 | Urgent case later found not serious | Stays a complaint; severity at triage | B2 | NOT RUN | |
| CI-24 | Reclassification service → complaint | New signed version, escalation, triage; awareness kept | B2 | NOT RUN | |
| CI-25 | Complaint → service (down-grade) | Refused | B2 | NOT RUN | |
| CI-26 | Two people sign the same Case at once | The second is refused | B2 | NOT RUN | |
| CI-27 | The words hold a name or phone | Masked on save | B2 | NOT RUN | |
| CI-28 | Unknown time zone typed | Refused: choose from the list | B2 | NOT RUN | |
| CI-29 | Escalation, one-record mode | The Complaint has the Case's reference and every fact; nothing asked again | B2 | NOT RUN | |
| CI-30 | Escalation, service-first mode | New complaint, facts copied, both linked; the rule unchanged | B2 | NOT RUN | |
| CI-31 | Connect: the import brings the escalated complaint's QMS ID | Same complaint updated; ownership passes to the QMS; no duplicate | B2 | NOT RUN | |
| CI-32 | Connect: master fields after hand-over | Read-only, "Correct it in your QMS"; MDARIX decisions editable | B2 | NOT RUN | |
| CI-33 | Complete: correcting a fact on an MDARIX complaint | Saved with a reason; history old → new | B2 | NOT RUN | |
| CI-34 | QMS complaint not expected | Named reason, signed, not the Case's signer outside the trial | B2 | NOT RUN | future: password signature on 'QMS complaint not expected'; not verification until built |
| CI-35 | Withdraw: entered in error | Before escalation only; signed; not the logger outside the trial | B2 | NOT RUN | |
| CI-36 | Bulk assign and bulk follow-up | Up to 200 at once; no bulk signing | B2 | NOT RUN | |
| CI-37 | Pending always owned | Owner, due task and alert on every Pending Case | B2 | NOT RUN | |
| CI-38 | Escalation with a likely duplicate | One strong match pre-selected "Attach"; "Create new" possible | B2 | NOT RUN | |
| CI-39 | The word "Case" | No screen uses "Case" for an investigation | B2 | NOT RUN | |
| CI-40 | Getting started Part 1 on the sample | Steps 1–10 tick in order on SAMPLE-CASE-11 / RV-11 | B2 | NOT RUN | |
| CI-41 | Getting started: service-only branch | Steps 3–8 not needed; QA review card; 9–10 open | B2 | NOT RUN | |
| CI-42 | Getting started: not reportable | Steps 6–8 skipped; still feeds trends | B2 | NOT RUN | |
| CI-43 | Customer contact privacy | Masked in exports, never in AI, need-to-know, erased per retention | B2 | REQUIRES HUMAN DECISION | |
| CI-44 | Signed complaint Case from before the upgrade | Escalated by the upgrade step, audited; sample rows untouched | B2 | NOT RUN | future: writing step of the 0.10.93 upgrade (only the listing step exists); not verification until built |

## Triage (TR) → backlog B2 (merged from the triage deep dive by `b2-case-design/spec.md`, 7 Nov 2026)
TR-01 to TR-24 are the deep dive's scenario table, in its order. TR-25 to TR-41 are its matrix rows not already covered (matrix rows 3, 9, 10, 12, 13, 14, 15 and 22 map to TR-18, TR-06, TR-01, TR-05, TR-04, TR-20, TR-19 and TR-23). Expected behaviour in full: the spec, section 8.3.

| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| TR-01 | Harm unknown at triage | "Not known yet", fast track kept, follow-up in 1 working day | B2 | NOT RUN | |
| TR-02 | Severity raised later | New version with a reason; a raise reopens the fast track | B2 | NOT RUN | |
| TR-03 | Severity lowered later | Never below the floor; reason; versioned | B2 | NOT RUN | |
| TR-04 | Awareness conflict | Reopens; deadlines from the earliest; confirm awareness | B2 | NOT RUN | |
| TR-05 | Later awareness than the earliest known | Signed; second person outside the trial | B2 | NOT RUN | |
| TR-06 | Threat ticked, then not a threat | Signed exclusion with a reason | B2 | NOT RUN | |
| TR-07 | Remedial action needed (US) | 5 work days; clearing needs a reason | B2 | NOT RUN | |
| TR-08 | Triage target missed | Overdue alert, backup, escalation role | B2 | NOT RUN | |
| TR-09 | No second person (backup) | Required with 2+ people; one-person trial labelled | B2 | NOT RUN | |
| TR-10 | Owner leaves | "Reassign owner", versioned | B2 | NOT RUN | |
| TR-11 | Triage reopened after new information | Automatic, with an alert | B2 | NOT RUN | |
| TR-12 | Several markets, different clocks | One row per market; own market first | B2 | NOT RUN | |
| TR-13 | Complaint escalated from a Pending Case | Routine if never triaged; fast if flagged | B2 | NOT RUN | |
| TR-14 | Triage done in the QMS, flagged | A person confirms a death or a threat | B2 | NOT RUN | |
| TR-15 | Bulk triage | Bulk assign only | B2 | NOT RUN | |
| TR-16 | Sample clock | A person's triage record never moves | B2 | NOT RUN | |
| TR-17 | Trial with one user | Allowed; "one person" | B2 | NOT RUN | |
| TR-18 | Malfunction that could cause harm (RV-11) | Potential harm asked; Serious+ → fast | B2 | NOT RUN | |
| TR-19 | Death reported after triage | Fast-track reopening and alert | B2 | NOT RUN | |
| TR-20 | Case triaged, then its QMS complaint linked | Inherits the event's triage | B2 | NOT RUN | |
| TR-21 | Historical import of 3,000 open complaints | Imported backlog view; read by query | B2 | NOT RUN | |
| TR-22 | Disposition before triage on a flagged complaint | Refused: triage first | B2 | NOT RUN | |
| TR-23 | QMS complaint closed, with a death | Second look "closed without a reportability decision?" | B2 | NOT RUN | |
| TR-24 | Two people triage at once | Version check refuses the second | B2 | NOT RUN | |
| TR-25 | Complaint, no harm, no malfunction | Routine, one click, pre-filled | B2 | NOT RUN | |
| TR-26 | Malfunction, potential harm below Serious | Routine, potential harm recorded | B2 | NOT RUN | |
| TR-27 | Minor harm | Fast track | B2 | NOT RUN | |
| TR-28 | Serious injury | Fast; floor Serious | B2 | NOT RUN | |
| TR-29 | Serious injury, remedial action needed | Fast; structured containment; its task opened | B2 | NOT RUN | |
| TR-30 | Death | Fast; floor Catastrophic; threat question answered | B2 | NOT RUN | |
| TR-31 | Threat ticked | EU 2 days, US 5 work days; escalation role told | B2 | NOT RUN | |
| TR-32 | Awareness unresolved | Confirmed with its basis | B2 | NOT RUN | |
| TR-33 | Pending Case, flagged | Fast triage before signing | B2 | NOT RUN | |
| TR-34 | Pending Case, unflagged | No triage | B2 | NOT RUN | |
| TR-35 | Service only, Inquiry, Not a complaint | No triage unless flagged | B2 | NOT RUN | |
| TR-36 | Inquiry (imported) with harm | Fast at once; second look decides too | B2 | NOT RUN | |
| TR-37 | Imported, triaged in the QMS, no flag | Accepted with source QMS | B2 | NOT RUN | |
| TR-38 | Imported, triaged in the QMS, death | A person confirms | B2 | NOT RUN | |
| TR-39 | Foreign incident | Same rule; the incident's market first | B2 | NOT RUN | |
| TR-40 | No country | Every market's shortest clock; country before the tree | B2 | NOT RUN | |
| TR-41 | Sample story item (RV-11 via SAMPLE-CASE-11) | Left for the person; story step 3 | B2 | NOT RUN | |

## Decision tree configuration (DT) → backlog B4, B4b, B4c (from `decision-tree-deep-dive/report.md`, 7 Nov 2026)
Configuration and safety cases for customer-configurable reportability questionnaires per market: the MDARIX floor (locked, cited, in the rule register) plus the organisation's own layer, which can only raise the outcome. B4b and B4c are proposed items, pending the owner's decision D12 in that report.

| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| DT-01 | Author tries to remove the death question (US Q1) | Refused: an MDARIX floor question (21 CFR 803.50(a)(1)) cannot be removed or retired | B4b | NOT RUN | |
| DT-02 | Author edits a floor question's wording or clause | Refused; help text and examples beside it are allowed | B4b | NOT RUN | |
| DT-03 | Author tries to write a rule ending in "Not reportable" | Not offered in the builder; refused on import. Not reportable = no rule applies | B4b / B4c | NOT RUN | future: B4b (organisation rule builder and rule import); not verification until built |
| DT-04 | Organisation rule raises: implant AND malfunction → Reportable 30 days | A floor "not reportable" becomes Reportable; the one-sentence result names the organisation rule | B4b | NOT RUN | |
| DT-05 | Organisation rule "lab evaluation not complete → Needs more information" | Not reportable cannot be signed while it applies | B4b | NOT RUN | |
| DT-06 | A floor question answered Unknown | Needs more information; a request to the reporter is raised; Not reportable refused (Unknown is never No) | B4 | NOT RUN | |
| DT-07 | An Unknown that could only shorten the clock (US Q6, EU threat) | Reportable with the shorter clock and its note | B4 | NOT RUN | |
| DT-08 | An organisation question left Unknown inside a raising rule | Needs more information; Not reportable refused | B4b | NOT RUN | future: B4b (organisation raising rules); not verification until built |
| DT-09 | A new version fails an MDARIX starter test row | Cannot be sent for approval | B4b | NOT RUN | |
| DT-10 | A new version fails an RG-xx row (RG-01 to RG-05, RG-10, RG-12, RG-13) | Cannot be sent for approval | B4b | NOT RUN | |
| DT-11 | A new version fails the organisation's own test row | Cannot be sent for approval | B4b | NOT RUN | |
| DT-12 | The editor of a version tries to approve it (outside a one-person trial) | Refused: a second person must approve; audited | B4b | NOT RUN | |
| DT-13 | An administrator tries to approve a version | Refused: administrators never approve | B4b | NOT RUN | |
| DT-14 | A one-person trial approves its own version | Allowed, labelled "Same person (trial practice)" | B4b | NOT RUN | |
| DT-15 | The version changes after the approval request | Back to draft; the approval is refused as "version changed" | B4b | NOT RUN | |
| DT-16 | Effective date in the past; in the future; at midnight in the organisation's zone, across daylight saving | Past refused; future shows Scheduled; in use from the exact moment in the organisation's zone | B4 | NOT RUN | future: B4b (rule write path with effective dates; the read side is RR-13); not verification until built |
| DT-17 | An open draft assessment crosses a new version's effective date | Prompt: re-check with the new version (diff shown) or continue on the old one with a reason; the signed record names the version used | B4b | NOT RUN | future: B4b (re-check prompt with the diff, or continue on the old version with a reason); not verification until built |
| DT-18 | A signed conclusion on an open complaint, which the new version would decide differently | Signed record unchanged; a re-check task, never an automatic change | B4b | NOT RUN | future: B4b (re-check task on a signed conclusion; the signed record never changing is B6-37 and RG-12); not verification until built |
| DT-19 | The same on a closed complaint | Listed in the impact list only | B4b | NOT RUN | |
| DT-20 | Awareness before a floor change, assessment after it | The floor in force at awareness applies ("at the event"); the current floor is shown for comparison | B4 | NOT RUN | |
| DT-21 | Two markets: incident in Germany, device also sold in the US | EU/NI tree required with its own version and clock; the US shown as "may also apply", advice only | B4 | NOT RUN | |
| DT-22 | A new US version is published | The EU/NI, GB, India and Canada versions and open assessments are untouched | B4b | NOT RUN | |
| DT-23 | MDARIX releases a new floor version | Banner, "See what changes" diff with citation, "Adopt in a new draft"; organisation rules referring to a retired floor question are flagged | B4c | NOT RUN | |
| DT-24 | A floor update not adopted by the law's effective date | New floor applies to new assessments from that date; organisation layer carried over; authors and approvers told (decision D8) | B4c | NOT RUN | |
| DT-25 | Export to Excel, change a floor question offline, import | Floor change refused with the list; organisation changes shown as a diff into a new draft; never published by import | B4c | NOT RUN | |
| DT-26 | Import a file from another market, or with a changed fingerprint | Other market refused; fingerprint mismatch shown as "not an approved version" | B4c | NOT RUN | |
| DT-27 | Author maps a floor judgement question (US Q5) to a record fact | Refused as an answer; allowed only as a note beside the question | B4b | NOT RUN | |
| DT-28 | Connect: a confirmed fact changes at the source | Open draft: "The record changed: confirm again"; signed conclusion: a re-check task | B4b | NOT RUN | |
| DT-29 | Retire an organisation question used in a rule | Refused until the rule is changed; a retired question stays on old versions and their signed records | B4b | NOT RUN | |
| DT-30 | Reorder questions | Organisation questions move; floor questions keep their order; outcomes and tests unchanged | B4b | NOT RUN | |
| DT-31 | A floor exception is requested | First release: not available. If allowed later (D4): applicability questions only, two signatures, 12-month expiry; refused for death, serious injury, threat or recurrence | B4c | NOT RUN | |
| DT-32 | Downgrade override: Reportable → Not reportable outside the trial | Needs a second person (a regulatory approver); the clock keeps running meanwhile (decision D7) | B4b | NOT RUN | |
| DT-33 | A floor version's content is changed in code without a new version | The build test fails (content hash per version) | B4 | NOT RUN | |
| DT-34 | The same facts on an MDARIX-owned complaint and on a QMS-imported one | The same questionnaire, outcome, clock and rule IDs; the fact's origin shown | B4 | NOT RUN | |
| DT-35 | A Customer Admin without the "Questionnaire author" set opens the section | Read only | B4b | NOT RUN | |
| DT-36 | Random organisation rules added to each market's floor | Never lowers the outcome and never lengthens the clock (property test) | B4b | NOT RUN | future: B4b (organisation rules over the floor and their property test); not verification until built |
| DT-37 | The floor rules against 0.10.92's logic | Identical suggestion and report type for every Yes/No/Unknown combination of the core questions in all five markets | B4 | NOT RUN | |
| DT-38 | "None of these" on a criteria group when the record says a death | Disabled; each criterion still answerable on its own | B4 | NOT RUN | |

## Product 360 (P360) → backlog W1 (from `w1-product-supplier-360/spec.md`, 7 Nov 2026)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| P360-01 | Product with no complaints (imported, with versions and lots) | Tiles read 0; "No complaints recorded for this version"; no error | W1 | NOT RUN | |
| P360-02 | Version with no lots | "No lots recorded"; complaints still listed; rates "units not known" | W1 | NOT RUN | |
| P360-03 | Imported product without versions | "No versions recorded"; complaints at product level; a data limitation shown | W1 | NOT RUN | |
| P360-04 | Change after the incident (IV-14) | Listed with its date; earlier complaints counted "before", never listed as related | W1 | NOT RUN | |
| P360-05 | Rev A vs Rev B compare (sample) | Pressure sensor: Precision Sensors → NovaSense, SAMPLE-CHG-014 named | W1 | NOT RUN | |
| P360-06 | Origin on every record | Sample · Your import (date, ID) · Created in MDARIX · From <system> | W1 | NOT RUN | |
| P360-07 | Connect: imported master data | No edit control; "Correct it in <system> and import again" | W1 | NOT RUN | |
| P360-08 | Links both ways | Complaint, investigation, trend card → product and version in one click; back to each record kind | W1 | NOT RUN | |
| P360-09 | CAPA effectiveness check planned, not recorded | "Planned for <date>; not yet recorded"; never "effective" | W1 | NOT RUN | |
| P360-10 | Persona without the Products tab | No rail entry; a link opens the page as the extra tab; read-only | W1 | NOT RUN | |
| P360-11 | Another organisation's product ID | 404; no counts leak | W1 | NOT RUN | |
| P360-12 | 5,000-complaint organisation | p95 < 1 s; query counts as the spec | W1 | NOT RUN | |
| P360-13 | Sample removed, restarted, or read on day 0/7/15/29 | Seed rows removed and re-seeded; the same relative story | W1 | NOT RUN | |
| P360-14 | Old "Products" link on the new navigation | Opens Product 360 | W1 | NOT RUN | |

## Supplier 360 (S360) → backlog W1 (from `w1-product-supplier-360/spec.md`, 7 Nov 2026)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| S360-01 | Supplier with no parts | "No parts are recorded"; counts 0; no pattern | W1 | NOT RUN | |
| S360-02 | One part used by several products | Each product and version listed; the pattern rule evaluated across them | W1 | NOT RUN | |
| S360-03 | A lot with parts from two suppliers | On both pages, each with its genealogy line; never "caused by" | W1 | NOT RUN | |
| S360-04 | A part with two recorded suppliers; genealogy names no supplier | Both listed; "<supplier> is a recorded supplier of it"; no attribution to one | W1 | NOT RUN | |
| S360-05 | Supplier change after the incident (IV-14) | Before/after split; earlier complaints never listed under the change | W1 | NOT RUN | |
| S360-06 | Same problem on 2+ versions with its parts | Pattern to review with counts, units, rates; "not a confirmed signal"; "Open an investigation" | W1 | NOT RUN | |
| S360-07 | Pattern already under investigation | "Open <investigation> (covers N)" instead of a new one | W1 | NOT RUN | |
| S360-08 | One version only, or below the threshold (CP-15) | No pattern statement; plain counts | W1 | NOT RUN | |
| S360-09 | Units released unknown for some lots | No rate; "units not known for X of Y lots" | W1 | NOT RUN | |
| S360-10 | NovaSense sample story | One version, lots 003–008, SAMPLE-INV-001, inspection evidence, CAPA-02 | W1 | NOT RUN | |
| S360-11 | Inspection evidence and evidence requests | Shown with source, reliability, status and answer | W1 | NOT RUN | |
| S360-12 | Supplier corrective action request (SCAR) | Not offered; "planned for a later release" | W1 | NOT RUN | |
| S360-13 | Persona without the Products tab | As P360-10 | W1 | NOT RUN | |
| S360-14 | Another organisation's supplier ID | 404; no counts leak | W1 | NOT RUN | |
| S360-15 | 5,000-complaint organisation | p95 < 1 s for list, page, complaints and lots | W1 | NOT RUN | |
| S360-16 | Imported supplier (Connect) | Read-only; origin with system, ID and last loaded | W1 | NOT RUN | |


## Routine path (RT) → backlog B7 (from `b7-routine-path/spec.md` section 2.3, 10 Nov 2026)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| RT-01 | Not a complaint: Service only | Case check signed Service only with a reason; QA review; closed with a resolution summary | B7 | NOT RUN | |
| RT-02 | Not a complaint: Inquiry | As RT-01 | B7 | NOT RUN | |
| RT-03 | Not a complaint: no deficiency confirmed | Follow-up answered no deficiency; sign; QA review | B7 | NOT RUN | |
| RT-04 | Not a complaint, then a complaint | Rescan or addendum with a harm or fault word reopens it; QA reclassifies; awareness never moves | B7 | NOT RUN | |
| RT-05 | Pending, not flagged | Follow-up due next working day; never closes as Pending | B7 | NOT RUN | |
| RT-06 | Pending, flagged (harm not known) | Fast triage before signing; provisional clock shows | B7 | NOT RUN | |
| RT-07 | Pending, confirm no deficiency | No deficiency -> RT-03; deficiency -> complaint; unresolved after attempts -> complaint | B7 | NOT RUN | |
| RT-08 | Complaint, no harm, no service, off the watch | Sign and escalate; Confirm triage; Resolve and close: one signature; Complete closes, Connect ready to close; never without customer told or problem code | B7 | NOT RUN | |
| RT-09 | Complaint and service work | As RT-08; ticket pre-filled from the Case; service completion never closes the complaint | B7 | NOT RUN | |
| RT-10 | No fault found | Correction No fault found; cause Undetermined with a reason; still a complaint | B7 | NOT RUN | |
| RT-11 | Device not returned | Device returned = not returned after the set attempts; evaluated on the description | B7 | NOT RUN | |
| RT-12 | Known issue | Joins the open investigation; that decision decides it | B7 | NOT RUN | |
| RT-13 | Trigger (recurrence, new failure mode) or by choice | Escalated; routine path never offered while a trigger is met; the problem code lets the triggers fire on Case-made complaints | B7 | NOT RUN | |
| RT-14 | Market assessment started | Must be signed first; Resolve and close not offered in full | B7 | NOT RUN | |
| RT-15 | Reporter withdraws | Reason 'reporter withdrew, no deficiency confirmed' allowed only off the watch; still a complaint | B7 | NOT RUN | |
| RT-16 | Minor malfunction (could not cause serious harm) | Since 0.10.95 a malfunction from Q3 puts it on the watch: follows RT-17 | B7 | NOT RUN | |
| RT-17 | On the watch, every market signed not reportable | Resolve and close offered with the signed conclusions (no routine basis) | B7 | NOT RUN | |
| RT-18 | Q6 Unknown, markets pending | Blocked until each market is signed; Unknown never No | B7 | NOT RUN | |
| RT-19 | Reportable | REPORTABLE trigger: never the routine path | B7 | NOT RUN | |
| RT-20 | Not reportable, investigated by choice or recurrence | As RT-13 with the markets signed | B7 | NOT RUN | |
| RT-21 | Minor harm, off the watch | Routine path offered; Resolve and close | B7 | NOT RUN | |
| RT-22 | Death or serious injury | Fast track, acknowledgement 1 h, urgent e-mail (opt-in); never the routine path | B7 | NOT RUN | |
| RT-23 | Death or serious injury, not reportable | INJURY trigger: investigation; causality rationale | B7 | NOT RUN | |
| RT-24 | Harm not known yet | Fast; blocked until harm known and markets signed | B7 | NOT RUN | |
| RT-25 | Imported complaint (QMS-owned) | Resolve and mark ready to close in your QMS; MDARIX never closes it | B7 | NOT RUN | |
| RT-26 | Closed, then new harm | Complete: the complaint reopens, the closure is superseded; alert | B7 | NOT RUN | |
| RT-27 | Anonymous reporter | Customer told = Not possible: anonymous, with the reason | B7 | NOT RUN | |
| RT-28 | Two reporters, one event | Customer told per reporter with a contact; others not needed with a reason | B7 | NOT RUN | |
| RT-29 | Reply e-mail to an open Case | Offered Add to CASE-...; never a second Case by itself | B7 | NOT RUN | |
| RT-30 | Imported old call | Imported backlog; no overdue alarms; note to check the source system | B7 | NOT RUN | |

## Bulk Case import and export (BK) → backlog B7 (spec section 6.5)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| BK-01 | Download the template | As the scenario | B7a | NOT RUN | |
| BK-02 | Names in the words are masked; the report shows counts | As the scenario | B7a | NOT RUN | |
| BK-03 | Contact columns are refused | As the scenario | B7a | NOT RUN | |
| BK-04 | A re-upload duplicates nothing and fills empty facts | As the scenario | B7a | NOT RUN | |
| BK-05 | A re-upload that changes the words is set aside | As the scenario | B7a | NOT RUN | |
| BK-06 | An unknown lot is kept and flagged | As the scenario | B7a | NOT RUN | |
| BK-07 | A recent row with a death word goes to fast triage | As the scenario | B7a | NOT RUN | |
| BK-08 | An old row goes to the backlog with no alarms | As the scenario | B7a | NOT RUN | |
| BK-09 | An over-limit file is refused whole | As the scenario | B7a | NOT RUN | |
| BK-10 | The export is masked by default; unmasking needs a reason and is audited; a trial is always masked | As the scenario | B7a | NOT RUN | |
| BK-11 | Formula cells escaped; SHA-256 in the audit | As the scenario | B7a | NOT RUN | |
| BK-12 | The QMS round trip merges by mdarix_ref | As the scenario | B7a | NOT RUN | |
| BK-13 | No route signs in bulk | As the scenario | B7a | NOT RUN | |

## E-mail intake (EM) → backlog B7 (spec section 6.5)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| EM-01 | Unknown address refused at SMTP; nothing stored | As the scenario | B7b | NOT RUN | |
| EM-02 | A normal mail becomes a draft; received = server time | As the scenario | B7b | NOT RUN | |
| EM-03 | Make it a case carries channel, Message-ID, masked words, attachments | As the scenario | B7b | NOT RUN | |
| EM-04 | A reply offers Add to case | As the scenario | B7b | NOT RUN | |
| EM-05 | Same Message-ID stored once | As the scenario | B7b | NOT RUN | |
| EM-06 | Same body shows possible duplicate | As the scenario | B7b | NOT RUN | |
| EM-07 | Infected attachment never stored | As the scenario | B7b | NOT RUN | |
| EM-08 | Wrong type or too large refused with the reason | As the scenario | B7b | NOT RUN | |
| EM-09 | Auto-reply goes to the bin, purged after 30 days | As the scenario | B7b | NOT RUN | |
| EM-10 | Rate limits answer 451 | As the scenario | B7b | NOT RUN | |
| EM-11 | A death word raises the alert | As the scenario | B7b | NOT RUN | |
| EM-12 | Not a case on a fault word needs a quality reviewer | As the scenario | B7b | NOT RUN | |
| EM-13 | Non-English flagged; translation addendum | As the scenario | B7b | NOT RUN | |
| EM-14 | After rotation the old address works 30 days | As the scenario | B7b | NOT RUN | |
| EM-15 | Raw view audited and need-to-know | As the scenario | B7b | NOT RUN | |
| EM-16 | Receiver down: senders retry; health check shows it | As the scenario | B7b | NOT RUN | |
| EM-17 | Forwarded earlier date becomes a first-knowledge candidate | As the scenario | B7b | NOT RUN | |
| EM-18 | A token never writes into another organisation | As the scenario | B7b | NOT RUN | |

## Urgent alert (UA) → backlog B7 (spec section 6.5)
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| UA-01 | Opted in: e-mail sent at once, no patient data | As the scenario | B7a | NOT RUN | |
| UA-02 | Opted out: in-app only | As the scenario | B7a | NOT RUN | |
| UA-03 | SMTP failure shown; escalation stays; no duplicate e-mails | As the scenario | B7a | NOT RUN | |
| UA-04 | Overdue acknowledgement gets one reminder | As the scenario | B7a | NOT RUN | |
| UA-05 | Reopening with a death sends the alert | As the scenario | B7a | NOT RUN | |
| UA-06 | No address or deactivated account: skipped and recorded | As the scenario | B7a | NOT RUN | |

## Investigation challenge and closed loop (B5) → backlog B5 (from `b5-challenge-closed-loop/spec.md` 5.5, 11 Nov 2026)
Targeted unit and database tests exist for each (named in the last column); none has been run as a scenario, so all stay NOT RUN until the ~24 Nov test release.
| ID | Scenario | Expected behaviour | Item | Status | Notes |
|---|---|---|---|---|---|
| B5-01 | Units unknown for one lot of a version after the decision | That version shows counts by calendar days only, "units unknown for X of Y lots", never a rate from partial units (targeted test: test_b5_loop_api.py, test_b5_loop_rules.py) | B5 | NOT RUN | |
| B5-02 | A later complaint with no version | Listed apart as "version unknown"; counted in no version (PV-1) (targeted test: test_b5_loop_api.py) | B5 | NOT RUN | |
| B5-03 | A change took effect after the first scope complaint | That complaint counts against H-1, never for it (IV-14) (targeted test: test_b5_draft_rules.py) | B5 | NOT RUN | |
| B5-04 | Sample investigation SAMPLE-INV-001 opens Challenge | Drafts H-1 (SAMPLE-CHG-014) and H-2 (lots 003, 004), each with records for, against and missing, labelled by rule and version, never ranked; "You may already have this" on the sample hypothesis (IV-01, IV-02, IV-03) (targeted test: test_b5_challenge_api.py) | B5 | NOT RUN | |
| B5-05 | Records contradict the leading hypothesis and nothing contradicting is linked | C-1 asks; Submit for review is blocked until answered or marked not applicable (IV-04) (targeted test: test_b5_questions.py, test_b5_brief.py) | B5 | NOT RUN | |
| B5-06 | Fewer than 3 scope complaints, or none with a version or lot | H-0 lists what is missing; no other draft (IV-05) (targeted test: test_b5_draft_rules.py) | B5 | NOT RUN | |
| B5-07 | Only the supplier's statement supports the leading hypothesis | C-6 asks for independent evidence; the statement stays an assertion (IV-09) (targeted test: test_b5_questions.py) | B5 | NOT RUN | |
| B5-08 | Evidence or complaint text carries instructions | Rules read structured fields and codes only (IV-10) (targeted test: none yet; the facts reader selects structured columns only) | B5 | NOT RUN | |
| B5-09 | An open question is linked to the leading hypothesis | C-5 asks; material until answered or accepted as a limitation (IV-15) (targeted test: test_b5_questions.py) | B5 | NOT RUN | |
| B5-10 | A CAPA from the decision is signed not effective | One impact assessment and its task for the owner, audited REOPEN_TRIGGER_FIRED; the decision is never changed (CP-07) (targeted test: test_b5_triggers.py) | B5 | NOT RUN | |
| B5-11 | Few complaints after the action | "Too few to tell" or "Too early"; never "effective" (CP-08) (targeted test: test_b5_loop_rules.py) | B5 | NOT RUN | |
| B5-12 | More complaints after the action, or 2 or more after the CAPA was signed effective | LATER_COMPLAINTS_MORE or RECURRENCE_AFTER_EFFECTIVE opens one impact assessment per group (CP-09) (targeted test: test_b5_triggers.py (rule)) | B5 | NOT RUN | |
| B5-13 | A product change names a new version | New vs old version over the same period; 2 or more complaints with the problem on the new version open an impact assessment (CP-10) (targeted test: test_b5_followup_fields.py for the new version, test_b5_triggers.py (rule); the new vs old view is untested) | B5 | NOT RUN | |
| B5-14 | A later complaint reports death or serious injury | LATER_SERIOUS_HARM opens one impact assessment (IV-07) (targeted test: test_b5_triggers.py) | B5 | NOT RUN | |
| B5-15 | A complaint on a lot a field action covered, after its effective date | COMPLAINT_ON_ACTIONED_LOT opens one impact assessment (targeted test: test_b5_triggers.py (rule)) | B5 | NOT RUN | |
| B5-16 | Sample decision signed; SAMPLE-CAPA-02 has no check result yet | Did it work? reads "Too early"; no after-action complaints are invented (B5-D10) (targeted test: test_b5_loop_api.py) | B5 | NOT RUN | |
| B5-17 | A decision superseded by a new one | Did it work? reads the new decision and lists the old; triggers never fire on the old (IV-16) (targeted test: test_b5_loop_api.py, test_b5_triggers.py) | B5 | NOT RUN | |
| B5-18 | Sample complaints in an organization with its own investigations | Never counted in a customer investigation's numbers or triggers (R6) (targeted test: test_b5_triggers.py) | B5 | NOT RUN | |
| B5-19 | MDARIX_CHALLENGE or MDARIX_CLOSED_LOOP off | The API answers 404, the screens are hidden, the sweep fires nothing (targeted test: test_b5_challenge_api.py, test_b5_loop_api.py, test_b5_triggers.py, vitest) | B5 | NOT RUN | |

## Rule register (RR) → backlog B4 (from `b4-rule-register/spec.md`, 11 Nov 2026)

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| RR-01 | Version 1 of every floor against today's code, every answer combination | Identical suggestion, report type, notes and folded questions (covers DT-37; test_b4_equivalence.py) | B4 | NOT RUN | |
| RR-02 | An Unknown floor answer (DT-06) | Pending information; Not reportable refused (test_b4_equivalence.py, test_market_assessment_rules.py) | B4 | NOT RUN | |
| RR-03 | An Unknown that only shortens the clock: US Q6, EU/GB threat (DT-07) | Reportable with the shorter report and its note (test_b4_equivalence.py) | B4 | NOT RUN | |
| RR-04 | A register file with an unknown catalog id, a duplicate code, a missing field | The loader refuses, naming the file (test_rule_register_unit.py) | B4 | NOT RUN | |
| RR-05 | Overlapping versions, a gap, or an end before a start (ED-12) | The loader refuses, naming the files (test_rule_register_unit.py) | B4 | NOT RUN | |
| RR-06 | A floor version's content changed without a new version (DT-33) | The build test fails, naming the file (test_rule_register_unit.py, test_rule_pins_unit.py) | B4 | NOT RUN | |
| RR-07 | Awareness 28 Feb / 1 Mar 2027 around a test-only US-floor-2 (ED-1..ED-4) | The authority's awareness day picks the version (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-08 | Awareness before a floor change, assessment after it (DT-20, ED-10) | The floor in force at awareness applies; today's floor shown for comparison (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-09 | Signed under v1, v2 deployed (ED-5, ED-9) | Signed record, columns, fingerprint and report due date unchanged (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-10 | Draft saved under v1, correction v3 deployed, sign (ED-6) | 409 FLOOR_CHANGED; re-save picks v3; sign succeeds (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-11 | Draft awareness edited across a floor change (ED-7) | Next save picks the floor of the new awareness day (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-12 | Two markets, one floor change (DT-21, ED-8) | Each market picks its own version by its own authority zone (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-13 | A future version before its date (ED-13) | Listed as Scheduled; never used for an earlier awareness (test_rule_register_unit.py) | B4 | NOT RUN | |
| RR-14 | Deadline across a daylight-saving change (RG-11, ED-14) | Identical latest day, end and zone to today's code (test_b4_equivalence.py) | B4 | NOT RUN | |
| RR-15 | Rule changes after the incident (RG-12) | The version in force at awareness is kept on the conclusion (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-16 | Routine path signs not reportable (ED-15) | Each market's row stores its floor and rules applied routine-basis-1 (test_b4_effective_dating.py) | B4 | NOT RUN | |
| RR-17 | The same facts on an MDARIX complaint and an imported one (DT-34) | Same outcome, clock and rule IDs (test_b4_equivalence.py: the engine reads answers only) | B4 | NOT RUN | |
| RR-18 | A pinned regulatory function or the eMDR rule book changed without a new version | The pin test fails, naming the file (test_rule_pins_unit.py) | B4 | NOT RUN | |
| RR-19 | Any member opens Decision trees > Rules; an unknown code | Every rule listed read-only with its starter mark; unknown code 404; no write route (test_b4_register_api.py) | B4 | NOT RUN | |
| RR-20 | MDARIX_RULE_REGISTER=off | Today's code; register routes 404; Rules tab hidden; floor columns not written (test_b4_switch) | B4 | NOT RUN | |

## Markets (B9) → backlog B9 (from `b9-markets/spec.md`, approved 11 Nov 2026)

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| B9-01 | India Reportable conclusion, organization window 30 days | Due 15 calendar days from the regulation (IN-floor-2, starter), awareness day = day 1 (test_b9_india_period.py) | B9 | NOT RUN | |
| B9-02 | India Reportable conclusion, organization window exactly 15 calendar days | The organization's window is used (test_b9_india_period.py) | B9 | NOT RUN | |
| B9-03 | India draft saved under IN-floor-1, signed after IN-floor-2 | 409 FLOOR_CHANGED; re-save picks IN-floor-2; sign succeeds (test_b9_india_period.py) | B9 | NOT RUN | |
| B9-04 | India conclusion signed under IN-floor-1 | Record, floor code and due date unchanged byte for byte (test_b9_india_period.py) | B9 | NOT RUN | |
| B9-05 | Approved India report, official MvPI MDAE v1.2 form | Each mapped value in its box; record page appended; field map still to be checked once by a person against the printed form (test_b9_mvpi_form.py) | B9 | NOT RUN | |
| B9-06 | Approved India report, ADRMS entry sheet | All 16 ADRMS mandatory fields listed in screen order, a value or "enter in ADRMS" (test_b9_adrms_sheet.py) | B9 | NOT RUN | |
| B9-07 | India initial submitted | Follow-up and final only on demand, never automatic; optional next-report date labelled "No legal clock: your date" (test_b9_india_chain.py) | B9 | NOT RUN | |
| B9-08 | India Final created | The chain ends: no further follow-up or final (test_b9_india_chain.py) | B9 | NOT RUN | |
| B9-09 | India tenant role Importer | R1 and A_IMPORTER change only; same floor and 15 days | B9 | NOT RUN | |
| B9-10 | Approved Canada report | Official HC Pub. 110180 form filled, read back field by field | B9 | NOT RUN | |
| B9-11 | Canada Preliminary recorded as submitted | One Final draft created, due on the A5 anticipated date | B9 | NOT RUN | |
| B9-12 | Canada Final or Preliminary & Final submitted | Nothing created after it | B9 | NOT RUN | |
| B9-13 | Canada Final without E2 root cause or E3 corrective actions | Refused | B9 | NOT RUN | |
| B9-14 | Canada Update or Final | Health Canada file number (A4) carried from the acknowledgement | B9 | NOT RUN | |
| B9-15 | Canada tenant role Importer | A1 and A7 follow the role | B9 | NOT RUN | |
| B9-16 | US reporting role set by an Approver with a reason | Saved and audited REPORTING_ROLE_SET | B9 | NOT RUN | |
| B9-17 | US reporting role set by an admin alone | Refused | B9 | NOT RUN | |
| B9-18 | US importer floor | 30 calendar days; no 5-day report | B9 | NOT RUN | |
| B9-19 | US user facility floor | 10 work days; no malfunction report | B9 | NOT RUN | |
| B9-20 | Unknown answers under the importer and user facility floors | Never read as No | B9 | NOT RUN | |
| B9-21 | F2 report numbers | Importer FEI/CFN-yyyy-5 digits, user facility HCFA-yyyy-4 digits; never with G8 | B9 | NOT RUN | |
| B9-22 | FDA's importer and user facility examples | Rebuilt block by block, schema-valid (local fixtures only) | B9 | NOT RUN | |
| B9-23 | Importer malfunction report | Goes to the manufacturer only; no FDA route offered | B9 | NOT RUN | |
| B9-24 | Death reported by an importer or user facility | Goes to FDA and the manufacturer | B9 | NOT RUN | |
| B9-25 | Importer / user facility follow-ups | Numbered 1, 2, 3 without gaps; one open at a time | B9 | NOT RUN | |
| B9-26 | MDARIX_B9_US_USER_FACILITY off (default) | User facility role not offered; its routes 404 | B9 | NOT RUN | |
| B9-27 | Another tenant | Its reports and role are never seen | B9 | NOT RUN | |
| B9-28 | Each B9 switch off, then on | Drafts stay signable after a re-save; routes 404 while off | B9 | NOT RUN | |
| B9-29 | B4 equivalence with every B9 switch on and off | Green; IN-floor-1 still compared with today's code at version 1 | B9 | NOT RUN | |
| B9-30 | Routine path signs not reportable | Stores the role floor in force | B9 | NOT RUN | |
| B9-31 | Importer role switched off after a US report is approved | Still an importer's report: role and recipients as frozen at Send for approval; no FDA route for an importer malfunction | B9 | NOT RUN | |
| B9-32 | Conclusion re-signed after approval names other recipients | Routes keep the recipient list frozen at Send for approval | B9 | NOT RUN | |
| B9-33 | Typed F2 equal to an earlier manufacturer number (and the reverse) | Refused, REPORT_NUMBER_IN_USE; a generated number skips the other role's | B9 | NOT RUN | |
| B9-34 | Manufacturer's US decision guide | Lists only the manufacturer's report types | B9 | NOT RUN | |
| B9-35 | Signed conclusion card | Shows its rules (floor) and the role it was decided in | B9 | NOT RUN | |
| B9-36 | Canada foreign incident (CA-floor-2) | Due by the end of the day after awareness (provisional until the corrective-action decision day is known); CA5 Unknown with CA6 Yes takes the foreign clock; signed CA-floor-1 rows unchanged | B9 | NOT RUN | |
| B9-37 | Register pins on a Linux (LF) checkout | Every pin holds | B9 | NOT RUN | |

## EU and GB MIR (B8) → backlog B8 (from `b8-eu-gb-mir/B8-execution-plan.md` 6.5, approved 11 Nov 2026)

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| B8-01 | First EU report of a chain | Offers Initial or Combined initial and final only; any other type 422 NOT_THIS_POSITION | B8 | NOT RUN | |
| B8-02 | EU Initial recorded as submitted | Exactly one Follow-up draft created, due on the Initial's 1.2f date, audited REPORT_FOLLOW_UP_CREATED (automatic) | B8 | NOT RUN | |
| B8-03 | EU Follow-up recorded as submitted | The next Follow-up draft is created, due on its 1.2f | B8 | NOT RUN | |
| B8-04 | Combined or Final report submitted | Nothing follows; a further report is refused (chain ended) | B8 | NOT RUN | |
| B8-05 | Next report while the last is not accepted | Send for approval refused, 409 PREVIOUS_NOT_ACCEPTED | B8 | NOT RUN | |
| B8-06 | Draft switched to Final (Reportable incident) | The mandatory set changes to the Final's schema at once | B8 | NOT RUN | |
| B8-07 | 1.1c on a later report | Carried from the Initial's recorded submission; "Unknown" when none | B8 | NOT RUN | |
| B8-08 | 1.3.1b on every report | The complaint's business ID, the same on each report of the chain | B8 | NOT RUN | |
| B8-09 | EU conclusion re-signed "not reportable" with a chain draft open | The draft is kept and offered as Final (Non-reportable incident) with 4.2b from the signed rationale; a person chooses | B8 | NOT RUN | |
| B8-10 | Re-sign with an approved, unsent report in the chain | That approval is superseded; sent reports never change | B8 | NOT RUN | |
| B8-11 | After a Final | "Updated final report" only on demand, type Final again | B8 | NOT RUN | |
| B8-12 | Each EU MIR type | The built XML is valid against that type's vendored XSD (SB-11252) | B8 | NOT RUN | |
| B8-13 | Send for approval while the XML would be refused | 422 MIR_MISSING / MIR_INVALID naming each block | B8 | NOT RUN | |
| B8-14 | Download after approval, Settings changed later | The XML is the approved one, byte for byte; the fingerprint covers it | B8 | NOT RUN | |
| B8-15 | XML before approval or from a superseded snapshot | Not served | B8 | NOT RUN | |
| B8-16 | MIR-layout PDF | Every value in the XML is in the PDF; same snapshot, same bytes | B8 | NOT RUN | |
| B8-17 | PDF title | "prepared by MDARIX"; never claims the Commission or MHRA made it | B8 | NOT RUN | |
| B8-18 | Report approved before B8 | Keeps its worksheet PDF; no XML rebuilt | B8 | NOT RUN | |
| B8-19 | 1.1a NCA | Follows the incident country (vendored NCA list) | B8 | NOT RUN | |
| B8-20 | 1.2a | The organisation's day the report was sent for approval | B8 | NOT RUN | |
| B8-21 | 1.2d | Never filled without a person; the signing day is a hint only | B8 | NOT RUN | |
| B8-22 | Address and contact parts | Entered once, reach every report | B8 | NOT RUN | |
| B8-23 | Personal fields (3.3, 3.4) while the tenant setting is off | Blank | B8 | NOT RUN | |
| B8-24 | Final without the full 4.3 table | Refused until every period and region is entered | B8 | NOT RUN | |
| B8-25 | Each GB MIR type | The built XML is valid against that type's vendored GB 7.2.1 XSD | B8 | NOT RUN | |
| B8-26 | GB file | Holds no EU-only element (1.2d, EUDAMED, PMCF, height) | B8 | NOT RUN | |
| B8-27 | GB Annex B-G codes | Required on every GB type (B8-D3) | B8 | NOT RUN | |
| B8-28 | Northern Ireland incident | Route "MHRA MORE (EU form)" with the EU XML; 1.1a asked | B8 | NOT RUN | |
| B8-29 | EU incident outside Northern Ireland | Never offers MORE | B8 | NOT RUN | |
| B8-30 | Another tenant's chain | Never seen | B8 | NOT RUN | |
| B8-31 | MDARIX_B8_EU_MIR / MDARIX_B8_GB_MIR off, on, off | Today's worksheet back, mir.xml 404, no automatic draft; drafts still sendable | B8 | NOT RUN | |
| B8-32 | B4 equivalence | Green, no floor file changed | B8 | NOT RUN | |

## Other countries (OC) → backlog B9b (from `other-country-reports/spec.md` §4 and `B9b-execution-plan.md` §6, approved 9 and 11 Nov 2026)

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| OC-01 | Pick a country | A country outside the five markets can be chosen; an EU/EEA country, GB or the UK is sent to its own tree | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-02 | Signed Reportable conclusion for a country | Creates one Other Regulatory Report (form ATTACHED) | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-03 | Any answer set with an Unknown | Never Not reportable (Needs more information) | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-04 | Record "Submitted" | Refused without a file or a date | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-05 | Report ID "Not issued yet" | Allowed; filled in later, audited | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-06 | Acknowledgement | Updates the status and keeps the file | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-07 | Follow-up | Linked to its parent, with its own Report ID and status | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-08 | Several follow-ups | Allowed, no fixed order | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-09 | Close with a follow-up open | Refused | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-10 | Due date | From a window naming the country (name or ISO code); else a manual date labelled "Due date entered by the customer" | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-11 | Overdue | An overdue Other Regulatory Report is listed | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-12 | Second file | Never overwrites the first; both kept | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-13 | Infected or failed-scan file | Refused | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-14 | Another organisation's record | Never seen or changed | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-15 | Inspection pack | Lists the reports and their files | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-16 | Signed conclusion | Stores `OTHER-floor-1` and its content hash | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-17 | MDARIX_B9B_OTHER off | Picker hidden, routes 404; existing records readable | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-18 | B4 equivalence | Green with the switch on and off | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-19 | "Submitted" without the recorder's signature | Refused; the signed material holds the file's SHA-256 | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |
| OC-20 | EU outermost region or Åland | Not offered; says "This may fall under the EU MDR: check with your consultant" | B9b | NOT RUN | API-tested (run 1); E2E NOT RUN |

## Deadline protection, speed, reviews and trace (B6a) → backlog B6 (from `b6-speed-evidence/B6a-spec.md` §10, approved 11 Nov 2026)

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| B6-01 | Daily deadline list at 06:00 organisation time | One e-mail per organisation per local day, from 06:00 in the oversight calendar's zone; a second run that day queues nothing | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-02 | Daily list on a day with nothing due | Still sent: "0 open reporting deadlines today" | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-03 | Order of the list | Overdue first, then soonest; zone shown with each due time | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-04 | No text in the e-mail or the queue | References, markets, dates and states only; no description, patient or reporter text; no addresses in the queue | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-05 | Switch the daily list off | Allowed under My account; refused for the last recipient left on | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-06 | Download the deadline list (CSV, PDF) | Needs data.export; audited; PDF one page per 40 lines, dated, "check MDARIX when it is back" | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-07 | Back-entry more than 24 h after awareness | Refused without a late-entry reason (422 LATE_ENTRY_REASON_NEEDED); 23 h needs none; reason stored, audited, shown "Entered late" | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-08 | Clock of a back-entered Case | Counts from awareness, never from entry; may show overdue at once | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-09 | Duplicate check before saving a back-entry | Possible duplicates (Cases, complaints, e-mails to check) shown before Save; the person links or saves anyway; no automatic merge | B6a | NOT RUN | API-tested (run 1); E2E NOT RUN |
| B6-10 | Clock offset over 1 s | Readiness clock check degraded; operations alert once, and once when it clears | B6a | NOT RUN | Unit-tested (run 1); E2E NOT RUN |
| B6-11 | NTP unreachable | Clock check says unknown, never ok | B6a | NOT RUN | Unit-tested (run 1); E2E NOT RUN |
| B6-12 | Complaint page at 5,000 complaints | p95 <= 500 ms (local, in-process) | B6a | FAIL | PASS in run 3 (p50 351 / p95 411 ms, 106 queries); run 4 on a laptop short of memory: 424 / 539 ms: re-measure |
| B6-13 | Story page at 5,000 complaints | p95 <= 500 ms (local, in-process) | B6a | FAIL | FAIL, accepted as a known limit for now (run 3: p50 587 / p95 634 ms; run 4, laptop short of memory: 663 / 873 ms; 129 queries) |
| B6-14 | Scoped read equals the organisation-wide read | For every complaint: same items, same order, same dates | B6a | NOT RUN | PASS (sample + 200 + linked Case and cross-complaint task, run 3; 5,000 load set passed on run-2 code, 73 min; run 4: paging proof and memo PASSED at 5,000; the per-complaint scoped proof stopped on an out-of-memory socket error, NOT RUN to the end on run-4 code) |
| B6-14b | Triage list paged on the server (run 4) | Pages in order equal the whole list; same counts; an item past the page found by its address; triage screen p95 <= 500 ms at 5,000 | B6a | FAIL | Equivalence PASS (sample and 5,000); speed FAIL (p95 2.0 s at 5,000, was 4.9 s; owner decision) |
| B6-15 | Query count | Flat with organisation size (100 vs 1,000 complaints) | B6a | PASS | PASS (tests/test_b6a_query_budget.py: same count at 100 and 1,000; budget 115 / 140) |
| B6-16 | LCP on the production bundle | <= 2.5 s on both pages | B6a | NOT RUN | NOT RUN (Playwright not run in this build) |
| B6-17 | Release checks | release-checks JSON produced with versions, timings, pass/fail | B6a | NOT RUN | PARTLY (dry run only, run 2; no real run) |
| B6-18 | Sign-in lockout | 4 failures still sign in; 5 lock | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-19 | Lock length | 14:59 still locked; 15:00 open | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-20 | MFA failures | 4 then accepted; 5 lock | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-21 | Signing re-authentication | 4 allowed; 5 throttled | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-22 | Idle session | 29 min alive; 31 min ended | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-23 | Session length | 11:59 alive; 12:01 ended | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-24 | Rate limits | limit-th allowed; limit+1 429 with Retry-After | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-25 | Request sizes | At the limit accepted; one byte over refused | B6a | PASS | PASS (tests/test_b6a_boundaries.py; e-mail 25 MB / 30 per hour constants only here, both sides in test_mail_in.py) |
| B6-26 | Rows | At the limit accepted; one over refused | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-27 | Password length | 12 accepted; 11 refused | B6a | PASS | PASS (tests/test_b6a_boundaries.py, run 2 and run 3 regression set) |
| B6-28 | Audit trail review flags | Each flag found on a crafted trail, absent on a clean one | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-29 | Reviewer's own flagged actions | Need a second reviewer | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-30 | Review signature | Needs password + MFA | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, password and MFA, run 5) |
| B6-31 | Signed review | Content unchanged afterwards | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, fingerprint, tamper caught, run 5) |
| B6-32 | Access review | Every row marked before signing | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-33 | Own row in the access review | Marked by another person | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-34 | Configuration snapshot | Holds no secret (connector keys absent) | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-35 | Configuration comparison | Shows who, when and why | B6a | PASS | PASS (tests/test_b6a_signed_reviews.py, run 5) |
| B6-36 | Reporting facts edit | Needs a reason | B6a | PASS | PASS (tests/test_b6a_change_reason.py, run 5) |
| B6-37 | Facts changed after signing | Flag shown; signed bytes unchanged | B6a | PASS | PASS (tests/test_b6a_change_reason.py, run 5) |
| B6-38 | Re-upload behind a signed decision | Needs a reason | B6a | PASS | PASS (tests/test_b6a_reupload_reason.py, run 6: no reason refused, one reason per run, QMS sync reason automatic, signed conclusions flagged never rewritten) |
| B6-39 | Trace this value | Reaches the field, its change, its import line and its snapshot | B6a | PASS | PASS (tests/test_b6a_trace.py, run 7: event date to the complaint field, the sample file's import row and the approved snapshot with its SHA-256; awareness change with its reason and values; a typed value's before/after) |
| B6-40 | Trace | Read only | B6a | PASS | PASS (tests/test_b6a_trace.py, run 7: audit events, report state and entries unchanged after tracing; no write method) |
| B6-41 | Similar wording | Pair suggested | B6a | PASS | PASS (tests/test_b6a_similar_wording.py, tests/test_b6a_similar_wording_unit.py, run 7: 90 % pair suggested, unrelated not, bounds 0.5 / 90 days / product / 500 records; wording-only never pre-selected). Precision on the load set: NOT RUN (new laptop) |
| B6-42 | Dismissed similar pair | Not shown again | B6a | PASS | PASS (tests/test_b6a_similar_wording.py, run 7: dismissed with the audited DUPLICATE_DISMISSED, not suggested again) |
| B6-43 | Value Centre | Medians on known data | B6a | PASS | PASS (tests/test_b6a_value_centre_unit.py, tests/test_b6a_value_centre.py, run 7: median/p90 on known data; baseline the first 30 days, fixed after; QMS history apart; sample excluded) |
| B6-44 | Value Centre | No per-person numbers | B6a | PASS | PASS (tests/test_b6a_value_centre.py, test_b6a_value_centre_unit.py, valueCentre.test.tsx, run 7: no name, account or actor in the answer, the CSV or the screen) |
| B6-45 | Another organisation | Sees nothing of any new B6a screen or route | B6a | PASS | PASS: Part C routes (tests/test_b6a_signed_reviews.py, runs 5-6); Part D run 7: trace 404 REPORT_NOT_FOUND, similar-wording pairs not listed, Value Centre only its own numbers |
| B6-46 | Each B6 switch off/on | Signed records stay readable | B6a | PASS | PASS: MDARIX_B6_REVIEWS and MDARIX_B6_CHANGE_REASON (runs 5-6); MDARIX_B6_TRACE, MDARIX_B6_SIMILAR_WORDING, MDARIX_B6_VALUE_CENTRE off/on in their tests (404 or hidden, then back), and the report, intake, oversight and case regression set with all three off: 64 passed (run 7) |
| B6-47 | Validation evidence | A test's `requirement` marker appears in the JUnit XML | B6b | NOT RUN | |
| B6-48 | Validation evidence | An XLSX written by the new writer reads back equal through the product's XLSX reader, and a cell starting with "=" stays text | B6b | NOT RUN | |
| B6-49 | Validation evidence | The validation-pack generator fails on each traceability check (class-A REQ without a negative scenario, REQ without a scenario, unknown scenario, PASS without evidence, marker with an unknown ID) and lists all of them | B6b | NOT RUN | |
| B6-50 | Validation evidence | The generator refuses to overwrite a release folder holding a signed approval | B6b | NOT RUN | |
| B6-51 | Validation evidence | The same tag gives byte-identical DOCX and XLSX | B6b | NOT RUN | |
| B6-52 | Validation evidence | Every class-A REQ has at least one tagged test or a scripted OQ step | B6b | NOT RUN | |
| B6-53 | Recovery check | A broken audit chain on the restored copy fails the recovery check | B6b | NOT RUN | |
| B6-54 | Recovery check | A configuration difference with no change event after the signed snapshot is flagged | B6b | NOT RUN | |
| B6-55 | Recovery check | A pending outbox event older than the restore point is held, audited, and sent only after a replay | B6b | NOT RUN | |
| B6-56 | Health report | A health report holds no other organisation's data | B6b | NOT RUN | |
| B6-57 | Deviation log | A deviation cannot be closed without a retest result and an approver | B6b | NOT RUN | |
| B6-58 | Release approval | A release approval record cannot be produced while a critical deviation is open | B6b | NOT RUN | |

## Platform controls (PL) → B6b (drafted 12 Nov 2026 for the owner's review: owner decision O15, MDX-B10-005 OP-2)

Scenarios for the 17 class-A requirements that had none, and negative scenarios for the 12 class-A requirements that
had scenarios but no negative one. Each row names its requirement in `requirements.csv`; "Tests to tag" are the
existing tests expected to give the evidence once they carry the `requirement` marker (MDX-VAL-001 section 16.1,
tagging plan). Drafts: the quality approver reviews and approves each expected result before any is executed (MDX-VAL-001 section 8, class A).

| ID | Scenario | Expected | Backlog | Status | Notes |
|---|---|---|---|---|---|
| PL-01 | Sign a decision; the record and the signature are both saved | The decision shows as signed and its signature verifies | B6b | NOT RUN | REQ-SIG-004; draft for owner review; tests to tag: tests/test_signing_recovery.py |
| PL-02 | Negative: the record save fails after the signature is prepared | The signature stays PENDING and is never shown as valid; the settlement job resolves it; the record is not shown as signed | B6b | NOT RUN | REQ-SIG-004; negative; draft for owner review; tests to tag: tests/test_signing_recovery.py |
| PL-03 | A user with signing authority and current signer training signs a regulated decision | Signature accepted and audited | B6b | NOT RUN | REQ-SIG-005; draft for owner review; tests to tag: tests/test_authorization_matrix.py |
| PL-04 | Negative: a user without signing authority tries to sign | Refused (403); the refusal is audited; nothing is signed | B6b | NOT RUN | REQ-SIG-005; negative; draft for owner review; tests to tag: tests/test_authorization_matrix.py, tests/test_business_permissions.py |
| PL-05 | Negative: a user with signing authority but no recorded training on the current document version tries to sign, in any organisation (every organisation, not only a trial) | Refused (409 TRAINING_REQUIRED), naming the missing training; nothing is signed | B6b | NOT RUN | REQ-SIG-005; negative; draft for owner review; the trial-only rule of 31 Oct 2026 (decision 6) is superseded by the owner's approval of 12 Nov 2026 (O25); tests to tag: tests/test_market_assessment_api.py::test_the_training_rule_binds_every_organization_not_only_a_trial, tests/test_complaint_disposition_api.py::test_an_organization_outside_a_trial_signs_only_after_its_training_record |
| PL-06 | A rule version built by an engineering account and approved by a different approver account | The register loads | B6b | NOT RUN | REQ-SOD-003; draft for owner review; tests to tag: tests/test_rule_register_unit.py |
| PL-07 | Negative: builder and approver are the same account under different typed names | The register refuses to load and names the file | B6b | NOT RUN | REQ-SOD-003; negative; draft for owner review; tests to tag: tests/test_rule_register_unit.py |
| PL-08 | Negative: an UPDATE or DELETE is run on an audit row directly in the database | Refused by the database trigger; the row is unchanged | B6b | NOT RUN | REQ-AUD-001; negative; draft for owner review; tests to tag: tests/test_day35_audit_immutability.py |
| PL-09 | Daily audit-chain verification on an intact chain | Reported as verified, with the head recorded as an anchor | B6b | NOT RUN | REQ-AUD-002; draft for owner review; tests to tag: tests/test_audit_hash_chain.py |
| PL-10 | Negative: one audit row's stored hash is altered in a test database (trigger disabled by the database owner) | Verification reports the break at that row and raises an operations alert | B6b | NOT RUN | REQ-AUD-002; negative; draft for owner review; tests to tag: tests/test_audit_hash_chain.py |
| PL-11 | Negative: edit a signed PMS document version | Refused; a change is a new version that supersedes it; the signed version is unchanged | B6b | NOT RUN | REQ-REC-005; negative; draft for owner review; tests to tag: tests/test_qms_documents_rules.py, tests/test_qms_documents_api.py |
| PL-12 | Purge an organisation with MFA; the completion job runs | Only that organisation's records are erased; every other organisation is unchanged | B6b | NOT RUN | REQ-REC-006; draft for owner review; tests to tag: tests/test_export_purge_mfa.py, tests/test_purge_completion_job.py |
| PL-13 | Negative: erase or purge records under legal hold | The held records are not erased; the refusal is audited | B6b | NOT RUN | REQ-REC-006; negative; draft for owner review; tests to tag: tests/test_customer_admin_erasure_hold.py |
| PL-14 | Negative: delete a customer organisation's audit events before their retention date, without a recorded hand-back | Refused: the trail goes only after the recorded hand-back (purge refused EXPORT_REQUIRED; outside that purge the database refuses any deletion of audit events, trigger `audit_events_immutable`) | B6b | NOT RUN | REQ-REC-006; negative; draft for owner review; the trigger `audit_events_retention` only sets the retention date; tests to tag: tests/test_tenant_data.py::test_no_caller_deletes_a_customer_organizations_trail_without_the_hand_back, tests/test_tenant_data.py::test_a_purge_needs_an_export_made_after_the_suspension_or_a_recorded_waiver |
| PL-15 | Negative: an eMDR with a block FDA requires left empty is checked before approval | The check refuses it and names the missing block; approval is not offered | B6b | NOT RUN | REQ-ARD-002; negative; draft for owner review; tests to tag: test to add in tests/test_fda_3500a_emdr.py (MDX-VAL-002 RSK-023) |
| PL-16 | A complete eMDR is checked before approval | The check passes and approval is offered | B6b | NOT RUN | REQ-ARD-002; draft for owner review; tests to tag: tests/test_fda_3500a_emdr.py |
| PL-17 | Negative: an outbox event of organisation A is processed while organisation B has pending events; an event whose payload names organisation B is on A's row | The job reads and writes only A's rows; B's rows are neither read nor changed; B's e-mail is not sent for A; the event whose payload names another organisation is dead-lettered at once (PAYLOAD_TENANT_MISMATCH) and never handled | B6b | NOT RUN | REQ-TEN-002; negative; draft for owner review; tests to tag: tests/test_outbox_payload_tenant.py, tests/test_scheduled_job_scope.py (one test per scheduled job; RSK-026, DEV-0.11.04-002) |
| PL-18 | Export an organisation | Every record, version and file is in the export with a SHA-256 per entry and the verified audit head; counts match the manifest | B6b | NOT RUN | REQ-EXP-001; draft for owner review; tests to tag: tests/test_day25_retention_export.py |
| PL-19 | Negative: one file in an export is changed after the export | Its SHA-256 no longer matches the manifest; the manifest check reports it | B6b | NOT RUN | REQ-EXP-001; negative; draft for owner review; tests to tag: test to name (MDX-VAL-002 RSK-035) |
| PL-20 | Negative: a cell starting with =, +, - or @ is exported to CSV | Written as text, never as a formula; other values unchanged | B6b | NOT RUN | REQ-EXP-002; negative; draft for owner review; tests to tag: tests/test_csv_safe.py |
| PL-21 | The requester downloads an export before it expires | The file is streamed behind sign-in | B6b | NOT RUN | REQ-EXP-003; draft for owner review; tests to tag: tests/test_tenant_data.py |
| PL-22 | Negative: the export link is used after its expiry | Refused (410 EXPORT_EXPIRED) before and after the hourly job deletes the export; the refusal is audited | B6b | NOT RUN | REQ-EXP-003; negative; draft for owner review; tests to tag: tests/test_tenant_data.py::test_an_export_past_its_download_period_is_refused_before_the_hourly_job_deletes_it, tests/test_tenant_data.py::test_exports_are_deleted_after_their_download_period |
| PL-23 | Negative: another person of the same organisation uses the requester's export link | Refused (403 EXPORT_NOT_REQUESTER); the refusal is audited | B6b | NOT RUN | REQ-EXP-003; negative; draft for owner review; tests to tag: tests/test_tenant_data.py::test_only_the_person_who_asked_downloads_an_export_and_a_refusal_is_audited (threat model PT-13) |
| PL-24 | Restore the latest backup into an empty database | The restore completes; the audit chain of every organisation verifies | B6b | NOT RUN | REQ-BAK-001; draft for owner review; tests to tag: tests/test_backup_retention.py; restore drill |
| PL-25 | Negative: a person erased after the backup was taken; the backup is restored | The erasures are re-applied; the erased personal data does not come back | B6b | NOT RUN | REQ-BAK-001; negative; draft for owner review; tests to tag: restore drill step (`reapply_erasures`, backend/app/tenant_purge.py) |
| PL-26 | Negative: the newest production backup is 27 hours old | The backup-age check raises an alert | B6b | NOT RUN | future: a tagged test of the backup-age alert (the check exists and alerts at 26 h or more; no test found); not verification until built; REQ-BAK-002; negative; draft for owner review; tests to tag: tests/test_backup_retention.py, tests/test_infra_backup_role.py |
| PL-27 | The newest production backup is 2 hours old | No alert | B6b | NOT RUN | REQ-BAK-002; draft for owner review; tests to tag: tests/test_backup_retention.py |
| PL-28 | Quarterly drill: restore the latest backup with the key kept off the server into an empty database | Restored; recovery record written | B6b | NOT RUN | REQ-BAK-003; draft for owner review; tests to tag: quarterly drill record (no automated test) |
| PL-29 | Negative: the drill is run with a wrong or missing key | Decryption fails; the drill is recorded as FAIL with a deviation, never as a pass | B6b | NOT RUN | REQ-BAK-003; negative; draft for owner review; tests to tag: quarterly drill record (no automated test) |
| PL-30 | Negative: an MDARIX platform administrator without a customer grant tries to change a Case | Refused; the refusal is audited | B6b | NOT RUN | REQ-SEC-001; negative; draft for owner review; tests to tag: tests/test_support_access_customer_approval.py |
| PL-31 | Negative: a support grant whose requester, approver and recipient are not three different people | Refused | B6b | NOT RUN | REQ-SEC-001; negative; draft for owner review; tests to tag: tests/test_support_access_sod.py |
| PL-32 | Negative: a deactivated account's open session tries an action on a record | Refused (401); nothing changes | B6b | NOT RUN | REQ-SEC-002; negative; draft for owner review; tests to tag: tests/test_auth_session_lifecycle.py |
| PL-33 | Negative: a request with an expired session | Refused (401); the user signs in again | B6b | NOT RUN | REQ-SEC-002; negative; draft for owner review; tests to tag: tests/test_auth_session_lifecycle.py, tests/test_session_permissions.py |
| PL-34 | Negative: a deadline that falls across a daylight-saving change is shown on the Case, the daily deadline list, an export and a reminder | The same date and time on every surface; none is shifted by one hour | B6b | NOT RUN | REQ-CLK-002; negative; draft for owner review; tests to tag: tests/test_one_deadline_api.py |
| PL-35 | Negative: a second record with a later awareness is linked to a Case | The earlier awareness stays; the later one never replaces it | B6b | NOT RUN | REQ-AWR-001; negative; draft for owner review; tests to tag: tests/test_intake_rules.py |
| PL-36 | Negative: a Case is saved without an awareness date | It is never shown without a deadline: the provisional clock is on the deadline list with the clarification task | B6b | NOT RUN | REQ-AWR-002; negative; draft for owner review; tests to tag: tests/test_intake_rules.py |
| PL-37 | Negative: outside a trial, the person who entered a later awareness also approves it | Refused; a second person is needed | B6b | NOT RUN | REQ-AWR-003; negative; draft for owner review; tests to tag: tests/test_intake_triage_api.py |
| PL-38 | Negative: a death is reported only in the description, with the structured death field left empty | The Case is still put on the fast track | B6b | NOT RUN | REQ-TRG-001; negative; draft for owner review; tests to tag: tests/test_intake_triage_api.py, tests/test_signals_triage.py |
| PL-39 | Negative: new information raises the severity of a Case already triaged as not urgent | Triage reopens with an alert; it does not stay closed | B6b | NOT RUN | REQ-TRG-002; negative; draft for owner review; tests to tag: tests/test_intake_triage_api.py |
| PL-40 | Negative: an override tries to set "Service only" on a complaint that reports an injury | Refused; the outcome stays a complaint | B6b | NOT RUN | REQ-CLS-001; negative; draft for owner review; tests to tag: tests/test_intake_rules.py |
| PL-41 | Negative: a service record is raised to a complaint some days later | The complaint keeps the original awareness; it is not reset to the day of the change | B6b | NOT RUN | REQ-CLS-005; negative; draft for owner review; tests to tag: tests/test_intake_rules.py |
| PL-42 | Negative: one field of a signed record version is changed in a test database | Verification fails; the signature is shown as not valid for that content | B6b | NOT RUN | REQ-SIG-002; negative; draft for owner review; tests to tag: tests/test_human_decision_unit.py |
| PL-43 | Negative: a 3500A field has no value in the approved snapshot | The field stays empty and is listed as not placed; no value is guessed | B6b | NOT RUN | REQ-ARD-001; negative; draft for owner review; tests to tag: tests/test_fda_3500a_emdr.py |
| PL-44 | Negative: an imported row with an impossible date | The row goes to quarantine with its reason; no Case is created from it | B6b | NOT RUN | REQ-IMP-001; negative; draft for owner review; tests to tag: tests/test_import_quarantine_unit.py |
| PL-45 | Negative: a quarantined imported row reports a death | It still reaches triage while quarantined | B6b | NOT RUN | REQ-IMP-003; negative; draft for owner review; tests to tag: tests/test_import_quarantine_unit.py |
| PL-46 | Negative: the approver account may not approve rule content | The register refuses to load and names the file | B6b | NOT RUN | REQ-SOD-003; negative; split from PL-07 (one condition per scenario), draft for owner review; tests to tag: tests/test_rule_register_unit.py |
| PL-47 | A quality approver signs a conclusion; the screen and the PDF are opened | Both show the signer's printed name, the date and time of signing (UTC and the organisation's zone) and the meaning of the signature | B6b | NOT RUN | REQ-P11-001; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026); the signature row stores the user ID and role, not a printed name (`backend/app/db/models/foundation.py:1051-1053`): to verify on every display and print (MDX-VAL-013 question 5) |
| PL-48 | Negative: a signing request with an empty meaning | Refused; nothing is signed | B6b | NOT RUN | REQ-P11-001; negative; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026) |
| PL-49 | Two users are created in one organisation | Each has its own sign-in identifier; every signature names exactly one of them | B6b | NOT RUN | REQ-P11-002; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026); tests to tag: tests/test_customer_admin_account_security.py |
| PL-50 | Negative: a new user is created with the identifier of an existing or deactivated user | Refused; the identifier is never reused or reassigned | B6b | NOT RUN | REQ-P11-002; negative; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026) |
| PL-51 | A user enters the password or the authenticator code wrongly five times | The account is locked for 15 minutes; each failure and the lock are in the audit trail | B6b | NOT RUN | REQ-P11-003; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026); tests to tag: tests/test_auth_hardening.py, tests/test_auth_limits.py |
| PL-52 | Negative: the right password and code are entered during the lock | Refused until the lock ends; the attempt is audited | B6b | NOT RUN | REQ-P11-003; negative; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026) |
| PL-53 | An administrator resets a user's authenticator after the user reports the phone lost | The old authenticator stops working at once; the reset is audited | B6b | NOT RUN | REQ-P11-004; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026); tests to tag: tests/test_customer_admin_account_security.py |
| PL-54 | Negative: a code from the old authenticator is used to sign after the reset | Refused; nothing is signed | B6b | NOT RUN | REQ-P11-004; negative; draft for owner review (21 CFR Part 11 requirements, 12 Nov 2026) |
| PL-55 | Negative: a signed conclusion whose recorded facts do not change (or change in a way no input of the signed conclusion uses) is opened | No "Facts changed after signing: re-check" flag; the signed record is unchanged | B6b | NOT RUN | REQ-RPT-009, REQ-RPT-008; negative; draft for owner review (REQ-RPT-004 split, 13 Nov 2026); tests to tag: tests/test_b6a_change_reason.py::test_a_signed_conclusion_is_flagged_never_rewritten_when_its_facts_change |
| PL-56 | Negative: a later rule version is approved after a conclusion was signed under the earlier one | The signed conclusion still names the earlier version; its due date and fingerprint are unchanged; the current version is shown for comparison only | B6b | NOT RUN | REQ-RPT-004; negative; draft for owner review (REQ-RPT-004 split, 13 Nov 2026); tests to tag: tests/test_b4_effective_dating.py::test_a_signed_conclusion_never_changes_when_a_new_floor_version_arrives |
