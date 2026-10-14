# Subprocessors (facts for the lawyer)

The services that receive or store customer or personal data when MDARIX runs in production, as the software is
configured today. This is a factual inventory for the privacy notice and the data processing agreement, not legal
text; the website does not show this file. Fill in each provider, legal entity and region when it is contracted, and
keep the list current: a new provider is added here before it receives any data.

| Service | Provider (to fill in) | Purpose | Data categories | Region (to fill in) | Used when |
|---|---|---|---|---|---|
| Hosting (application server) | Google Cloud (Google Cloud India Private Limited), Compute Engine | Runs the web application, API, background worker and scheduler; holds uploaded files when the local file store is used | All customer content and account data in transit and in memory; application logs | Mumbai, India (`asia-south1`) | Always |
| PostgreSQL database | During the validation phase: on the application server above (no separate provider); managed Cloud SQL later | Stores every record: accounts, quality records, audit trail, signatures; point-in-time recovery and snapshots | All customer content and account data; audit trail (with network addresses) | Mumbai, India | Always |
| Object storage | _storage provider_ (`MDARIX_OBJECT_STORAGE_PROVIDER=s3`, `MDARIX_OBJECT_STORAGE_REGION`) | Uploaded evidence files and data exports, encrypted | Customer documents and files; export archives | _region_ | When the S3 file store is configured (planned for pilots) |
| Off-site backup storage | Google Cloud Storage, copied by the server's own service account (no keys) | Encrypted daily backups, kept up to 90 days | Everything in the database and file store, encrypted with a key the provider never holds | Delhi, India (`asia-south2`) | When off-site backup is configured |
| Email delivery (SMTP) | Resend (`smtp.resend.com`) | Account activation, password reset, trial and notification emails | Recipient name and email address; email content (no quality records) | United States | Always |
| AI model provider(s) | Each provider in `MDARIX_GENAI_CONTRACTED_PROVIDERS` (see `docs/compliance/AI_PROVIDER_REGISTER.md`) | Drafting and analysis features, only for organizations whose administrator switched AI on | Text of the quality records sent with a request, masked per the organization's settings | _region per provider_ | Only when AI is switched on for an organization (off by default) |
| Error reporting | Sentry (`MDARIX_SENTRY_DSN`) | Diagnosing server errors | Error messages, stack traces and request paths; request bodies and cookies are not sent | _region_ | Only if `MDARIX_SENTRY_DSN` is set |
| Inbound email (evidence by email) | Resend (`RESEND_API_KEY`) | Receives evidence sent to the organization's inbound address | Email content and attachments sent in, sender address | _region_ | Only if inbound evidence email is switched on |

Self-hosted AI models (for example on the MDARIX server itself) are not subprocessors. Payment processing is not part
of the product today.
