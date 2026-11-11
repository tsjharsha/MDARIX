# Data requests: access, export, erasure, deletion and legal hold

How MDARIX staff and customer administrators handle requests about personal data and customer data. Each step
below is recorded in the audit trail with who did it and why. Answer requests within one month (GDPR Art. 12);
reply to the requester from the privacy address (`MDARIX_PRIVACY_EMAIL`). How long each kind of data is kept is in
`docs/compliance/DATA_RETENTION_SCHEDULE.md`.

## Who is the controller

For data a customer puts into MDARIX (its users, its quality records), **the customer is the controller** and MDARIX
is the processor: forward a request from one of the customer's people to that customer's administrator and help
them act on it. For data MDARIX collects itself (trial and demo requests, website contact), MDARIX is the
controller and handles the request directly.

## 1. Access or portability: "give me a copy of my data"

* **A whole organization** (end of a pilot, or the customer asks for its data): Customer administrator, or Platform
  Admin > Customers & Tenants > tenant > **Data** > **Prepare export**, with the reason and a current code from
  your authenticator app (a session alone cannot take everything). The background worker writes one zip:
  a JSON Lines file per table, a spreadsheet (CSV) bundle of investigations, complaints, CAPAs and the evidence index,
  every stored file, and `manifest.json` with row counts, a SHA-256 per entry and the audit trail's verified head.
  Passwords, secrets, tokens and encrypted keys are never included. Download it within 7 days (the scheduler then
  deletes it); every download is audited. Send it by a secure channel, never by email attachment.
  Customer contacts are masked, and patient and reporter details typed into submitted reports (with the frozen
  official PDF/XML files that carry them) read "Personal data held: yes", unless the customer administrator ticks
  "Include patient and reporter details from submitted reports" (needs `data.export`; the export's reason covers it;
  audited `EXPORT_PERSONAL_DATA_INCLUDED` with box ids and counts, never values). A trial's export is always masked.
  An export prepared while the organization is suspended or terminated is the hand-back (section 3) and always holds
  everything.
* **One person**: the customer administrator downloads `GET /api/v1/admin/people/{id}/export` (signed in as the
  organization's administrator; a button in Users is not built yet). The JSON document holds the account record, memberships, a summary of
  sessions, the last 500 sign-in events, the audit events the person caused (up to 10,000; `audit_events_truncated`
  says when the organization export is needed for the rest) and their feedback. No credentials, session hashes or
  authenticator material. The export is audited (`PERSONAL_DATA_EXPORTED`, by account id). Business records the
  person created are in the organization export, linked to the account id in the document.

## 2. Erasure: "delete my personal data" (one person)

1. Verify the request comes from the person (reply to their known address; for a customer's user, the customer
   administrator confirms).
2. **Offboard** the user (Users > person > Offboard). Erasure is refused for an active account, and while the
   organization is under a legal hold (section 4).
3. **Erase personal data** (Users > person > Erase personal data, or Platform Admin
   `POST /api/v1/platform-admin/users/{id}/erase`), entering the request and how it was verified.

What happens: name, email and credentials are replaced (`removed-…@removed.invalid`), the authenticator and recovery
codes are removed, sessions, invitations, password-reset and sign-in records are deleted, roles are removed, and
unpublished feedback is deleted. The erasure is written to the erasure log (by account id) so it can be repeated
after a restore from backup.

What erasure leaves, and why (say so in the reply):

* **Audit rows** cannot be changed (they are hash-chained and append-only). They keep the account id, which no
  longer identifies anyone, and the network address and browser recorded at the time, for the audit retention
  period, as a legal obligation of regulated medical-device quality records and for security. New audit rows name
  people by id only; rows written before that rule, and reasons typed by administrators, may contain a name or an
  email address, and stay as they are.
* **Free text in records**: a name or address that colleagues typed into a complaint, investigation note, evidence
  file or comment is not searched out. If the person points to specific records, the customer administrator
  corrects them (section 5); the correction is audited.
* **Records the person created** stay, linked to the now-anonymous account id.
* **Published feedback** stays only as consented; to withdraw it, unpublish it first (Platform Admin > Trial
  feedback).
* **Backups** keep the old data until they expire (section 6).

## 3. Deleting an organization's data

* **Free trials** are deleted automatically 30 days after they end (scheduler job `trial-retention`), and the
  requester is told in the invitation, the reminders and the trial-ended email. A trial under a legal hold is
  skipped and the skipped run is recorded in its audit trail. So is a trial whose open MVP request (Next steps) asks
  to move its data into the MVP: it is kept while the request is open, at most 90 days after the trial ends, and
  deleted 14 days after the request is closed at the earliest (`backend/app/trial/retention.py`). Close the request
  in Platform Admin › Identity & Access › Onboarding once the data has moved, or will not.
* **On request or at the end of a contract**:
  1. Suspend or terminate the organization.
  2. Hand the data back: **Prepare export** (section 1) after the suspension, and send it. The deletion is refused
     (`EXPORT_REQUIRED`) until an export made after the suspension is ready, unless you record in
     `export_waiver_reason` why none is handed back (for example "customer declined a copy in writing, ticket 4711";
     until the screen has the field, send it with `POST /api/v1/platform-admin/tenants/{id}/purge`). The export, or
     the waiver, is named in the records that survive the deletion. Free trials need neither.
  3. Platform Admin > tenant > **Data** > **Delete all data** (type the organization key, re-enter your password
     and a current authenticator code, give the reason).

Deleted: every table holding the organization's rows (discovered from the database), the whole audit trail and every
stored file, in its dedicated database too if it has one. Kept: the organization row (archived), subscription and
plan history, pseudonymized account and trial-request rows as the record of the contract, and the erasure log. The
trail restarts with one `TENANT_DATA_DELETED` event naming who deleted what, why, and which export was handed back.

How it runs, and what to do when it stops halfway:

* **Stage one, the database rows, is all-or-nothing.** If any table still holds rows, nothing is changed, the
  organization keeps its status and the screen shows the error (`PURGE_INCOMPLETE`).
* **Stage two, the stored files and a dedicated database**, runs after the rows are committed; each step is tried
  three times. If one still fails, the organization stays **PURGING**, the trail records `TENANT_PURGE_INCOMPLETE`
  with the error, and operations is alerted. Fix the cause (file-store credentials, network, the dedicated
  database), then either press **Delete all data** again (it resumes; the export is not asked for again) or run, with
  the database owner's credentials:

  ```bash
  python scripts/complete_tenant_purge.py --dry-run     # what is pending, files left, last error
  python scripts/complete_tenant_purge.py               # finish them (or --tenant <id>)
  ```

  The organization becomes ARCHIVED only when nothing of it is left. The script exits 1 while anything is still
  incomplete. The trial-retention job reports organizations it left PURGING the same way.

## 4. Legal hold

If a customer, regulator or court requires data to be preserved (for example a recall investigation or litigation):

1. Set the hold: `PUT /api/v1/platform-admin/tenants/{id}/legal-hold` with `{"hold": true, "reason": ...}`, as a
   Platform Administrator signed in with your authenticator (a panel on the tenant page is not built yet;
   `GET` on the same address shows the current hold). In the reason write who asked, the reference,
   the scope and the date: it is the record (`LEGAL_HOLD_SET` in the organization's audit trail, with your id).
   Keep the requester's letter in the customer's file.
2. While the hold is set, MDARIX refuses: **Delete all data** (the refusal is recorded as
   `TENANT_PURGE_REFUSED_LEGAL_HOLD`), **Erase personal data** for anyone in the organization, the automatic
   deletion of an ended trial (recorded as `TRIAL_RETENTION_SKIPPED_LEGAL_HOLD`), finishing an incomplete purge, and
   repeating erasures after a restore. Nothing has to be extended by hand.
3. A second request for the same data: set the hold again with the new reason; both are recorded.
4. When the hold is lifted, clear it with the reason (`{"hold": false, ...}`, recorded as `LEGAL_HOLD_CLEARED` with
   the previous reason). Deletion that was held back resumes: an ended trial is deleted on the next daily run;
   pending requests are handled as in sections 2 and 3.

## 5. Rectification

Users correct their own name in My Account; customer administrators correct users and records in the console.
Audit events are not changed; the correction itself is audited.

## 6. Backups and restores

Deleted and erased data remains in encrypted backups until they expire: 14 days on the server
(`MDARIX_BACKUP_KEEP_DAYS`, 30, then one a month for `MDARIX_BACKUP_KEEP_MONTHS`, 12), the same in the off-site copy (bucket lifecycle rule), and the managed database's
point-in-time recovery window and snapshots (see `BACKUP_AND_RESTORE.md`). On a versioned object-storage bucket,
deleted files keep a noncurrent version until the bucket's noncurrent-version expiry rule (set it to 30 days)
removes it. Say so in replies to erasure requests.

A backup is never put back into use without repeating the erasures. Every erasure and purge is in `erasure_log`;
after any restore, before users sign in:

```bash
# against the newest copy of the database (the old instance, or the newest backup restored aside)
python scripts/reapply_erasures.py --export-log erasure_log.jsonl
# against the restored database
python scripts/reapply_erasures.py --import-log erasure_log.jsonl --dry-run
python scripts/reapply_erasures.py --import-log erasure_log.jsonl
```

It erases again every account that is identifiable again and purges again every organization whose rows, accounts
or files are back, and marks each log row `reapplied_at`. Organizations under a legal hold are listed and left
alone. Erasures made after the newest surviving copy of the log cannot be known to the restored system: if the old
database is lost, check the operations log and the audit-trail exports for erasures since that copy and repeat them
by hand.
