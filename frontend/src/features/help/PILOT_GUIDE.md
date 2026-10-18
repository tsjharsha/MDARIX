# MDARIX pilot guide

This guide is for the people taking part in an MDARIX design-partner pilot: the customer administrator who sets the organization up, and the quality, risk and regulatory staff who take complaints from signal to a signed decision in it. It describes what MDARIX does today. MDARIX supports investigations; it is not your quality management system, it does not submit anything to a regulator, and it never makes a regulated decision for you: authorized people decide, and sign.

## From the free trial to the MVP

The MVP is the paid design-partner pilot that follows a free trial: MDARIX working on your real complaints, connected to your own systems, run by your own team. It lasts from 3 months to 1 year, agreed in a written proposal that also carries its price, before anything is signed. In a trial workspace, **Next steps** (in the menu, and in the Help menu) explains what changes and sends a request for an MVP conversation to the MDARIX team.

- **A dedicated database, run by MDARIX.** The MVP runs on a dedicated MDARIX transactional database, set up only for your organization and hosted and run by MDARIX. It holds only your organization's data. Your complaint, QMS, PLM and ERP systems stay your systems of record.
- **Real data only.** There is no sample data in the MVP. If you uploaded your own data in the trial and removed the sample data, MDARIX moves that data into your MVP database when you ask for it in your request. Otherwise nothing is moved, and the trial data is deleted 30 days after the trial ends.

The MVP starts in five steps. Setup takes at least 2 to 3 weeks, and the MVP itself starts only when the setup is validated and you have signed it off:

1. **Agree the scope (week 0).** A call to agree your goals and which products, sites and systems are in scope. You receive a written proposal with the MVP length and price. Then the agreement and the data processing agreement are signed.
2. **Install and secure (week 1).** MDARIX sets up the dedicated database for your organization. Your Customer Administrator is set up with two-factor sign-in and configures users, roles and security settings.
3. **Connect and map your data (week 2).** Each source system gets a mapping file: which field in your system becomes which field in MDARIX. A test load is checked against your record counts, then the mapping is approved and released.
4. **Validate and sign off (week 3).** Validation testing against your intended use, your own acceptance testing and training for your team. You sign off the setup. MDARIX is not a validated (GxP) system out of the box; your quality system and its validation stay yours.
5. **Work on your real complaints (the MVP starts).** Your team takes real complaints from signal to signed decision. MDARIX reviews progress with you regularly against success criteria agreed at the start.

What MDARIX needs from you: a sponsor who owns the MVP's goals, a named Customer Administrator, an IT contact for the installation and the connections, the list of systems in scope with a sample export from each, at least two quality team members for the workflow, and time for validation testing in week 3.

## Roles

Every person has one account in your organization with one base role. A customer administrator can give a person additional workflow roles on top of it (Users, then the person, then Additional roles, with a reason that is kept in the audit trail), so one person can cover several steps. The server checks the person's roles on every action; the screens only hide what the role cannot do.

The workflow roles, in the order a case meets them:

- **PMS / Signal Triage Lead**: triages new signals (complaints and trends), decides what each needs, opens investigations from them and assigns cases.
- **Quality Investigator**: works the case: scope, evidence, evidence requests, hypotheses and the other intelligence, the risk and regulatory review requests, and writes and submits the Decision Brief.
- **Risk Reviewer**: carries out the risk reviews of cases that need one. Reads and reviews evidence; does not change case records.
- **Regulatory Reviewer**: carries out the regulatory reviews of cases that need one, and may approve regulatory documents. Does not change case records.
- **Quality Reviewer**: reviews each submitted Decision Brief for quality: accepts it for decision, returns it, rejects its conclusion or escalates it. Can also assign cases.
- **Authorized Decision Maker**: signs the decision on a brief that the quality review accepted.
- **Leader (Quality Manager)**: every right of the roles above, including signing; escalated briefs go to the Leaders.

Two more roles take no step in the workflow:

- **Viewer**: reads everything in the organization and can verify signatures; changes nothing, runs no AI and exports nothing.
- **Customer Administrator**: runs the organization (users and their roles, integrations, data mapping, security settings, AI processing, audit exports). The same account can open the workspace ("Open workspace" in the console header) to look at cases, open and manage them and use Ask MDARIX, but it holds no workflow role, can never be given one and never signs. A person who administers and also investigates uses a second account for the case work.

## Who you need: the minimum team

Three rules decide how many people a case needs:

- **Whoever wrote a Decision Brief cannot review or sign it.** The person who created, submitted or edited a brief version cannot carry out its quality review, and cannot sign the decision on it.
- **Only people with approval authority sign**: Authorized Decision Makers and Leaders. Each signature needs the person's password and the code from their authenticator app.
- **Administrators never sign**, whatever authority is configured.

So the smallest team that can take a case from signal to a signed decision is **two people, plus an administrator account**:

1. **Person A**, Quality Investigator, with Signal Triage Lead as an additional role (and Risk Reviewer and Regulatory Reviewer as additional roles when the case needs those reviews): triages the signal, works the case and writes and submits the brief.
2. **Person B**, Quality Reviewer with Authorized Decision Maker as an additional role (or a Leader): reviews the brief and signs the decision. Person B must not edit the brief, or they become one of its authors.
3. **The customer administrator** sets the organization up, invites A and B and gives them their roles.

For a pilot that tests how your organization really works, we recommend one person per workflow role (six people: triage lead, investigator, risk reviewer, regulatory reviewer, quality reviewer and decision maker), as in MDARIX's own end-to-end tests. A Leader can stand in for any of them, except on a brief they wrote.

## First steps for the customer administrator

1. **Sign in and set up multi-factor authentication.** Open the invitation email, choose a password of at least 12 characters, then add MDARIX to an authenticator app when asked (Security, "Set up MFA"). Save the recovery codes shown once. Administrators, Leaders and Authorized Decision Makers set up MFA at their first sign-in; everyone needs it before their first signature.
2. **Invite your colleagues and give them their roles.** In the console, open Users, then Invite, and choose each person's base role. Then add any additional workflow roles they need (see "Who you need" above). They receive an email with a single-use activation link; an expired link can be replaced with "Forgot password?" on the sign-in page, or by sending a new invitation.
3. **Decide on AI processing.** AI processing is off for a new organization: nothing from your organization is sent to an AI model, and the features answer from rules. To turn it on, open Security, then AI processing, read what will be sent and to which provider, and confirm your acknowledgement. Personal details are masked before anything is sent. The change is recorded in the audit trail and you can turn it off again at any time.
4. **Import your data, in order.** Open the workspace, then Import data (any role that may change records can do this). Download each CSV template and fill it from an export of your own systems. Load products first, then lots, then complaints, then the other templates (components, suppliers, changes, risks, investigations, evidence, CAPAs and the rest), because later files refer to earlier ones. Remove patient and personal details first, or choose to have them replaced. Choose the date order your file uses (YYYY-MM-DD, DD/MM/YYYY or MM/DD/YYYY); comma, semicolon and tab separated files are read; save files as CSV UTF-8. "Check file" reports every problem without saving anything. By default a file with any problem imports nothing; you can choose instead to import the rows that pass and download the others, with their problems, to fix and import again, and to have personal details in the text (names, phone numbers, emails, record numbers) replaced by placeholders such as [PERSON] instead of refused. Each import is recorded in the audit trail (counts only).
5. **Release your data mapping** (only when your systems are connected through an integration rather than CSV files). In Data Mapping, review the field mapping version and send it for approval. An approver reviews and approves it before it is released. In an organization with a single administrator, that administrator may approve their own release by typing a reason; the approval is recorded as self-approved in the audit trail.

## The investigation workflow

Choose the product, version and case in the context bar at the top of each page; every section below it follows that choice. **My Work** lists what is waiting for you: tasks assigned to you, work your roles can pick up, and evidence requests sent to you.

### 1. Triage the signal (Signal Triage Lead)

In **Signals**, new signals come from your complaints and from the trend rule (by default, three related complaints within 30 days). Start triage, set the priority and decide what the signal needs: monitor it, no action, duplicate of another signal (linked, never deleted), investigation required, or escalated (which makes it critical). From a signal that needs an investigation, create the investigation: the case takes the signal's priority, and the signal follows its case until the case closes. A case can also be opened directly in Investigations with "Open an investigation".

### 2. Set the scope and gather evidence (Quality Investigator)

Open the case in **Investigations**. Its tabs follow the work: Workspace, Intelligence, Scope, Reviews, Decision Brief, Decision, Story and CAPAs. Save the **Scope** first (which products, versions, lots and complaints the case covers); saving the first scope starts the case. Each change to the scope is a new version with its reason; earlier versions are kept unchanged.

In **Evidence**, link the evidence the case needs and review each item: accepted, accepted with a limitation, rejected, quarantined or superseded, and whether it supports, contradicts or only gives context. Some outcomes need a reason. Nothing is ever unlinked. When something is missing, send an evidence request (Evidence, Requests) to a colleague, to everyone holding a role, or to a supplier; the answer comes back into the case to be reviewed. An open urgent request (high or critical) holds the brief back.

### 3. Work out what happened (Quality Investigator)

In the case's **Intelligence** tab, record hypotheses, unknowns, the failure chain and observations. When AI processing is on, the AI's analysis, hypotheses and challenges appear beside yours exactly as the AI wrote them, and each statement cites its evidence; your own judgement of each hypothesis (supported, contradicted, retired and so on) is recorded next to it. Nothing is ever marked as confirmed. **Ask MDARIX** (Intelligence) answers questions from your organization's records and lists the evidence behind each answer.

### 4. Risk and regulatory reviews (Risk Reviewer, Regulatory Reviewer)

A **risk review** is needed when the case is high or critical priority, or a complaint in its scope reports a serious injury or a death. A **regulatory review** is needed when a complaint in scope reports a death, a serious injury or a malfunction, or the case is critical. The investigator requests them in the case's **Reviews** tab; a Risk or Regulatory Reviewer starts and completes them. An outcome asking for more evidence or escalating a safety or regulatory concern keeps the case waiting until a new review is completed.

### 5. The Decision Brief and its quality review (Quality Investigator, Quality Reviewer)

The investigator writes the **Decision Brief**: the problem, the evidence, the explanations considered, what is still unknown and the proposed conclusion. Submitting checks that the scope is complete, the evidence is reviewed, no urgent request is open and the required reviews are done; the problem statement and the proposed conclusion must be filled in. On submission the version is frozen with a fingerprint of its content.

A **Quality Reviewer** who did not write it then reviews the brief and either accepts it for decision, returns it to the author (for evidence, analysis, a risk review or a regulatory review), rejects the proposed conclusion, or escalates it to the Leaders. Every outcome except accepting needs a comment. A returned brief goes back to the author as a task; an accepted one goes to the decision makers' queue.

## Decisions and sign-off

1. In **Decisions**, **Approvals** lists the accepted briefs waiting for a signature (shown to people who may sign). Open one to see the brief and the case.
2. Acknowledge the unknowns that remain, choose the outcome (accept the conclusion, accept it with conditions, reject the conclusion and send the case back to work, or close with no further action) and write your remarks.
3. Sign with your password and the code from your authenticator app. MDARIX refuses the signature if you have no approval authority, if you wrote or edited the brief, or if the brief changed after it was accepted. Five wrong codes lock signing for 15 minutes.
4. The signature records who signed, what it means, when, the brief version and a fingerprint of everything it covered. A signed decision is never edited: a later decision supersedes it.
5. **Verify a signature** (in Decisions) shows whether each signature still matches what was signed. Anyone in the organization, Viewers included, can verify.

**After the decision.** Follow-ups the decision calls for (CAPA, product change, field action review, risk reassessment, regulatory action) become tasks for the right role. Evidence that arrives after the decision triggers an impact assessment; a material impact reopens the case. The case closes when its closure checks pass. In **Trust & Audit**, each case has its timeline, a replay of what was known when, the AI runs, an integrity check and an audited export.

Cases decided before the Decision Brief existed keep the earlier path in Decisions, Decision center (record the decision, a second person reviews it, an approver signs). New cases use the brief.

## Exports

- **Audit trail**: customer administrators export the organization's audit events as CSV from Audit in the console. Exports contain only your organization's events.
- Exporting needs the export permission, which every role holds except Viewer.

## Sessions

You are signed out after 30 minutes without activity and must sign in again after 12 hours at most. Two minutes before an inactivity sign-out, MDARIX asks whether you want to stay signed in. After signing in again you return to the page you were on. If MDARIX cannot be reached, the page says so and keeps trying; that is not a sign-out.

## Getting help

- **Help menu, "Report a problem"**: describe what happened and what you expected. The report reaches the MDARIX team with the page you were on and, when a request had just failed, its reference number. Do not include patient or personal data. If the report cannot be sent, the form offers an email to support instead.
- **Error references**: when something cannot be loaded, the message shows a reference for support. Quote it when you contact us; it lets us find the exact failed request.
- **Share feedback**: tell us what works and what to improve. Your answers go to the MDARIX team; nothing is shown publicly unless you agree to it, and you can withdraw that consent at any time.
- **Contact support** in the Help menu shows the support email address for your installation.
