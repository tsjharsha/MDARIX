# Authority reports for five markets: initial and follow-up reports

**Spec for owner approval.** Prepared 6 Nov 2026. This is research and design only; no code was changed.

**Workbook:** `authority-forms-mapping.xlsx` (in this folder). It has one sheet per market and a Counts sheet. Every row maps an MDARIX data field to the form block, the XML path, the mandatory rule, the code list, the MDARIX source and today's status.

**Baseline:** MDARIX v0.10.91.

---

## 1. Summary

| Market | Form and version | Report types | Next report | Output |
|---|---|---|---|---|
| **US** | Form FDA 3500A, eMDR HL7 ICSR R2 (package ChangeLog last entry 1 Aug 2024; paper form 09/2025) | Manufacturer, importer and user facility; each initial or follow-up (supplemental) | Follow-up #n, within 30 calendar days of receiving new information (21 CFR 803.56) | HL7 XML (eMDR), plus a PDF in the eSubmitter 3500A layout |
| **EU** | MIR 7.3.1 (form SB-11154; XSD SB-11252, 10 Jun 2026); mandatory since 1 May 2026 | Initial; Follow up; Combined initial and final; Final (Reportable incident); Final (Non-reportable incident) | Auto-created after an Initial or Follow-up is submitted; none after a Final or Combined report | MIR XML (one XSD per type) plus a PDF |
| **GB** | GB MIR 7.2.1 (MHRA schema, May/Jun 2025), submitted in MORE | Same five types | Same rule as EU; MHRA requires a final report unless the report was Combined | **MHRA does not accept PDF.** Proposal: GB XML for MORE upload, plus a PDF record copy |
| **Canada** | Mandatory Medical Device Problem Reporting Form for Industry, HC Pub. 110180 (April 2018) | Preliminary; Update; Final; Preliminary & Final | Final due on the date the preliminary report promised (s.60(2)(h), s.61); updates as needed | Official fillable PDF, filled; sent by e-mail. No XML exists |
| **India** | MvPI Medical Device Adverse Event Reporting Form, Version 1.2 | Initial; Follow up; Final; Trend | No statutory follow-up clock found; follow-up and final on demand | Official form PDF plus an ADRMS entry sheet. No XML route found |

Mandatory fields, counted for the main report type (workbook, Counts sheet):

| Market (main report type) | Mandatory | Held | Derivable | Ask at the step | Status today: exists / partly / missing |
|---|---|---|---|---|---|
| US manufacturer initial (fields eMDR rejects) | 12 | 10 | 2 | 0 | 11 / 1 / 0 |
| US importer initial | 9 | 7 | 2 | 0 | 6 / 1 / 2 |
| US user facility initial | 4 | 2 | 2 | 0 (one user-facility profile, set once) | 1 / 1 / 2 |
| EU Initial | 28 rows + 2 file attributes | 16 | 11 (+2 attributes) | 1 | 13 / 14 / 1 |
| GB Initial | 30 rows + 2 file attributes | 19 | 10 (+2) | 1 | 16 / 14 / 0 |
| Canada Preliminary | 27 | 11 (+1 partly asked) | 10 | 5 | 12 / 9 / 6 |
| India Initial (ADRMS-marked) | 16 | 8 (+1 partly asked) | 7 | 0 | 10 / 6 / 0 |

Notes on the counts:
- "Held" means a table and column holds the value today.
- "Derivable" means MDARIX can compute the value from held data, for example the report number, the report type, the awareness date or the classification.
- "Ask" means a person enters the value once, on the report's one completion screen.
- The US H6 codes count as held: they come from the tenant's approved IMDRF mappings, and today each needs a person's Confirm. Where no mapping exists, the person picks the code at the step.
- **EU and GB have many more fields that become mandatory on Final and Combined reports.** Section 4 lists them: root cause, risk assessment, Annex B/C/D/G codes and similar-incident counts. Most of those must be asked for or come from the investigation.

---

## 2. Principles that apply to every market

1. **Never guess.** Each value is held, derived from held data by a stated rule, or asked for. A blank stays blank. Unknown is never No.
2. **One completion screen.** Every value that must be asked for appears on one screen: "Finish the report". It is grouped as "This event", "Your product (enter once)" and "Your organization (enter once)". Values entered once are reused on every later report.
3. **Files are ready at approval.** Approving the report generates both the PDF and the XML, freezes them with the snapshot, and shows them for download. There is no separate "Generate" click.
4. **One source for both files.** The XML is built first. The PDF is rendered from the same values, so the two files cannot disagree.
5. **The mapping sheet is the rule book.** Each market's mandatory and conditional rules are exported from the workbook into the repository as a CSV. The code reads that file, and a test checks that every Mandatory row is enforced.
6. **MDARIX never submits.** The customer submits through the authority's route and records the submission. That stays as it is.
7. **A report chain, not one report.** Each event has an initial report and numbered follow-ups (and a final, where the market has one), linked to the initial report and sharing its report number.

---

## 3. United States: eMDR (Form FDA 3500A)

### 3.1 Form, version and sources

**The XML specification** is FDA's eMDR Implementation Package. MDARIX uses the local copy the owner supplied. It contains:
- `HL7Medwatch.xlsx`, whose ChangeLog was last updated 1 Aug 2024;
- the eight MDR examples, as XML and PDF pairs;
- the XSDs (`Con170227.xsd`) and the Ack3 examples.

The required version code is `V3NORMED_2016` (ICSR R2).

**The PDF model** is "FDA eSubmitter Generated Form 3500A". It has three pages:
- a header with Mfr Report #, UF/Importer Report #, Form Code and Exemption Number;
- sections A to H;
- File Attachments.

**The official paper form** is Form FDA 3500A (09/2025), OMB 0910-0291, which expires 30 Sep 2027. Its numbering differs from the eMDR package:

| Item | 09/2025 paper form | eMDR package and eSubmitter layout |
|---|---|---|
| Procode and common name | D2a Procode, D2b Common name | D2A Common name, D2B Procode |
| Section F | F8 Approximate age … F13 Manufacturer | F8 Date of report … F14 Manufacturer |
| Sex and race | A3 Sex only; one combined A5 "Race and/or Ethnicity" | A3a Sex, A3b Gender, A5 Ethnicity, A6 Race |

**The mapping follows the package.** It is what eMDR validates.

**Regulations** (eCFR text read through law.cornell.edu on 6 Nov 2026; ecfr.gov refused the automated fetch):

| Section | Rule |
|---|---|
| 803.12(a) | Manufacturers and importers must send initial and supplemental reports electronically. |
| 803.12(b) | User facilities may file on paper Form 3500A. |
| 803.50 | Manufacturers report within 30 calendar days of becoming aware. |
| 803.53 | 5 work days when remedial action is needed to prevent an unreasonable risk of substantial harm, or after FDA asks in writing. |
| 803.56 | Supplemental reports go in within 30 calendar days of receiving the new information. They must be marked as supplemental or follow-up, cross-reference the original report number (and the UF or importer report number it was based on), and contain only new, changed or corrected information. |
| 803.40 | Importers report within 30 calendar days. Death or serious injury goes to FDA with a copy to the manufacturer; a malfunction goes to the manufacturer only. |
| 803.30 | User facilities report within 10 work days. A death goes to FDA and to the manufacturer; a serious injury goes to the manufacturer, or to FDA if the manufacturer is unknown. |
| 803.33 | User facilities send an annual report on Form FDA 3419 by 1 January. Out of scope here. |

### 3.2 Report types and what triggers the next report

| Report | Who | Trigger | Clock | Key blocks |
|---|---|---|---|---|
| Manufacturer initial | Manufacturer | Signed REPORTABLE US conclusion | 30 calendar days, or 5 work days | G6 = 30-day or 5-day + Initial; G8 report number; H1; H6 |
| Manufacturer follow-up #n | Manufacturer | New or corrected information after submission (see below) | 30 calendar days from receipt of the information | G8 = same number; G6 = Follow-up #n; H2 types; changed values only |
| Importer initial | Importer | Importer's own REPORTABLE conclusion | 30 calendar days | F1 = Importer; F2 importer report number; F7 = Initial; F10 codes |
| Importer follow-up #n | Importer | New information | (803.56 applies to manufacturers; the importer's follow-up clock is **to confirm**) | F2 = same; F7 = Follow-up #n |
| User facility initial | User facility | Death or serious injury | 10 work days | F1 = User Facility; F2 user facility number; F4 e-mail |
| User facility follow-up #n | User facility | New information | to confirm | F7 = Follow-up #n |

**Follow-up rules from FDA's package:**
- **Same number.** A follow-up uses the same report number (G8, or F2 for importers and user facilities).
- **Sequential.** Follow-up numbers start at 1 and go up by one. eMDR rejects a follow-up when the initial report or an earlier follow-up has not arrived (Ack3 examples "MISSING_INITIAL_REPORT" and "MISSING_OUTOFORDER_SUPPLEMENTS").
- **How FDA merges values.** A single value in a follow-up overwrites the earlier one. Codes and narratives are appended, so narrative should not be repeated. A blank value does not clear a field.
- **Report numbers:**
  - Manufacturer and importer: 7-digit CFN or 10-digit FEI, then yyyy, then a 5-digit sequence that resets each year.
  - User facility: 10-digit HCFA number, then yyyy, then a 4-digit sequence.
  - F2 and G8 are never used together.
  - Test reports use sequence numbers that start with 7.
- **H2 follow-up types** are Correction, Additional information, Response to FDA request and Device evaluation. They are tick boxes, and more than one may be ticked. FDA's example ticks Correction and Additional information.

**Proposed MDARIX triggers for a follow-up.** MDARIX suggests a follow-up, and the user creates it in one click. There is no auto-create, as the owner asked. MDARIX suggests one when any of these happens:
- a value in the approved snapshot changes in the source data (H2 suggestion: Correction);
- a new value appears for a block that was blank (Additional information);
- the device evaluation finishes, or the H3 or H6 investigation codes change (Device evaluation);
- an FDA request is recorded (Response to FDA request; this replaces today's separate RESPONSE obligation for the US);
- the signed conclusion changes after submission (today this is only a warning).

The suggestion shows what changed. It proposes the 30-day due date from "Date you received this information", which is prefilled with the date of the change and can be edited.

### 3.3 Mandatory fields

FDA's own list ("Required 3500A fields", HL7Medwatch.xlsx, Instructions sheet). eMDR rejects a report without these:

| Report | Required fields |
|---|---|
| Manufacturer initial | B5; D2 Procode; G1 contact e-mail; G8; H1; H6 × 7 (clinical, impact, device problem, component, type of investigation, findings, conclusions) |
| Manufacturer follow-up | G6 (+ follow-up number); G8 |
| Importer initial | B5; D2 Procode; F1; F2; F4 e-mail; F10 × 4 (clinical, impact, device problem, component) |
| Importer follow-up | F1; F2; F7 (+ follow-up number) |
| User facility initial | B5; F1; F2; F4 e-mail |
| User facility follow-up | F1; F2; F7 (+ follow-up number) |

**Conditional rules** (all in the workbook):
- age needs its unit, and weight needs its unit;
- D7b is needed when D7a is Yes;
- D9 needs the return date when the device was returned;
- F11 and F13 need their dates when Yes;
- "Other" choices need their text (D5, F12, G2, H7);
- the H1 count of events is needed only for summary reports;
- H9 is needed when a correction or removal was reported.

**Required if known.** Everything else that the regulation asks for when "reasonably known" is marked "Required if known" (21 CFR 803.30 for user facilities; 803.42 and 803.52 for importers and manufacturers by reference). eMDR does not reject these when blank. MDARIX shows them as "known? enter it", never as blockers.

**MDARIX's own rule (proposed):** a manufacturer follow-up must tick at least one H2 box. 803.56 requires the report to say it is supplemental, and H2 is how FDA's form says what kind.

### 3.4 Output formats

- **XML.**
  - Format: HL7 ICSR `PORR_IN040001UV01`, validated against `Con170227.xsd`.
  - One report per file; the batch ID is CFN/FEI + timestamp.
  - Characters are limited to Windows-1252.
  - Attachments go in as Base64, with filenames up to 200 characters each and 2,000 in total.
- **PDF.**
  - **Layout:** a three-page render in the eSubmitter 3500A layout, made from the XML values.
  - **Header:** Mfr Report # / UF/Importer Report # / Form Code / Exemption Number.
  - **Body:** sections A to H as in "Manufacturer Initial - Typical", then "File Attachments".
  - **Record page:** MDARIX's record page (preparers, approval, checksum) follows as a separate page.
  - **Title:** see decision D1. MDARIX must not print "FDA eSubmitter Generated".
- **Official 09/2025 fillable form.** Keep today's fill (0.10.89) as a second PDF for user facilities that file on paper (803.12(b)). See decision D2.

### 3.5 How MDARIX gets each value

The workbook's US sheet lists all 218 rows. The main points:

**Held today:**
- B5 description; B3 event date; D1 brand; D2 procode; D4 model, lot, expiry and serial; D5 operator; H5 single use;
- G1 contact (organisation, e-mail, phone); G4 510(k)/PMA;
- the IMDRF/FDA codes for H6 and F10; the awareness date for G3 and F6.

**Derived (proposed):**
- **Report numbers.** G8 and F2 come from a new organization setting, "FDA registration number (CFN or FEI)" per US responsible party, or the HCFA number for a user facility, plus a yearly sequence.
- **G6 and F7.** They come from the report kind and the clock.
- **Follow-up number.** It comes from the report chain.
- **B4.** It is the date of approval, editable until submission.
- **G2 Report source.** It is derived from the reporter type, and is "Foreign" when the incident country is not the US.
- **H1.** It comes from the signed answers.
- **F11 and F13.** Their Yes and date come from the recipients each rule requires.
- **H10.** It lists the other reports on the same complaint.
- **The full UDI.** It is built from the DI plus lot, expiry and serial (GS1 human-readable form).

**Asked at the step (event):**
- B2 date of death;
- D6a and D6b (implants only);
- D7a, D8 and E4, each Yes/No/Unknown;
- D9 return date;
- F12 location;
- H2 types (on follow-ups);
- H3 Yes/No, prefilled from the investigation;
- H7 remedial types, prefilled from the CAPA action types;
- H8 usage;
- H9 correction/removal number.

**Asked once and reused:**
- **Per product:** catalog number, combination product (Yes/No), UDI issuing entity.
- **Per lot:** manufacture date (H4).
- **Per organization:** CFN/FEI, user-facility profile, fax.
- **For the responsible parties:** address split into street, city, state, postcode and country, and contact first and last name. FDA wants these as separate parts.

**Personal data (A1–A6, B6, B7, D10, E1, E3).** Today MDARIX never stores these, by design. FDA does not require them. See decision D3.

### 3.6 Click path (fewest clicks)

| Step | Today (v0.10.91) | Proposed |
|---|---|---|
| Create the report | 0 clicks: created when the US conclusion is signed | Same. The report number is assigned and everything held or derived is prefilled |
| Fill gaps | Type the Mfr report #; type B4; 4–7 separate code "Confirm" clicks; once-facts | One screen, "Finish the report", with only the asked fields. **"Confirm all codes"**: one click over the visible list of suggested codes, each still changeable. No report number or B4 to type |
| Ask for approval | "Send for approval" | Same. MDARIX also builds a draft XML, runs the XSD and mapping-sheet checks, and shows a draft PDF marked DRAFT |
| Approve | Second person, password + MFA | Same. **On approval the PDF and XML are generated and frozen** |
| Files | "Generate the PDF" + "Download the eMDR XML" (2 clicks) | "Download PDF" / "Download XML", ready at once |
| Follow-up | Not possible (only a "follow-up due" flag) | "Create follow-up #n" (1 click): prefilled, shows only what changed, suggests the H2 types → Send for approval → Approve → files ready |

**The fewest possible clicks** for a complete report, from "reportable" to both files ready, is 3:
1. Confirm all codes.
2. Send for approval.
3. Approve.

### 3.7 What changes from today

| Area | Today (v0.10.91) | Change |
|---|---|---|
| Report kinds | `report_obligations.kind` is INITIAL or RESPONSE; one INITIAL per complaint and market; no follow-up number | Add FOLLOW_UP and FINAL; reuse `parent_id` to point to the initial report; add `sequence` (0 = initial), unique per chain |
| H2 | NOT_USED | Ask at step on follow-ups |
| G6 | Always "Initial"; no follow-up choice | Follow-up + number |
| Section F | Empty; no importer or user-facility reports | Built, if decision D4 says so |
| Report number | Typed; only its format is checked | Generated from CFN/FEI or HCFA + yearly sequence; settable starting sequence |
| Official 3500A PDF | Filled since 0.10.89 | Kept for paper filing; the eSubmitter-layout PDF becomes the default |
| XML checks | Missing-field blocking in `emdr.py` (hand-coded) | Driven by the mapping sheet's CSV; per report type (M-I, M-F, I-I, I-F, U-I, U-F) |
| Files | Generated on click after approval | Generated at approval; draft previews before it |
| Follow-up endpoint | `POST /follow-up` only sets FOLLOW_UP_DUE | Creates the follow-up obligation, with clock = 30 days from information receipt |
| RESPONSE (US) | A separate worksheet | A follow-up with H2 = Response to FDA request |

---

## 4. European Union: Manufacturer Incident Report (MIR) 7.3.1

### 4.1 Form, version and sources

**Form:** MIR v7.3.1. The Commission's page says "New MIR form – mandatory as from 1st May 2026" (PMSV reporting forms page, updated 7 May 2026).

- **PDF form build:** SB-11154, dated 06-05-2026. It is an XFA, password-protected form; saving, signing and XML import or export need Adobe Acrobat Professional.
- **Builds still accepted:** SB-10781, SB-11010 and SB-11154.
- **XSDs:** build SB-11252, 10 Jun 2026. There is one XSD per report type, plus a "PDFgeneric" XSD. The root element is `<incident>`, with no namespace.
- **Changelog:** the latest entry makes 4.3.3d `howWereDetermined` mandatory in Combined and Final (Reportable).
- **Re-checked 9 Nov 2026 (owner request):** the Commission's page still lists the PDF form SB-11154 ("update 7 May 2026"), the XSD/XSL package SB-11252, the help text and the changelog SB-11252 (10/06/2026). No newer build and no changelog entry after 10 Jun 2026. The page: "All MIR 7.3.1. versions from the December 2025 publication are acceptable (until further notice if necessary)"; versions before SB-10781 "can no longer be used". The SB-11252 change (4.3.3d `howWereDetermined` minOccurs 0 → 1 in `incident-InitialFinal-v7.3.1.xsd` and `incident-FinalRep-v7.3.1.xsd`) is already in the workbook (Mandatory: C, FR). Files: [PDF](https://health.ec.europa.eu/document/download/e8ce9f53-82cb-44c8-a06e-91ad71c16b01_en?filename=md_new-reg_mir-form-v7.3.1_en.pdf), [XSD/XSL zip](https://health.ec.europa.eu/document/download/12d3a3db-b089-482d-b0d1-44e7cd2324da_en?filename=md_new-reg_mir-xsd-xsl-v7.3.1_en.zip), [help text](https://health.ec.europa.eu/document/download/dc6acc1b-f1ae-4512-b838-2fae869124c3_en?filename=md_new-reg_mir-help-v7.3.1_en.pdf), [changelog](https://health.ec.europa.eu/document/download/6d4a14de-c05f-4d50-975f-f20dfa0fa1c2_en?filename=md_new-reg_mir-changelog-v7.3.1_en.txt). The B8 build vendors these exact files into the repository and pins SB-11252; the release check (§ risks) compares the page before each B8+ release.
- **Help text:** v7.3.1, 35 pages. It gives the per-type mandatory table and the XML element map (chapter 5). It carries no date of its own (**to confirm**).
- **Official XSL files:** the package's XSL files show that the official PDF imports and exports this XML. A customer can therefore load MDARIX's XML into the official MIR PDF.
- **Timelines** (MDR Art 87):
  - 15 days for any serious incident (Art 87(3));
  - 2 days for a serious public health threat (Art 87(4));
  - 10 days for a death or unanticipated serious deterioration (Art 87(5)).

  Days are calendar days, counted from the day after awareness (MDCG 2023-3 Rev.2, Q14).
- **Final report:** required by Art 89(5), with no deadline in days.
- **EUDAMED:** the vigilance module is "in development". It becomes mandatory 6 months after a notice in the OJEU (MDCG 2023-3 Q21). One secondary source says not before 2028 (**to confirm**). Until then, reports go to the NCA of the country where the incident occurred, by e-mail or national portal, as PDF or XML.

### 4.2 Report types and follow-up rule

| Type (XML `reportType` value) | Available when | What follows (owner's rule) |
|---|---|---|
| `Initial` | First report, investigation not complete | **Auto-create a Follow-up draft on submission** |
| `Follow up` | Only after an Initial; more than one allowed | **Auto-create the next draft on submission** |
| `Combined initial and final` | First report only, if the investigation is complete within the initial deadline | Nothing |
| `Final (Reportable incident)` | Only after an Initial | Nothing automatic. Offer "Updated final report" (the help text allows one) |
| `Final (Non-reportable incident)` | Only after an Initial, once the root-cause analysis is complete | Nothing automatic |

**Proposed auto-follow-up behaviour:**
- **The draft.** The draft is a full copy of the last approved report, with type Follow up. The MIR is a complete report each time, unlike the US delta.
- **Due date.** The draft is due on the 1.2f "expected date of next report" given in the report just submitted.
- **Switching to a final.** The user can switch the draft's type to Final (Reportable incident) or Final (Non-reportable incident) with one choice. The mandatory set then changes to that type's XSD.
- **Linking.** Each report in the chain keeps the same 1.3.1b manufacturer reference. Follow-ups and finals carry 1.1c, the NCA reference, from the NCA's acknowledgement, or "Unknown" (help text).

### 4.3 Mandatory fields

The help text is authoritative. The workbook adds the XSD minOccurs for each type.

- **All types:**
  - 1.1a NCA; 1.2a submission date; 1.2b incident date; 1.2c awareness date; 1.2e type;
  - 1.3.1a submitter; 1.3.1b manufacturer reference;
  - 1.3.2 manufacturer name, SRN, contact, e-mail, phone, country, street, city, postcode;
  - 2.3a device name; risk class (2.4, one of a–d);
  - 3.1a description; 3.2a Annex A choice 1; 3.2c device location; 3.3a Annex E and F choice 1;
  - 3.4a initial reporter role; 3.4h country.
- **Initial and Follow-up only:** 1.2f next report date; 4.1a preliminary results.
- **All types except Final (Non-reportable incident):** 1.2d awareness of reportability (new in 7.3.x); 1.2g classification.
- **Follow-up only:** 4.1c initial actions; 4.1d further investigations.
- **Follow-up, Final (Reportable incident) and Final (Non-reportable incident):** 1.1c NCA reference.
- **Combined, Final (Reportable incident) and Final (Non-reportable incident):** 2.1a UDI-DI; 2.1b UDI-PI; 2.1c Basic UDI-DI; 2.3p NB numbers (by risk class).
- **Every type except Initial:** 2.3b device description.
- **Combined and Final (Reportable incident) only:**
  - 2.5 market distribution;
  - 4.2a root cause; 4.2c root cause confirmed; 4.2d risk assessment reviewed;
  - 4.2e Annex B, C and D codes; 4.2f Annex G codes;
  - 4.2g corrective action ("n/a" allowed); 4.2i final comments;
  - 4.3 similar incidents and devices on the market, for periods N to N-3, in the country, the EEA plus CH and TR, and the world, with the method.
- **Final (Non-reportable incident):** 4.2b rationale is the only mandatory field in section 4.
- **Conditional:**
  - 1.3.3 authorised representative, when the manufacturer is outside the EU/EEA, Turkey or Northern Ireland;
  - 1.3.4 submitter details, when the submitter is "Other";
  - 2.2b, when 2.2a is filled;
  - 2.4e, for a legacy class;
  - 2.4f and 4.1b, for medicinal substances.

### 4.4 Output formats

- **XML.** Each report type validates against its own XSD and carries `xsi:noNamespaceSchemaLocation`, as the official export XSL does. The root attributes `sCreateTimeStamp` and `sFormLanguage` are required.
- **PDF.** The official PDF is XFA and password-protected, so MDARIX cannot fill it the way it fills the US form. Proposal:
  1. MDARIX renders its own PDF in MIR section order (1 to 5) with the official labels, from the XML;
  2. the help text tells the customer the XML can be imported into the official MIR PDF (Acrobat Pro) if the NCA wants the official PDF.

  See decision D10.

### 4.5 How MDARIX gets each value; what changes

**Held:**
- the manufacturer and AR details, SRN, brand, EMDN, Basic UDI-DI and UDI-DI;
- the NB number and certificate, and the MDR risk class (product_registrations, CE);
- model, serial, lot, expiry and software version;
- description, the Annex A/E/F/G/B/C/D mappings and the country.

**Derived:**
- **NCA and report.** 1.1a NCA comes from the incident country (a new NCA reference list). 1.1c is the authority reference recorded on the initial report.
- **Dates.** 1.2a is the approval date. 1.2d is the date the EU conclusion was signed REPORTABLE (see decision D13).
- **Type and classification.** 1.2e comes from the report kind. 1.2g comes from the EU clock: the 2-day clock gives "Serious public health threat"; the 10-day clock gives "Death" or "Unanticipated serious deterioration in state of health", depending on whether death is recorded; the 15-day clock gives "All other reportable incidents".
- **References.** 1.3.1b is the complaint business ID.
- **Device location and distribution.** 3.2c is "Manufacturer" when the device was returned. 2.5 comes from the markets where the product has a registration.
- **Investigation and actions.** 4.1a, 4.1c, 4.1d and 4.2g come from the investigation and CAPA records, and stay editable. 4.2b comes from the rationale of a signed NOT_REPORTABLE conclusion.

**Asked at the step:**
- 1.2f next report date;
- 4.2a root cause; 4.2c; 4.2d; 4.2i;
- 4.3.3a/b and the 4.3.3c denominators;
- FSCA, PSR and PMCF references when they apply.

**Asked once per product:** catalogue number, UDI issuing entity, the 2.4 device-type flags, 2.4e/f and 4.3.3b basis.

**The responsible-party address and contact name must be split into parts.**

**Changes from today:**

| Area | Today | Change |
|---|---|---|
| Output | Worksheet PDF only; no XML | MIR XML for each type, validated against its own XSD; MIR-layout PDF |
| Report type | Chosen in 1.2e on the single obligation | Each type is its own report in the chain |
| Follow-ups | Never auto-created | Created on submission, per the rule above |
| Reference fields | 1.1c and 1.3.1b typed | Derived and carried forward |
| New fields | 1.2d (new in 7.3.x) and the 4.3 counts have no source | Sources as above |

---

## 5. Great Britain: GB MIR (MHRA)

### 5.1 Form, route and sources

- **Law.** The UK MDR 2002 Part 4A, as amended by SI 2024/1368, in force 16 June 2025.
- **Route.** MHRA's "Vigilance reporting requirements" page (updated 5 Sep 2025) says serious incidents, trends and FSCAs must go through **MORE**. "The MHRA will not accept any reports received via any other routes including email." The exception is FSCAs outside GB, which go to aic@mhra.gov.uk.
- **Form.** It is the **GB MIR schema 7.2.1**, which is based on EU MIR 7.2.1, not 7.3.1. Source: GB MIR and FSCA schema implementation guide, Version 1, May 2025.
- **Submission formats.** That guide says the PDF has not been a submission route since 2022. Reports go in through MORE web forms, XML upload or API.
- **Northern Ireland.** Incidents occurring in Northern Ireland use the **EU form within MORE**. Which EU version MORE accepts is **to confirm**.
- **Timelines.** 2 calendar days for a serious public health threat; 10 for a death or unanticipated serious deterioration; 15 for other serious incidents (gov.uk guidance; legislation.gov.uk refused the automated fetch).
- **Final report.** A final report is required on completion of the investigation unless the report was combined initial and final. "There is no statutory timescale for provision of the final incident report… as soon as possible." Long investigations need interim follow-ups in MORE. MHRA questions must be answered within 3 UK working days.

### 5.2 Differences from the EU MIR (GB help text and XSDs)

- **Removed fields:** EUDAMED fields (`ncaEudamedNum`, `refNumEudamed`); 1.2d `mfrAwarenessReportDate`; the PMCF/PMPF question; height; unit-of-use and issuing-entity sub-fields.
- **Submitter:** "United Kingdom Responsible Person" added as a choice (`reporterUKRP`). The AR/UKRP block is marked Y for all report types.
- **Nomenclature:** GMDN only.
- **New fields:** `UKABIdNum`, `UKABCertNum` and `udiIssueEntity` (GS1, HIBCC, ICCBBA, IFA).
- **IMDRF codes:** Annex B, C, D and G codes are marked Y for **all** report types ("A minimum of one IMDRF code must be populated", with placeholder codes allowed). The June 2025 XSDs agree. The 7.2.1 changelog (31 Oct 2025) says "fix minOccurs=0": **a conflict, to confirm in MORE**.

### 5.3 Report types, follow-up rule and output

- **Report types and follow-up rule:** the same five types and the same auto-follow-up rule as the EU (section 4.2). MHRA explicitly requires the final.
- **Output.** The owner asked for "PDF only". MHRA does not accept PDF. Recommendation (decision D11):
  1. generate the **GB 7.2.1 XML** for upload into MORE, validated against the GB XSD for each type;
  2. generate a PDF copy as MDARIX's record.

  Without the XML, the customer re-keys every field into MORE's web form.

### 5.4 Changes from today

| Area | Today | Change |
|---|---|---|
| Output | Worksheet PDF | GB XML + PDF |
| Report chain | One report per market | The report chain, with follow-ups auto-created as for the EU |
| Annex B/C/D/G codes | Not required on an initial report | Required on an initial report (pending the conflict above) |
| Northern Ireland | Not separated from GB | A separate path using the EU form, routed to MORE |

---

## 6. Canada: mandatory medical device problem report

### 6.1 Form, rules and sources

- **Form.** "Mandatory Medical Device Problem Reporting Form for Industry", Canada Vigilance – Medical Device Problem Reporting Program. The PDF is HC Pub. 110180 (April 2018), 5 pages, fillable AcroForm with 94 fields; the field names are in the workbook. The canada.ca page says the HTML version "is not a form" and the PDF must be used.
- **Guidance.** "Incident reporting for medical devices: Guidance document" (2021; new provisions in effect 23 Jun 2021; the 2011 guidance is archived).
- **Regulations.** SOR/98-282 s.59–61.1 (current to 19 Oct 2026):
  - **Canadian incident.** A preliminary report is due within **10 days** of awareness for a death or serious deterioration (s.60(1)(a)(i)). It is due within **30 days** where a recurrence could cause one (s.60(1)(a)(ii)).
  - **Foreign incident.** Since 2021 this covers Class I only (s.59(1.1)). It is reportable only when the manufacturer told a foreign regulator it intends corrective action, or the regulator required action. It is due "as soon as possible", which the guidance reads as 48 hours. Class II–IV devices fall under the s.61.2 foreign risk notification (72 hours).
  - **Preliminary report contents** (s.60(2)(a)–(i)) include **a timetable, including the date of the final report**.
  - **Final report** (s.61). It is due on the reporter's own timetable; there is no fixed statutory deadline. It contains the number of persons affected, the cause and the actions taken.
  - **Importer reporting** (s.61.1). The importer may report on the manufacturer's behalf after written notice to the Minister.

### 6.2 Report types and follow-up rule

**Types (form A5):** Preliminary, Update, Final, Preliminary & Final.
- A combined Preliminary & Final report is allowed when the investigation is complete.
- A preliminary report fills all sections except E2 and E3.
- Updates and finals fill the * fields plus any field that changed.
- Health Canada's file number (from the acknowledgement letter) and the reporter's file number go on all of them.

**Proposed rule:**
- **When a Preliminary report is submitted,** MDARIX auto-creates the **Final** draft. It is due on the A5 "anticipated date for the final report" given in the preliminary report.
- **Updates** are created on demand ("Create update").
- **Nothing is created** after a Final or a Preliminary & Final report.

### 6.3 Mandatory fields, output, values

**Mandatory fields:**
- **On every report (*):** A2 contact; A3 reporter file no.; A4 HC file no. (once assigned); A5 type; A6 date submitted; B1 classification; C1 brand.
- **Preliminary:** everything except E2 and E3.
- **Finals:** E2 root cause and E3 corrective actions (or the rationale for no action).

**Output:**
- **PDF.** Fill the official AcroForm PDF directly with pypdf, as the US 3500A fill does.
- **Route.** Submission by e-mail to hc.mdpr-dimm.sc@canada.ca, with "MDPR" in the subject line (2021 guidance). The form and the older page give different addresses: **to confirm**.
- **No XML or portal** exists for device incidents.

**Values:**
- **Held:** contact; brand; lot and serial; expiry; class; licence no. (MDL registration); description; dates.
- **Derived:**
  - file numbers;
  - type;
  - B1 from the CA clock and the incident country;
  - A5 date of the previous report;
  - E1 from the investigation plan;
  - E3 from the CAPAs.
- **Asked:**
  - C6 age of device (or derived from the manufacture date);
  - C7 time in use;
  - C8 labelled sterile (once per product);
  - D2, D4 and D5 complainant name, address and contact, which are personal (decision D3);
  - E2 root cause.
- **Asked once per organization:**
  - A8 HC company ID;
  - A9 MDEL number;
  - the s.61.1 importer authorisation.

### 6.4 Changes from today

| Area | Today | Change |
|---|---|---|
| Output | Worksheet PDF (HC_MDPR, a starter form) | The official form, filled |
| Report chain | A5 chosen on one obligation | A chain: Preliminary → Final (auto); Update on demand |
| A5 dates | Neither held | Final due date asked; previous-report date derived |
| Organization facts | HC company ID and MDEL not held | Asked once per organization |

---

## 7. India: Materiovigilance Programme of India (MvPI)

### 7.1 Form, rules and sources

- **Form.** "Medical Device Adverse Event Reporting Form – Materiovigilance Program of India (MvPI)", **Version 1.2**. It is 4 pages, fillable, with 172 fields that have generic names. PDF metadata dates it Aug 2024; the release date is **to confirm**.
  - It is meant for manufacturers, importers, distributors and healthcare professionals.
  - Section F is for the manufacturer, authorised representative or licence holder only.
  - **The paper form marks no field as mandatory.**
- **Online route.** IPC's **ADRMS** portal marks these fields mandatory:
  - patient involved; report type; date of report;
  - serious case and its reasons;
  - reporter department, country and mobile; reported by; primary reporter;
  - device category; device name; device information;
  - event date; adverse event category; description; patient outcome.

  Sources: ADRMS User Manual for Stakeholders, Version 00, 18 Aug 2025, and the SOP of 3 Feb 2026.
- **ADRMS follow-ups.** Choose "follow-up", enter the original report number, and update the report.
- **Submission routes:**
  - e-mail to mvpi-ipc@gov.in (form v1.2 instructions);
  - post to IPC Ghaziabad;
  - ADRMS web entry.

  **No XML or E2B import for devices was found (to confirm).**
- **Law.** MDR 2017, consolidated text to GSR 777(E), 14 Oct 2022:
  - **Rule 26(ii), manufacturing licence holders.** Report any suspected unexpected serious adverse event and the action taken, including any recall, "within fifteen days".
  - **Rule 38, importers.** Report foreign regulatory actions within 15 days. An importer's SAE duty outside Rule 38 is **to confirm**.
  - **PSURs.** Due under Rule 65 and the Seventh Schedule for devices with no predicate.
- **CDSCO circular, 15 May 2024.** Licence holders "should also use the MvPI platform". This was read only in secondary sources: **to confirm**.

### 7.2 Report types and follow-up rule

**Types:** Initial, Follow up, Final, Trend. An initial report may also serve as the final one.

No statutory follow-up or final deadline was found. A 2018 CDSCO draft for IVDs only (follow-up within 30 days) is not final law.

**Proposed rule:**
- Do not auto-create a follow-up for India.
- After an Initial is submitted, show "Follow-up or final report pending" with buttons "Create follow-up" and "Create final".
- Keep an optional "next report date" chosen by the user, with no legal clock (decision D15).

### 7.3 Output, values, changes

**Output:**
1. **The official v1.2 form, filled.** The field names are generic (for example `checkbox_1jeo`), so the mapping is by position and is tested by rendering.
2. **An "ADRMS entry sheet".** It lists the values in ADRMS screen order, for fast copying, because ADRMS has no import.

**Values:**
- **Held:** licence no. (CDSCO registration); risk class A–D; brand; GMDN; UDI; model; lot; serial; event date; description.
- **Derived:**
  - type of event;
  - serious event and reasons (from the IN answers);
  - patient outcome (from death and serious injury; otherwise asked);
  - investigation;
  - CAPA.
- **Asked:**
  - the device category items not held;
  - section C patient details, which are optional and personal;
  - B13–14 frequency of similar events.

**Changes from today:**

| Area | Today | Change |
|---|---|---|
| Report type (P2) | Always "Initial" | Follow up and Final become real reports in the chain |
| Output | Worksheet PDF | Official form fill + ADRMS entry sheet |

---

## 8. Shared data changes

These are the smallest changes that serve all five markets. They are listed once and reused.

| Change | Where | Why |
|---|---|---|
| `kind`: add FOLLOW_UP, FINAL; reuse `parent_id` to point at the initial report; add `sequence` (unique per chain) | report_obligations | Report chain for all markets |
| Map the report kind and sequence to each market's own type value | forms.py, per market | G6/F7, `reportType`, A5, Type of Report |
| `info_received_on` on follow-ups | report_obligations | US 30-day supplemental clock |
| FDA CFN/FEI (manufacturer, importer), HCFA (user facility), next sequence per year | organization settings, per US responsible party | Report-number generator |
| Address in parts (street, city, state, postcode, country); contact first and last name | market_responsible_parties | FDA, MIR and MORE need the parts |
| `catalog_number`, `combination_product`, `udi_issuing_entity`, `labelled_sterile` | products | US, EU, GB, CA, IN |
| `manufactured_on` | lot_batches | H4, MIR 2.3i, CA C6, IN A16 |
| NCA reference list (country → NCA name, e-mail) | reference data | EU 1.1a and routing |
| Mapping-sheet CSV per market (exported from the workbook) | backend/app/authority_reports/rules/ | One rule book; test-enforced |

---

## 9. Phased build plan

Each phase is one release and one PR, as agreed. Targeted tests run while building. The full release gates (pytest, ruff, vitest, build) run before every deploy.

| Phase | Scope | Targeted tests |
|---|---|---|
| **1. Report chain and fewest clicks** (all markets) | Kinds FOLLOW_UP and FINAL, `parent_id` chain, `sequence`; report-number generator (CFN/FEI + year + sequence; settable start; test prefix 7); files generated at approval; draft preview (watermarked); "Finish the report" one screen; "Confirm all codes"; mapping-sheet CSV loader and per-type mandatory check | Chain: unique sequence, no gaps, follow-up n blocked until n-1 is submitted; number format and yearly reset; approval produces both files and the snapshot checksum covers them; the CSV rule test (every Mandatory row is enforced); click-count test on the Next step card |
| **2. US manufacturer follow-ups and eSubmitter-layout PDF** | PDF rendered from the XML in the eSubmitter layout; follow-up XML (G6 Follow-up + number, H2, changed values only, narrative appended); follow-up suggestions with the 30-day clock; FDA request → follow-up | Rebuild FDA's "Manufacturer Initial - Typical" and "Manufacturer Follow-up" from fixture data: XSD-valid, structure equal to FDA's XML; PDF text has the same blocks as FDA's example PDFs; delta test (unchanged values left out, narratives not repeated); H2 suggestion rules; 803.56 due-date test |
| **3. US importer and user facility** (if D4 = yes) | Section F; F2 numbers (FEI/CFN-yyyy-5 digits; HCFA-yyyy-4 digits); recipients per 803.30 / 803.40; F11 and F13 derived; user-facility paper route via the official 09/2025 form | Rebuild FDA's Importer Initial/Follow-up and User Facility Initial/Follow-up examples; F2 and G8 never both set; recipient routing table tests |
| **4. EU MIR XML and PDF, auto follow-up** | MIR 7.3.1 XML per type with schema location; MIR-layout PDF; auto-create on submission (not after Final or Combined); NCA list; 1.2d; 4.3 inputs | Each of the 5 types validates against its own XSD; minimal and maximal fixtures; auto-create rule table (5 types × submitted); 1.1c carried forward, "Unknown" fallback; mandatory set switches when the draft is retyped to Final |
| **5. GB MIR** (and the Northern Ireland path) | GB 7.2.1 XML (UKRP, GMDN, UKAB, issuing entity); PDF record copy; NI uses the EU form | Each of the 5 GB XSDs validates; EU-only elements are absent; NI routing test |
| **6. Canada and India** | Canada: official AcroForm fill; Preliminary → Final auto-create on the A5 date; updates. India: official v1.2 fill by position + ADRMS entry sheet; follow-up/final on demand | Rendered-page checks (PNG) for both forms; * fields required on updates and finals; E2/E3 required on finals; India: values land in the right boxes (position test) |

Recommended order: 1 → 2 → 4 → 5 → 6, with 3 when D4 is decided. Phases 1 and 2 give the owner's main asks: the eSubmitter-style PDF and US follow-ups.

---

## 10. Risks

| Risk | Effect | Mitigation |
|---|---|---|
| A PDF that looks like FDA's eSubmitter output is taken for an FDA-generated record | Misleading | Same layout, MDARIX's own title and record page (D1) |
| Paper form numbering (09/2025) differs from the eMDR package | Wrong block labels | Map to the package; note the paper numbers in the PDF legend and the workbook |
| EU MIR builds change often (three builds accepted; XSD updated Jun 2026) | Rejected files | Pin the build in forms.py; a release check compares against the Commission's page |
| GB lags at 7.2.1; Annex B–G rule conflicts; Northern Ireland version unclear | Rejected uploads | Confirm in MORE before phase 5; keep GB and NI as separate form variants |
| EUDAMED vigilance goes live (not before 2028, unconfirmed) | A new submission route (M2M) | Out of scope; the XML model stays reusable |
| Customers already have their own MDR sequence | Duplicate numbers (Ack3 duplicate errors) | Settable starting sequence; numbers never reused |
| Personal data (patient, reporter) if stored | Privacy duty (DPDP, GDPR, HIPAA where it applies) | D3: optional, report-only, never sent to AI |
| Auto-created follow-ups create clocks nobody asked for | Noise, false overdue | EU/GB: due date = 1.2f, chosen by the user; Canada: the A5 date; India: no auto-create |
| Similar-incident counts (EU 4.3) need denominators MDARIX does not hold | Final reports blocked | Ask per period in v1; later import distribution data |
| Health Canada and India contact routes disagree across official pages | Mis-sent reports | Mark "to confirm"; owner checks with the authorities |
| India form field names are generic | Values in the wrong box | Position-based map + rendered-page test |

---

## 11. Open decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | US PDF title. FDA's examples say "FDA eSubmitter Generated Form 3500A". | Same layout and blocks, titled "Form FDA 3500A – eMDR content, prepared by MDARIX". Never claim FDA generated it. |
| D2 | Keep the official 09/2025 fillable 3500A? | Yes, as a second PDF, mainly for user facilities filing on paper (803.12(b)). The eSubmitter-layout PDF is the default. |
| D3 | Personal data (US A1–A6, B6, B7, D10, E1, E3; EU 3.3b–f; Canada D2–D5; India C). Today never stored. | Allow optional entry at the step, stored only in that report's snapshot, never used by AI or analytics, with a tenant setting (default off). Canada's complainant fields are needed for a preliminary report, so the Canadian screen asks for them. |
| D4 | Build importer and user-facility reports? | Importer: yes, in phase 3 (tenants that import into the US). User facility: build with phase 3 but show it only for tenants marked as a user facility; low priority, as no current customer is one. |
| D5 | When the US report number is assigned | At "Send for approval", so the draft shows it. Never reused; a settable starting sequence per year. |
| D6 | Generate the files at approval, removing the "Generate the PDF" click | Yes. |
| D7 | Draft PDF and XML before approval | Yes. A PDF marked DRAFT plus the XSD and mandatory-check result; the downloadable XML only after approval. |
| D8 | "Confirm all codes" in one click | Yes, with every suggested code visible and changeable. It is still a person's confirmation, not a guess. |
| D9 | US follow-ups: manual with suggestions (not auto); an FDA request becomes a follow-up with H2 "Response to FDA request" | Yes to both. |
| D10 | EU PDF: the official MIR PDF cannot be filled (XFA, password-protected) | MDARIX renders the MIR-layout PDF from the XML, and the help text explains that the XML imports into the official PDF. |
| D11 | GB output: the owner asked for PDF only, but MHRA accepts only MORE (web, XML upload, API) | Produce the GB XML for MORE upload, plus the PDF as a record copy. |
| D12 | Northern Ireland incidents | A separate path: EU MIR form, submitted in MORE. Confirm with MHRA which EU version MORE accepts. |
| D13 | EU 1.2d "awareness date of reportability" | Derive it as the date the EU conclusion was signed REPORTABLE, editable. When it differs from 1.2c, MDARIX adds the explanation line to section 5 (MDCG 2023-3 Q15). |
| D14 | EU/GB auto follow-up details | On submission of an Initial or Follow-up: create a Follow up draft copied from the last approval, due on 1.2f; the user may switch it to a Final. After a Final: offer "Updated final report", never auto. |
| D15 | India follow-ups | No auto-create (no legal clock found); "Create follow-up / final" buttons and an optional next-report date. |
| D16 | Canada final | Auto-create the Final draft when the Preliminary is submitted, due on the anticipated date given in A5. |
| D17 | The mapping workbook as the rule book | Yes. Export a CSV per market into the repository; a test fails if code and sheet disagree. Any change to the rules is made in the sheet first. |
| D18 | Out of scope for v1 | Voluntary malfunction summary reporting (VMSR, H1 summary), the drug section C beyond the G4 combination-product tick, the user-facility annual report (Form 3419), EU/GB FSCA and trend forms, and Canada foreign risk notifications and summary reports. |

---

## 12. Could not verify

- **US.**
  - ecfr.gov refused the automated fetch, so the CFR text was read via law.cornell.edu. I did not read 803.32, 803.42 or 803.52 in full.
  - The importer and user-facility follow-up clocks are not settled.
  - How a manufacturer cites a UF or importer report number it received (H10 or another block) is **to confirm**.
  - I did not read FDA's eMDR web page; I used the package alone.
  - Whether gaps in the MDR sequence number are acceptable is **to confirm**.
- **EU.**
  - The help-text revision date.
  - The EUDAMED vigilance date ("not before 2028" comes from one secondary source).
  - National NCA portals.
  - MDCG 2021-1 Rev.1 (not read).
  - The exact on-form labels: the official PDF is XFA and locked, so the labels come from the help text.
- **GB.**
  - legislation.gov.uk refused the fetch, so the regulation 44ZH and 44ZN text was not read.
  - The Annex B–G mandatory conflict.
  - Whether newer XSDs sit behind the MORE login.
  - Which EU version MORE accepts for Northern Ireland.
- **Canada.**
  - The current e-mail address and address locator (official pages disagree).
  - Whether a form newer than April 2018 exists.
  - The meaning of the E1 note on the form.
  - The C4 iii "Device Identification No" meaning.
- **India.**
  - ipc.gov.in HTML pages returned HTTP 500, so the official form page, toolkit and release date of v1.2 were not read.
  - The CDSCO circular of 15 May 2024 (secondary sources only).
  - Whether ADRMS accepts XML or E2B.
  - How licence holders get ADRMS accounts.
  - An importer's SAE duty outside Rule 38.

---

## 13. Sources (all read 6 Nov 2026 unless stated)

**United States**
- FDA eMDR Implementation Package (local copy; zip dated 5 Aug 2024; HL7Medwatch.xlsx ChangeLog to 1 Aug 2024): `HL7Medwatch.xlsx`, MDR examples (XML + PDF), XML schemas, Ack examples.
- Form FDA 3500A (09/2025), `FDA-3500A_Eng_Stat_Sec_Ext_09-15-2025.pdf` (local copy).
- 21 CFR 803.12, 803.30, 803.33, 803.40, 803.50, 803.53, 803.56: https://www.law.cornell.edu/cfr/text/21/803.12 (and the same pattern for each section). ecfr.gov redirected the automated fetch.

**European Union**
- PMSV reporting forms page (MIR 7.3.1, "mandatory as from 1st May 2026"; update 7 May 2026): https://health.ec.europa.eu/medical-devices-sector/new-regulations/guidance-mdcg-endorsed-documents-and-other-guidance/pmsv-reporting-forms_en
- MIR 7.3.1 PDF form: https://health.ec.europa.eu/document/download/e8ce9f53-82cb-44c8-a06e-91ad71c16b01_en?filename=md_new-reg_mir-form-v7.3.1_en.pdf
- MIR 7.3.1 help text: https://health.ec.europa.eu/document/download/dc6acc1b-f1ae-4512-b838-2fae869124c3_en?filename=md_new-reg_mir-help-v7.3.1_en.pdf
- MIR 7.3.1 XSD/XSL (SB-11252, 10 Jun 2026): https://health.ec.europa.eu/document/download/12d3a3db-b089-482d-b0d1-44e7cd2324da_en?filename=md_new-reg_mir-xsd-xsl-v7.3.1_en.zip
- MIR changelog: https://health.ec.europa.eu/document/download/6d4a14de-c05f-4d50-975f-f20dfa0fa1c2_en?filename=md_new-reg_mir-changelog-v7.3.1_en.txt
- MDCG 2023-3 Rev.2 (January 2025): https://health.ec.europa.eu/document/download/af1433fd-ed64-4c53-abc7-612a7f16f976_en?filename=mdcg_2023-3_en.pdf
- Regulation (EU) 2017/745, consolidated 10 Jan 2025 (Art 87, 89), EUR-Lex.
- EUDAMED overview: https://health.ec.europa.eu/medical-devices-eudamed/overview_en

**Great Britain**
- Vigilance reporting requirements (updated 5 Sep 2025): https://www.gov.uk/government/publications/medical-devices-post-market-surveillance-requirements/vigilance-reporting-requirements
- GB MIR and FSCA schema implementation guide, Version 1, May 2025: https://assets.publishing.service.gov.uk/media/6825a453ffcd6ecfbf1ab8e6/GB_schema_implementation_guide.pdf
- GB data-requirement files (GB XSDs 7.2.1, GB help text, changelog; published 9 Jun 2025): https://www.gov.uk/government/publications/documentation-for-implementation-of-data-requirements-under-the-new-post-marketing-surveillance-regulations
- MORE guidance (updated 9 Jun 2025): https://www.gov.uk/guidance/manufacturers-online-reporting-environment-more

**Canada**
- Form page: https://www.canada.ca/en/health-canada/services/drugs-health-products/medeffect-canada/adverse-reaction-reporting/mandatory-medical-device-problem-reporting-form-industry-adverse-reaction-reporting.html
- Form PDF (HC Pub. 110180, April 2018): https://www.canada.ca/content/dam/hc-sc/migration/hc-sc/dhp-mps/alt_formats/pdf/medeff/report-declaration/md-mm_form-eng.pdf
- Guidance (2021): https://www.canada.ca/en/health-canada/services/drugs-health-products/reports-publications/medeffect-canada/incident-reporting-medical-devices-guidance-2021.html
- SOR/98-282 s.59–61.6: https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/page-5.html

**India**
- MDAE form v1.2 (copy read): https://nhsrcindia.org/sites/default/files/Medical-Devices-Adverse-Event-Reporting-Form-(Version-1.2).pdf
- CDSCO copy with instructions: https://www.cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadPublic_NoticesFiles/MEDICAL%20DEVICE%20ADVERSE.pdf
- IPC form page (HTTP 500, not read): https://ipc.gov.in/8-category-en/1312-medical-device-adverse-event-reporting-form-for-licence-holders-health-care-proffesionals-english-editable-version.html
- ADRMS User Manual for Stakeholders: https://ipc.gov.in/images/mvpi/ADRMS-USER-MANUAL-FOR-STAKEHOLDERS.pdf
- ADRMS MDAE capture SOP (3 Feb 2026): https://ipc.gov.in/images/mvpi/Capture-and-record-the-information-of-MDAE-while-reporting-in-ADRMS.pdf
- MDR 2017 consolidated (to GSR 777(E), 14 Oct 2022): https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/m_device/mdr,%202017%20(1).pdf

**MDARIX code:** tag v0.10.91: `backend/app/authority_reports/` (forms.py, emdr.py, fda_3500a.py, worksheet.py, render.py, router.py, rules.py), `backend/app/reportability/markets.py`, `backend/app/db/models/authority_reports.py`, `frontend/src/features/workspace/sections/ReportsTab.tsx`.
