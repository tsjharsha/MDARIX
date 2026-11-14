# Customer implementation and validation instructions

> **SUPERSEDED (12 Nov 2026, B6b).** These MVP-1.0 instructions ask a customer to run installation qualification on a hosted service, which does not fit MDARIX as SaaS, and are retired. Do not give it to a customer or use it as evidence. Successor: the customer validation instructions [MDX-CUS-006](../validation/MDX-CUS-006_CUSTOMER_VALIDATION_INSTRUCTIONS.md) (B6b Part E, 14 Nov 2026); see [docs/validation/README.md](../validation/README.md).

1. Assign the customer validation owner, quality reviewer, system owner, and approver.
2. Record the approved MDARIX commit, environment, migration head, and configuration versions.
3. Use isolated approved validation tenants and representative approved data.
4. Execute IQ-001/IQ-002, then OQ-001 through OQ-004, then PQ-001 through PQ-003.
5. Record PASS, FAIL, or DEVIATION for every test; attach redacted traces, screenshots, audit IDs, and SHA-256 hashes.
6. Investigate failures, assess impact, approve corrective action, and retest.
7. Obtain quality and system-owner approval before declaring the release validated.
8. Retain the signed protocol, results, deviations, evidence manifest, and summary under the customer's retention policy.

Customer-specific infrastructure qualification, intended-use decisions, access
reviews, backup/restore qualification, and regulatory submission decisions
remain customer responsibilities.

