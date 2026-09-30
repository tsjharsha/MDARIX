# MDARIX MVP AI Validation Report

## Scope

This report covers the MVP AI surface using synthetic tenant data planes. Production
provider operations, billing reconciliation, hosted monitoring, and customer
credentials are intentionally outside the MVP scope.

## Completed implementation

- Provider abstraction supports Groq and Ollama with deterministic fail-closed fallback.
- Prompt/context safety controls remain enabled: tenant authorization, field filtering,
  provenance, temporal scope, bounded output, no hidden chain-of-thought persistence,
  and mandatory human review.
- Ask MDARIX now keeps control-plane identity, entitlement, and audit checks separate
  from data-plane product, investigation, evidence, hypothesis, and retrieval reads.
- Investigation, hypothesis, challenger, failure-chain, scenario, counterfactual,
  and Decision Brief routes now resolve business sessions through the tenant data-plane
  dependency.
- AI context is built from authorized tenant-scoped records and preserves evidence
  provenance, unknowns, contradictions, and limitations.

## Validation evidence

- Focused backend AI regression: **51 passed, 3 warnings**.
- Ask/retrieval integration and grounding regression: **7 passed, 2 warnings**.
- Frontend production build: **passed**.
- Authenticated Chromium AI workflow test: **passed** across Ask MDARIX,
  Investigations, Evidence, Decision, AI Assurance, and Audit pages.
- Mobile Chromium AI workflow test: **passed**.
- `git diff --check`: **passed**.

## MVP conclusion

The AI implementation and tenant data-plane routing are complete for the internal
synthetic-data MVP. Responses remain advisory and must not be treated as regulatory,
causal, approval, or external-write decisions.

## Explicitly outside MVP scope

- Production provider credentials, monitoring, and cost reconciliation.
- Hosted multi-instance deployment evidence.
- Real customer endpoints and schemas.
- Production retention, backup, and disaster-recovery evidence.
