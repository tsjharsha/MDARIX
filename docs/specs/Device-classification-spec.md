# Device and IVD risk classes across markets: what MDARIX should hold and do

Version 1, 11 Nov 2026. **APPROVED by the owner on 11 Nov 2026 (see "Approval record").** Nothing here is built. No code, database or git state was changed. Decisions marked **⚑** touch regulatory interpretation or signed records. They need the owner's explicit answer. Each ⚑ says what happens **if no answer arrives** (always the safer path). Per the owner's rule for new work (7 Nov), nothing here starts without a green signal.

- **Code read** (read-only, `git show` / `git grep`): branch `feat/b8-eu-gb-mir` (tip `dd1870b7`). Every `file:line` is on that branch, under `backend/app/` unless shown. The migration head was checked on `feat/b9b-other-countries` and `feat/b6a-speed-reviews`.
- **Regulatory sources:** read on the web on 11 Nov 2026, official sites first. Each fact has its URL in section 2. **[O]** = read on the official page or the official PDF. **[O-snip]** = from a search extract of an official page that would not open. **[2nd]** = secondary source only: **to confirm**. Every legal statement stays "starter, for your consultant to confirm", as in B4, B8 and B9.
- **Not in scope:** choosing a class for a customer (pre-market work, Part D is parked), any price, any claim of compliance.

---

## 1. Purpose, in plain words

Every market gives a device a risk class. MDARIX already asks for it on some authority forms. Today it is one short text per registration, with a starter list for six markets.

The class matters to a post-market system for three reasons:
1. **Authority forms ask for it.** EU and GB MIR item 2.4, India MvPI A1, Canada form C4 i. A wrong or vague class on a filed report is a finding.
2. **Periodic post-market duties depend on it.** In the EU, a class I device needs a PMS report, class IIa a PSUR at least every two years, IIb and III at least every year. Great Britain, Canada, Australia and (for new devices) India have their own class-linked periodic reports. A customer must not miss one.
3. **Incident (vigilance) reporting mostly does not depend on it.** The EU, GB, US, Canada, India, Australia, China, Singapore and Brazil set incident deadlines by the event, not the class (section 2). So MDARIX's reportability rules (B4 floors) stay as they are.

**MDARIX prepares and reminds; the customer decides the class and files.** MDARIX stores the class the customer states, with its legal basis and the rule they used, and a person confirms it. MDARIX never assigns a class.

---

## 2. Research: classes and class-linked duties per market

### 2.1 Comparison table

| Market | Classes (devices / IVDs) | Legal basis | Who classifies | Third-party body | Class-linked post-market duties | Incident reporting class-based? |
|---|---|---|---|---|---|---|
| **EU** | Devices I (with Is, Im, Ir), IIa, IIb, III. IVDs A (A sterile), B, C, D | MDR 2017/745 Art. 51, Annex VIII (22 rules). IVDR 2017/746 Art. 47, Annex VIII (7 rules) | Manufacturer, by the rules. Dispute with the notified body goes to the competent authority (MDR Art. 51(2)) | Notified body for Is/Im/Ir (only those aspects), IIa, IIb, III. IVDR: A sterile (sterility aspects), B, C, D | MDR: class I **PMSR** (Art. 85), updated when necessary. **PSUR** IIa at least every 2 years; IIb and III at least annually (Art. 86(1)). Class III and implantables: PSUR submitted via EUDAMED to the notified body, which adds its evaluation (Art. 86(2)). IVDR: A/B PMSR (Art. 80); C/D PSUR at least annually; D submitted to the NB (Art. 81) | No (MDR Art. 87: event-based 2/10/15 days) |
| **Northern Ireland** | As EU | EU MDR and IVDR apply in NI (Windsor Framework) | Manufacturer | EU notified body; UK notified body gives CE+UKNI | As EU | No |
| **Great Britain** | UKCA: devices I (Is, Im), IIa, IIb, III, active implantable; IVDs general, Annex II List A, List B, self-test. CE-marked devices accepted to 30 June 2028 / 2030 | UK MDR 2002 as amended (MDD/IVDD-based). PMS: new Part 4A, SI 2024/1368, in force 16 June 2025 | Manufacturer | UK approved body for Is/Im, IIa and above, List A/B, self-test | **PMSR** (reg. 44ZL): class I and IVD class A/B/general; first within 3 years, then at least every 3 years. **PSUR** (44ZM): IIa first within 2 years then every 2 years; IIb, III, IVD C/D, List A/B first within 1 year then every year. To the approved body by agreement; approved body reports on class III, implantables, List A/B. MHRA: on request, within 3 UK working days | No |
| **US** | Class I, II, III (devices and IVDs alike). Route: exempt, 510(k), De Novo, PMA | 21 CFR 860; device types in 21 CFR 862–892 (16 panels); FD&C Act s.513 | **FDA**, by regulation and product code | None mandatory (FDA reviews) | **PMA annual report** (21 CFR 814.84, yearly from approval). **522 orders** possible for class II or III meeting set criteria. Tracking orders (21 CFR 821) and post-approval studies (814.82) per order | No (21 CFR 803: 5/30 days by event) |
| **Canada** | Class I–IV for devices (Schedule 1 Part 1) and IVDs (Part 2) | Medical Devices Regulations SOR/98-282 s.6–7, Schedule 1 | Manufacturer applies the rules; Health Canada checks at licensing | MDSAP auditing organisation for the QMS certificate (II–IV) [O-snip] | **Summary report** (s.61.4): class II every 2 years, III and IV every year; notify the Minister within 72 h if the benefit-risk changed; give it on request (s.61.5); keep 7 years (s.61.6). Class I: none. Licence (MDL) only for II–IV; class I under an establishment licence | No (s.59–61: 10/30 days by event) |
| **India** | Devices A–D; IVDs A–D | MDR 2017 Rule 4, First Schedule Part I (devices) and Part II (IVDs) | **Central Licensing Authority** classifies and publishes class-wise lists (Rule 4(3)–(4)) | Notified bodies registered with CDSCO audit A/B sites; C/D inspected by CDSCO officers or a notified body | **PSUR only for a new device without a predicate or a new IVD** (Rule 65(b)): every 6 months for 2 years, then yearly for 2 years, to the Central Licensing Authority, within 30 days of each period's end. Not class-based. No other class-linked periodic report found | No (Rule 26: 15 days, B9) |
| **Australia** | I, Is, Im, IIa, IIb, III (AIMD now class III); IVD class 1–4 | Therapeutic Goods (Medical Devices) Regulations 2002, Schedules 2 and 2A | Manufacturer | TGA or accepted overseas certificates for Is/Im and IIa+ | **Annual reports for the first 3 years** on the ARTG: class III, AIMD, implantable IIb, IVD class 4; due 1 Oct for 1 July–30 June [O-snip] | No |
| **Japan** | Class I–IV (general / controlled / specially controlled); IVDs class I–III | PMD Act Art. 2(5)–(7); MHLW Notification 298 (2004), per generic name (JMDN) | **MHLW**, by published list | Registered certification bodies for class II (and III with standards) | Use-results evaluation for some new devices; conditional approvals with risk plans [O-snip] | No (15/30 days) |
| **China** | Class I–III (devices); IVD reagents I–III, own catalogue | Rules for Classification (CFDA Decree 15, 2016); SAMR Decree 48 (IVD, 2021) | **NMPA** catalogue; new products confirmed by NMPA | None (authorities review) | **Periodic risk evaluation report** (SAMR Decree 1, Art. 39): within 60 days after each full year from first registration; class I reports only kept by the holder [O] | No (7/20 days) |
| **Brazil** | Class I–IV (devices, RDC 751/2022); IVD I–IV (RDC 830/2023) | RDC 751/2022 Annex I (22 rules); RDC 830/2023 | Applicant, by the rules; ANVISA decides doubts | ANVISA GMP certificate for III–IV; INMETRO certification for some products whatever the class | Registration renewal (10 years) for III–IV only; no class-linked periodic report found | No (RDC 67/2009) [2nd] |
| **Singapore** | Class A–D (devices and IVDs) | Health Products Act; Health Products (Medical Devices) Regulations 2010; HSA guidance GN-13, GN-14 | Manufacturer, by HSA rules | None local; overseas approvals shorten routes | None class-linked found | No |
| **Saudi Arabia** | Devices A, A sterile, A measuring, A reusable surgical, B, C, D; IVD A–D | Medical Devices Law (M/54) and Implementing Regulation; SFDA MDS-REQ1 Annex 5; guidance MDS-G008 v2.0 (2022) | Manufacturer | Not checked | Not checked | Not checked |
| **IMDRF/GHTF model** | A–D (devices and IVDs) | GHTF/SG1/N77:2012 (devices); IMDRF/IVD WG/N64:2021 (IVDs, replaces GHTF/SG1/N045:2008) | (A model, not law) | — | — | — |

### 2.2 Facts and sources, per market

**EU (MDR and IVDR)**
- MDR class I PMSR, IIa PSUR "at least every two years", IIb/III "at least annually", class III and implantable PSURs submitted through EUDAMED to the notified body; non-implantable IIa/IIb PSURs are not submitted to EUDAMED but made available to the notified body and, on request, to competent authorities. First PSUR within one year (IIb, III) or two years (IIa); the data collection period starts at the MDR certification date, or at the MDR date of application (26 May 2021) when not MDR-certified; periods are contiguous. Legacy (MDD/AIMDD) devices use their MDD class and are not submitted in EUDAMED. Source: MDCG 2022-21 (Dec 2022) [O, official document text read from the copy at https://www.team-nb.org/wp-content/uploads/members/M2022/MDCG-2022-21-PSUR.pdf; the health.ec.europa.eu copy https://health.ec.europa.eu/system/files/2022-12/mdcg_2022-21_en.pdf answered "too many requests"].
- MDR Art. 51 (classes, disputes), Art. 52(7) (Is/Im/Ir: notified body only for those aspects), Annex VIII rules 1–22 (e.g. rule 11 for software), Art. 85, 86, 87; IVDR Art. 47, 48, 80, 81, Annex VIII rules 1–7 (rule 4 self-testing and near-patient testing). Sources: https://eur-lex.europa.eu/eli/reg/2017/745/oj and https://eur-lex.europa.eu/eli/reg/2017/746/oj. **EUR-Lex refused automated reading in this session: the article texts were not re-read today. To confirm** (the PSUR facts above are confirmed through MDCG 2022-21).
- EUDAMED: the first four modules (actors, UDI/devices, notified bodies and certificates, market surveillance) are mandatory from 28 May 2026 (Commission Decision (EU) 2025/2371, OJ 27 Nov 2025). The vigilance and post-market surveillance module, which carries PSURs, is not yet mandatory [O-snip] https://health.ec.europa.eu/latest-updates/eudamed-four-first-modules-will-be-mandatory-use-28-may-2026-2025-11-27_en. **To confirm:** how class III PSURs reach the notified body until that module is mandatory.

**Great Britain and Northern Ireland**
- PMSR (44ZL) and PSUR (44ZM) by class, timings, approved-body review, MHRA on request within 3 UK working days, records 10 years (15 for implantables), applies to devices placed on the GB market from 16 June 2025, no backdating [O] https://www.gov.uk/government/publications/medical-devices-post-market-surveillance-requirements/requirements-of-the-manufacturers-pms-system
- SI 2024/1368 inserts Part 4A into UK MDR 2002 [O-snip] https://www.legislation.gov.uk/uksi/2024/1368/made (the page would not open: legislation text not re-read).
- CE acceptance in GB: MDD/AIMDD to the earlier of certificate expiry or 30 June 2028; IVDD and EU MDR/IVDR to 30 June 2030; NI applies EU MDR (26 May 2021) and IVDR (26 May 2022); UKNI where a UK notified body assessed [O] https://www.gov.uk/guidance/regulating-medical-devices-in-the-uk
- UK class names (UKCA: I, Is, Im, IIa, IIb, III, AIMD; IVD general, List A, List B, self-test): the gov.uk page only names class I and general IVDs. Also the PMS page does not mention self-test IVDs. **To confirm** from the 2002 Regulations.

**US**
- Classes and route: ~1,700 device types in 16 panels, 21 CFR 862–892; class I/II not exempt need a 510(k); class III needs a PMA; the product code carries the class; unclassified devices show a proposed class [O] https://www.fda.gov/medical-devices/overview-device-regulation/classify-your-medical-device and https://www.fda.gov/medical-devices/classify-your-medical-device/product-code-classification-database
- 522: class II or III devices whose failure would likely have serious adverse health consequences, with significant pediatric use, implanted more than one year, or life-sustaining/supporting outside a user facility [O] https://www.fda.gov/medical-devices/postmarket-requirements-devices/522-postmarket-surveillance-studies-program
- PMA annual reports at 1-year intervals from approval (814.84) [O-snip] https://www.fda.gov/medical-devices/premarket-approval-pma/pma-postapproval-requirements
- 21 CFR 860.3 definitions and 821 tracking: ecfr.gov redirected to a block page. **To confirm.**

**Canada**
- s.61.4–61.6 summary reports (text above) [O] https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/page-6.html and https://laws-lois.justice.gc.ca/eng/regulations/SOR-98-282/section-61.4.html
- Classes I–IV by Schedule 1 (s.6), higher class when two apply (s.7); MDL for II–IV; class I under an establishment licence; IVD rules in Part 2 [O-snip] https://laws-lois.justice.gc.ca/eng/regulations/sor-98-282/fulltext.html, https://www.canada.ca/en/health-canada/corporate/about-health-canada/legislation-guidelines/acts-regulations/frequently-asked-questions-medical-devices-regulations.html, https://www.canada.ca/en/health-canada/services/drugs-health-products/medical-devices/application-information/guidance-documents/guidance-document-guidance-risk-based-classification-system-vitro.html
- **To confirm:** what date a summary-report cycle counts from (licence date or another anniversary): s.61.4 does not say.

**India**
- Rule 4(1)–(4): devices and IVDs A (low), B (low moderate), C (moderate high), D (high); the Central Licensing Authority classifies and publishes class-wise lists [O] https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2022/m_device/Medical%20Devices%20Rules,%202017.pdf (CDSCO's consolidated copy).
- Rule 65(b): the holder of a Form MD-27 permission (new device without predicate, new IVD) submits PSURs every six months for two years, then yearly for two more years, from the market launch date [O] same PDF. The schedule text "Post Marketing Surveillance" in the same PDF (in the clinical investigation schedule) adds: due within 30 calendar days of each period's end; the authority may extend the duration [O]. **To confirm:** whether the duty also binds the Form MD-29 (manufacture) holder: Rule 65's heading covers both, clause (b) names MD-27 only.
- Licensing: class A (except non-sterile, non-measuring) and B by the State Licensing Authority, C and D by the Central Licensing Authority; notified bodies audit A/B; class A non-sterile non-measuring exempt from licensing (G.S.R. 102(E), 11 Feb 2020) [O-snip] https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/MDfAq24.pdf. **To confirm:** the registration route that replaces licensing for those class A devices.
- CDSCO IVD PMS guidance, **draft for public comment, 2022**: adverse-event reporting focus on class C and D IVDs and point-of-care / home-use IVDs [O] https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadPublic_NoticesFiles/2Draft%20Guidance%20on%20PMS.pdf. Final status **to confirm**.

**Australia, Japan, China, Brazil, Singapore, Saudi Arabia, IMDRF** (one check by a separate research pass, same day)
- TGA classes, Schedules 2 and 2A, annual reports [O-snip] https://www.tga.gov.au/products/medical-devices/overview/overview-medical-devices-and-ivd-regulation, https://www.tga.gov.au/resources/guidance/submitting-annual-reports-medical-devices, https://www.tga.gov.au/resources/guidance/reclassifying-active-implantable-medical-devices-aimd. tga.gov.au timed out: **to confirm** in a browser.
- Japan [O] https://www.pmda.go.jp/english/review-services/reviews/0004.html; [O-snip] https://www.pmda.go.jp/files/000245839.pdf, https://www.pmda.go.jp/files/000273975.pdf
- China [O] https://english.nmpa.gov.cn/2019-10/11/c_415411.htm, https://english.nmpa.gov.cn/2024-06/05/c_1049322.htm, https://english.nmpa.gov.cn/2019-12/16/c_961748_2.htm
- Brazil [O] https://www.gov.br/anvisa/en/rules-and-regulations/arquivos/rdc-751_2022.pdf/@@display-file/file; IVD RDC 830/2023 [O-snip]; RDC 67/2009 deadlines [2nd]
- Singapore [O] https://www.hsa.gov.sg/medical-devices/registration-of-medical-devices/register-your-device/overview/; [O-snip] https://www.hsa.gov.sg/medical-devices/guidance-documents/
- Saudi Arabia [O] https://www.sfda.gov.sa/sites/default/files/2022-12/MDS%E2%80%93G008.pdf
- IMDRF [O-snip] https://www.imdrf.org/documents/principles-vitro-diagnostic-ivd-medical-devices-classification and https://www.imdrf.org/documents/ghtf-final-documents/ghtf-study-group-1-pre-market-evaluation (imdrf.org timed out).

---

## 3. What MDARIX has today (checked 11 Nov 2026)

| Area | Today | Evidence |
|---|---|---|
| Where the class lives | One `risk_class` text per product registration, 10 characters, optional | `db/models/regulatory_reference.py:57-58` |
| Markets a registration can name | US, EU, GB, NI, CA, IN, AU | `db/models/regulatory_reference.py:23` |
| Registration types | US 510K/PMA/DE_NOVO/EXEMPT; EU CE; GB UKCA/CE; NI CE/UKNI; CA MDL; IN CDSCO_LICENCE; AU ARTG | `regulatory_reference.py:35-43` |
| Class lists | US I–III; EU, NI **and GB** share one list: I, IIa, IIb, III, A–D; CA I–IV; IN A–D; **AU not checked** | `regulatory_reference.py:47-57` |
| Check at save | Case-insensitive match to the market's list; else 422 `RISK_CLASS_UNKNOWN` | `regulatory_reference.py:91-96` |
| MIR 2.4 (EU, GB) | A fixed list incl. MDR Is/Im/Ir as class I with the schema's type flag, IVDR A–D, MDD/AIMDD/IVDD legacy classes | `authority_reports/forms.py:757-776` |
| MIR 2.4 from a registration | `risk_class_choice` maps a bare "IIb" to MDR, "B" to IVDR; anything else: a person chooses | `forms.py:779-791`; `mir_xml.py:319-323` (a non-entry goes in as MDR text) |
| India MvPI A1, Canada C4 i | Filled from `risk_class` | `forms.py:539`, `forms.py:1750` |
| Which registration fills a form | Registrations of the form's market; the **first one with a class wins** (query has no order) | `authority_reports/worksheet.py:167-177`, `:582-590` |
| Product facts | One category: IMPLANT, SINGLE_USE, REUSABLE, SOFTWARE, IVD or KIT | `db/models/foundation.py:163-164` |
| PSUR / PMSR | Template text only ("the PSUR and the PMS plan" in the management review) | `qms_documents/templates.py:80-83`; five templates, none a PSUR (`:66-157`) |
| Periodic report calendar | None | — |
| Screen | Registration form: class drop-down per market | `frontend/src/features/workspace/sections/ImportReports.tsx:1031` |

### 3.1 Gap table

| # | Gap | Evidence | Part |
|---|---|---|---|
| G1 | EU/NI registration cannot hold Is, Im or Ir; MIR 2.4 then says "MDR class I" and loses the type flag | `regulatory_reference.py:47`, `forms.py:763-765` | A |
| G2 | IVDR class A sterile, self-test and near-patient cannot be recorded | `regulatory_reference.py:47` | A |
| G3 | GB uses the EU list. UKCA devices follow UK MDR 2002: no IVD A–D, but General / List A / List B / self-test, and Is/Im | `regulatory_reference.py:53` | A |
| G4 | No legal basis per registration: a GB "CE" row can be MDD (to 2028) or MDR (to 2030); an EU row can be a legacy MDD device | — | A |
| G5 | No classification rule or rationale stored (e.g. "Annex VIII rule 11"); no person confirms the class | — | A |
| G6 | Two registrations in one market with different classes: the form takes whichever comes first | `worksheet.py:582-590` | A |
| G7 | A Northern Ireland registration (market NI) is not read for the EU/NI MIR (the form reads market EU only) | `worksheet.py:167` | A |
| G8 | Device vs IVD not held per registration: Canada and India use the same letters for both | `regulatory_reference.py:55-56` | A |
| G9 | Canada class I has no licence, but the only type is MDL; India class A non-sterile non-measuring is not licensed, but the only type is CDSCO_LICENCE | `regulatory_reference.py:40-41` | A |
| G10 | Australia classes not checked | `regulatory_reference.py:48` | C |
| G11 | No dates that periodic reports count from (certificate date, first placed on the market, market launch, PMA approval) | `db/models/regulatory_reference.py:43-66` | B |
| G12 | No periodic report calendar, no reminders, no record of a PSUR/PMSR issued or sent | — | B |
| G13 | B9b other-country reports carry no device class | `other-country-reports/B9b-execution-plan.md` | C |
| G14 | No check that a class fits the registration (e.g. EU class I with a notified body; Canada class I with an MDL; US class III with a 510(k)) | `regulatory_reference.py:73-105` | A |

---

## 4. Proposed scope

Four parts. A and C are small and fit together. B is the main user value. D is parked.

| Part | What | Hours | Migration |
|---|---|---|---|
| **A** | Complete class lists per market and legal basis; rule and rationale; a person confirms; forms filled from the registration with checks | 30 | Yes (shared `tr32`) |
| **B** | Class-driven PMS obligations calendar (PMSR/PSUR/summary report/annual report), feeding P7 and the deadline list | 46 | Yes (same `tr32`) |
| **C** | Classes for Australia and for B9b other countries | 10 | Yes (same `tr32`) |
| **D** | Rule-based classification assistant | Parked (spec only if asked; 60–80 h for EU MDR + IVDR alone) | — |
| | **Total A+B+C** | **86** | One |

At about 7 build hours a day: A+C about 6 days, B about 7 days.

### 4.1 Part A: class lists, legal basis, rule, confirmation

**What changes for the user.** On a product's registration the user picks the **legal basis** (offered from the market and registration type), then the **class** from that basis's list, any **class features** (sterile, measuring, reusable surgical instrument, self-test, near-patient, implantable), and optionally the **rule** and a **rationale**. A person with regulatory approval **confirms** the class (name, date, audited). Forms then show "Class IIb (EU MDR, Annex VIII rule 11), confirmed by … on …". An unconfirmed class still fills the form, marked "not confirmed".

**Class lists, as register data** (`class-lists-1`, B4 register pattern, starter, effective from the start):

| Market / type | Legal basis codes | Classes | Features offered |
|---|---|---|---|
| EU, NI (CE, UKNI) | `EU_MDR`, `EU_IVDR`, `MDD`, `AIMDD`, `IVDD` (legacy) | MDR I, IIa, IIb, III; IVDR A, B, C, D; MDD I, IIa, IIb, III; AIMDD active implantable; IVDD general, List A, List B, self-test | MDR I: sterile, measuring, reusable surgical (any mix). IVDR A: sterile. IVDR: self-test, near-patient. All: implantable |
| GB UKCA | `UK_MDR_2002` | I, IIa, IIb, III, active implantable; IVD general, List A, List B, self-test | I: sterile, measuring. Implantable |
| GB CE | `EU_MDR`, `EU_IVDR`, `MDD`, `AIMDD`, `IVDD` | As EU | As EU |
| US | `US_21CFR` | I, II, III | Exempt (from the registration type); the classification regulation number (e.g. 21 CFR 870.1875) as the "rule" |
| CA | `CA_MDR_DEVICE`, `CA_MDR_IVD` | I, II, III, IV | Implantable |
| IN | `IN_MDR_2017_DEVICE`, `IN_MDR_2017_IVD` | A, B, C, D | A: sterile, measuring. "New device without predicate / new IVD (Rule 65)" |
| AU (Part C) | `AU_TG_MD_2002`, `AU_TG_IVD` | I, Is, Im, IIa, IIb, III, AIMD (legacy); IVD 1–4 | Implantable |

**Consistency checks** (warnings unless marked "refuse"; every warning names the source and is shown at the registration and on the report step):
1. Class not in the basis's list: **refuse** (as today).
2. A feature that the basis does not know (e.g. "reusable surgical" on IVDR): **refuse**.
3. EU/NI CE with MDR class I and no feature, and a notified body given: warn "plain class I needs no notified body".
4. Canada class I with an MDL, or class II–IV without: warn. India class A non-sterile non-measuring with a licence number: warn (to confirm).
5. US class III with type 510(k), or class I/II with PMA: warn ("unusual, check the product code").
6. Product category IMPLANT and the "implantable" feature not set (or the reverse): warn.
7. Two registrations in one market and basis with different classes: the form step asks which one; never the first found (fixes G6).
8. **Forms:** MIR 2.4 is derived from basis + class + features (Is/Im/Ir flags, legacy MDD/IVDD entries); MvPI A1 from the India registration; Canada C4 i from the Canada registration. The report step shows the source and "a person confirms" (2.4 is MUST in EU MIR, `forms.py:866-875`). A value typed on the form that differs from the confirmed registration: warn, and the frozen snapshot records both. Signed and approved reports never change (B3/B9 rule).
9. NI: the EU/NI MIR reads EU **and** NI registrations (fixes G7).

**Existing data.** No silent change. Rows today: EU/NI classes map one to one (I→MDR I, A→IVDR A…); basis set to `EU_MDR` / `EU_IVDR` by the letter, marked "basis assumed: check". GB rows: basis assumed `EU_MDR`/`EU_IVDR` for CE; for UKCA with IVD A–D the row is flagged "recheck: UK MDR 2002 has no IVD A–D" and keeps its text until a person fixes it (DC-D3 ⚑). Every migrated row is "not confirmed".

### 4.2 Part B: class-driven PMS obligations calendar

**What the user sees.** Per product, a "Periodic reports" card: for each registration that carries a periodic duty, the report kind, the current period (start and end), the due date, the recipient ("make available to your notified body", "submit to your notified body (EUDAMED)", "to the Central Licensing Authority", "on request of the Minister"), and the state (not started, issued, sent). Due and overdue periodic reports appear in the existing deadline list (Overdue / Due this week) and the watch, labelled "PSUR due" etc., beside the incident clocks. P7 (PSUR/PMSR tables and charts) opens with the product and the period pre-filled.

**Rules, as register data** (`pms-periodic-1`, starter, each line citing its source):

| Rule | Applies when | Report | Cycle | First period anchor | Recipient |
|---|---|---|---|---|---|
| EU-PMSR | EU/NI, `EU_MDR` class I; `EU_IVDR` A, B | PMSR | "When necessary": no fixed date; reminder at the customer's chosen interval (default 12 months, editable) | — | Make available to the competent authority on request (IVDR B: also the notified body, to confirm) |
| EU-PSUR-IIa | `EU_MDR` IIa | PSUR | At least every 24 months | MDR certificate date; else 26 May 2021 (MDCG 2022-21 §5.1) | Make available to the NB; implantable IIa: submit to the NB (EUDAMED) |
| EU-PSUR-IIb-III | `EU_MDR` IIb, III | PSUR | At least every 12 months | As above | Non-implantable IIb: make available to the NB. III and implantable: submit to the NB (EUDAMED) |
| EU-PSUR-IVD | `EU_IVDR` C, D | PSUR | At least every 12 months | IVDR certificate date (to confirm) | C: make available to the NB. D: submit to the NB |
| EU-LEGACY | `MDD`/`AIMDD` with a valid certificate | PSUR per MDD class (AIMDD as class III) | As above | 26 May 2021 | Make available; not in EUDAMED (MDCG 2022-21 §5.2.2) |
| GB-PMSR | `UK_MDR_2002` class I, IVD general/A/B; GB CE equivalents | PMSR | At least every 36 months | First placed on the GB market, or 16 June 2025 if earlier | MHRA on request (3 working days) |
| GB-PSUR-IIa | IIa | PSUR | 24 months, first within 2 years | As above | Approved body by agreement |
| GB-PSUR | IIb, III, active implantable, IVD C/D, List A/B | PSUR | 12 months, first within 1 year | As above | Approved body; it reports on III, implantables, List A/B |
| CA-SUMMARY | Canada II | Summary report | 24 months | MDL issue date (to confirm, DC-D6) | Keep; Minister on request; **72-hour notice if the benefit-risk changed** (a task, not a report) |
| CA-SUMMARY | Canada III, IV | Summary report | 12 months | As above | As above |
| IN-PSUR-NEW | India, "new device without predicate / new IVD (Rule 65)" set | PSUR | 6 months × 4, then 12 months × 2 | Market launch date | Central Licensing Authority, due 30 days after each period end |
| US-PMA-AR | US type PMA | PMA annual report | 12 months | PMA approval date | FDA |
| US-522 / ORDER | US, entered by the user when FDA issued an order (522, tracking, post-approval study) | As the order says | User's dates | Order date | FDA |
| AU-AR (Part C) | AU III, AIMD, implantable IIb, IVD 4 | Annual report | Yearly for 3 years | ARTG inclusion; period 1 Jul–30 Jun, due 1 Oct | TGA |

**What a person can change.** The customer's notified body may agree another schedule (MDCG 2022-21 allows the legacy schedule to continue). So each schedule can be **overridden** with a reason (audited): another anchor date, a shorter cycle, or "not applicable" with a reason. The rule's own cycle is the upper limit: a longer cycle needs a ⚑-level reason text "agreed with notified body …" and stays visible on the card (DC-D4).

**Record of a periodic report.** For each period: issued on (date), the file (scanned, SHA-256, never overwritten), sent on and to whom where a submission applies, NB evaluation received (file, for class III/implantables/IVD D). Recording "issued" carries the recorder's e-signature (B9b-N4 pattern) if DC-D5 says so. MDARIX never submits.

**What is not built.** No PSUR writing or conclusions (P7 gives tables; a person writes). No EUDAMED upload. No class-based change to incident reportability.

### 4.3 Part C: classes for Australia and other countries (B9b)

- Australia (already a registry market): its class list (table in 4.1); AU-AR rule in Part B.
- Other countries: a registration with market `OTHER` and an ISO `country` (the B9b picker's list), basis `OTHER`, class from a short starter list per country where known (Japan I–IV, IVD I–III; China I–III; Brazil I–IV; Singapore A–D; Saudi Arabia A, A sterile, A measuring, A reusable surgical, B, C, D; IVD A–D), else free text "as stated by the authority" (max 40 characters). Generic IMDRF A–D is offered as a hint only, never as the country's class.
- The Other Regulatory Report page and its pack line show the device's class in that country, from the registration, "not confirmed" until a person confirms.
- China's periodic risk evaluation report (class II/III, yearly) is offered as a **manual** periodic entry only (dates by the user), labelled "to confirm with your consultant".

### 4.4 Part D: a classification assistant (parked)

A question tree per Annex VIII (MDR 22 rules, IVDR 7 rules) and other markets would suggest a class. **Recommendation: park it.**
- MDARIX's intended use is post-market: complaints, decisions, reports, periodic duties. Classifying a device is **pre-market regulatory work**, done once, before CE marking, and reviewed by the notified body.
- A wrong suggestion carries real risk and would need consultant validation per market and per rule, plus a validation burden under B6.
- In the US, India, Japan and China the regulator assigns the class: an assistant adds little.
- What MDARIX does instead (Part A): store the class, the rule cited and the rationale, a person confirms, and link to the official rules text.
- Revisit only if a pilot customer asks, after B6, with a separate spec (estimate 60–80 h for EU MDR + IVDR only, plus consultant review).

---

## 5. Build steps

Hours include targeted tests. "(db)" = database test; "(unit)" = no database.

| # | Step | Part | Hours | Targeted tests |
|---|---|---|---|---|
| 0 | Branch from the agreed tip; one Alembic head; re-check every `file:line` here; CHANGELOG; scenarios DC-01..DC-30 in `scenario-register.md` | A | 1 | `alembic heads` = 1 |
| 1 | Migration `tr32` (section 6); models | A, B, C | 4 | (db) upgrade, downgrade, upgrade; `test_rls_coverage.py`; existing rows keep their class text |
| 2 | `class-lists-1` register data (all markets in 4.1 incl. AU and other countries) + loader + content hash; catalog source ids (MDR Annex VIII, IVDR Annex VIII, UK MDR 2002, 21 CFR 860, SOR/98-282 Sch. 1, MDR 2017 First Schedule, TG(MD)R 2002 Sch. 2/2A) | A, C | 5 | (unit) every class/feature/basis triple accepted or refused as listed; register pins; `test_standards_unit.py` |
| 3 | `check_registration`: basis, class, features, rule (80 chars), rationale (2,000 chars); checks 1–7 of 4.1; confirm route (regulatory approve, reason, audited `REGISTRATION_CLASS_CONFIRMED`; any later class change clears the confirmation, audited) | A | 6 | (unit) each check; (db) confirm by an approver; admin alone refused; change clears confirmation; another tenant's registration unseen |
| 4 | Existing data: basis assumed per 4.1, "check" mark, GB UKCA IVD A–D flagged; nothing rewritten silently | A | 2 | (db) a seeded row of each kind; GB UKCA "B" stays "B" and is flagged |
| 5 | Forms: MIR 2.4 derived from basis + class + features (EU and GB lists); MvPI A1; Canada C4 i; registration chosen per check 7; NI registrations read for EU/NI; source and "not confirmed" shown; typed value vs registration warning kept in the snapshot | A | 6 | (unit) every MDR I feature mix → the schema's flags (`mir_xml`); legacy MDD/IVDD entries; (db) two classes in one market asks; NI-only product fills 2.4; signed snapshot unchanged |
| 6 | Screens (new navigation): registration form with basis, class, features, rule, rationale, confirm; class line on the report step | A, C | 7 | vitest per screen; `tsc --noEmit` |
| 8 | `pms-periodic-1` register data (table 4.2), each rule with source and "starter" | B | 6 | (unit) rule picked for every basis × class × feature; Unknown basis → no rule and a "set the legal basis" prompt, never "no duty" |
| 9 | Schedule engine: periods from anchor and cycle, contiguous, first-period rules (EU 1 or 2 years, GB 1/2/3 years, India 6×4 then 12×2), due dates (India +30 days; others = period end unless the customer sets an issuance window), override with reason, class change mid-period starts a new schedule from the change date (old periods kept) | B | 10 | (unit) table tests per rule incl. leap years and month ends; contiguity; override audited; class change |
| 10 | Periodic report records: issued, file (scanned, SHA-256), sent to, NB evaluation file; optional recorder signature (DC-D5) | B | 6 | (db) file never overwritten; issued before period end refused; signature refusal codes in `test_signing_code_refusals.py` |
| 11 | Deadline list and watch: "PSUR due", "PMSR due", "Summary report due", "Annual report due"; Overdue / Due this week; Canada 72-hour task when a summary report records "benefit-risk changed" | B | 5 | (db) appears and leaves the list; 72-hour task clock; incident clocks unchanged (`test_legal_deadlines.py`, `test_intake_rules.py`) |
| 12 | Product "Periodic reports" card; record page; link to P7 with product and period | B | 8 | vitest; `tsc --noEmit` |
| 13 | Inspection pack: `12-periodic-reports.csv` (schedule, records, file hashes) | B | 2 | (db) pack file test |
| 14 | Part C: `OTHER` registrations with country; class on the Other Regulatory Report page and pack; China manual periodic entry | C | 6 | (db) OTHER-JP registration shown on an OTHER-JP report; free-text class limits; B9b tests green |
| 15 | Switches `MDARIX_DC_CLASSES` (A, C) and `MDARIX_DC_PMS_CALENDAR` (B), default on in test, owner sets production; off = today's behaviour, data kept | A, B | 3 | Off/on/off |
| 16 | Docs: user guide (registration, periodic reports), decision-table text for the periodic rules, environment reference, CHANGELOG | A, B | 3 | Decision-table doc test |
| 17 | Targeted suites on and off (B4 equivalence, rule pins, decision tables, authority reports API and rules, B8 MIR tests, B9 India/Canada form tests, B9b tests, legal deadlines, intake rules, story set); ruff; one independent read-only review; fixes | A, B, C | 6 | All green both ways |
| | **Total** (A 30, B 46, C 10) | | **86** | |

Hours per part: A = steps 0, 1 (2 h), 2 (4 h), 3, 4, 5, 6 (5 h), 15 (1 h), 16 (1 h), 17 (2 h) = 30 (step 7 is left empty: no registration import exists today); B = 1 (2 h), 8–13, 15 (2 h), 16 (2 h), 17 (3 h) = 46; C = 2 (1 h), 6 (2 h), 14, 17 (1 h) = 10 (shared steps split as shown).

**Cut order:** 1. China manual entry; 2. Part C other countries (keep Australia); 3. inspection pack file; 4. the recorder's signature on "issued". **Never cut:** "a person confirms"; no silent change to existing classes; signed reports unchanged; Unknown basis never means "no duty"; the switches; "MDARIX never submits".

### 5.1 Scenarios (DC-xx)

A: DC-01 EU MDR class I sterile+measuring gives MIR 2.4 class I with both flags; DC-02 legacy MDD IIb gives the MDD entry; DC-03 GB UKCA IVD "B" flagged, not changed; DC-04 two EU registrations with different classes: the step asks; DC-05 NI-only product fills 2.4; DC-06 class change clears the confirmation; DC-07 admin alone cannot confirm; DC-08 India A1 shows the confirmed class and its source; DC-09 Canada class I with MDL warns; DC-10 typed 2.4 differs from the registration: warning kept in the snapshot; DC-11 signed report unchanged after a class change. B: DC-12 EU IIa first PSUR at 24 months from the certificate date; DC-13 EU IIb non-implantable "make available"; DC-14 EU III "submit to NB"; DC-15 legacy MDD from 26 May 2021, not EUDAMED; DC-16 GB class I PMSR within 3 years of 16 June 2025 for a device already on the market; DC-17 GB IIb first within 1 year; DC-18 Canada III yearly, II every 2 years; DC-19 Canada "benefit-risk changed" creates the 72-hour task; DC-20 India new device 6-monthly ×4 then yearly ×2, due +30 days; DC-21 US PMA annual; DC-22 override shorter cycle audited; DC-23 longer cycle needs the NB text; DC-24 unknown basis prompts, never "no duty"; DC-25 overdue PSUR in the deadline list; DC-26 P7 opens with the period. C: DC-27 AU class III annual reports for 3 years; DC-28 OTHER-JP class shown on the report; DC-29 free text over 40 characters refused. All: DC-30 switches off keep today's behaviour and the data.

---

## 6. Migration

**One additive migration, `tr32_trial_device_classes.py`, revision `tr32deviceclasses`, `down_revision = "tr31othercountries"`** (the head on `feat/b9b-other-countries`; `feat/b6a-speed-reviews` adds none so far). Under the one-head rule it is re-attached to whatever head exists at merge, and renumbered if B6 or another item ships a migration first.

- `product_registrations`: `legal_basis String(30)`, `class_features text[] NOT NULL DEFAULT '{}'`, `classification_rule String(80)`, `classification_rationale Text`, `class_confirmed_by UUID`, `class_confirmed_at timestamptz`, `certified_on date`, `first_marketed_on date`, `new_device_rule65 boolean NOT NULL DEFAULT false`, `country String(2)` (required when `market = 'OTHER'`), `risk_class` widened to `String(40)` (free text for other countries). Market check gains `OTHER`. Unique key gains `COALESCE(country, '')`.
- New table `periodic_report_schedules` (registration, rule code, anchor, cycle months, override reason, valid from/to) and `periodic_report_records` (schedule, period start/end, issued on, file key + SHA-256, sent on, sent to, NB evaluation file, recorder signature id). Both with `tenant_id` and forced RLS like every tenant table.
- Data step: basis assumed for existing rows (section 4.1, "check" mark). No other backfill.
- Downgrade drops the new columns and tables; it refuses while any `OTHER` registration or any periodic record exists (no silent loss).
- Part A alone could avoid the tables, but not the columns: a migration is needed for any part.

---

## 7. Owner decisions

⚑ = touches regulatory interpretation or signed records: **needs your explicit answer.** "If no answer" is what the build does meanwhile.

| # | Decision | Recommendation (safe) |
|---|---|---|
| DC-D1 ⚑ | Store legal basis, features, rule and rationale per registration, and have a person confirm the class | Yes. Confirm = regulatory approve permission, reason, audited; a change clears it; an unconfirmed class still fills forms, marked "not confirmed". *If no answer:* stored and shown, no confirmation step. |
| DC-D2 ⚑ | Who may confirm | A Regulatory Approver, not the admin alone (as B9-D8). *If no answer:* the same. |
| DC-D3 ⚑ | GB UKCA class list = UK MDR 2002 (I, Is, Im, IIa, IIb, III, AIMD; IVD general, List A, List B, self-test) instead of today's EU list; existing GB UKCA rows with IVD A–D flagged, never changed | Yes. *If no answer:* the old list stays and the flag is shown only. |
| DC-D4 ⚑ | Periodic schedules as starter rules (table 4.2) with override; a longer cycle than the rule needs "agreed with notified body" text | Yes, labelled "starter, confirm with your consultant"; reminders only, never "compliant". *If no answer:* build the EU, NI, GB and Canada rules; India, US and Australia as manual entries only. |
| DC-D5 ⚑ | E-signature when recording a periodic report as issued | Yes, the recorder's signature with the file's SHA-256 (B9b-N4 pattern). *If no answer:* audited, no signature. |
| DC-D6 ⚑ | Anchor dates: EU = MDR certificate date, else 26 May 2021; GB = first placed on the GB market or 16 June 2025; Canada = licence date; India = market launch | As listed, each editable with a reason. *If no answer:* no anchor is assumed: the card asks the user for the first period end. |
| DC-D7 ⚑ | EU PMSR (class I, IVDR A/B) has no fixed cycle | A reminder every 12 months by default, editable, labelled "when necessary: your interval". *If no answer:* no reminder; the card lists it as "update when necessary". |
| DC-D8 ⚑ | India PSUR scope: MD-27 holders only, or MD-29 (manufacture) too | Offer the Rule 65 flag on any India registration; the label names Rule 65(b); consultant confirms. *If no answer:* the same. |
| DC-D9 | Part C (other countries) | Build Australia; other countries with starter lists and free text; China manual only. |
| DC-D10 ⚑ | Part D classification assistant | Park (section 4.4). *If no answer:* parked. |
| DC-D11 | Place in the sequence | After B6, before P7: Part A (+C) first, then Part B with P7, which uses its periods. Not in the big-bang release (cut-off 27 Nov). |
| DC-D12 | Switch defaults in production | Off until the owner's acceptance, then on. |

**Needing your explicit answer:** DC-D1, D2, D3, D4, D5, D6, D7, D8, D10.

---

## 8. To confirm with your consultant

- **EU:** issuance timeline after each PSUR data period (MDARIX uses the period end as the due date); how class III/implantable PSURs reach the notified body while the EUDAMED vigilance/PMS module is not mandatory; whether IVDR class B PMSR goes to the notified body; the IVDR anchor date; Annex VIII rule numbers to offer in the drop-down.
- **GB:** UK MDR 2002 class names as offered; whether GB PMS rules (Part 4A) apply to CE-marked devices in GB for PSUR timing; self-test IVDs (PMSR or PSUR); NI devices' PMS (EU rules) vs MHRA vigilance.
- **US:** whether customers with PMAs exist (else US-PMA-AR stays manual); 21 CFR 821 tracking scope; 522 order entries.
- **Canada:** the anchor of the summary-report cycle; whether the 72-hour notice is due on the conclusion day or the report day.
- **India:** Rule 65(b) scope (MD-27 vs MD-29); which schedule holds the "Post Marketing Surveillance" paragraph; status of the 2022 IVD PMS draft; the registration route for class A non-sterile non-measuring devices.
- **Australia, China:** annual report scope (TGA) and periodic risk evaluation report scope (NMPA) for an Indian exporter.

## 9. Documents to obtain (owner)

| For | Document | Why |
|---|---|---|
| EU | Consolidated MDR 2017/745 and IVDR 2017/746 (EUR-Lex PDF); MDCG 2022-21 from health.ec.europa.eu; MDCG 2021-24 (device classification) and MDCG 2020-16 (IVD classification), current revisions | Class lists, rule numbers, PSUR rules (EUR-Lex refused automated reading today) |
| GB | SI 2024/1368 text; MHRA PDFs "PMS obligations by medical device type" and "Medical devices: periodic safety update report" (updated 30 Sep 2025) | Part B GB rules |
| US | 21 CFR 860, 814.84, 821, 822 current text (ecfr.gov blocked automated reading) | US rules |
| Canada | SOR/98-282 Schedule 1 and s.61.4–61.6 current text; Health Canada classification guidance (non-IVD and IVD) | Lists, anchor |
| India | MDR 2017 consolidated with amendments; CDSCO class-wise lists (devices and IVDs); the IVD PMS guidance (final, if issued) | Lists, Rule 65 |
| Australia | TGA annual report guidance (tga.gov.au timed out) | AU-AR |

## 10. What I did not check

- EUR-Lex (MDR/IVDR article text), legislation.gov.uk (SI 2024/1368), ecfr.gov, tga.gov.au and imdrf.org would not open for automated reading; facts from them are marked [O-snip] or "to confirm".
- Saudi Arabia: routes per class, third parties, post-market duties, and incident deadlines: not checked. Japan's use-results evaluation periods; China's IVD classification announcement number; Brazil's RDC 67/2009 current status: not confirmed.
- B6a and later branches beyond the migration head; the frontend registration form beyond the class drop-down; the registration CSV import code; the deadline list and watch code (names taken from the B9 and B9b plans). Step 0 re-checks these.
- No database was read; hours are estimates from B8, B9 and B9b steps of similar size.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve classification spec, Lane 2 after AI-R, fix the two form problems now"**: every recommendation is accepted as written (DC-D1 store basis, rule and rationale with a confirm step; DC-D2 only a Regulatory Approver confirms; DC-D3 GB switches to the UK MDR 2002 list, existing GB IVD A–D rows flagged never changed; DC-D4 starter periodic rules with a reasoned override; DC-D5 issued periodic reports e-signed; DC-D6 anchor dates as recommended; DC-D7 EU PMSR 12-month reminder; DC-D8 India Rule 65 flag; DC-D10 Part D parked). Placement: **Lane 2 after AI-R** (DB-1 → AI-R → classification → E11 → E6 → E2). The two form problems (non-deterministic pick when a product has two registrations in one market; a Northern Ireland-only registration ignored on the EU/NI form) are fixed **now** as a small separate fix, ahead of the big-bang cut-off.

## Build status

- 12 Nov 2026: G6 and G7 fixed as the owner's small separate fix ("fix the two form problems now"): `release/bigbang-0.10.96` 793f6430, merged up the chain to `feat/b9b-other-countries` e301c653 (B8 follow-up f005598e: Northern Ireland recognised by the MORE route's names too). Unit tests `tests/test_registration_choice.py` 5 passed on the base, B8, B9b and B3; related unit tests 97 passed, 2 skipped on B9b; three DB worksheet tests passed on the base. Ready for owner acceptance. Details in `STATE.md`.

## Approval record

| Field | Value |
|---|---|
| Approved | 11 Nov 2026 |
| Approver | Srinivas Telikicherla, Founder & CEO, QA/RA (owner) |
| Approval words, as recorded | "approve classification spec, Lane 2 after AI-R, fix the two form problems now" |
| Where recorded | section "Owner approval (11 Nov 2026)" |
| Planning copy | `MDARIX-planning/device-classification/spec.md` (reference only) |
| Form of approval | The owner's written reply, recorded in the spec on the day; not an electronic or wet signature. This section was added on 12 Nov 2026 (owner decision O29); the approved text above is otherwise unchanged, except that a DRAFT status line now reads APPROVED |
