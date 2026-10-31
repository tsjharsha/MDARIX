// What MDARIX is beside the customer's systems (T-MSG): one message, the same words on the website, in the workspace,
// in the guides and in docs/user-guide (besideYourQms.test.tsx checks each place). It says only what ships today: a
// later release adds its part of the message when its feature ships, never before.

// 0.10.53 added the service-level close and the per-market assessment; 0.10.54 the signed documents (T-G35).
export const BESIDE_YOUR_QMS =
  "MDARIX works beside your QMS or complaint software. Your QMS keeps the complaint record, CAPA and change control. " +
  "MDARIX helps you decide and proves it: routine complaints close at service level with a documented reason, " +
  "serious ones are assessed per market, and you get signed documents to file in your QMS.";

// Reactive and proactive PMS, and the loop (T-MSG, F7.8), from 0.10.54: the trial guide, the in-app user guide and the
// management review report's PMS section (backend/app/readiness_home/summary.py PMS_FRAMING) say the same words. The
// sentence that MDARIX records the proactive sources joins only with the release that ships them.
export const PMS_FRAMING =
  "Post-market surveillance gathers data reactively, from what reaches you (complaints, service records, incidents, " +
  "field actions), and proactively, from what you go out to look for. The results feed one loop: PMS → risk " +
  "management → clinical evaluation → PSUR → back to the PMS plan.";

/** What MDARIX adds, in the trial today: where a place needs one more sentence. */
export const WHAT_MDARIX_ADDS =
  "MDARIX helps you find signals early, decide with evidence and prove each decision. A person always decides, and people submit every report.";
