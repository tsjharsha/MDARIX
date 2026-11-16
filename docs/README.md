# MDARIX documentation

Start here. Current verified state lives in [../STATUS.md](../STATUS.md); when a
document below disagrees with STATUS.md or with the code, the code and
STATUS.md win.

| Folder | Contents | Status |
|---|---|---|
| [handover/](handover/00_MDARIX_R1_HANDOVER_INDEX.md) | 56-part product and technical handover; single entry point [MDARIX_R1_COMPLETE_HANDOVER.md](MDARIX_R1_COMPLETE_HANDOVER.md) | Current overview |
| [product/](product/) | MVP scope and demo readiness, competitive positioning, demo tenant manifest | Current |
| [architecture/](architecture/) | System, database, data-plane, frontend, AI boundary, audit, signature, reporting and MVP capability designs. Target state: [MDARIX_TARGET_ARCHITECTURE_DESIGN.md](architecture/MDARIX_TARGET_ARCHITECTURE_DESIGN.md) (control plane + tenant cell, approved 2026-10-08), its [implementation plan](architecture/MDARIX_TARGET_ARCHITECTURE_IMPLEMENTATION_PLAN.md) and the [production database review](architecture/MVP1_PRODUCTION_DATABASE_ARCHITECTURE_REVIEW.md) that led to it; [baselines/](architecture/baselines/) records the pre-change state | Current reference |
| [architecture/admin/](architecture/admin/) | Platform and Customer Administration specifications | Current reference |
| [architecture/mapping/](architecture/mapping/) | Mapping Studio and canonical mapping designs | Current reference |
| [architecture/future/](architecture/future/) | Target-state designs that are **not built** yet | Future |
| [specs/](specs/) | Original R1 product/architecture specifications and per-capability contracts (Day 1 freeze onward) | Reference; some details superseded |
| [adr/](adr/) | Architecture decision records: ADR-001…ADR-010 (still *Proposed*); ADR-011…ADR-016 (*Accepted* 2026-10-08: control plane and tenant cell, data placement, deployment roles, cell identity and packages, platform access, migrations); ADR-017 (*Accepted* 2026-10-11: staging on Oracle Cloud Always Free, pilots on Azure) | Reference |
| [user-guide/](user-guide/) | Pilot guide pointer, the plain-language Quality Manager workflow walkthrough, the Platform Administrator's [Trial organizations](user-guide/PLATFORM_ADMIN_TRIAL_ORGANIZATIONS.md) page and [AI in MDARIX](user-guide/AI_IN_MDARIX.md) (switches, review, free trials) | Current |
| [diagrams/](diagrams/) | Mermaid architecture diagrams | Reference |
| [runbooks/](runbooks/) | Database hardening, production readiness gates, operations, developer tooling, simulator endpoints | Operational |
| [validation/](validation/README.md) | MDARIX validation documents (B6b): document control and index, Validation Master Plan, product risk assessment, GAMP 5 justification, scenario register (master copy), signature register | Drafts for review and signature — not a certification |
| [compliance/](compliance/) | Website trust-claims policy, data retention, regulatory decision tables; the MVP-1.0 CSA package and protocols are superseded by [validation/](validation/README.md) | Reference; MVP-1.0 CSA files retired |
| [generated/](generated/) | Generated schema inventory (a Day 2 snapshot; regenerate before relying on it) | Stale snapshot |
| [design-package-20260927/](design-package-20260927/) | Frontend design brief and HTML prototype | Design input |
| [history/](history/README.md) | Day/stage/part/package reports, reviews and past GO/NO-GO decisions | Archive — not current truth |
