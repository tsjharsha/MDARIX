# Domain and data model

MDARIX separates control-plane identity/configuration from tenant business data. Core domains are customer/tenant lifecycle, products and versions, complaints/signals, investigations, evidence, hypotheses/unknowns, risks, scenarios, decisions, integrations, mappings, AI executions, audit and signatures.

The canonical relationships are: customer → tenant → environment/data plane; product → product version → components/suppliers/sites/lots; complaint → investigation → evidence/hypothesis/decision. Provenance and tenant identifiers must remain on every business read, export and AI context.

Status: the model and migrations exist for the synthetic MVP. Do not infer that every UI subsection has a dedicated workflow or that production schemas have been validated.
