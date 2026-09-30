# MDARIX-R1 Complete Product and Technical Handover

**Version:** MVP 1.0 internal synthetic-validation handover  
**Repository:** MDARIX-R1  
**Status:** Consolidated index for the complete 56-document handover set

## How to use this document

This is the single entry point for the MDARIX-R1 handover. Each section below links to its corresponding detailed section. The linked source documents remain separate so they can be maintained, reviewed and versioned independently without creating conflicting copies of technical details.

## Executive status

MDARIX-R1 is an internal synthetic-data MVP with:

- React/Vite frontend and public website.
- FastAPI, SQLAlchemy, Alembic and PostgreSQL/pgvector backend.
- Control-plane tenant, identity, configuration and audit foundations.
- Four isolated synthetic customer data planes.
- Eight authenticated provider simulator environments.
- Investigation, evidence, Product 360, mapping, AI advisory and decision-governance foundations.
- Local Docker, worker, Mailpit and object-storage validation foundations.

This repository must not be described as production-ready solely from local evidence. Production TLS, hosted multi-instance validation, production backups/PITR, monitoring, real customer credentials, production storage, enterprise identity and formal compliance validation remain environment-dependent unless separately evidenced.

## Status vocabulary

| Status | Meaning |
|---|---|
| Implemented | Source code and reasonable local evidence exist. |
| Synthetic only | Validated against local tenants, simulators or development infrastructure. |
| Partial | Foundation exists, but workflow, coverage or evidence is incomplete. |
| Configuration required | Code exists but requires environment-specific values or services. |
| Production pending | Requires hosted infrastructure, approved credentials or operational evidence. |
| Deferred | Outside the current internal MVP scope. |

## 1. Product and architecture

1. [Executive product overview](handover/01_EXECUTIVE_PRODUCT_OVERVIEW.md)
2. [Current implementation status](handover/02_CURRENT_IMPLEMENTATION_STATUS.md)
3. [Repository structure](handover/03_REPOSITORY_STRUCTURE.md)
4. [System architecture](handover/04_SYSTEM_ARCHITECTURE.md)
5. [Domain and data model](handover/05_DOMAIN_AND_DATA_MODEL.md)
6. [Database handover](handover/06_DATABASE_HANDOVER.md)
7. [Backend architecture](handover/07_BACKEND_ARCHITECTURE.md)
8. [API reference](handover/08_API_REFERENCE.md)
9. [Frontend application handover](handover/09_FRONTEND_APPLICATION_HANDOVER.md)
10. [Public website handover](handover/10_WEBSITE_HANDOVER.md)

## 2. Identity, authorization and administration

11. [Identity, authentication and sessions](handover/11_IDENTITY_AUTHENTICATION_SESSION.md)
12. [Tenant isolation](handover/12_TENANT_ISOLATION.md)
13. [Roles, permissions and personas](handover/13_ROLES_PERMISSIONS_PERSONAS.md)
14. [Plans, entitlements and licensing](handover/14_PLANS_ENTITLEMENTS_LICENSING.md)
15. [Platform Administrator control plane](handover/15_ADMINISTRATOR_CONTROL_PLANE.md)
16. [Customer Administration](handover/16_CUSTOMER_ADMINISTRATION.md)

## 3. Investigation, evidence and AI

17. [Investigation workspace](handover/17_INVESTIGATION_WORKSPACE.md)
18. [Product 360 and Product Reality Graph](handover/18_PRODUCT360_REALITY_GRAPH.md)
19. [Evidence and retrieval](handover/19_EVIDENCE_AND_RETRIEVAL.md)
20. [AI and GenAI architecture](handover/20_AI_GENAI_AGENTIC_ARCHITECTURE.md)
21. [Hypotheses, challengers and unknowns](handover/21_HYPOTHESIS_CHALLENGER_UNKNOWNS.md)
22. [Decision Center and governance](handover/22_DECISION_CENTER_GOVERNANCE.md)
23. [Electronic signatures and approvals](handover/23_ELECTRONIC_SIGNATURE_APPROVALS.md)

## 4. Integrations, configuration and governance

24. [Integration architecture](handover/24_INTEGRATION_ARCHITECTURE.md)
25. [Data mapping and configuration](handover/25_DATA_MAPPING_CONFIGURATION.md)
26. [Audit logging and correlation](handover/26_AUDIT_LOGGING_CORRELATION.md)
27. [Security architecture](handover/27_SECURITY_ARCHITECTURE.md)
28. [Privacy, PII/PHI and AI boundaries](handover/28_PRIVACY_PII_PHI_AI_BOUNDARIES.md)
29. [Trust, assurance and validation](handover/29_TRUST_ASSURANCE_VALIDATION.md)
30. [Ask MDARIX](handover/30_ASK_MDARIX.md)
31. [Object storage, files and exports](handover/31_OBJECT_STORAGE_FILES_EXPORTS.md)
32. [Notifications and email](handover/32_NOTIFICATIONS_EMAIL.md)
33. [Configuration management](handover/33_CONFIGURATION_MANAGEMENT.md)

## 5. Environment, operations and recovery

34. [Development environment setup](handover/34_DEV_ENVIRONMENT_SETUP.md)
35. [Docker infrastructure](handover/35_DOCKER_INFRASTRUCTURE.md)
36. [CI/CD and DevSecOps](handover/36_CI_CD_DEVSECOPS.md)
37. [Testing and validation](handover/37_TESTING_QA_VALIDATION.md)
38. [Backup, restore and recovery](handover/38_BACKUP_RESTORE_RECOVERY.md)
39. [Operational support runbook](handover/39_OPERATIONAL_SUPPORT_RUNBOOK.md)
40. [Deployment runbook](handover/40_DEPLOYMENT_RUNBOOK.md)
41. [Troubleshooting guide](handover/41_TROUBLESHOOTING_GUIDE.md)
42. [Known limitations and technical debt](handover/42_KNOWN_LIMITATIONS_TECHNICAL_DEBT.md)
43. [Deferred and future scope](handover/43_DEFERRED_AND_FUTURE_SCOPE.md)
44. [Configuration reference](handover/44_CONFIGURATION_REFERENCE.md)
45. [Environment variable reference](handover/45_ENVIRONMENT_VARIABLE_REFERENCE.md)

## 6. Reference matrices and onboarding

46. [Database dictionary](handover/46_DATABASE_DICTIONARY.md)
47. [API endpoint matrix](handover/47_API_ENDPOINT_MATRIX.md)
48. [UI screen and action matrix](handover/48_UI_SCREEN_AND_ACTION_MATRIX.md)
49. [Role and permission matrix](handover/49_ROLE_PERMISSION_MATRIX.md)
50. [Feature traceability matrix](handover/50_FEATURE_TRACEABILITY_MATRIX.md)
51. [Test traceability matrix](handover/51_TEST_TRACEABILITY_MATRIX.md)
52. [Support and ownership handover](handover/52_SUPPORT_AND_OWNERSHIP_HANDOVER.md)
53. [New developer first week guide](handover/53_NEW_DEVELOPER_FIRST_WEEK_GUIDE.md)
54. [Release and change management](handover/54_RELEASE_AND_CHANGE_MANAGEMENT.md)
55. [Open questions and handover risks](handover/55_OPEN_QUESTIONS_AND_HANDOVER_RISKS.md)

## MVP release conclusion

The correct conclusion is **internal synthetic MVP / controlled technical demo**, subject to the test and evidence results recorded in the linked documents. A design-partner or production GO decision requires explicit execution and retention of the relevant browser, security, deployment, backup, monitoring, connector and identity evidence.

## Evidence rule

Do not promote a local test result to a production claim. Record the command, environment, timestamp, tenant fixture, result, artifact location and owner for every release gate. Redact secrets, personal data and customer identifiers from committed evidence.

