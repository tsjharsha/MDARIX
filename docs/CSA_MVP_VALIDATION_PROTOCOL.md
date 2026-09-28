# MDARIX MVP software validation protocol

Document ID: `MDARIX-CSA-MVP-1.0`  
Version: `1.0`  
Status: **Ready for controlled execution**  
Intended use: internal synthetic/design-partner MVP validation.

## 1. Purpose and scope

This protocol defines risk-based computer software assurance for the MDARIX
MVP. It covers installation, operation, performance, tenant isolation,
governed decisions, AI safeguards, document export, connector recovery, and
the main browser personas. It does not certify FDA, ISO, HIPAA, or 21 CFR Part
11 compliance.

## 2. Roles and independence

The system owner approves scope and release. A quality reviewer reviews the
protocol, deviations, evidence, and summary. Test executors record observed
results. The approver must not silently alter evidence after approval.

## 3. Entry criteria

- Approved release commit and environment identifier recorded.
- Required database migrations applied and migration head recorded.
- Synthetic tenants, users, roles, plans, and records seeded.
- Test data and expected outcomes approved.
- Evidence directory and access permissions created.

## 4. Execution

Execute all tests in `validation/csa_package.py` in IQ → OQ → PQ order. Record
actual steps, timestamp, actor, environment, result, deviations, and artifact
SHA-256. A failed test is not a pass; it requires a deviation and retest.

## 5. Acceptance and deviations

Acceptance criteria are test-specific. Deviations require an identifier,
impact assessment, containment/corrective action, owner, approval, retest, and
closure decision. Cross-tenant leakage, uncontrolled mutation, missing audit
evidence, or irreproducible approval is a critical failure and blocks release.

## 6. Evidence and approval

Use `build_evidence_manifest()` to create the immutable evidence index. Store
redacted traces, screenshots, migration output, audit IDs, test results, and
reports under the test-specific paths. Do not overwrite an approved artifact;
issue a new package version. The summary report may be approved only after all
required tests and deviations are closed.

## 7. Rollback and recovery

If a qualification failure affects integrity or isolation, stop execution,
preserve evidence, restore the known-good validation snapshot, document the
event, and retest the affected requirement after correction.

