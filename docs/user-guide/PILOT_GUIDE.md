# MDARIX pilot guide

This guide is for the people taking part in an MDARIX design-partner pilot: the customer administrator who sets the organization up, and the quality and regulatory staff who investigate complaints in it. It describes what MDARIX does today. MDARIX supports investigations; it is not your quality management system, it does not submit anything to a regulator, and it never makes a regulated decision for you.

## Roles

Every person has one account per organization and one role. The role decides what they can do; the server checks it on every action.

- **Viewer**: reads products, signals, investigations, evidence and decisions. Cannot change records, run AI or export.
- **Investigator**: everything a Viewer can do, plus opening and managing investigations, importing data, running the AI analysis steps and exporting.
- **Reviewer**: the same rights as an Investigator; records the human review of a decision.
- **Approver**: an Investigator's rights plus approving regulatory documents and signing decisions it has the authority for.
- **Leader**: every business right, including approval and signature.
- **Customer Administrator**: manages the organization (users, roles, integrations, data mapping, security settings, audit exports). The same account can switch into the workspace with an Investigator's rights ("Open workspace" in the console header, "Admin console" to return). A Customer Administrator cannot sign decisions or approve regulatory documents.

The person who records a decision cannot also sign it: a second authorized person signs.

## First steps for the customer administrator

1. **Sign in and set up multi-factor authentication.** Open the invitation email, choose a password of at least 12 characters, then add MDARIX to an authenticator app when asked (Security, "Set up MFA"). Save the recovery codes shown once. MFA is required for administrators and before every electronic signature.
2. **Invite your colleagues.** In the console, open Users, then Invite. Give each person the role they need. They receive an email with a single-use activation link; an expired link can be replaced with "Forgot password?" on the sign-in page, or by sending a new invitation.
3. **Decide on AI processing.** AI processing is off for a new organization: nothing from your organization is sent to an AI model, and the features answer from rules. To turn it on, open Security, then AI processing, read what will be sent and to which provider, and confirm your acknowledgement. The change is recorded in the audit trail and you can turn it off again at any time.
4. **Import your data, in order.** Open the workspace, then Import data (any role that may change records can do this). Download each CSV template and fill it from an export of your own systems. Load products first, then lots, then complaints, then the other templates (components, suppliers, changes, risks, investigations, evidence, CAPAs and the rest), because later files refer to earlier ones. Remove patient and personal details first. Choose the date order your file uses (YYYY-MM-DD, DD/MM/YYYY or MM/DD/YYYY); comma, semicolon and tab separated files are read; save files as CSV UTF-8. "Check file" reports every problem without saving anything; a file with any problem imports nothing. Each import is recorded in the audit trail.
5. **Release your data mapping** (only when your systems are connected through an integration rather than CSV files). In Data Mapping, review the field mapping version and send it for approval. An approver reviews and approves it before it is released. In an organization with a single administrator, that administrator may approve their own release by typing a reason; the approval is recorded as self-approved in the audit trail.

## The investigation workflow

1. **Start from a signal.** The Dashboard and Signals show complaints and trends for your products. Choose the product and version in the context bar at the top of each page.
2. **Open an investigation.** In Investigations, choose "Open an investigation", write the question it must answer, and select the complaints that prompted it. You can search the complaints by identifier or description. The case is assigned to you; Manage lets you reassign, rephrase, close or reopen it, each with a reason of at least ten characters kept in the audit trail.
3. **Work the case.** Open the case's workspace and run, in order: Run Analysis (grounded observations and gaps), Generate Hypotheses (competing explanations, none chosen for you), and Run Challenger, Unknowns and Chain (challenges, missing information and the failure chain, which may stay unresolved). Each step can take up to a minute. Every AI statement cites the evidence it used; statements that could not be verified are marked as such. With AI processing off, the same steps answer from rules.
4. **Ask questions.** Ask MDARIX answers questions about your organization's records and lists the evidence behind each answer.
5. **Prepare the brief.** "Generate Investigation Brief" assembles a versioned package of the evidence, explanations and open questions for human review.

## Decisions and sign-off

1. In Decisions, the Decision Center shows what is known, the challenges, the hypotheses and the unknowns for the selected case. "Generate AI Advisory" gives a suggestion that is labelled as advisory; it is never a decision.
2. A person with the right to change records chooses a decision option and writes the rationale, then records the decision. It is saved as "requires review".
3. A reviewer records the human review: approved, rejected, or more evidence needed.
4. An authorized approver signs: they choose approve or reject, write their remarks, and confirm with their password and the code from their authenticator app. The signature records who signed, what it means, when, and a fingerprint of the exact decision version. If the decision changes afterwards, it must be reviewed and signed again.
5. "Verify a signature" (in Decisions) lists the case's decisions and shows whether each signature still matches the decision it was given for.

## Exports

- **Audit trail**: customer administrators export the organization's audit events as CSV from Audit in the console. Exports contain only your organization's events.
- Exporting needs the export permission (Investigator, Reviewer, Approver, Leader, Customer Administrator).

## Sessions

You are signed out after 30 minutes without activity and must sign in again after 12 hours at most. Two minutes before an inactivity sign-out, MDARIX asks whether you want to stay signed in. After signing in again you return to the page you were on. If MDARIX cannot be reached, the page says so and keeps trying; that is not a sign-out.

## Getting help

- **Help menu, "Report a problem"**: describe what happened and what you expected. The report reaches the MDARIX team with the page you were on and, when a request had just failed, its reference number. Do not include patient or personal data. If the report cannot be sent, the form offers an email to support instead.
- **Error references**: when something cannot be loaded, the message shows a reference for support. Quote it when you contact us; it lets us find the exact failed request.
- **Share feedback**: tell us what works and what to improve. Your answers go to the MDARIX team; nothing is shown publicly unless you agree to it, and you can withdraw that consent at any time.
- **Contact support** in the Help menu shows the support email address for your installation.
