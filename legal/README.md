# Legal documents

The website shows three documents from this folder. Your lawyer writes them; engineering only places the approved
files here. Until a file exists, its page says the document is being finalized and gives the privacy or support
address instead.

| File | Shown at | Linked from |
|---|---|---|
| `privacy.md` | `/privacy` | Footer, signup, demo request, the in-app privacy notice |
| `terms.md` | `/terms` | Footer, signup, demo request |
| `trial-agreement.md` | `/trial-agreement` | Footer, signup, the trial invitation email |

Format: Markdown with `#`/`##`/`###` headings (the page shows its own title, so a first `# Title` line is skipped), paragraphs, `-` or `1.` lists, `**bold**`, and `[text](https://…)` or
`[text](mailto:…)` links. Nothing else is rendered (no HTML, no images). Maximum 200 KB per file.

Staging and production refuse to start until all three files are here, none of them still carries the
**DRAFT** banner or a `[PLACEHOLDER]` in square brackets, the company details are set, and
`MDARIX_LEGAL_TEXT_APPROVED=true` (see `docs/runbooks/ENVIRONMENT_VARIABLES.md`). On the server this folder is
mounted read-only into the API (`docker-compose.prod.yml`), so an updated document is live after
`docker compose -f docker-compose.prod.yml restart api` without a new release.

## Facts about the product for the lawyer

These describe what the software does today, so the documents match it. Engineering keeps this list current.

**Who the operator is.** The legal name, postal address, support and privacy addresses come from
`MDARIX_COMPANY_LEGAL_NAME`, `MDARIX_COMPANY_ADDRESS`, `MDARIX_SUPPORT_EMAIL` and `MDARIX_PRIVACY_EMAIL` and are shown
in the footer, on `/contact` and in every email.

**Personal data collected**
- Trial signup: name, work email and organization name.
- Demo requests: name, work email and phone number. The requester's IP address is stored only as a salted one-way
  hash, to limit repeated requests.
- Trial feedback: the questionnaire answers, linked to the user and organization. Nothing is shown publicly unless
  the person chose "named" or "anonymous" publication and a platform administrator published it; withdrawing
  consent unpublishes it.
- Signed-in use: user name, email, role, sign-in times, authenticator (MFA) secret (encrypted), and an audit trail
  of actions taken (who, what, when). Electronic signatures record the signer, meaning and time.
- Customer content: quality, complaint, supplier and product records a customer uploads or connects. Customers are
  asked not to enter patient-identifiable data during a pilot (decision 6.5 of the readiness review).

**Where it is processed**
- Hosting provider and region: a single cloud server plus a managed Postgres database (fill in the provider and
  region when chosen).
- Email: the SMTP provider configured in `MDARIX_SMTP_HOST` sends account, trial and notification emails. Resend is
  used only if inbound evidence email is switched on.
- AI: only providers listed in `MDARIX_GENAI_CONTRACTED_PROVIDERS` (under a no-training, limited-retention
  agreement) or self-hosted models receive content in staging and production; free tiers are refused by the server.
  List each contracted provider as a subprocessor.
- Error reporting: Sentry, only if `MDARIX_SENTRY_DSN` is set. Request bodies and cookies are not sent.

**How long it is kept** (the full schedule, with what enforces each period, is
`docs/compliance/DATA_RETENTION_SCHEDULE.md`)
- A free trial lasts 30 days for up to 3 users and 5,000 uploaded rows. Trial data is deleted 30 days after the trial
  ends; while the organization's request to move it into an MVP is open, it is kept, at most 90 days after the end.
  The person who requested the trial is emailed 7 days and 1 day before the end and when it ends.
- Paid customers: kept for the subscription term. At the end, the customer's data is handed back as a full export
  (or the customer's written waiver is recorded) and then deleted; one person's data can be exported or erased on
  request (`docs/runbooks/DATA_REQUESTS.md`).
- Audit trail and electronic signatures: append-only and never changed. Each event is kept for at least 7 years from
  the event (the database dates every event), and for as long as the customer's account exists if that is longer.
  When an organization's data is deleted at the end of the contract, its trail goes to the customer in the export and
  is then deleted with everything else; the customer keeps it for its own regulatory period.
- Erasure leaves some things behind, and the documents should say so: audit rows keep the person's account id (which
  no longer identifies them) and the network address and browser recorded at the time; free text that colleagues
  typed into quality records or reasons (for example a name in a complaint description) is not searched out.
- Backups: encrypted; 14 days on the server (`MDARIX_BACKUP_KEEP_DAYS`), up to 90 days in the off-site copy, plus
  the server disk's daily snapshots (14 days, kept in Mumbai). During the validation phase the database runs on the
  server itself, with no point-in-time recovery. Erased data stays in backups for that period;
  after any restore the erasures are repeated from the erasure log before the system is used.
- A legal hold (a court, regulator or the customer requires preservation) suspends deletion for that organization
  until it is lifted; setting and lifting it are recorded with the reason.
- AI providers: what each contracted provider keeps, and for how long, is in
  `docs/compliance/AI_PROVIDER_REGISTER.md`. AI processing is off for a new organization until its administrator
  switches it on.
- Subprocessors (hosting, database, file storage, backups, email, AI, error reporting): `legal/SUBPROCESSORS.md`.

**Cookies and browser storage**
- One session cookie (`__Host-mdarix_session`), strictly necessary, HTTP-only and secure; it ends after 30 minutes
  without activity and at the latest 12 hours after sign-in (renewed while the person keeps working; 10 minutes while
  the second sign-in factor is pending).
- Browser local storage for preferences only (dismissed notices, table column choices, onboarding progress). No
  analytics, advertising or third-party tracking cookies.

**Security measures** (also stated on `/security`): TLS for all traffic, row-level isolation between organizations
in the database, encrypted authenticator secrets and connector credentials, passwords hashed with scrypt and checked
against known breached passwords, sign-in rate limits and lockout, authenticator-app MFA, virus scanning of uploads,
an append-only, hash-chained audit trail verified daily, and encrypted backups.

**Not offered today** (the documents should not promise them): single sign-on (OIDC/SAML), certifications such as
ISO 27001, SOC 2 or HIPAA attestation, a validated (GxP/Part 11) system, data residency choices beyond the chosen
hosting region, and dedicated databases per customer during pilots.

## What the lawyer still has to produce

Engineering cannot write these; pilots with real customer data should not start until they exist.

1. The three documents above: `privacy.md`, `terms.md`, `trial-agreement.md`.
2. A data processing agreement (DPA) for customers, with its list of subprocessors (`legal/SUBPROCESSORS.md`) and,
   for any transfer outside the EEA/UK, the Standard Contractual Clauses (and the UK addendum where it applies).
3. The breach-notification commitment: MDARIX tells the affected customer without undue delay and in any case within
   72 hours of becoming aware of a personal-data breach, so the customer can meet its own deadline; the DPA should
   state the channel and what the notice contains.
