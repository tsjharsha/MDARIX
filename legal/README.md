# Legal documents

The website shows three documents from this folder. Your lawyer writes them; engineering only places the approved
files here. Until a file exists, its page says the document is being finalized and gives the privacy or support
address instead.

| File | Shown at | Linked from |
|---|---|---|
| `privacy.md` | `/privacy` | Footer, signup, the account activation page and invitation emails, the in-app privacy notice |
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
- Trial signup: name, work email, organization name, job title, country, optional phone and answers about the
  organization; and, since 0.10.33, when the request was sent and the version ("Last updated" date and SHA-256) of
  each of the three documents served at that moment (`onboarding_requests.legal_acceptance`). Sign-up refuses
  countries under comprehensive sanctions (Cuba, Iran, North Korea, Syria, the Crimea and the so-called DNR/LNR).
- Demo requests: booked from inside a trial (name, work email, optional phone, times and topics). The website form
  is parked; when it was offered it stored the requester's IP address only as a salted one-way hash.
- Server request logs (Caddy, stdout): client IP, user agent, path without query string, time; kept by Docker's
  size-based log rotation (`docker-compose.prod.yml`, 10 x 20 MB per service), so no fixed period.
- Browser error reports (`client_error_reports`) and help-menu problem reports (`support_problem_reports`, also
  emailed to the support mailbox): deleted with the organization's data; error reports sent before sign-in have no
  organization and are deleted 90 days after they arrive (scheduler job `trial-retention`, since 0.10.37).
- Trial feedback: the questionnaire answers, linked to the user and organization. Nothing is shown publicly unless
  the person chose "named" publication (credited with their job title and company name, never their own name) or
  "anonymous" (credited by their area of work only) and a platform administrator published it; withdrawing consent
  unpublishes it.
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
  ends; while the organization's request to move it into a pilot is open, it is kept, at most 90 days after the end.
  The person who requested the trial is emailed 7 days and 1 day before the end and when it ends.
- Paid customers: kept for the subscription term. At the end, the customer's data is handed back as a full export
  (or the customer's written waiver is recorded) and then deleted; one person's data can be exported or erased on
  request (`docs/runbooks/DATA_REQUESTS.md`).
- Audit trail and electronic signatures: append-only and never changed or deleted while the account exists (each
  event carries a 7-year `retention_until`, but the documents must not promise 7 years: an account can end sooner).
  When an organization's data is deleted at the end of the contract, its trail goes to the customer in the export and
  is then deleted with everything else; the customer keeps it for its own regulatory period. A free trial's trail is
  deleted with the trial (no export unless asked for).
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
against known breached passwords, sign-in rate limits and lockout, authenticator-app MFA, virus scanning of every stored file (evidence
attachments; CSV and Excel imports are read in memory, never stored, and macro workbooks are refused),
an append-only, hash-chained audit trail verified daily, and encrypted backups.

**Not offered today** (the documents should not promise them): single sign-on (OIDC/SAML), certifications such as
ISO 27001, SOC 2 or HIPAA attestation, a validated (GxP/Part 11) system, data residency choices beyond the chosen
hosting region, and dedicated databases for free trials (trials share the platform; each paid pilot gets a dedicated database
hosted and run by MDARIX). AI is off for free trials and the server refuses to switch it on for them.

## What the lawyer still has to produce

Engineering cannot write these; pilots with real customer data should not start until they exist.

1. The three documents above: `privacy.md`, `terms.md`, `trial-agreement.md`.
2. A data processing agreement (DPA) for customers, with its list of subprocessors (`legal/SUBPROCESSORS.md`) and,
   for any transfer outside the EEA/UK, the Standard Contractual Clauses (and the UK addendum where it applies).
3. The breach-notification commitment: MDARIX tells the affected customer without undue delay and in any case within
   72 hours of becoming aware of a personal-data breach, so the customer can meet its own deadline; the DPA should
   state the channel and what the notice contains.
