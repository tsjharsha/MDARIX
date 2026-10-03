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

Staging and production refuse to start until all three files are here, the company details are set, and
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

**How long it is kept**
- A free trial lasts 30 days for up to 3 users and 5,000 uploaded rows. Trial data is deleted 30 days after the trial
  ends; the person who requested the trial is emailed 7 days and 1 day before the end and when it ends.
- Paid customers: kept for the subscription term; export and deletion on request (see the data-subject request
  runbook).
- Audit trail and electronic signatures: append-only for the life of the customer's account, because medical-device
  quality records require it.
- Backups: encrypted, kept for the number of days set in `MDARIX_BACKUP_KEEP_DAYS` (default 14), plus the managed
  database's own point-in-time recovery window.

**Cookies and browser storage**
- One session cookie (`__Host-mdarix_session`), strictly necessary, HTTP-only and secure; it expires one hour after
  sign-in or after 30 minutes without activity (10 minutes while the second sign-in factor is pending).
- Browser local storage for preferences only (dismissed notices, table column choices, onboarding progress). No
  analytics, advertising or third-party tracking cookies.

**Security measures** (also stated on `/security`): TLS for all traffic, row-level isolation between organizations
in the database, encrypted authenticator secrets and connector credentials, passwords hashed with scrypt and checked
against known breached passwords, sign-in rate limits and lockout, authenticator-app MFA, virus scanning of uploads,
an append-only, hash-chained audit trail verified daily, and encrypted backups.

**Not offered today** (the documents should not promise them): single sign-on (OIDC/SAML), certifications such as
ISO 27001, SOC 2 or HIPAA attestation, a validated (GxP/Part 11) system, data residency choices beyond the chosen
hosting region, and dedicated databases per customer during pilots.
