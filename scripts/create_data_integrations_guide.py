from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = "docs/MDARIX_Data_Integrations_E2E_Guide.docx"
NAVY = "173A56"
TEAL = "0B7F7A"
PALE = "EAF5F4"
BLUE = "EAF2F8"
GRAY = "D9E2E8"

def shade(cell, color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), color)
    tcPr.append(shd)

def borders(table, color=GRAY):
    tblPr = table._tbl.tblPr
    b = tblPr.first_child_found_in("w:tblBorders")
    if b is None:
        b = OxmlElement("w:tblBorders"); tblPr.append(b)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = "w:" + edge
        el = b.find(qn(tag))
        if el is None:
            el = OxmlElement(tag); b.append(el)
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "5"); el.set(qn("w:color"), color)

def cell_text(cell, text, bold=False, color=None, size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text); r.bold = bold; r.font.size = Pt(size)
    if color: r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

def table(doc, headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers)); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = True; borders(t)
    for i, h in enumerate(headers):
        shade(t.rows[0].cells[i], NAVY); cell_text(t.rows[0].cells[i], h, True, "FFFFFF", 9)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, value in enumerate(row):
            shade(cells[i], "FFFFFF" if ri % 2 == 0 else BLUE); cell_text(cells[i], str(value), False, NAVY, 8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t

def flow(doc, lines):
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER; borders(t, TEAL)
    c = t.cell(0, 0); shade(c, PALE); c.text = ""
    for i, line in enumerate(lines):
        p = c.add_paragraph() if i else c.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after = Pt(4)
        r = p.add_run(line); r.font.name = "Consolas"; r.font.size = Pt(9); r.font.color.rgb = RGBColor.from_string(NAVY)
    doc.add_paragraph()

def bullet(doc, text, level=0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.add_run(text); return p

def step(doc, number, title, purpose, actions, validation, role="Platform Administrator"):
    h = doc.add_heading(f"Step {number}  {title}", level=2)
    h.runs[0].font.color.rgb = RGBColor.from_string(NAVY)
    p = doc.add_paragraph(); p.add_run("Purpose. ").bold = True; p.add_run(purpose)
    p = doc.add_paragraph(); p.add_run("Primary operator. ").bold = True; p.add_run(role)
    doc.add_paragraph("Configuration actions", style="Heading 3")
    for a in actions: bullet(doc, a)
    doc.add_paragraph("Exit validation", style="Heading 3")
    for v in validation: bullet(doc, v)

doc = Document()
sec = doc.sections[0]; sec.top_margin = Inches(.65); sec.bottom_margin = Inches(.65); sec.left_margin = Inches(.72); sec.right_margin = Inches(.72)
styles = doc.styles
styles["Normal"].font.name = "Aptos"; styles["Normal"].font.size = Pt(10); styles["Normal"].font.color.rgb = RGBColor.from_string(NAVY)
for name, size in [("Title", 25), ("Heading 1", 17), ("Heading 2", 13), ("Heading 3", 11)]:
    styles[name].font.name = "Aptos Display"; styles[name].font.size = Pt(size); styles[name].font.color.rgb = RGBColor.from_string(NAVY)

p = doc.add_paragraph(style="Title"); p.alignment = WD_ALIGN_PARAGRAPH.LEFT; p.add_run("MDARIX Data and Integrations E2E Configuration Guide")
p = doc.add_paragraph(); p.add_run("Platform Administrator operating procedure for customer data configuration, connector setup, mapping, release, and ingestion validation").italic = True
doc.add_paragraph("Version 1.0  |  Internal MVP validation  |  Owner: MDARIX Platform Administration")
doc.add_heading("Purpose and scope", level=1)
doc.add_paragraph("This guide explains how a Platform Administrator configures the Data & Integrations control plane for a customer tenant. It follows the ten-step sequence shown in the MDARIX application: define the data model, define rules, connect source systems, map source fields, release configuration, run ingestion, and reconcile results. The guide is written for synthetic validation tenants and can later be applied to approved customer endpoints.")
doc.add_paragraph("The procedure keeps control-plane administration separate from customer business data. Every operation must be tenant-scoped, audited, idempotent, and reversible through a draft or release version. AI remains advisory and must use authorized, provenance-aware context.")
doc.add_heading("MVP operating roles", level=1)
table(doc, ["Role", "Responsibilities", "Cannot do"], [
    ["Platform Administrator", "Create tenants, configure models/connectors, approve releases, inspect runs and failures", "Read another tenant's business records outside authorized control-plane views"],
    ["Customer Administrator", "Review tenant configuration, approve mappings, manage tenant users and integrations", "Change platform-wide catalog or another tenant's configuration"],
    ["Quality Investigator", "Use imported product, complaint, evidence, and investigation records", "Publish connector or mapping releases"],
    ["Approver", "Review release evidence and sign governed decisions", "Approve own prohibited changes where SoD applies"],
])
doc.add_heading("End to end architecture", level=1)
flow(doc, [
    "Customer source systems (QMS / PLM / ERP / Supplier)",
    "        | authenticated connector API: health -> schema -> records",
    "        v",
    "Connector catalog -> schema registry -> mapping version -> validation",
    "        |                                  |",
    "        +------------ approved release ----+",
    "                         v",
    "Tenant data plane: products, versions, complaints, evidence, lots, provenance",
    "                         |",
    "                 ingestion run / reconciliation / audit",
    "                         v",
    "MDARIX investigator, AI advisory, human review, decision and export"
])
doc.add_paragraph("Diagram 1. Configuration moves from source discovery to a versioned, tenant-bound release before records are written.", style="Caption")
doc.add_heading("Control-plane and data-plane boundary", level=1)
flow(doc, [
    "Control plane: users | tenants | plans | permissions | connector references | mappings | releases | audit",
    "                                      | tenant-bound resolver",
    "                                      v",
    "Data plane A       Data plane B       Data plane C       Data plane D",
    "customer records   customer records   customer records   customer records",
    "No cross-tenant session, query, export, attachment, or AI context is permitted"
])
doc.add_paragraph("Diagram 2. The application resolves the tenant data plane on the server; the browser never selects an arbitrary database.", style="Caption")

doc.add_heading("Preflight checklist", level=1)
for x in [
    "Confirm the customer and tenant exist and the operator is authorized for that tenant.",
    "Confirm the target environment is Sandbox, Validation, UAT, Demo, or Production as intended.",
    "Confirm the connector endpoint, authentication reference, owner, data residency, retention, and rate limit are approved.",
    "Confirm the mapping and configuration release has an immutable version and an audit reason.",
    "Use synthetic data for MVP validation; never paste production credentials into source control, screenshots, or test logs.",
]: bullet(doc, x)

step(doc, 1, "Define the MDARIX data model", "Choose the MDARIX records and fields into which customer data will be written.", [
    "Open Platform Administration > Data & Integrations > Data model.",
    "Select Product, Product Version, Component, Product Component, Supplier, Manufacturing Site, Lot / Batch, Product Change, Complaint, Investigation, Evidence, and any required reference objects.",
    "Review field type, required flag, sensitivity, identifier, nullable status, relationship, and lifecycle status.",
    "Confirm tenant_id and source provenance fields are present for every tenant-owned business record.",
    "Record the model version in the configuration baseline; do not edit an active version in place.",
], ["All required target fields are identified.", "Sensitive fields have an allowed access policy.", "A draft model version and audit event exist."])

step(doc, 2, "Configure rules and reference data", "Define validation rules and controlled values before source data is mapped.", [
    "Open Rules & reference data and create or select controlled values for complaint type, severity, status, regions, product families, suppliers, and investigation states.",
    "Define required-field, format, uniqueness, relationship, date, and value-range rules.",
    "Mark each rule as warning or blocking and document the business reason.",
    "Version reference data and rules together with the mapping baseline where a change could affect ingestion.",
], ["A test record can be classified without free-text drift.", "Blocking rules reject invalid records with field-level errors.", "Warnings are visible in reconciliation and do not silently disappear."])

step(doc, 3, "Register the connector", "Create a reusable connector definition without storing raw credentials in the UI or repository.", [
    "Open Connector catalog and choose the connector type: TrackWise/Veeva QMS, PLM/Teamcenter, ERP/Oracle, or Supplier/Coupa simulator for MVP.",
    "Enter display name, owner, tenant, environment, base URL, API version, health route, schema route, record routes, and documentation link.",
    "Select authentication scheme and reference a secret-manager or environment credential; never type the secret into a mapping record.",
    "Configure timeout, retry count, backoff, rate limit, pagination mode, incremental cursor, idempotency key, and error mapping.",
    "Run Test connection and save only a redacted response and correlation ID.",
], ["Health check returns an authorized response.", "Schema endpoint is reachable and versioned.", "Credential reference is tenant-scoped and not exposed in API responses."])

step(doc, 4, "Discover and approve the source schema", "Capture the source objects and fields that the mapping will consume.", [
    "Open Source schemas and select the connector instance.",
    "Fetch the schema and compare it with the last approved version.",
    "Review added, removed, renamed, type-changed, and requiredness-changed fields.",
    "Classify drift as compatible, review-required, or blocking.",
    "Approve the schema version only after the owner records the impact and test plan.",
], ["Schema version and checksum are persisted.", "Drift creates a visible review item.", "An incompatible schema cannot be released accidentally."])

step(doc, 5, "Configure credentials and access", "Bind a safe credential reference to the connector and prove least privilege.", [
    "Open Credentials and create a tenant-scoped reference with name, provider, scope, expiry, rotation owner, and last-tested timestamp.",
    "Grant only read scopes required for discovery and incremental ingestion; grant write scope only when explicitly required.",
    "Test expiry, rotation, invalid credential, unauthorized route, and revoked credential behavior in the simulator.",
    "Confirm secret values are masked in UI, audit records, traces, and worker logs.",
], ["Valid credentials pass health/schema calls.", "Invalid or expired credentials fail safely.", "Rotation produces a new credential reference without exposing the old value."])

step(doc, 6, "Build and validate mappings", "Map customer source fields into the selected MDARIX canonical objects.", [
    "Open Mappings and select the customer, connector, source schema version, target model version, and mapping version.",
    "Map object, field, value, relationship, conditional, lookup, and derived fields.",
    "Define transformations such as date normalization, status translation, unit conversion, trimming, and controlled-value lookup.",
    "Set missing-field behavior: reject, warn, default, or quarantine. Never silently discard a source field.",
    "Run dry run against representative records and inspect source value, target value, rule result, provenance, and error text.",
], ["Required mappings have no gaps.", "Every output carries source system, source record ID, schema version, mapping version, and ingestion timestamp.", "Dry-run counts and samples are reviewed by Customer Admin."])

step(doc, 7, "Create customer configuration", "Adopt the approved mapping and connector configuration for one tenant and environment.", [
    "Open Customer configuration and select the target tenant/environment.",
    "Review effective configuration against the global baseline.",
    "Choose deliberate adoption for the mapping, connector, rules, AI settings, and retention values.",
    "Review differences, deferred updates, and rollback version.",
    "Require Customer Admin approval where the tenant policy requires it.",
], ["No global change silently propagates to a customer.", "The effective configuration shows source, target, version, and adoption state.", "An audit event records actor, reason, previous version, and new version."])

step(doc, 8, "Release configuration", "Promote a tested configuration version so ingestion workers can use it.", [
    "Open Releases and create a release candidate from the validated mapping/schema/configuration versions.",
    "Review dependency analysis, validation results, unresolved warnings, and affected customers/environments.",
    "Obtain required approval and electronic signature with re-authentication and separation of duties.",
    "Promote to Demo or Validation; keep Production promotion outside the synthetic MVP gate.",
    "Record deployment result, release ID, rollback version, and evidence links.",
], ["Only a published active release is executable.", "A stale version or failed validation blocks promotion.", "Rollback restores the previous known-good release without deleting evidence."])

step(doc, 9, "Run ingestion and monitor failures", "Import records through the authenticated connector and persist durable run evidence.", [
    "Open Runs & failures and start a run for one connector, tenant, environment, and release version.",
    "Verify cursor, page count, received, accepted, rejected, duplicate, skipped, unresolved, and error counts.",
    "Inspect retry history, correlation ID, idempotency key, dead-letter records, and worker heartbeat.",
    "Replay only a selected dead-letter or failed item after correcting the cause; do not duplicate accepted records.",
    "Confirm attachments and report artifacts use tenant-prefixed storage keys and authorized download checks.",
], ["Run status is durable across worker restart.", "Retries are bounded and observable.", "Dead letters are retained with a reason and replay result."])

step(doc, 10, "Reconcile and sign off", "Compare source and target results and formally close the configuration cycle.", [
    "Open Reconciliation and compare source totals with accepted, rejected, duplicate, skipped, unresolved, and error totals.",
    "Review representative accepted and rejected records with provenance and field-level differences.",
    "Confirm no cross-tenant record, search result, export row, attachment, report, or AI context is visible.",
    "Customer Admin accepts the mapping outcome; Approver signs the release or remediation decision where required.",
    "Export the evidence package containing release, schema, mapping, run, reconciliation, audit IDs, and screenshots.",
], ["Reconciliation is accepted or has an owned remediation plan.", "Audit and signature records verify.", "The final evidence package is downloadable by authorized users only."])

doc.add_heading("E2E validation scenarios", level=1)
table(doc, ["Scenario", "Setup", "Expected result"], [
    ["Happy path", "Tenant A, valid connector, approved schema and mapping", "Health -> schema -> dry run -> release -> ingestion -> reconciliation succeeds"],
    ["Tenant isolation", "Tenant A and B users and records", "Neither API, search, export, attachment, report, nor AI context crosses the tenant boundary"],
    ["Schema drift", "Remove or rename a required source field", "Run is blocked or quarantined with a versioned drift record"],
    ["Retry and replay", "Temporary simulator failure then recovery", "Bounded retry succeeds once; replay is idempotent"],
    ["Dead letter", "Permanent validation error", "Record enters dead letter with reason and can be replayed after correction"],
    ["Credential rotation", "Rotate connector secret during a run", "Old credential is revoked, new reference is used, and event is audited"],
    ["Release rollback", "Promote a bad mapping version", "Release is rolled back and future runs use the prior version"],
    ["Unauthorized action", "Customer Admin attempts platform-only action", "Server returns controlled 403 and creates no mutation"],
])
doc.add_heading("Evidence pack contents", level=1)
for x in ["Configuration screenshots for each step and selected tenant/environment.", "Redacted API traces with correlation IDs and HTTP statuses.", "Schema and mapping version checksums, dry-run results, and reconciliation counts.", "Run, retry, dead-letter, replay, and worker heartbeat records.", "Audit IDs, approval/signature evidence, and rollback version.", "Desktop/mobile screenshots, keyboard focus evidence, accessibility scan, and negative isolation results.", "A short exception register with owner, severity, remediation, and retest result."]: bullet(doc, x)
doc.add_heading("Troubleshooting decision path", level=1)
flow(doc, ["Health fails -> verify endpoint, DNS, credential reference, TLS mode, and rate limit", "Schema fails -> inspect route, auth scope, schema version, and connector logs", "Mapping fails -> inspect required fields, transformations, reference values, and drift", "Run fails -> inspect cursor, retry history, idempotency, dead letter, and worker heartbeat", "Reconciliation differs -> compare source totals, rejected rows, duplicates, and replay history", "AI result is empty or generic -> verify authorized tenant context, provenance, temporal scope, and provider availability"])
doc.add_heading("MVP boundary", level=1)
doc.add_paragraph("The internal MVP uses synthetic customer systems and validation tenants. Real customer credentials, hosted production TLS, production monitoring, production backup/PITR, and customer-specific operational commitments are separate deployment gates. No demo operator should present synthetic connector evidence as proof of a real customer integration.")
doc.add_heading("Operator sign-off", level=1)
table(doc, ["Gate", "Owner", "Status", "Evidence reference"], [["Data model and rules approved", "Platform Admin", "", ""], ["Connector and credentials tested", "Platform Admin", "", ""], ["Mapping dry run accepted", "Customer Admin", "", ""], ["Release approved and signed", "Approver", "", ""], ["Ingestion and reconciliation accepted", "Customer Admin", "", ""], ["Isolation and accessibility evidence reviewed", "QA / Security", "", ""]])

doc.save(OUT)
print(OUT)
