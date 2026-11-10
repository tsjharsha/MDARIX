# ADR-002: Product as Core Object

## Context
Complaints are important, but medical-device decisions ultimately concern product reality.
## Decision
Product is the core R1 business object.
## Rationale
Complaints, investigations, risks, components, suppliers, lots, evidence, hypotheses, and decisions must connect to products and product versions.
## Consequences
Domain, UI, graph, API, and database contracts are product-centered.
## Alternatives Considered
Complaint-centered architecture was rejected because it narrows lifecycle reasoning.
## Status
ACCEPTED (owner, 10 Nov 2026)

## Acceptance gate
The decision holds only while all of these are true:
- Every applicable object carries its product, and its product version where a version applies.
- A version always belongs to its product and to that product's tenant.
- Filtering by version is correct: with a version chosen, every section shows that version's records, and anything
  that is genuinely product-level says so in its label.
- Relationships across versions are explicit (an investigation spanning two versions names both); none is implied.
- Historical records keep their original version; a later version never rewrites them.
- An unknown or unverified version is never silently converted to a known one: it is refused or shown as unknown.
