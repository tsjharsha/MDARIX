# MDX-VAL-003 GAMP 5 category justification

| Field | Value |
|---|---|
| Document ID | MDX-VAL-003 |
| Title | GAMP 5 category justification |
| Version | 0.3 |
| Status | DRAFT |
| Author (R) | Sriharsha Telikicherla, Product & Engineering, system owner |
| Reviewer | Independent CSV consultant (confirms; not engaged yet) |
| Approver (A) | Srinivas Telikicherla, QA/RA, quality approver |
| Drafting | Drafted with software assistance; every line reviewed by Sriharsha Telikicherla (MDX-VAL-000, DC-R43) |
| Date | 12 Nov 2026 |
| Code baseline | Product code at `628c624a`, plus two changes on branch `feat/b6b-validation-pack`: the SUPERSEDED banner in `validation/csa_package.py` and its test, and `cb75e8da` (the rule register refuses a version approved by its own builder, owner decision O3: `backend/app/rule_register/register.py` and its test) |

Change history

| Version | Date | Change | By |
|---|---|---|---|
| 0.1 | 12 Nov 2026 | First draft (B6b Part A); revised after a software-assisted review, findings dispositioned by the author (libraries, customer-side rules worded as template instructions) | Sriharsha Telikicherla |
| 0.2 | 12 Nov 2026 | After a second software-assisted review, findings dispositioned by the author: whose view the category takes (section 4); owner decision O3 on the rule register; how each rule is checked (section 7); unconditional approval meaning, consultant confirmation tracked as OP-1 | Sriharsha Telikicherla |
| 0.3 | 12 Nov 2026 | Editorial fixes after a third software-assisted review: code baseline names `cb75e8da`; OP-1 cites B6b-D5 | Sriharsha Telikicherla |

## 1. Purpose and scope

This document states the GAMP 5 software category of each part of MDARIX and why. The category guides how much
of the validation effort sits with MDARIX as supplier and how much with the customer, and how MDARIX validates
work it does for a single customer.

It covers the MDARIX application as released by tag, the platform software it runs on, and any software MDARIX
writes for one customer. The categories here are a proposal **to confirm with your consultant** (MDX-VAL-013,
question 2). This document is not shown to any customer before the consultant confirms it (owner decision B6b-D5,
MDX-VAL-000 section 4).

## 2. References

| Ref | Document |
|---|---|
| R1 | ISPE GAMP 5, A Risk-Based Approach to Compliant GxP Computerized Systems, 2nd edition (2022), software categories and appendix M4. **To confirm with your consultant** |
| R2 | MDX-VAL-001 Validation Master Plan |
| R3 | MDX-VAL-002 Product risk assessment |

## 3. Decision (owner decision B6b-D5)

| Part | Category | Short reason |
|---|---|---|
| The MDARIX application (web application, API, background service, database schema), as released by tag | **4: configured product** | One product, one code base and one version for every customer; each customer configures it through settings and data, never through code |
| Rule content shipped with MDARIX (rule register versions, starter question sets, reporting windows) | Part of Category 4 (configuration supplied with the product) | Held as versioned data with a content hash, checked when it loads; a change is a new version, never an edit |
| Platform software: operating system, PostgreSQL, container runtime, web server, file scanner, Python and Node runtimes | **1: infrastructure software** | Used as supplied; MDARIX tests only its own use of them (MDX-VAL-001, VMP-R16 and VMP-R17) |
| Libraries built into the application (for example FastAPI, SQLAlchemy, React) | Part of Category 4 (components of the product) | Tested as part of the product; listed by version in each release's software bill of materials; changed under the change-impact rule (MDX-VAL-001 section 9.3) |
| Anything MDARIX writes for one customer: a custom connector, a custom mapping, a custom report or a script run for one customer | **5: custom application** | Written for one customer and not part of the shared product; validated as custom software |

## 4. Why MDARIX is Category 4

GAMP 5 places a product in Category 4 when it is configured to meet a user's business process, and in Category 5
when it is written to a user's requirements. The category is the regulated user's view: for the customer, MDARIX is
a configured product (Category 4). MDARIX itself develops the product as its own code; its software lifecycle is to
be documented in MDX-SOP-001 (B6b Part C), and each release will be validated under MDX-VAL-001 once that plan is
approved (MDX-VAL-001 section 9.4). The following facts support Category 4 for MDARIX.

1. **One product, one version.** Every customer runs the same released version on the shared plane (`VERSION`,
   the git tag and `.github/workflows/release.yml`). There is no customer branch of the code.
2. **Customers configure, never code.** A customer administrator sets users and roles, organisation settings,
   switches, reporting windows, e-mail intake and import mappings through the product's own screens. No customer
   can add or change program code.
3. **Rules are data.** Each rule MDARIX applies is one JSON file per rule version in
   `backend/app/rule_register/data/`. `backend/app/rule_register/register.py` refuses the register when a version's
   content does not match its content hash, when versions overlap, or when coverage has a gap. A change of rule is a
   new version file; the file records who wrote it and who approved it (the owner or a named regulatory approver).
   The register refuses a version approved by the person who built it (owner decision O3, MDX-VAL-002 RSK-065). Signed records name the version they used.
4. **Roles and permissions are fixed data.** Personas and their permissions are defined in
   `access_control/personas.py` and `backend/app/access/permissions.py`; the customer assigns them, it does not
   define new permission logic.
5. **The configuration can be captured and compared.** The configuration snapshot (`backend/app/signed_reviews/`)
   records an organisation's configuration, can be signed by the customer, and is compared with a later snapshot,
   showing who changed what, when and why.

### 4.1 What this means for validation

- **GAMP-R01** Each release pack shall cover the rule content shipped in that release (rule register versions and
  their content hashes) as well as the program code.
- **GAMP-R02** The customer UAT/PQ template (MDX-CUS-001) shall instruct the customer to use its signed configuration
  snapshot as the configuration under test.
- **GAMP-R03** The customer UAT/PQ template (MDX-CUS-001) shall instruct the customer to check the starter rule
  content against its own procedures before relying on it.
- **GAMP-R04** The Category 4 decision shall not reduce MDARIX's own testing: each MDARIX function is tested at the
  assurance level of its class in MDX-VAL-002, whatever its GAMP category.

## 5. Why custom work is Category 5

- **GAMP-R05** Software that MDARIX writes for one customer shall be treated as Category 5.
- **GAMP-R06** Category 5 work shall have its own requirements, design, code review, tests and release approval, in
  addition to the product's own validation.
- **GAMP-R07** Category 5 work shall be recorded per customer and listed in that customer's change notice and
  periodic review.
- **GAMP-R08** Category 5 work shall not run on the shared plane without the quality approver's signed release
  approval.

Examples: a connector written for one customer's complaint system; a mapping MDARIX writes for one customer's export
format; a one-off data correction script. A mapping the customer builds with the product's own mapping screens is
customer configuration (Category 4), not Category 5.

## 6. Why platform software is Category 1

- **GAMP-R09** Platform software shall be used as supplied.
- **GAMP-R10** The version of each platform component shall be recorded in the IQ record of each release.
- **GAMP-R11** An upgrade of platform software shall follow the change-impact rule in MDX-VAL-001 section 9.3.

The cloud provider's infrastructure is assessed as a supplier in the hosting assessment (MDX-SUP-004).

## 7. How these rules are checked

| Rules | Check | Evidence |
|---|---|---|
| GAMP-R01 | The IQ record lists the rule-register versions and content hashes of the release (MDX-VAL-001 section 14) | IQ record |
| GAMP-R02, GAMP-R03 | The quality approver checks the instructions in MDX-CUS-001 before approving it | MDX-CUS-001, signed |
| GAMP-R04 | The RTM shows coverage per class, whatever the category | RTM; VSR |
| GAMP-R05 to GAMP-R08 | The release approval record and the customer change notice list any Category 5 work | Release approval record; change notice |
| GAMP-R09 to GAMP-R11 | The IQ record lists platform versions; the change impact names any platform upgrade | IQ record; change impact |

## 8. Open points

| # | Point | Owner |
|---|---|---|
| OP-1 | The consultant to confirm Category 4 for the product and Category 5 for custom work, and say what else they would treat as Category 5 (MDX-VAL-013, question 2). Version 1.0 is signed only after the consultant's written answer to question 2 (owner decision B6b-D5) | Srinivas |
| OP-2 | Whether customer-written organisation rules (rules that can only raise an outcome) need any extra customer test beyond the UAT/PQ template | Srinivas |
| OP-3 | Closed 12 Nov 2026: `register.py` refuses the same person as builder and approver (owner decision O3) | Sriharsha |

## Signatures

Unsigned. The signed PDF and its `signatures.csv` row are added after review (MDX-VAL-000 section 2.6).

| Role | Name | Meaning of signature | Signature | Date |
|---|---|---|---|---|
| Author (R), system owner | Sriharsha Telikicherla, Product & Engineering | I am responsible for this justification and reviewed every line of the draft. | | |
| Reviewer (C) | Independent CSV consultant | I confirm, or comment on, the categories and their rationale. | | |
| Approver (A), quality approver | Srinivas Telikicherla, QA/RA | I approve this justification for use. | | |
