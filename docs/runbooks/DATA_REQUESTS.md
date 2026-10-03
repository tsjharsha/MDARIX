# Data requests: access, export, erasure, deletion and legal hold

How MDARIX staff and customer administrators handle requests about personal data and customer data. Each step
below is recorded in the audit trail with who did it and why. Answer requests within one month (GDPR Art. 12);
reply to the requester from the privacy address (`MDARIX_PRIVACY_EMAIL`).

## Who is the controller

For data a customer puts into MDARIX (its users, its quality records), **the customer is the controller** and MDARIX
is the processor: forward a request from one of the customer's people to that customer's administrator and help
them act on it. For data MDARIX collects itself (trial and demo requests, website contact), MDARIX is the
controller and handles the request directly.

## 1. Access or portability: "give me a copy of my data"

* **A whole organization** (end of a pilot, or the customer asks for its data): Customer administrator, or Platform
  Admin > Customers & Tenants > tenant > **Data** > **Prepare export**. The background worker writes one zip:
  a JSON Lines file per table, every stored file, and `manifest.json` with row counts, a SHA-256 per entry and the
  audit trail's verified head. Passwords, secrets, tokens and encrypted keys are never included. Download it within
  7 days (the scheduler then deletes it); every download is audited. Send it by a secure channel, never by email
  attachment.
* **One person**: export the organization, then give them the rows that concern them (their `auth_users` row, the
  audit events where `actor_ref` is their account id, records they created). There is no per-person export yet.

## 2. Erasure: "delete my personal data" (one person)

1. Verify the request comes from the person (reply to their known address; for a customer's user, the customer
   administrator confirms).
2. **Offboard** the user (Users > person > Offboard). Erasure is refused for an active account.
3. **Erase personal data** (Users > person > Erase personal data, or Platform Admin
   `POST /api/v1/platform-admin/users/{id}/erase`), entering the request and how it was verified.

What happens: name, email and credentials are replaced (`removed-…@removed.invalid`), the authenticator and recovery
codes are removed, sessions, invitations, password-reset and sign-in records are deleted, roles are removed, and
unpublished feedback is deleted. Records the person created stay, linked to the now-anonymous account id.

What stays and why: audit events cannot be changed (they are hash-chained and append-only). They keep the account
id, which no longer identifies anyone, and the network address and browser recorded at the time, for the audit
retention period, as a legal obligation of regulated medical-device quality records and for security. Say so in the
reply. Published feedback stays only as consented; to withdraw it, unpublish it first (Platform Admin > Trial
feedback).

## 3. Deleting an organization's data

* **Free trials** are deleted automatically 30 days after they end (scheduler job `trial-retention`), and the
  requester is told in the invitation, the reminders and the trial-ended email.
* **On request or at the end of a contract**: suspend or terminate the organization, prepare and hand back an export
  if wanted, then Platform Admin > tenant > **Data** > **Delete all data** (type the organization key, re-enter your
  password, give the reason).

Deleted: every table holding the organization's rows (discovered from the database), the whole audit trail and every
stored file. Kept: the organization row (archived), subscription and plan history, and pseudonymized account and
trial-request rows, as the record of the contract. The trail restarts with one `TENANT_DATA_DELETED` event naming
who deleted what and why. The deletion is all-or-nothing: if anything would remain, nothing is changed and the
error is shown; the scheduled job alerts operations.

Backups: deleted data remains in encrypted backups until they expire (`MDARIX_BACKUP_KEEP_DAYS`, the managed
database's recovery window, and the off-site bucket's lifecycle rule; see BACKUP_AND_RESTORE.md). It is never
restored into production; if a restore is ever needed, repeat the deletion afterwards. On a versioned object-storage
bucket, deleted files keep a noncurrent version until the bucket's noncurrent-version expiry rule (set it to 30 days)
removes it.

## 4. Legal hold

If a customer, regulator or court requires data to be preserved (for example a recall investigation or litigation):

1. Record the hold: who asked, scope, reference, date, in the customer's file.
2. Do **not** run "Delete all data" or "Erase personal data" for that organization; tell the platform team.
3. For a trial under hold, extend its subscription (Platform Admin > Plans & Licensing) so retention does not purge
   it, and note the hold as the reason.
4. When the hold is lifted, record it and continue the normal schedule.

## 5. Rectification

Users correct their own name in My Account; customer administrators correct users and records in the console.
Audit events are not changed; the correction itself is audited.
