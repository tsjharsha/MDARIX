# Executive Product Overview

MDARIX R1 is a medical-device lifecycle investigation and decision-intelligence platform. It connects records from systems of record, reconstructs product and temporal context, helps investigators inspect evidence and competing explanations, and preserves human decision authority.

## Core principle

MDARIX is a **system of intelligence, not a system of record**. QMS, PLM, ERP, supplier and manufacturing systems remain authoritative. MDARIX maintains governed context, provenance, mappings, investigation state, evidence relationships, AI execution records and human decisions.

## Primary MVP personas

- MDARIX Platform Administrator: controls customers, tenants, configuration, integrations, plans, security and audit.
- Customer Administrator: manages one tenant’s users, roles, mappings, connectors, security and audit visibility.
- Quality Investigator: frames a signal, reviews product context, evidence, hypotheses, unknowns and investigation briefs.
- Approver/decision authority: reviews evidence and signs or rejects governed decisions where authority permits.

## Core journey

1. A tenant is provisioned and connected to approved synthetic provider APIs.
2. Provider records are read through authenticated connector contracts.
3. Mapping, schema and provenance information are preserved.
4. Product, version, complaint, evidence and investigation context is assembled.
5. Investigators review facts, hypotheses, contradictions and unknowns.
6. AI may summarize authorized context, but remains advisory and human review is required.
7. A governed decision package is reviewed, signed and audited.

## MVP boundary

The current MVP is designed for synthetic validation customers and local validation infrastructure. Real customer credentials, production PostgreSQL TLS, hosted multi-instance evidence, production backup/PITR, production monitoring and customer acceptance evidence are not represented as complete.
