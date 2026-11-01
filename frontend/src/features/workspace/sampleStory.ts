// The free trial's sample dataset, explained (Getting started › sections/SampleData.tsx): what it holds, how it was
// made and the pain point each part re-creates, with the requirement behind it and the screen that shows it. The
// records are those backend/app/trial/sample_data.py writes when a trial is approved; the counts come from the
// trial's status (GET /api/v1/trial/status, `sample`). References come from the one catalog of standards
// (features/shared/standards.ts) where it has the exact entry, and are kept as written where it has none.
import { cite } from "../shared/standards";

export type SampleCounts = {
  products?: number;
  lots?: number;
  complaints?: number;
  investigations?: number;
  capas?: number;
  risks?: number;
};

export type SamplePain = {
  key: string;
  title: string;
  /** What the sample holds for this pain, point by point, as loaded at the start of the trial. */
  inSample: readonly string[];
  /** Why it matters: what an inspector or notified body checks, in one sentence. */
  requirement: string;
  /** The requirement it comes from (built with cite from the catalog). */
  reference: string;
  opens: { section: string; tab?: string };
  action: string;
};

export const SAMPLE_PAINS: readonly SamplePain[] = [
  {
    key: "routine",
    title: "Routine complaints that wait for a person",
    inSample: [
      "SAMPLE-RT-01 and RT-02: a filter re-seated on the phone and a frayed cable replaced, each ready to close at service level with one signature.",
      "SAMPLE-RT-03: the same cable wear three weeks earlier, already closed: with RT-02, a recurring matter.",
      "SAMPLE-RT-04: an alarm that belongs to the open investigation; SAMPLE-RT-05: a new failure mode, on the reportability watch.",
    ],
    requirement: "Every complaint is evaluated, and the decision not to investigate is recorded with its reason.",
    reference: cite("ISO13485_8_2_2"),
    opens: { section: "Complaints", tab: "Dispositions" },
    action: "Open the dispositions",
  },
  {
    key: "calls",
    title: "Calls logged as they come in",
    inSample: [
      "SAMPLE-CALL-01 to 04: four calls to the service desk, from a question about the instructions to a monitor taken out of use.",
      "SAMPLE-CALL-02 and SAMPLE-RT-05 are the same event, called in nine days before the formal complaint: a likely duplicate.",
      "SAMPLE-URG-01: free flow at set-up and a patient moved to intensive care, logged as urgent before the awareness time is known.",
    ],
    requirement: "Feedback is gathered as it arrives, and a possible complaint is judged without delay.",
    reference: cite("ISO13485_8_2_1", "ISO13485_8_2_2"),
    opens: { section: "Complaints", tab: "First contact" },
    action: "Open the first contacts",
  },
  {
    key: "hidden",
    title: "Complaints hidden in plain sight",
    inSample: [
      "SAMPLE-RV-01: a serious injury cancelled as a suspected duplicate.",
      "SAMPLE-RV-02: an inquiry that describes a patient choking.",
      "SAMPLE-RV-03 to 05: three No Fault Found returns on OrbitCare 300 within a year.",
    ],
    requirement: "Every complaint is evaluated, and investigated where the device may have failed.",
    reference: cite("ISO13485_8_2_2", "QMSR"),
    opens: { section: "Complaints", tab: "Second look" },
    action: "Open the second look",
  },
  {
    key: "clocks",
    title: "Reporting clocks already running",
    inSample: [
      "SAMPLE-RV-06: no occlusion alarm, patient moved to intensive care.",
      "SAMPLE-RV-07: zero flow for 40 seconds, staff switched to manual ventilation (France).",
      "SAMPLE-RV-08: free flow, patient outcome not yet known.",
      "Sample FDA and EU reporting windows of 30, 15 and 10 days.",
    ],
    requirement:
      "FDA reports within 30 calendar days (5 work days when remedial action is needed); EU serious incidents within 15 days, sooner for a death.",
    reference: cite("21 CFR 803", "MDR_87"),
    opens: { section: "Complaints", tab: "Reportability" },
    action: "Open the reportability watch",
  },
  {
    key: "harm-closed",
    title: "Harm closed without an investigation",
    inSample: [
      "SAMPLE-RV-09: an alarm too quiet to hear on a busy ward.",
      "The patient needed oxygen; the record was closed after a training call.",
    ],
    requirement: "A complaint that involves injury is investigated, or the reason it is not is recorded.",
    reference: cite("ISO13485_8_2_2"),
    opens: { section: "Readiness" },
    action: "See the inspection check",
  },
  {
    key: "trend",
    title: "A trend that started with a change",
    inSample: [
      "SAMPLE-CHG-014: OrbitCare 300 Rev B moved its pressure sensor to a new supplier and cut incoming inspection from 32 to 13 units per lot.",
      "Pressure-alarm complaints rose afterwards, mostly from lots 003 and 004.",
      "Lots carry quantities, so the rate is counted per unit in the field.",
      "PulseWatch 410 and VentraLink 250 stay flat, as a background.",
    ],
    requirement: "Complaint data is analysed for trends, and a significant increase is reported.",
    reference: cite("ISO13485_8_4", "MDR_88"),
    opens: { section: "Signals", tab: "Trend check" },
    action: "Open the trend check",
  },
  {
    key: "investigate",
    title: "An investigation with its evidence",
    inSample: [
      "SAMPLE-INV-001: why did pressure alarms rise after Rev B?",
      "Evidence: the supplier change, the incoming inspection results for lots 003 and 004, and the complaint trend.",
      "Its Decision Brief, written by a sample author, is waiting for your quality review and your signature.",
    ],
    requirement: "The cause is found before action is taken, and every conclusion traces back to its evidence.",
    reference: cite("ISO13485_8_2_2", "ISO13485_8_5_2"),
    opens: { section: "Investigations" },
    action: "Open the investigation",
  },
  {
    key: "capa",
    title: "CAPAs closed without proof they worked",
    inSample: [
      "SAMPLE-CAPA-01: closed without an effectiveness check.",
      "SAMPLE-CAPA-02: opened after the sample case's brief, due in 45 days; its effectiveness check is planned 30 days later.",
    ],
    requirement: "Corrective action is verified to be effective and to have no adverse effect.",
    reference: cite("ISO13485_8_5_2"),
    opens: { section: "Records", tab: "Effectiveness checks" },
    action: "Open the effectiveness checks",
  },
  {
    key: "reports",
    title: "Report worksheets and what happened to each",
    inSample: [
      "SAMPLE-RV-09: a finished US example, its FDA 3500A worksheet approved by a second person and its submission recorded with FDA's acknowledgements.",
      "SAMPLE-RV-10: an India report (MvPI worksheet) sent by e-mail and bounced, now waiting for a correction and a new approval.",
      "The organization's own US guide (your version 2) in use, and a draft whose own test fails, so it cannot be published.",
    ],
    requirement: "Reports go to the authority on time, and what was sent, when and with what result is kept.",
    reference: cite("ISO13485_8_2_3", "CFR803_50", "IN_MDR"),
    opens: { section: "Complaints", tab: "Reports" },
    action: "Open the reports",
  },
  {
    key: "follow-through",
    title: "Questions, owners and reminders",
    inSample: [
      "SAMPLE-RV-08: a question to the reporter for the patient's outcome, two attempts unanswered and the reply overdue.",
      "SAMPLE-RV-01: a request to the hospital that stayed unanswered after three attempts to each contact.",
      "The sample author is away for a week with you as the backup; SAMPLE-RV-08 and SAMPLE-RT-03 have you as their owner.",
    ],
    requirement: "Complaint handling keeps its records: who was asked what, when, and who answers for each event.",
    reference: cite("ISO13485_8_2_2"),
    opens: { section: "Complaints", tab: "Communications" },
    action: "Open the communications log",
  },
  {
    key: "lot-impact",
    title: "Which other lots share the suspect part",
    inSample: [
      "OrbitCare 300 Rev B's pressure sensor came from one sensor lot in lots 003 and 004, the lots with most pressure-alarm complaints, and in three lots without complaints yet (006 to 008).",
      "Where each lot went, with units still in stock; lot 008 has no distribution imported.",
    ],
    requirement:
      "Corrective action is proportionate to the effects of the problem, including the product already in the field.",
    reference: cite("ISO13485_8_5_2"),
    opens: { section: "Investigations", tab: "Scope" },
    action: "Open the case scope",
  },
  {
    key: "imports",
    title: "An import with rows set aside",
    inSample: [
      "Sample complaints export.xlsx: every row written or set aside, with its data-quality report.",
      "SAMPLE-RJ-01 has no description; SAMPLE-RJ-02 named a caller and a phone number, kept only as placeholders, and suggests harm, so it reaches triage.",
    ],
    requirement: "Records are complete and legible, and personal data is kept only where it is needed.",
    reference: cite("ISO13485_4_2_5"),
    opens: { section: "Import data" },
    action: "Open the import reports",
  },
  {
    key: "risk",
    title: "Post-market data that never reached the risk file",
    inSample: [
      "SAMPLE-RSK-01 and 02: OrbitCare risks no review has reassessed since the harm and malfunction complaints.",
      "SAMPLE-RSK-03: a VentraLink risk no review has reassessed since the malfunction complaints.",
      "PulseWatch 410: no risk recorded in MDARIX at all.",
    ],
    requirement: "Production and post-production information is fed back into the risk file.",
    reference: cite("ISO14971_10"),
    opens: { section: "Records", tab: "Risk file input" },
    action: "Open the risk file input",
  },
];

/** How the sample was made, in the order a quality lead would ask. */
export const SAMPLE_MADE: readonly string[] = [
  "Synthetic: written for MDARIX. No real company, device, patient or person, and no personal data.",
  "Built from the pain points above: each part re-creates a finding quality teams and inspectors keep meeting, so what MDARIX shows on the sample is what it looks for in your own records.",
  "Dated from the day your trial started, so reporting clocks, trends and due dates are live.",
  'Easy to tell apart: product, lot, complaint, investigation, CAPA and risk identifiers start with SAMPLE-, and product, supplier, evidence, CAPA and risk names end in "(Sample)".',
  "In your organization's workspace only. It does not count toward your upload limit; once your own data is in you can remove it (the trial owner, under About the sample data), and it is deleted with the trial's data in any case.",
];

/** The sample's size as short facts ("3 devices"), leaving out what the status did not count. */
export function sampleFacts(counts: SampleCounts | null | undefined): string[] {
  if (!counts) return [];
  const facts: [number | undefined, string, string][] = [
    [counts.products, "device", "devices"],
    [counts.lots, "lot", "lots"],
    [counts.complaints, "complaint", "complaints"],
    [counts.investigations, "investigation", "investigations"],
    [counts.capas, "CAPA", "CAPAs"],
    [counts.risks, "risk", "risks"],
  ];
  return facts
    .filter(([value]) => typeof value === "number" && Number.isFinite(value) && value > 0)
    .map(([value, one, many]) => `${value} ${value === 1 ? one : many}`);
}
