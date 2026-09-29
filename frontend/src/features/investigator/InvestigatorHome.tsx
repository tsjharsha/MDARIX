import { ArrowRight, CircleAlert, ClipboardCheck, FileSearch, ShieldCheck } from "lucide-react";
import type { AppView } from "../../app/router";

type InvestigatorHomeProps = {
  tenantName: string;
  userName: string;
  productName: string;
  version: string;
  investigationCount: number;
  evidenceCount: number;
  limitationsCount: number;
  onNavigate: (view: AppView) => void;
};

const steps: Array<{ view: AppView; label: string; description: string }> = [
  { view: "products", label: "Product reality", description: "Select the product and released version that define the case." },
  { view: "signals", label: "Signals & complaints", description: "Understand observed patterns without claiming causality." },
  { view: "investigations", label: "Investigation", description: "Scope the question and carry the same context forward." },
  { view: "evidence", label: "Evidence", description: "Review provenance, support, contradiction, and missing evidence." },
  { view: "ask", label: "Ask MDARIX", description: "Use tenant-authorized AI assistance with visible limitations." },
  { view: "decision", label: "Human decision", description: "Prepare review; only an authorized human decides." },
];

export function InvestigatorHome({ tenantName, userName, productName, version, investigationCount, evidenceCount, limitationsCount, onNavigate }: InvestigatorHomeProps) {
  return <div className="investigator-home content">
    <section className="investigator-welcome">
      <div><span className="eyebrow">Quality Investigator workspace</span><h2>Good afternoon, {userName}</h2><p>{tenantName} · Follow one connected story from product reality to a defensible human decision.</p></div>
      <div className="investigator-context"><span>Current case context</span><strong>{productName}</strong><small>{version ? `Version ${version}` : "Version not selected"}</small></div>
    </section>
    <section className="investigator-metrics" aria-label="My work summary">
      <button onClick={() => onNavigate("investigations")}><span>Open investigations</span><strong>{investigationCount}</strong><small>Continue authorized work</small></button>
      <button onClick={() => onNavigate("evidence")}><span>Linked evidence</span><strong>{evidenceCount}</strong><small>Trace source and provenance</small></button>
      <button onClick={() => onNavigate("investigations")}><span>Needs attention</span><strong>{limitationsCount}</strong><small>Unknowns, gaps, or limitations</small></button>
    </section>
    <section className="investigator-story"><div className="section-heading"><div><span className="eyebrow">Connected investigation story</span><h2>Product → evidence → decision</h2></div><p>Every step remains tenant-scoped and carries the selected product, version, investigation, and temporal context.</p></div><div className="investigator-step-grid">{steps.map((step, index) => <button key={step.view} onClick={() => onNavigate(step.view)}><span className="investigator-step-number">0{index + 1}</span><strong>{step.label}</strong><p>{step.description}</p><ArrowRight size={16} aria-hidden="true" /></button>)}</div></section>
    <section className="investigator-attention-grid">
      <article><CircleAlert size={20} /><div><span className="eyebrow">Evidence posture</span><h3>Separate facts from interpretation</h3><p>Supporting, contradicting, contextual, unknown, and missing evidence stay visible before review.</p></div><button className="secondary-link" onClick={() => onNavigate("evidence")}>Review evidence</button></article>
      <article><FileSearch size={20} /><div><span className="eyebrow">Investigation brief</span><h3>Prepare, do not decide</h3><p>AI can summarize authorized context, but causality, regulatory conclusions, and approvals remain human-controlled.</p></div><button className="secondary-link" onClick={() => onNavigate("investigations")}>Open workspace</button></article>
      <article><ShieldCheck size={20} /><div><span className="eyebrow">Trust and audit</span><h3>Trace every conclusion</h3><p>Use assurance and audit views to inspect provenance, temporal scope, limitations, and review status.</p></div><button className="secondary-link" onClick={() => onNavigate("assurance")}>Inspect assurance</button></article>
    </section>
    <section className="investigator-next"><ClipboardCheck size={20} /><div><strong>Recommended next action</strong><p>Start with the selected product version, inspect the current signal pattern, then open or continue the investigation.</p></div><button className="primary-action" onClick={() => onNavigate("products")}>Open Product 360 <ArrowRight size={16} /></button></section>
  </div>;
}
