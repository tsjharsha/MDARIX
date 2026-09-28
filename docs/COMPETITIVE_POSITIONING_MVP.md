# MDARIX MVP competitive positioning and validation plan

## Target customer

The initial design partner is a medical-device manufacturer with an active
post-market or product-quality investigation that crosses QMS/complaint,
PLM/product-version, ERP/manufacturing, supplier, and evidence sources. The
primary users are quality investigators and regulatory reviewers; secondary
users are product/R&D, supplier quality, manufacturing quality, and executives.

## Focused MVP promise

MDARIX is an evidence-bounded investigation intelligence layer above existing
systems of record. It helps a team move from a complaint or signal to a
reviewable human decision by connecting product reality, temporal context,
provenance, contradictions, unknowns, and governed approval. It does not
replace a QMS/PLM/ERP, make a regulatory determination, or claim certified
submission capability.

## Differentiation hypothesis

| Alternative | Their typical system-of-record focus | MDARIX MVP position |
|---|---|---|
| Veeva / TrackWise / MasterControl | Quality, complaint, CAPA, and regulated records | Connect investigation context across those records and product reality |
| Greenlight Guru | Product development and quality workflows | Trace a post-market question across released product, evidence, and field context |
| Ketryx | Software lifecycle, requirements, and compliance traceability | Combine cross-system product investigation, uncertainty, and human decision review |
| Custom spreadsheets/search | Fast local analysis but weak governance and provenance | Preserve tenant scope, field policy, source provenance, audit, and review state |

This is a positioning hypothesis, not a claim that MDARIX has benchmarked or
outperforms any named vendor. Vendor comparisons must be re-reviewed before
publication and must not use competitor logos or unsupported feature claims.

## Design-partner scorecard

Record baseline and MDARIX results for the same investigation type:

| Metric | Definition | Evidence | Target is agreed with partner |
|---|---|---|---|
| Complaint-to-investigation time | First qualified signal timestamp → investigation opened | Source/audit timestamps | TBD |
| Evidence retrieval time | Investigation request → first reviewable evidence set | Retrieval and audit timestamps | TBD |
| Mapping/import success | Valid records imported ÷ records attempted | Connector run and reconciliation | TBD |
| Decision traceability | Decisions with finding → hypothesis → observation → evidence → source links | Decision/audit evidence | 100% for pilot decisions |
| Isolation result | Foreign records exposed across API/search/export/AI/attachments | Automated test report | 0 exposures |
| Review rework | Evidence requests or reopened review packages per case | Case history | Baseline then improvement |

No ROI, time saving, customer reference, or case-study claim may be published
until a named partner approves the measurement method and the underlying
evidence.

## Pilot protocol

1. Select one investigation archetype and record the baseline process.
2. Agree scope, data boundary, users, success thresholds, and privacy terms.
3. Use synthetic validation data or customer-approved data only.
4. Run the same investigation through MDARIX and capture timestamps, mappings,
   evidence links, isolation results, and decision traceability.
5. Review the results with the partner and record limitations and deviations.
6. Obtain written approval before using any reference, metric, logo, or case
   study in sales or website material.

## Current status

- Product positioning hypothesis: **implemented in website copy and this plan**.
- Measurement framework: **implemented**.
- Customer ROI evidence: **pending named design partner execution**.
- Design-partner validation: **pending external participant**.
- Customer references/case studies: **pending written approval**.

