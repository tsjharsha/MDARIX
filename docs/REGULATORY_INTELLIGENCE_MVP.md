# MDARIX regulatory intelligence MVP

MDARIX provides tenant-scoped evidence organization and preparation workflows for `ESTAR_510K`, `GSPR`, `CER`, and `IFU`. Each generated claim carries a confidence definition, citation IDs, authoritative clause keys, and a traceability status. Untraceable claims are explicitly surfaced and require human review.

The official-source catalog currently covers FDA 510(k), EU MDR 2017/745, ISO 13485, and ISO 14971. FDA and EUR-Lex links point to public authoritative pages. ISO entries are metadata and official landing-page links only; licensed ISO text is not bundled. A customer may provide licensed clause content/indexes through the ingestion adapter.

Confidence semantics are fixed and tested:

- `HIGH`: verified authoritative citation and no contradiction.
- `MEDIUM`: relevant support exists but citation/evidence coverage is incomplete.
- `LOW`: incomplete, indirect, or contradicted; human review is required.
- `UNKNOWN`: insufficient verified evidence.

Document identities and immutable versions are persisted tenant-scoped through the regulatory API. Draft, review, approval, and archive transitions are audited with optimistic locking. eSTAR output is a preparation package, not an official FDA form or submission.

The implementation is advisory and preparation-only. It does not provide regulatory advice, automated approval, certified submission packages, or a claim that every statement is traceable when the source evidence is missing. Production-scale vector latency and licensed-source ingestion require deployment/customer evidence outside the local synthetic MVP.
