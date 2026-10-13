// The free trial's sample dataset, explained (Getting started › sections/SampleData.tsx): what it holds, how it was
// made and the pain point each part re-creates, with the requirement behind it and the screen that shows it. The
// records are those backend/app/trial/sample_data.py writes when a trial is approved; the counts come from the
// trial's status (GET /api/v1/trial/status, `sample`).

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
  /** The requirement it comes from. */
  reference: string;
  opens: { section: string; tab?: string };
  action: string;
};

export const SAMPLE_PAINS: readonly SamplePain[] = [
  {
    key: "hidden",
    title: "Complaints hidden in plain sight",
    inSample: [
      "SAMPLE-RV-01: a serious injury cancelled as a suspected duplicate.",
      "SAMPLE-RV-02: an inquiry that describes a patient choking.",
      "SAMPLE-RV-03 to 05: three No Fault Found returns on OrbitCare 300 within a year.",
    ],
    requirement: "Every complaint is evaluated, and investigated where the device may have failed.",
    reference: "ISO 13485 clause 8.2.2, part of FDA's QMSR since 2 February 2026",
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
    reference: "21 CFR 803; EU MDR Article 87",
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
    reference: "ISO 13485 clause 8.2.2",
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
    reference: "ISO 13485 clause 8.4; EU MDR Article 88",
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
    reference: "ISO 13485 clauses 8.2.2 and 8.5.2",
    opens: { section: "Investigations" },
    action: "Open the investigation",
  },
  {
    key: "capa",
    title: "CAPAs closed without proof they worked",
    inSample: [
      "SAMPLE-CAPA-01: closed without an effectiveness check.",
      "SAMPLE-CAPA-02: its effectiveness check is due in 12 days.",
    ],
    requirement: "Corrective action is verified to be effective and to have no adverse effect.",
    reference: "ISO 13485 clause 8.5.2",
    opens: { section: "Records", tab: "Effectiveness checks" },
    action: "Open the effectiveness checks",
  },
  {
    key: "risk",
    title: "Post-market data that never reached the risk file",
    inSample: [
      "SAMPLE-RSK-01 to 03: risks no review has reassessed since the harm and malfunction complaints.",
      "PulseWatch 410: no risk recorded in MDARIX at all.",
    ],
    requirement: "Production and post-production information is fed back into the risk file.",
    reference: "ISO 14971:2019 clause 10",
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
  "In your organization's workspace only. It does not count toward your upload limit, and it is deleted with the trial's data.",
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
