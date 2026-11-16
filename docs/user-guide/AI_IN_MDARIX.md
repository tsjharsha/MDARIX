# AI in MDARIX

Plain-language guide for customer administrators, quality staff and trial users. AI is **off** unless every switch
below allows it; every step in MDARIX also works by hand, and Ask MDARIX always answers from your own records.

## What AI may do

| Feature | What it is for | Risk | What it must never do |
|---|---|---|---|
| Ask MDARIX | Answer a question from your organization's records, with citations | Low: advice you read | Answer without a cited record, or guess |
| Summaries | Summarise a signal's complaints; explain why a second-look record may be a complaint | Low | Say a record is or is not a complaint, or reportable |
| Case analysis | Propose an analysis, competing explanations and challenges for an investigation | Medium: a proposal you may turn into a record | State a root cause as fact, or rank explanations as decided |
| Drafting | Draft the investigation brief from reviewed analysis | Medium | Enter a Decision Brief or a report unreviewed |
| Evidence extraction | Propose observations from an evidence document, each with its source | Medium | Become evidence before a person accepts it |
| Code suggestions | Propose IMDRF codes from the complaint text | Medium | Be confirmed by "Confirm all codes" (not built yet) |
| Decision advisory | Advice beside a decision | — | **Not offered** |
| Regulatory drafting (the regulatory copilot) | Draft regulatory document sections | — | **Not offered** until AI is qualified; the rules draft is shown |

No feature may decide anything. MDARIX refuses to declare a feature that would.

## The switches (all must allow it)

1. **MDARIX's service** lists the features it allows. A feature it does not allow is shown off and locked.
2. **Your organization**: a customer administrator turns AI processing on under **Security › AI processing**,
   with a reason, an acknowledgement of where the records go, and **your password and authenticator code**.
3. **Each feature**: in the **AI features** table on the same page, each feature is turned on separately, again with
   a reason, your password and authenticator code. Turning a feature or AI off needs only a reason.
4. **Your monthly allowance**: when it is used up, features answer from rules until next month.

Every change is recorded in the audit trail with your reason.

## Reviewing AI output

Every AI output is labelled **"AI proposal, not reviewed"** until a person decides:

- **Accept**: it may now be used.
- **Edit**: write the corrected text and why; your text is used, the AI's stays in the history.
- **Reject**: say why; it is never used.

Until then it is not used anywhere that matters: not in the Decision Brief draft, not in the brief's facts, not in
the evidence summary, and the Decision Center's readiness ignores it. Reports list it with the label. Opening a case
never starts an AI run; a person asks for one.

## Free trials

- AI in a free trial works **only on the sample data** that came with the trial, and only on sample records nobody
  edited. On your own records the answer is "AI available on paid plans".
- Questions you type are limited to 300 characters. **Do not type real patient or complaint data.**
- AI uses free AI services that may process the sample data outside India. The trial's administrator switches AI on
  and confirms this first.
- MDARIX's Platform Administrator can set AI Active or Inactive for each person in the trial. A person whose switch is
  Inactive sees "AI is not enabled for your account". While the trial has not switched AI on, nobody has AI.
- Results from free AI services are never used to qualify AI for paid use.

## What is sent, and what is kept

- Personal information (e-mail addresses, phone numbers, dates of birth, identifying numbers, addresses and labelled
  names) is masked before anything is sent.
- MDARIX keeps one record per AI request: the feature, who asked, the model that answered and a fingerprint (hash) of
  what was sent, not the masked content itself.
