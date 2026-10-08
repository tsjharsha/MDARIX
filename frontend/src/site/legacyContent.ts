// Content of the original MDARIX public site, preserved verbatim when the site was consolidated into 8 pages.
// The new pages (./pages.tsx) are built from these objects so no copy is lost; edit wording here.
export type MenuItem = { label: string; href: string; future?: boolean; description?: string };
export type MenuGroup = { title: string; items: MenuItem[] };
const current = (label: string, href: string, description?: string): MenuItem => ({ label, href, description });
const future = (label: string, anchor: string): MenuItem => ({ label, href: `/platform/${anchor}` });

export const menus: Record<string, MenuGroup[]> = {
  Platform: [
    {
      title: "Product Intelligence",
      items: [
        current("Product 360", "/platform/product-360", "See product, version, configuration, and lifecycle context."),
        current(
          "Product Reality Graph",
          "/platform/reality-graph",
          "Connect product, supplier, lot, complaint, change, and evidence relationships.",
        ),
        current(
          "ProductVersion Intelligence",
          "/platform/product-version",
          "Compare revisions, scope, and impact with traceable context.",
        ),
        current(
          "Timeline Intelligence",
          "/platform/timeline",
          "Understand what changed, when it became effective, and when it became known.",
        ),
      ],
    },
    {
      title: "Investigation Intelligence",
      items: [
        current(
          "Ask MDARIX",
          "/platform/ask-mdarix",
          "Ask a controlled investigation question and preserve its scope.",
        ),
        current("Investigation Workspace", "/platform/investigation"),
        current("Evidence Intelligence", "/platform/evidence"),
        current("Hypothesis Intelligence", "/platform/hypotheses"),
        current("AI Challenger", "/platform/challenger"),
        current("Unknowns Radar", "/platform/unknowns"),
      ],
    },
    {
      title: "Decision Intelligence",
      items: [
        current("Failure Chain Intelligence", "/platform/failure-chain"),
        current("Counterfactual Analysis", "/platform/counterfactual"),
        current("Decision Center", "/platform/decision-center"),
        current("Investigation Brief", "/platform/investigation-brief"),
      ],
    },
    {
      title: "Trust & Governance",
      items: [
        current("AI Assurance", "/platform/ai-assurance"),
        current("AI Provenance", "/platform/ai-provenance"),
        current("Human Review & Approval", "/platform/human-review"),
        current("Audit Trail", "/platform/audit-trail"),
        current("Enterprise Administration", "/platform/enterprise-administration"),
      ],
    },
  ],
  Solutions: [
    {
      title: "By Challenge",
      items: [
        current("Investigate Complaint Increases", "/solutions#complaints"),
        current("Understand Product Changes", "/solutions#changes"),
        current("Find Affected Products & Lots", "/solutions#affected"),
        current("Investigate Supplier Issues", "/solutions#supplier"),
        current("Connect Fragmented Evidence", "/solutions#evidence"),
        current("Challenge Suspected Root Causes", "/solutions#challenge"),
        current("Identify Missing Evidence", "/solutions#unknowns"),
      ],
    },
    {
      title: "By Role",
      items: [
        current("Quality Leaders", "/solutions#quality-leaders", "See the full investigation picture."),
        current("Investigators / QA", "/solutions#investigators", "Move from signal to evidence."),
        current("Regulatory Affairs", "/solutions#regulatory", "Prepare traceable review context."),
        current("Product / R&D", "/solutions#product", "Connect changes to outcomes."),
        current("Supplier Quality", "/solutions#supplier-quality", "Follow supplier and component relationships."),
        current("Manufacturing Quality", "/solutions#manufacturing", "Understand affected lots and changes."),
        current("Executives", "/solutions#executives", "Review decision-ready assurance."),
      ],
    },
    {
      title: "By Investigation",
      items: [
        current("Complaint Investigation", "/solutions#complaint-investigation"),
        current("ProductVersion Investigation", "/solutions#version-investigation"),
        current("Change Investigation", "/solutions#change-investigation"),
        current("Supplier Investigation", "/solutions#supplier-investigation"),
        current("Component Investigation", "/solutions#component-investigation"),
        current("Lot / Batch Investigation", "/solutions#lot-investigation"),
        current("Risk & Failure Investigation", "/solutions#risk-investigation"),
        current("Cross-System Investigation", "/solutions#cross-system"),
      ],
    },
    {
      title: "Investigate with MDARIX",
      items: [
        current(
          "Why did complaints increase after Rev B?",
          "/platform/investigation",
          "Follow a signal through product version, change, component, supplier, lots, evidence, hypotheses, unknowns, assurance, and human decision.",
        ),
      ],
    },
  ],
  "Product Lifecycle": [
    {
      title: "Discover & Define",
      items: [
        future("Product Strategy", "strategy"),
        future("User / Clinical Need", "clinical-need"),
        future("Product Requirements", "requirements"),
      ],
    },
    {
      title: "Develop & Prove",
      items: [
        future("Design & Development", "design"),
        future("Design Controls", "design-controls"),
        future("Verification & Validation", "verification"),
        future("Clinical Intelligence", "clinical"),
        future("Regulatory Intelligence", "regulatory"),
      ],
    },
    {
      title: "Build & Release",
      items: [
        future("Manufacturing Intelligence", "manufacturing"),
        current("Supplier Intelligence", "/platform/supplier-intelligence"),
        current("Component Intelligence", "/platform/component-intelligence"),
        current("Lot / Batch Intelligence", "/platform/lot-batch-intelligence"),
        current("Change Intelligence", "/platform/change-intelligence"),
      ],
    },
    {
      title: "Monitor, Improve & Evolve",
      items: [
        current("Complaint Intelligence", "/solutions#complaints"),
        current("Post-Market Investigation", "/platform/investigation"),
        future("Signal Intelligence", "signal"),
        current("Evidence Intelligence", "/platform/evidence"),
        future("CAPA Intelligence", "capa"),
        future("Field Action / Recall Intelligence", "recall"),
        current("Product Change Intelligence", "/platform/timeline"),
        future("Continuous Monitoring", "monitoring"),
        future("Product Retirement", "retirement"),
      ],
    },
  ],
  Trust: [
    {
      title: "A Different Intelligence Layer",
      items: [
        current("Not Another QMS", "/why-mdarix#not-qms", "Keep existing systems of record."),
        current(
          "Product Reality",
          "/why-mdarix#product-reality",
          "Understand relationships across lifecycle information.",
        ),
        current("Investigation Intelligence", "/why-mdarix#investigation", "Investigate across connected context."),
        current(
          "Evidence Before Inference",
          "/why-mdarix#evidence",
          "Separate facts, interpretations, hypotheses, and decisions.",
        ),
      ],
    },
    {
      title: "Trustworthy Investigation",
      items: [
        current("Challenge the Explanation", "/why-mdarix#challenge"),
        current("AI You Can Inspect", "/why-mdarix#inspectable-ai"),
        current("Humans Decide", "/why-mdarix#humans-decide"),
      ],
    },
    {
      title: "Questions MDARIX Helps Explore",
      items: [
        current("What changed before the signal?", "/solutions#changes"),
        current("Which versions and lots are affected?", "/solutions#affected"),
        current("What evidence contradicts the cause?", "/solutions#challenge"),
        current("What information is still missing?", "/solutions#unknowns"),
      ],
    },
    {
      title: "Trust Foundations",
      items: [
        current("AI Assurance", "/platform/ai-assurance"),
        current("Security & Access", "/security"),
        current("Plans & Entitlements", "/plans"),
        current("Integration Approach", "/integrations"),
      ],
    },
  ],
  Company: [
    {
      title: "Company",
      items: [
        current("Why MDARIX", "/why-mdarix", "Evidence-first investigation intelligence for medical-device teams."),
        current("Our approach", "/company", "A governed intelligence layer above existing systems of record."),
        current("Contact", "/request-demo", "Discuss your investigation workflow with MDARIX."),
      ],
    },
    {
      title: "Trust",
      items: [
        current("Security & access", "/security"),
        current("AI assurance", "/ai-trust"),
        current("Integration approach", "/integrations"),
      ],
    },
  ],
};

// Keep the lifecycle menu distinct from the platform's generic investigation pages.
const lifecycleMonitorGroup = menus["Product Lifecycle"].find((group) => group.title === "Monitor, Improve & Evolve");
if (lifecycleMonitorGroup) {
  lifecycleMonitorGroup.items = lifecycleMonitorGroup.items.map((item) =>
    item.label === "Post-Market Investigation"
      ? current(item.label, "/platform/post-market-surveillance")
      : item.label === "Evidence Intelligence"
        ? current(item.label, "/platform/lifecycle-evidence-intelligence")
        : item,
  );
}

export const pages: Record<string, { eyebrow: string; title: string; copy: string }> = {
  "/": {
    eyebrow: "Product investigation intelligence for medical devices",
    title: "Turn post-market signals into defensible product decisions.",
    copy: "Connect complaints, product context, lifecycle evidence, risk, and human review in one governed investigation story.",
  },
  "/platform": {
    eyebrow: "Platform & AI",
    title: "A connected intelligence layer for product investigation.",
    copy: "Reconstruct product reality, investigate competing explanations, expose contradictions and unknowns, and preserve traceable human decisions.",
  },
  "/solutions": {
    eyebrow: "Solutions",
    title: "Start with the question your team needs to answer.",
    copy: "Investigate complaint increases, product changes, affected lots, supplier issues, fragmented evidence, suspected causes, and missing information across systems.",
  },
  "/product-lifecycle": {
    eyebrow: "Product lifecycle",
    title: "Intelligence from product definition through post-market evolution.",
    copy: "Current investigation capabilities anchor a broader lifecycle vision. Future areas are identified clearly without implying working functionality.",
  },
  "/why-mdarix": {
    eyebrow: "Why MDARIX",
    title: "Evidence before inference. Challenge before conclusion.",
    copy: "MDARIX works above your existing systems of record to reconstruct product reality and make investigation intelligence inspectable.",
  },
  "/resources": {
    eyebrow: "Resources",
    title: "Explore product investigation intelligence.",
    copy: "Learn how MDARIX connects product reality, evidence, temporal context, investigation, decisions, assurance, and governance.",
  },
  "/roadmap": {
    eyebrow: "Product roadmap",
    title: "Current capabilities and the broader lifecycle direction.",
    copy: "Future roadmap areas are informational and do not represent available workflows or committed release dates.",
  },
  "/integrations": {
    eyebrow: "Integrations",
    title: "Work above the systems you already trust.",
    copy: "QMS, PLM, ERP, MES, supplier, document, and evidence platforms remain authoritative systems of record.",
  },
  "/security": {
    eyebrow: "Security & access",
    title: "Controlled, separated by organization, and traceable by design.",
    copy: "Authentication, role and field authorization, action controls, provenance, and human authority form the current security foundation. Independent certification is not claimed.",
  },
  "/ai-trust": {
    eyebrow: "AI trust",
    title: "Grounded intelligence with visible limits.",
    copy: "MDARIX preserves evidence references, temporal context, contradictions, unknowns, provenance, and human review. AI does not create the final regulated decision.",
  },
  "/request-demo": {
    eyebrow: "Get started",
    title: "Try MDARIX free for 30 days.",
    copy: "Your own private workspace, ready-made sample data, and simple templates to try your own records. No credit card, no integration project.",
  },
  "/company": {
    eyebrow: "Company",
    title: "A more defensible way to investigate product reality.",
    copy: "MDARIX is designed for medical-device teams that need connected evidence, visible uncertainty, and accountable human decisions.",
  },
};

export const solutionHeroVisuals: Record<string, { src: string; alt: string }> = {
  complaints: {
    src: "/medtech-solution-complaints.png",
    alt: "MedTech complaint signals connected to product versions and evidence",
  },
  changes: {
    src: "/medtech-solution-changes.png",
    alt: "MedTech product change investigation connected to field evidence",
  },
  affected: {
    src: "/medtech-solution-affected.png",
    alt: "MedTech products and manufacturing lots mapped for impact review",
  },
  supplier: {
    src: "/medtech-solution-supplier.png",
    alt: "MedTech supplier, component, site, and lot relationships under review",
  },
  evidence: {
    src: "/medtech-solution-evidence.png",
    alt: "MedTech evidence intelligence view with provenance and evidence gaps",
  },
  challenge: {
    src: "/medtech-solution-challenge.png",
    alt: "MedTech competing explanations compared against authorized evidence",
  },
  unknowns: {
    src: "/medtech-solution-unknowns.png",
    alt: "MedTech investigation unknowns and missing evidence highlighted for review",
  },
  "quality-leaders": {
    src: "/medtech-role-quality-leaders.png",
    alt: "Quality leaders reviewing medical-device signals, evidence strength, risk context, and decisions",
  },
  investigators: {
    src: "/medtech-role-investigators.png",
    alt: "Medical-device investigators connecting complaints, versions, suppliers, lots, hypotheses, and unknowns",
  },
  regulatory: {
    src: "/medtech-role-regulatory.png",
    alt: "Regulatory reviewer inspecting a medical-device evidence package with provenance and approval controls",
  },
  product: {
    src: "/medtech-role-product.png",
    alt: "Medical-device product and research team comparing design revisions, components, versions, and field outcomes",
  },
  "supplier-quality": {
    src: "/medtech-role-supplier-quality.png",
    alt: "Supplier quality professional tracing a component from supplier through lot to field signal",
  },
  manufacturing: {
    src: "/medtech-role-manufacturing.png",
    alt: "Manufacturing quality team reviewing production lots, process observations, and device signals",
  },
  executives: {
    src: "/medtech-role-executives.png",
    alt: "Executive team reviewing a decision-ready medical-device risk and evidence summary",
  },
  "complaint-investigation": {
    src: "/medtech-investigation-complaint.png",
    alt: "Medical-device complaints connected to product versions, field reports, and evidence",
  },
  "version-investigation": {
    src: "/medtech-investigation-version.png",
    alt: "Medical-device hardware and software versions compared with field signals and evidence",
  },
  "change-investigation": {
    src: "/medtech-investigation-change.png",
    alt: "Medical-device design and manufacturing changes linked to post-market outcomes",
  },
  "supplier-investigation": {
    src: "/medtech-investigation-supplier.png",
    alt: "Medical-device supplier, component, lot, and field signal relationships",
  },
  "component-investigation": {
    src: "/medtech-investigation-component.png",
    alt: "Medical-device component lineage traced from specification through field evidence",
  },
  "lot-investigation": {
    src: "/medtech-investigation-lot.png",
    alt: "Medical-device manufacturing lots, distribution paths, and complaint evidence mapped for review",
  },
  "risk-investigation": {
    src: "/medtech-investigation-risk.png",
    alt: "Medical-device hazards, controls, residual risk, and evidence connected for investigation",
  },
  "cross-system": {
    src: "/medtech-investigation-cross-system.png",
    alt: "QMS, PLM, ERP, supplier, and manufacturing systems connected in a medical-device investigation",
  },
};

export const capabilityCopy: Record<string, { eyebrow: string; title: string; copy: string }> = {
  challenger: {
    eyebrow: "Current capability · AI Challenger",
    title: "Challenge the explanation before it becomes a conclusion.",
    copy: "Compare competing explanations against authorized medical-device evidence while keeping contradictions, unknowns, limitations, and human responsibility visible.",
  },
  "ai-assurance": {
    eyebrow: "Current capability · AI Assurance",
    title: "Inspect how advisory intelligence is bounded and reviewed.",
    copy: "Make grounding, uncertainty, provider limitations, safety controls, and human review requirements visible around every AI-assisted investigation step.",
  },
  "ai-provenance": {
    eyebrow: "Current capability · AI Provenance",
    title: "Trace every insight back to its evidence context.",
    copy: "Connect observations, source records, temporal scope, provenance, and authorized retrieval so reviewers can inspect where an AI-assisted interpretation came from.",
  },
  "human-review": {
    eyebrow: "Current capability · Human Review",
    title: "Keep accountable people at the decision boundary.",
    copy: "Bring evidence, contradictions, gaps, remarks, version context, and approval controls together so humans remain responsible for governed decisions.",
  },
  "audit-trail": {
    eyebrow: "Current capability · Audit Trail",
    title: "Preserve the story of what changed, who acted, and why.",
    copy: "Follow investigation events, record versions, evidence actions, approvals, and provenance in a reviewable audit story.",
  },
  "enterprise-administration": {
    eyebrow: "Current capability · Enterprise Administration",
    title: "Operate tenants, access, integrations, and configuration from one governed control plane.",
    copy: "Give platform administrators a clear view of customer boundaries, identity, mappings, integrations, AI assurance, security, and operational health.",
  },
};

// What a design partner can use today, what is built together during a pilot, and what is planned. Keep this in
// step with the product: nothing moves to "Available today" until it works for a customer.
export const capabilityStatus: { label: string; text: string; items: string[] }[] = [
  {
    label: "Available today",
    text: "In every workspace, including the free trial.",
    items: [
      "Product 360: products, versions, lots, components and suppliers",
      "Complaint signals and investigations with competing hypotheses",
      "Evidence, contradictions and open questions kept side by side",
      "AI answers that show the evidence they used and flag anything unverified",
      "Human decisions with electronic signatures and an audit trail",
      "CSV import with templates and a personal-data check",
      "Roles, customer administration and authenticator-app MFA",
    ],
  },
  {
    label: "With design partners",
    text: "Built and validated together during a pilot.",
    items: [
      "Live connections to your QMS, PLM, ERP and supplier systems",
      "Mapping your fields and reference data to the MDARIX model",
    ],
  },
  {
    label: "Planned",
    text: "Not available yet.",
    items: [
      "Single sign-on (OpenID Connect and SAML)",
      "Ready-made connectors for named vendor systems",
      "A dedicated database for each customer",
    ],
  },
];

export const lifecycleContent: Record<string, { eyebrow: string; title: string; copy: string }> = {
  strategy: {
    eyebrow: "Product lifecycle · Discover",
    title: "Turn market and patient needs into a governed product direction.",
    copy: "Frame the intended use, target users, clinical problem, market need, business goals, and regulatory pathway before detailed design work begins.",
  },
  "clinical-need": {
    eyebrow: "Product lifecycle · Discover",
    title: "Define the clinical need and the outcome the device must support.",
    copy: "Connect user needs, patient populations, care settings, clinical risks, and measurable outcomes so product requirements begin with a clear clinical purpose.",
  },
  requirements: {
    eyebrow: "Product lifecycle · Define",
    title: "Translate user needs into traceable product requirements.",
    copy: "Establish functional, safety, performance, usability, software, security, and regulatory requirements with ownership, rationale, and verification intent.",
  },
  design: {
    eyebrow: "Product lifecycle · Develop",
    title: "Manage design decisions with evidence attached to every requirement.",
    copy: "Coordinate design outputs, interfaces, risk controls, configuration decisions, and revisions while preserving traceability from requirement to implementation.",
  },
  "design-controls": {
    eyebrow: "Product lifecycle · Develop",
    title: "Make design controls visible from planning through release.",
    copy: "Organize design inputs, outputs, reviews, verification, validation, change control, and approval evidence into a reviewable design history.",
  },
  verification: {
    eyebrow: "Product lifecycle · Prove",
    title: "Show that the design meets its specified requirements.",
    copy: "Bring test protocols, results, deviations, failures, corrective actions, and approval records together so verification status is inspectable and complete.",
  },
  clinical: {
    eyebrow: "Product lifecycle · Prove",
    title: "Connect clinical evidence to product decisions.",
    copy: "Maintain the relationship between clinical evaluation, intended use, benefit-risk reasoning, usability evidence, and the product configuration under review.",
  },
  regulatory: {
    eyebrow: "Product lifecycle · Release",
    title: "Prepare a traceable regulatory evidence story.",
    copy: "Draft regulatory narratives from the evidence of the exact product version, with every statement citing its source. MDARIX drafts for your team to review and approve; it does not submit anything to a regulator.",
  },
  manufacturing: {
    eyebrow: "Product lifecycle · Build",
    title: "Connect released design intent to manufacturing reality.",
    copy: "Relate manufacturing processes, suppliers, components, lots, deviations, inspections, and release records back to the approved product configuration.",
  },
  signal: {
    eyebrow: "Product lifecycle · Monitor",
    title: "Detect and investigate signals across the installed product base.",
    copy: "Combine complaints, service data, adverse events, returns, trends, and product-version context to distinguish emerging signals from isolated observations.",
  },
  capa: {
    eyebrow: "Product lifecycle · Improve",
    title: "Move from a confirmed issue to controlled improvement.",
    copy: "Link investigation findings to containment, root-cause analysis, corrective and preventive actions, effectiveness checks, owners, and approval evidence.",
  },
  recall: {
    eyebrow: "Product lifecycle · Act",
    title: "Coordinate field action decisions with complete product scope.",
    copy: "Identify affected versions, lots, markets, customers, risk rationale, communications, execution status, and evidence for a controlled field action.",
  },
  monitoring: {
    eyebrow: "Product lifecycle · Monitor",
    title: "Continuously watch product performance and evidence quality.",
    copy: "Track trends, thresholds, open unknowns, supplier performance, complaint patterns, and changes that may alter the product risk picture.",
  },
  retirement: {
    eyebrow: "Product lifecycle · Evolve",
    title: "Retire products with traceability and accountability.",
    copy: "Preserve the final configuration, support obligations, residual risks, records, customer impact, and regulatory responsibilities through product retirement.",
  },
  "supplier-intelligence": {
    eyebrow: "Product lifecycle · Build & Release",
    title: "Understand supplier connections behind product signals.",
    copy: "A product issue may involve a component, material, supplier, or supplier change. MDARIX helps teams connect supplier and component information with product records and emerging signals, supporting clearer investigations and impact assessments.",
  },
  "component-intelligence": {
    eyebrow: "Product lifecycle · Build & Release",
    title: "See how component relationships affect product decisions.",
    copy: "Components connect product design, suppliers, manufacturing, risk, and field performance. MDARIX helps teams see these relationships in context, making it easier to assess whether a component-related issue may affect other products or versions.",
  },
  "lot-batch-intelligence": {
    eyebrow: "Product lifecycle · Build & Release",
    title: "Assess lot and batch context when investigating product signals.",
    copy: "Lot and batch information can help teams assess the scope and distribution of a potential issue. MDARIX connects lot context with product, manufacturing, supplier, and post-market records to support structured investigation and impact review.",
  },
  "change-intelligence": {
    eyebrow: "Product lifecycle · Build & Release",
    title: "Understand the product impact of every change.",
    copy: "Changes to design, components, suppliers, processes, labeling, or software can affect requirements, risks, evidence, and products in the field. MDARIX helps teams connect change proposals to those relationships so impact assessments are supported by product context.",
  },
};

Object.assign(lifecycleContent, {
  "post-market-surveillance": {
    eyebrow: "Product lifecycle · Monitor, Improve & Evolve",
    title: "Turn post-market information into connected product insight.",
    copy: "Post-market surveillance brings together complaints, adverse events, service information, returns, trends, and other field evidence. MDARIX connects this information to products, versions, lots, risks, investigations, and decisions so teams can review emerging signals in context.",
  },
  "lifecycle-evidence-intelligence": {
    eyebrow: "Product lifecycle · Monitor, Improve & Evolve",
    title: "Make lifecycle evidence easier to find, connect, and evaluate.",
    copy: "Evidence is most useful when reviewers can see the product question, risk, investigation, or decision it supports. MDARIX preserves source, version, date, provenance, contradictions, limitations, and missing links across the lifecycle.",
  },
});

export const anchorPages: Record<string, { eyebrow: string; title: string; copy: string }> = {
  complaints: {
    eyebrow: "Solution · Complaint signals",
    title: "Find out what changed before complaints increased.",
    copy: "Connect complaint patterns to product versions, changes, components, suppliers, lots, and evidence so investigators can separate a signal from a conclusion.",
  },
  changes: {
    eyebrow: "Solution · Product changes",
    title: "Understand the changes that shaped the signal.",
    copy: "Compare product revisions and controlled changes with complaint timing, affected lots, configuration, and supporting evidence.",
  },
  affected: {
    eyebrow: "Solution · Affected products and lots",
    title: "Trace impact from version to lot.",
    copy: "Follow product versions, component relationships, suppliers, and lot context to identify what is affected and what remains unknown.",
  },
  supplier: {
    eyebrow: "Solution · Supplier investigation",
    title: "Connect supplier context to product reality.",
    copy: "Bring supplier, component, change, lot, and complaint relationships into one investigation workspace.",
  },
  evidence: {
    eyebrow: "Solution · Evidence intelligence",
    title: "Make evidence visible before inference.",
    copy: "Review source anchors, reliability, temporal context, contradictions, and missing evidence before forming a hypothesis.",
  },
  challenge: {
    eyebrow: "Solution · AI Challenger",
    title: "Challenge the explanation before it becomes a conclusion.",
    copy: "Expose competing hypotheses, contradictions, unknowns, and limitations so authorized humans can review the reasoning.",
  },
  unknowns: {
    eyebrow: "Solution · Unknowns radar",
    title: "See what the investigation still cannot establish.",
    copy: "Surface incomplete traceability, missing lot references, unsupported failure chains, and other evidence gaps.",
  },
  "quality-leaders": {
    eyebrow: "Role · Quality leaders",
    title: "Give quality leaders the full investigation picture.",
    copy: "Review product reality, evidence quality, competing explanations, assurance, and human decisions in one governed view.",
  },
  investigators: {
    eyebrow: "Role · Investigators / QA",
    title: "Move from signal to evidence with confidence.",
    copy: "Build a traceable investigation across product, change, supplier, lot, complaint, evidence, and hypothesis context.",
  },
  regulatory: {
    eyebrow: "Role · Regulatory affairs",
    title: "Prepare traceable review context.",
    copy: "Preserve provenance, limitations, temporal context, and human review boundaries for regulated investigation workflows.",
  },
  product: {
    eyebrow: "Role · Product and R&D",
    title: "Connect product changes to outcomes.",
    copy: "Understand how revisions, components, configuration, and lifecycle events relate to downstream signals.",
  },
  "supplier-quality": {
    eyebrow: "Role · Supplier quality",
    title: "Follow supplier and component relationships.",
    copy: "Investigate supplier-linked signals with affected lots, component revisions, evidence, and missing context in view.",
  },
  manufacturing: {
    eyebrow: "Role · Manufacturing quality",
    title: "Understand affected lots and changes.",
    copy: "Connect manufacturing context to product versions, lots, complaints, evidence, and investigation decisions.",
  },
  executives: {
    eyebrow: "Role · Executives",
    title: "Review decision-ready assurance.",
    copy: "See what is known, what is challenged, what remains unresolved, and where human authorization is required.",
  },
};

export const solutionOverrides: Record<string, { eyebrow: string; title: string; copy: string }> = {
  complaints: {
    eyebrow: "Solution · Complaint signals",
    title: "Understand what is driving an increase in complaints.",
    copy: "A rise in complaints may relate to a product version, component, supplier, lot, market, or change. MDARIX helps teams review these connections in context, explore possible patterns, and document the evidence behind their assessment.",
  },
  changes: {
    eyebrow: "Solution · Product changes",
    title: "See how product changes relate to field experience.",
    copy: "Design, component, supplier, software, and manufacturing changes can affect products already in use. MDARIX connects change history with product context and post-market signals to help teams assess possible relationships.",
  },
  affected: {
    eyebrow: "Solution · Affected products and lots",
    title: "Map potential impact across products and lots.",
    copy: "When an issue is identified, teams need to understand which products, versions, configurations, or lots may be involved. MDARIX connects these records to organize scope assessment and review supporting relationships.",
  },
  supplier: {
    eyebrow: "Solution · Supplier investigation",
    title: "Follow supplier relationships through to product impact.",
    copy: "Supplier-related issues can affect multiple components, products, and lots. MDARIX connects supplier records with product and post-market context to support a complete review of potential impact.",
  },
  evidence: {
    eyebrow: "Solution · Evidence intelligence",
    title: "Bring scattered evidence into the decision context.",
    copy: "Relevant information can be spread across quality, regulatory, product, supplier, and manufacturing systems. MDARIX connects available records to the issue under review and makes missing evidence visible.",
  },
  challenge: {
    eyebrow: "Solution · AI Challenger",
    title: "Test suspected causes against connected evidence.",
    copy: "A plausible cause should be evaluated against available facts and alternative explanations. MDARIX organizes hypotheses, supporting or conflicting evidence, and uncertainty before a conclusion.",
  },
  unknowns: {
    eyebrow: "Solution · Unknowns radar",
    title: "Make evidence gaps visible before decisions are finalized.",
    copy: "MDARIX identifies missing, outdated, or conflicting evidence links so reviewers understand what is known, what remains uncertain, and what still needs attention.",
  },
  "complaint-investigation": {
    eyebrow: "Solution - Complaint investigation",
    title: "Understand the signal before deciding what changed.",
    copy: "Connect complaint patterns to product versions, field reports, affected lots, and supporting evidence so investigators can frame the right question without overstating causality.",
  },
  "version-investigation": {
    eyebrow: "Solution - Version investigation",
    title: "See which product version belongs in the investigation.",
    copy: "Compare released versions, effective dates, configuration context, changes, and field experience to keep the review anchored to the correct device revision.",
  },
  "change-investigation": {
    eyebrow: "Solution - Change investigation",
    title: "Trace product changes to the outcomes they may affect.",
    copy: "Relate design, component, supplier, software, and manufacturing changes to post-market signals and evidence while keeping relationships distinct from proof.",
  },
  "supplier-investigation": {
    eyebrow: "Solution - Supplier investigation",
    title: "Follow supplier context through to product impact.",
    copy: "Connect supplier, component, site, lot, change, and field records to support a complete review of potential product impact.",
  },
  "component-investigation": {
    eyebrow: "Solution - Component investigation",
    title: "Trace a component across the device lifecycle.",
    copy: "Bring specifications, suppliers, revisions, manufacturing context, affected products, and field evidence together for a focused component review.",
  },
  "lot-investigation": {
    eyebrow: "Solution - Lot investigation",
    title: "Map lot context before assessing scope.",
    copy: "Connect manufacturing lots, sites, distribution paths, products, complaints, and evidence to make potential impact and remaining gaps visible.",
  },
  "risk-investigation": {
    eyebrow: "Solution - Risk investigation",
    title: "Keep risk review connected to evidence and controls.",
    copy: "Relate hazards, risk controls, residual-risk observations, product context, and investigation evidence while preserving human review and approval boundaries.",
  },
  "cross-system": {
    eyebrow: "Solution - Cross-system investigation",
    title: "Bring the investigation together across systems of record.",
    copy: "Use governed mappings to connect QMS, PLM, ERP, supplier, and manufacturing context while each source remains authoritative and provenance stays visible.",
  },
};

// Each date is the year the document was published; reference pages that change continuously have no date.
export const postMarketResources: {
  type: string;
  date: string | null;
  title: string;
  text: string;
  href: string;
}[] = [
  {
    type: "FDA guidance",
    date: "2025",
    title: "AI-enabled medical devices: lifecycle and postmarket performance considerations",
    text: "FDA draft guidance covering lifecycle documentation, transparency, bias, and postmarket performance monitoring for AI-enabled devices.",
    href: "https://www.fda.gov/news-events/press-announcements/fda-issues-comprehensive-draft-guidance-developers-artificial-intelligence-enabled-medical-devices",
  },
  {
    type: "FDA guidance",
    date: "2022",
    title: "Postmarket Surveillance under Section 522",
    text: "Final guidance on active, systematic, scientifically valid collection, analysis, and interpretation of marketed-device information.",
    href: "https://www.fda.gov/regulatory-information/search-fda-guidance-documents/postmarket-surveillance-under-section-522-federal-food-drug-and-cosmetic-act",
  },
  {
    type: "EU guidance",
    date: "2025",
    title: "MDCG 2025-10: Post-market surveillance guidance",
    text: "European Commission guidance for post-market surveillance of medical devices and in vitro diagnostic medical devices.",
    href: "https://health.ec.europa.eu/latest-updates/mdcg-2025-10-guidance-post-market-surveillance-medical-devices-and-vitro-diagnostic-medical-devices-2025-12-19_en",
  },
  {
    type: "EU / AI guidance",
    date: "2025",
    title: "MDCG 2025-6: FAQ on the interplay between the MDR/IVDR and the AI Act",
    text: "Joint guidance discussing post-market monitoring, interaction with other AI systems, and integration with existing MDR/IVDR monitoring plans.",
    href: "https://health.ec.europa.eu/latest-updates/mdcg-2025-6-faq-interplay-between-medical-devices-regulation-vitro-diagnostic-medical-devices-2025-06-19_en",
  },
  {
    type: "WHO publication",
    date: "2021",
    title: "Guidance for post-market surveillance and market surveillance of medical devices",
    text: "A practical framework for collecting and evaluating experience from marketed devices and identifying when action may be needed.",
    href: "https://www.who.int/publications/i/item/9789240015319",
  },
  {
    type: "WHO publication",
    date: "2021",
    title: "Generating evidence for AI-based medical devices",
    text: "Framework for training, validation, evaluation, and post-deployment monitoring of AI-based medical devices.",
    href: "https://iris.who.int/bitstream/handle/10665/349093/9789240038462-eng.pdf",
  },
  {
    type: "FDA resource",
    date: null,
    title: "FDA AI-enabled medical device list",
    text: "Reference list of AI-enabled devices authorized for marketing in the United States; useful for landscape and surveillance research.",
    href: "https://www.fda.gov/medical-devices/artificial-intelligence-enabled-medical-devices/list-artificial-intelligence-enabled-medical-devices",
  },
  {
    type: "FDA resource",
    date: null,
    title: "FDA postmarket requirements and safety monitoring",
    text: "FDA overview of reporting, device tracking, surveillance studies, recalls, and other postmarket obligations and resources.",
    href: "https://www.fda.gov/medical-devices/device-advice-comprehensive-regulatory-assistance/postmarket-requirements-devices",
  },
];

export const platformCapabilityData: Record<
  string,
  { kicker: string; summary: string; stats: string[]; cards: { title: string; text: string }[]; steps: string[] }
> = {
  "ask-mdarix": {
    kicker: "Ask MDARIX · governed investigation intelligence",
    summary:
      "Ask a focused question about an authorized investigation and receive a bounded response that keeps source evidence, temporal scope, uncertainty, and human responsibility visible.",
    stats: ["Authorized retrieval", "Cited evidence", "Uncertainty visible", "Human review"],
    cards: [
      {
        title: "Start with a precise question",
        text: "Frame the issue, product, ProductVersion, time window, and investigation scope before retrieval begins.",
      },
      {
        title: "Retrieve only what you can access",
        text: "Tenant, role, field, and record policies remain authoritative; a prompt cannot widen access or reveal hidden data.",
      },
      {
        title: "Separate answer from evidence",
        text: "Show supporting sources, contradictions, unknowns, missing evidence, and limitations alongside the interpretation.",
      },
      {
        title: "Abstain when the record is weak",
        text: "Unsupported causal claims are bounded or declined rather than presented as facts.",
      },
      {
        title: "Keep people accountable",
        text: "AI assists investigation; authorized reviewers decide what is accepted, escalated, or sent for further evidence.",
      },
    ],
    steps: ["Question", "Scope", "Retrieve", "Cite", "Challenge", "Review"],
  },
  "product-360": {
    kicker: "Product intelligence · MedTech product 360",
    summary:
      "A decision-ready view of a medical device as it exists across product versions, intended configuration, components, suppliers, manufacturing lots, complaints, investigations, risks, and evidence.",
    stats: ["Product + versions", "Components + suppliers", "Lots + field signals", "Evidence + decisions"],
    cards: [
      {
        title: "Configuration at a glance",
        text: "See the released device configuration, active components, revision identifiers, suppliers, sites, and status in one controlled product context.",
      },
      {
        title: "Version-aware impact",
        text: "Compare ProductVersions and follow a complaint or change to the affected configuration without losing source provenance.",
      },
      {
        title: "Manufacturing context",
        text: "Relate components, supplier records, sites, lots, and release history to the product configuration under review.",
      },
      {
        title: "Post-market connection",
        text: "Bring complaints, service observations, investigations, risks, and evidence into the same product story.",
      },
      {
        title: "Safe decision support",
        text: "Show missing links, contradictions, temporal limits, and unsupported conclusions instead of hiding uncertainty.",
      },
      {
        title: "Searchable product record",
        text: "Find a device, revision, component, supplier, lot, or linked signal quickly, then narrow the view by status, date, and authorized scope.",
      },
      {
        title: "Data quality you can inspect",
        text: "Surface missing attributes, conflicting source values, stale relationships, and unresolved mapping issues before they affect a review.",
      },
      {
        title: "Connected system handoff",
        text: "Use governed APIs and versioned mappings to exchange context with PLM, QMS, ERP/MES, and supplier systems while preserving ownership of source data.",
      },
    ],
    steps: [
      "Product",
      "Versions",
      "Configuration",
      "Components",
      "Suppliers",
      "Lots",
      "Signals",
      "Evidence",
      "Decision",
    ],
  },
  "reality-graph": {
    kicker: "Product Reality Graph · connected MedTech context",
    summary:
      "Map how a device, its versions, components, suppliers, sites, lots, changes, complaints, and evidence relate—so investigators can inspect the product story without mistaking a relationship for proof.",
    stats: ["Product relationships", "Configuration context", "Field signals", "Evidence provenance"],
    cards: [
      {
        title: "One connected product story",
        text: "Start with a product or signal and traverse the authorized links that explain its configuration, manufacturing context, and field experience.",
      },
      {
        title: "Relationship-first investigation",
        text: "Use the graph to locate relevant components, suppliers, lots, changes, complaints, and observations across the device lifecycle.",
      },
      {
        title: "Context before causality",
        text: "A graph path organizes evidence context; it does not automatically establish a root cause or regulatory conclusion.",
      },
      {
        title: "Visible gaps and conflicts",
        text: "Highlight missing links, inconsistent source values, temporal limits, and contradictory evidence before review.",
      },
      {
        title: "Ready for governed action",
        text: "Carry provenance, scope, uncertainty, and human accountability from exploration into the decision package.",
      },
    ],
    steps: ["Product", "Version", "Component", "Supplier", "Lot", "Signal", "Evidence", "Review"],
  },
  "product-version": {
    kicker: "ProductVersion intelligence · controlled MedTech release history",
    summary:
      "Keep every medical-device revision anchored to its product identity, approved configuration, effective dates, verification context, and field experience—so reviewers can see exactly which version was relevant to an investigation.",
    stats: ["Revision identity", "Change control", "Verification context", "Field impact"],
    cards: [
      {
        title: "A controlled revision record",
        text: "Keep product identity separate from ProductVersion identity, status, effective dates, and release ownership.",
      },
      {
        title: "Change-to-evidence trace",
        text: "Relate software or configuration changes to requirements, verification observations, complaints, affected lots, and review evidence.",
      },
      {
        title: "Release readiness context",
        text: "Make approval state, superseded versions, known limitations, and required human review visible before a release is relied upon.",
      },
      {
        title: "Temporal clarity",
        text: "Separate current, event-as-of, and known-as-of views so historical context is not rewritten by later updates.",
      },
      {
        title: "Impact without overclaiming",
        text: "Identify potentially affected products, components, sites, and signals while keeping causal conclusions bounded by evidence.",
      },
    ],
    steps: ["Product", "Revision", "Change", "Verify", "Release", "Monitor", "Impact", "Review"],
  },
  timeline: {
    kicker: "Timeline Intelligence · temporal MedTech context",
    summary:
      "Reconstruct the sequence around a product signal and distinguish when a change became effective, when it was recorded, and when the organization could have known about it.",
    stats: ["Effective dates", "Recorded events", "Known context", "Review points"],
    cards: [
      {
        title: "See the sequence",
        text: "Place product, version, configuration, supplier, lot, complaint, and evidence events on one readable investigation timeline.",
      },
      {
        title: "Three views of time",
        text: "Switch between current, event-as-of, and known-as-of context without mixing their meaning or rewriting history.",
      },
      {
        title: "Explain the change window",
        text: "Identify what changed before or after a signal, which records support the timing, and where the chronology is incomplete.",
      },
      {
        title: "Review with provenance",
        text: "Keep each event tied to its source, organization, product version and limitations before it informs a human decision.",
      },
    ],
    steps: ["Effective", "Recorded", "Known", "Change", "Signal", "Evidence", "Review"],
  },
  "post-market-surveillance": {
    kicker: "Post-market surveillance",
    summary:
      "Connect complaints, adverse events, service information, returns, trends, and field evidence to the products, versions, lots, risks, investigations, and decisions they inform.",
    stats: ["Complaints", "Field signals", "Product scope", "Review actions"],
    cards: [
      {
        title: "Connect field information",
        text: "Bring post-market records together with product, version, lot, component, supplier, and manufacturing context.",
      },
      {
        title: "Review emerging signals",
        text: "Explore patterns over time while keeping source records, limitations, and review rationale visible.",
      },
      {
        title: "Support governed action",
        text: "Link surveillance findings to investigations, risk review, CAPA, field action assessment, and human decisions.",
      },
    ],
    steps: ["Field data", "Product context", "Signal", "Investigation", "Assessment", "Action"],
  },
  "lifecycle-evidence-intelligence": {
    kicker: "Evidence intelligence",
    summary:
      "Make lifecycle evidence easier to find, connect, and evaluate by preserving its source, version, date, provenance, contradictions, limitations, and missing links.",
    stats: ["Sources", "Provenance", "Evidence gaps", "Decisions"],
    cards: [
      {
        title: "Keep evidence in context",
        text: "Link evidence to products, requirements, risks, investigations, changes, claims, assessments, and decisions.",
      },
      {
        title: "Expose limitations",
        text: "Make missing, outdated, conflicting, or weak evidence relationships visible before review conclusions are formed.",
      },
      {
        title: "Preserve the decision trail",
        text: "Show which evidence supported an assessment and retain the human review boundary around the decision.",
      },
    ],
    steps: ["Source", "Context", "Evidence", "Gap", "Review", "Decision"],
  },
};

export const investigationCapability = {
  kicker: "Investigation - governed MedTech review workspace",
  summary:
    "Move from a complaint or field signal to a structured, evidence-grounded investigation. MDARIX keeps product context, competing explanations, unknowns, provenance, and human review visible at every step.",
  stats: ["Signal context", "Evidence chain", "Hypotheses visible", "Human decision"],
  cards: [
    {
      title: "Frame the investigation",
      text: "Define the question, product and ProductVersion scope, time window, owner, and review objective before analysis begins.",
    },
    {
      title: "Build the evidence chain",
      text: "Connect complaints, changes, components, suppliers, lots, observations, and source records without rewriting authoritative systems.",
    },
    {
      title: "Compare explanations",
      text: "Keep hypotheses, supporting evidence, contradictions, failure chains, and unknowns separate so a plausible story is not mistaken for proof.",
    },
    {
      title: "Make gaps actionable",
      text: "Show missing tests, unavailable sources, stale records, and unresolved relationships so reviewers know what to investigate next.",
    },
    {
      title: "Prepare a governed decision",
      text: "Assemble a versioned brief with provenance and limitations; authorized humans remain responsible for conclusions and approvals.",
    },
  ],
  steps: ["Signal", "Scope", "Context", "Evidence", "Hypotheses", "Unknowns", "Review"],
};
export const evidenceCapability = {
  kicker: "Evidence - connected MedTech intelligence",
  summary:
    "Bring quality, product, supplier, manufacturing, and post-market records into one authorized evidence context. MDARIX preserves provenance, relationships, contradictions, and gaps so teams can review before they decide.",
  stats: ["Source provenance", "Product context", "Evidence gaps", "Review traceability"],
  cards: [
    {
      title: "Collect the evidence",
      text: "Connect source records from QMS, PLM, ERP, supplier, service, and post-market systems while keeping each system authoritative.",
    },
    {
      title: "Anchor every record",
      text: "Relate observations to the right product, ProductVersion, component, supplier, lot, complaint, investigation, and time window.",
    },
    {
      title: "Separate fact from inference",
      text: "Keep observed information distinct from interpretations, hypotheses, recommendations, and human decisions.",
    },
    {
      title: "Expose contradictions",
      text: "Make conflicting values, stale records, unavailable sources, and incomplete relationships visible instead of hiding uncertainty.",
    },
    {
      title: "Prepare traceable review",
      text: "Carry citations, source identifiers, limitations, and reviewer responsibility into the investigation brief and decision package.",
    },
  ],
  steps: ["Sources", "Context", "Provenance", "Evidence", "Gaps", "Review", "Decision"],
};
