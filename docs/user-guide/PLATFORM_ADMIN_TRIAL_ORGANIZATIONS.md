# Trial organizations (Platform Administrator)

Every free trial is handled in one place: **Platform Administration › Trial organizations**, in the left rail
directly after Customers & Tenants. Once a trial is approved it is listed only here. The customer lists (Customers,
Tenants, Subscriptions, renewals, customer users and administrators, the dashboard's customer figures) show pilot and
paying customers only. A trial converted to a pilot or a paid plan moves to Customers & Tenants.

Only a Platform Administrator (or MDARIX Administrator) can open this area or use its actions. The server checks this
on every request; hiding the menu from other roles is not the control. Every action is recorded in the trial's own
audit trail with your name, the time and your reason.

## The strip at the top

Five counts, each opening the place where it is handled:

| Count | Opens |
| --- | --- |
| Waiting for review | Requests |
| Active | Trials, filtered to active trials |
| Ending within 7 days | Trials, filtered to trials ending soon |
| Ended, data kept | Trials, filtered to ended trials whose data is still kept |
| Requests to end early waiting | Ending and deletion |

A trial in a **grace period** (a grace end set on Plans & Licensing › Subscriptions) counts as running until the grace
period ends, because its users can still sign in.

## Requests

Free-trial requests from the website. Requests from company e-mail addresses are approved automatically; the others
wait here.

- **Approve** creates the private 30-day trial workspace with sample data and e-mails the requester an invitation.
  Tick **Sample only** for an event or judge trial: the organization then cannot upload or import its own data.
- **Decline** needs a reason, which is kept for the audit. Nothing is created.
- **Resend invitation** when the first e-mail did not arrive.

Below the trial requests are the requests made from inside a trial: a pilot conversation and a one-to-one demo.

## Trials

One row per trial: company and MDARIX ID, trial owner, start and end, days left, extension used, users, sample data,
activity and support access. Filter by state (Active, Ending soon, Ended, Ended early, Data deleted, Converted), search
by name, MDARIX ID or the owner's e-mail, and sort by a column heading. Every filter is paged and sorted on the server.
The default order puts the trials that need a person first.

A trial in a grace period shows as running, with its days left counted to the grace end and "(grace period)" next to
them.

Click a row to open the **trial page**:

- **Header**: the company, its state, days left and the one next step in plain words.
- **Dates**: start, original end, current end, the grace period when there is one, the extension used of 30 days, and
  when the data will be deleted once the trial has ended.
- **People**: the owner and every user, invited or active.
- **Sample data**: loaded, removed by the owner or restarted, with counts, and how many of the organization's own rows
  were imported.
- **Activity**: the chapters the trial acted in, its last activity, a demo request and feedback.
- **AI and usage**: today one read-only line, "AI is off for free trials (trial terms)".
- **History**: the trial's audit events, newest first.

### Actions on the trial page

Each button is shown enabled only when the server would accept it; otherwise the reason is shown under it. Each opens
a drawer that states the effect in one sentence before you confirm.

| Action | What it does | Rules |
| --- | --- | --- |
| **Extend** | Moves the end by 1 to 30 days | A reason of 10 characters or more. In total a trial can run at most 30 days past its original end. A trial that ended normally can be reopened while its data is still kept, never after an early end, deletion or conversion, nor while the owner's request to end it waits. In a grace period the days count from the grace end. |
| **End early** | Ends the trial now | A reason of 10 characters or more. MDARIX raises an exit request "Ended by MDARIX" and approves it in the same step. The data is kept for 30 days; the owner is e-mailed. If the owner has already asked to end the trial, decide on that request instead. A trial in a grace period can be ended early. |
| **Convert to pilot or paid** | Moves the organization onto a pilot or paid plan | Any active plan except Free Trial. The Free Trial stays in the plan history and the owner becomes Customer Administrator. The organization leaves the trial lists and appears in Customers & Tenants. Refused while an exit request waits or after the data was deleted. |
| **Delete data now** | Deletes the trial's records and uploads and archives the workspace | Only when the retention rules say it is due: 30 days or more after the end, no legal hold and no open request to move the data into a pilot. Type the organization's name to confirm. The audit trail is kept. |
| **Open support workspace** | Read-only support access | As on Security › Support access: a second Platform Administrator approves, then the trial owner decides. |

A refused action (for example an extension past the 30 days) is recorded as refused, with its reason code, and
nothing changes.

## Ending and deletion

- **Requests to end early**: the owner's requests, to approve (with or without deleting the data) or decline.
- **Trials due for deletion**: trials whose 30 days after the end have passed. Open one to delete its data now.
  **Run deletion now** runs the nightly deletion at once for every due trial: the dialog lists the trials it will
  delete and the ones a legal hold or an open pilot request keeps, before you confirm.
- **Former trials**: converted trials (with the kind, plan and date, and **Open in Customers**) and trials whose data
  was deleted. Read-only.

## Feedback

Trial feedback and website quotes, as before.

## Where trials still appear outside this area

Audit trails, Security › Support access and Operations (queues and problem reports) keep showing trials, labelled
"Trial": an audit or security view never hides records.
