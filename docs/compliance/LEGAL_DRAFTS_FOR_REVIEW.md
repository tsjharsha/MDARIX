# Legal drafts for review

**Status: drafts for the lawyer. Not published.** Nothing in this file is on the website, in `legal/`, in the
application or in any email. Each section says what is missing today, proposes wording in the style of the current
documents, says where it would go, and lists the questions only the lawyer can answer. Once a section is approved,
engineering copies the approved text into the named file, sets its "Last updated" date and removes the section here.

Source: the final pre-launch compliance review of 18 October 2026 (findings CMP-12, CMP-13, CMP-14 and CMP-24). Prepared
for release 0.10.33 on 19 October 2026. The other findings of that review were fixed in 0.10.33 and are in the
published texts (see `CHANGELOG.md`).

**Owner rule that applies to every draft:** the website, the legal pages and the emails never show the founder's
personal name or address. Contacts are role-based (for example "Grievance Officer, grievance@mdarix.in"). Where the
law may require a named person, the draft says so as an open question instead of naming anyone.

Facts the drafts rely on (engineering keeps them true; `legal/README.md` has the full list):

- MDARIX is operated, during the product validation phase, by an individual in Hyderabad, India, while the company
  that will operate it is being registered (stated today in all three documents).
- Hosting and email are in India (Google Cloud Mumbai and Delhi; Zoho in India). AI is off for free trials, and the
  server refuses to switch it on for them.
- Sign-up is open worldwide except for the countries and regions listed in section 4. The country list includes every
  EU member state and the United Kingdom.
- Customers are asked not to upload patient-identifiable data during a trial. Complaint exports can still contain a
  reporter's or a healthcare professional's name.

---

## 1. CMP-12: a section for people in the EEA and the United Kingdom (GDPR and UK GDPR)

### Problem

MDARIX offers its trial to organizations in the EU and the UK (the sign-up list includes them; the site describes EU
MDR and UK reporting). GDPR Art. 3(2) and the UK GDPR then apply to the personal data MDARIX controls (requesters,
users, security records). The privacy policy today:

- names no lawful basis per purpose (Art. 13(1)(c));
- names no EU or UK representative (Art. 27), and does not say why none is needed;
- does not say how personal data reaches India from the EEA or the UK (Chapter V);
- gives customers' content (where MDARIX is a processor) only "we process it only on your instructions"
  (`terms.md` 4.2); a data processing agreement exists only for design partners, not for trials (Art. 28).

Retention periods per category, also asked for by Art. 13(2)(a), were added in 0.10.29 to 0.10.33.

### Proposed text

To go into `legal/privacy.md` as a new section after "Your rights":

> ## If you are in the European Economic Area or the United Kingdom
>
> The EU General Data Protection Regulation and the UK GDPR apply to the personal data we control about you. We rely
> on these legal bases:
>
> - **Your trial request, your account and the emails about them:** to take the steps you asked for before an
>   agreement and to perform the free trial agreement (contract).
> - **Sign-in and security records, server request logs, error and problem reports, and the audit trail:** our
>   legitimate interest in keeping the Service secure and working and in keeping a reliable record of what was done
>   in it. Where a customer needs the audit trail for its own legal obligations, we keep it for that customer.
> - **The record of which legal texts you accepted:** our legitimate interest in being able to show what was agreed.
> - **Publishing a quote from your feedback:** your consent, which you can withdraw at any time.
> - **Answering a questionnaire about the trial:** our legitimate interest in improving the Service; answering is
>   optional.
>
> Where our basis is legitimate interest, you can object at any time by writing to privacy@mdarix.in.
>
> **Where your data goes.** We process personal data in India (see "Where it is processed"). India is not covered by
> an adequacy decision of the European Commission or the UK. [Lawyer to complete: the transfer mechanism, for example
> the Standard Contractual Clauses and the UK Addendum in our data processing agreement, and how a person can obtain a
> copy.]
>
> **Our representative.** [Lawyer to complete: either the name and contact of our representative in the EU and in the
> UK, or the reason none is required.]
>
> **Complaints.** You can complain to the data protection authority where you live or work, or where you think the
> problem happened; in the UK, the Information Commissioner's Office.

To go into `legal/terms.md` 4.2 (and the trial agreement 3.3), replacing "Design partners receive a separate data
processing agreement with their order form":

> 4.2 Where your content contains personal data, we process it only on your documented instructions, as your
> processor, under the data processing terms in [Lawyer to complete: an annex to these terms, or a linked page]. They
> apply to every customer, including free trials. Design partners also sign them with their order form.

### Where it would go

- `legal/privacy.md`: new section "If you are in the European Economic Area or the United Kingdom".
- `legal/terms.md` 4.2 and `legal/trial-agreement.md` 3.3: processor terms for every customer, trials included.
- A new short data processing annex (Art. 28(3) items, the subprocessor list from `legal/SUBPROCESSORS.md`, breach
  notice within 72 hours as `privacy.md` already says, and the transfer clauses).

### Open questions for the lawyer

1. Is an Art. 27 representative needed in the EU and in the UK, or does the "occasional processing" exemption
   (Art. 27(2)(a)) apply to a free trial offered to businesses? If needed, who, and at what cost?
2. For the data MDARIX collects directly from people in the EEA or the UK (sign-up, accounts), does Chapter V apply
   at all (direct collection by a controller outside the EEA), or should the policy only describe where the data is?
3. For customer content, which mechanism: EU SCCs Module 2 (controller to processor) with the UK Addendum, signed as
   part of the trial agreement by click-wrap, or a signed DPA only once real data is uploaded?
4. Are the legal bases above the right ones, in particular legitimate interest for the audit trail and for the record
   of accepted texts?
5. Should the GDPR rights list replace the current "Depending on where you live" list, or sit beside it?

---

## 2. CMP-13: MDARIX is not a medical device and gives no medical, regulatory or legal advice

### Problem

The terms say decisions remain the customer's (3.1) and that MDARIX is not a validated system (3.3). They do not say
that MDARIX is not a medical device, that it gives no medical, clinical, legal or regulatory advice, or that its
outputs are not regulatory submissions. "Never submits anything to a regulator" is said only on the website
(/trust/regulations). The product shows reporting windows as counts of days (`backend/app/reportability/rules.py`),
readiness checks and inspection packs, which a customer could rely on.

### Proposed text

To go into `legal/terms.md` as a new 3.4:

> 3.4 MDARIX is not a medical device. It is not intended for the diagnosis, prevention, monitoring or treatment of any
> disease or injury, and it does not process patient data for any clinical purpose. It does not give medical, legal
> or regulatory advice. Reporting windows, readiness checks, signals, drafts and documents it produces are aids for
> your qualified staff, not regulatory submissions or determinations. MDARIX does not submit anything to any
> regulator. You remain responsible for deciding what is reportable, for checking the requirements and deadlines that
> apply to you, and for everything you submit.

To go into `legal/trial-agreement.md` 3.4, after "Decisions remain yours.":

> MDARIX is not a medical device and gives no medical, legal or regulatory advice; what it shows during the trial is
> an aid for your people, as the Terms of service (3.4) describe.

### Where it would go

- `legal/terms.md` new 3.4 (section "Decisions remain yours").
- `legal/trial-agreement.md` 3.4.
- Optionally the same sentence on `/trust/regulations`, next to "never submits anything to a regulator".

### Open questions for the lawyer

1. Does the intended-purpose wording above keep MDARIX outside the definition of medical device software under the
   EU MDR (Rule 11, MDCG 2019-11), the UK MDR 2002, the FDA's device software functions policy and India's Medical
   Devices Rules 2017? A regulatory specialist may need to confirm the qualification itself, not only the wording.
2. Is "not regulatory determinations" enough next to the liability cap (9.2), or should reliance on reporting
   windows be excluded expressly?
3. Should the same clause appear in the in-app "About" or help pages, not only in the terms?

---

## 3. CMP-14: who the customer contracts with, and the grievance contact

### Problem

The texts never name the operator: "the founder of MDARIX, operating it" (`terms.md`, `trial-agreement.md`,
`privacy.md`), and "Our contact for grievances under India's Digital Personal Data Protection Act, 2023 is the founder
of MDARIX, at that address" (`privacy.md`, Your rights). This follows the owner's rule that no personal name or
address appears on the site. But:

- a business customer cannot tell from the text who its contract is with;
- the IT (Reasonable Security Practices and Procedures and Sensitive Personal Data or Information) Rules, 2011, Rule
  5(9), ask a body corporate to publish the name and contact details of its Grievance Officer (passwords are sensitive
  personal data under those Rules);
- the DPDP Rules, once their notice and grievance provisions commence, ask for the business contact information of a
  person who can answer questions about the processing.

### Proposed text (role-based; no personal name or address)

To go into `legal/privacy.md`, replacing the grievance sentence in "Your rights":

> Our Grievance Officer handles complaints about how we process personal data, under India's Digital Personal Data
> Protection Act, 2023 and the Information Technology Rules, 2011: Grievance Officer, MDARIX, Hyderabad, Telangana,
> India, grievance@mdarix.in. We acknowledge a grievance within 24 hours and respond within one month of receiving it.

To go into `legal/terms.md`, after the first paragraph, and the same in the other two documents:

> Until the company is registered, MDARIX is operated by an individual sole proprietor based in Hyderabad, Telangana,
> India. The operator's full legal name and address are stated in each signed order form and data processing
> agreement, and we give them to any customer on request to support@mdarix.in.

### Where it would go

- `legal/privacy.md` "Your rights" (grievance) and the opening paragraph (who operates MDARIX).
- `legal/terms.md` and `legal/trial-agreement.md`, opening paragraph.
- Owner action before publishing: create the mailbox grievance@mdarix.in in Zoho Mail and decide who reads it.
- The 24-hour acknowledgement is a new promise; publish it only if the owner can keep it.

### Open questions for the lawyer

1. Is an individual operating MDARIX before registration a "body corporate" under Section 43A of the IT Act and the
   2011 Rules? If yes, does Rule 5(9) accept a designation ("Grievance Officer") with a role mailbox, or must a
   person's name be published? If a name is required, can it be the name of an appointed officer who is not the
   founder?
2. Do the DPDP Rules' "business contact information of a person" requirements accept a role and a mailbox?
3. Is "the operator's legal identity is in the order form and on request" acceptable for click-wrap trials, where no
   order form is signed? Does the Indian Contract Act or consumer law require the contracting party to be named in
   the click-wrap text itself?
4. When the company is registered: do the texts then name the company (which is not a personal name) with its
   registered office, and can the registered office be a commercial address rather than a home address?

---

## 4. CMP-24: sanctions and export control

### Problem

The sign-up country list included countries under comprehensive sanctions, and the terms have no sanctions or
export-control clause. Since 0.10.33 the list leaves out Cuba, Iran, North Korea and Syria, and the server refuses
those countries and the Crimea, so-called Donetsk People's Republic and Luhansk People's Republic regions (also typed
by name: `backend/app/trial/request_profile.py` `is_sanctioned_region`). There is no screening of people or
organizations against sanctions lists, and the terms still say nothing.

### Proposed text

To go into `legal/terms.md` as a new 2.4:

> 2.4 You confirm that your organization and your users are not located in, organized under the laws of, or
> ordinarily resident in a country or region subject to comprehensive sanctions, which today are Cuba, Iran, North
> Korea, Syria and the Crimea, so-called Donetsk People's Republic and so-called Luhansk People's Republic regions of
> Ukraine; and that none of them is named on, or owned or controlled by a person named on, a sanctions list of the
> United Nations, India, the European Union, the United Kingdom or the United States. You will not use the Service,
> or let anyone use it, in breach of sanctions or export-control laws. We may refuse or end a trial or subscription
> that would breach them.

To go into `legal/trial-agreement.md` as a new 1.5:

> 1.5 Trials are not offered to organizations in a country or region subject to comprehensive sanctions, or to
> anyone named on a sanctions list, as the Terms of service (2.4) describe.

### Where it would go

- `legal/terms.md` 2.4 and `legal/trial-agreement.md` 1.5.
- The country list in code (`frontend/src/features/auth/trialProfile.ts` `SANCTIONED_REGIONS` and
  `backend/app/trial/request_profile.py`) follows whatever list the lawyer approves.

### Open questions for the lawyer

1. Which regimes bind an India-based operator: UN sanctions as implemented in India, and which others? Do US export
   rules apply through the US cloud provider's terms (Google Cloud's terms restrict sanctioned countries), or because
   of US users and US-origin software?
2. Is the list right today? In particular Syria: the United States ended its Syria sanctions programme in mid-2025
   and the EU lifted most economic sanctions on Syria in May 2025, so it may no longer be "comprehensively"
   sanctioned. Should Russia or Belarus be treated differently from now (they are in the list as ordinary countries)?
3. Is a country check at sign-up enough during the validation phase, or is screening of the organization and the
   requester against consolidated lists needed before approval (manual review would be possible; automatic approval
   currently accepts company emails and, since 0.10.48, personal addresses such as Gmail at once)?
4. Should the refusal message name the reason (sanctions) or stay neutral, as it does now ("MDARIX cannot offer a free
   trial to organizations in this country or region")?
