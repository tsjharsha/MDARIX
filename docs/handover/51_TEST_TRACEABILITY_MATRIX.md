# Test traceability matrix

Every file named here exists; CI runs it in the job shown (`.github/workflows/ci.yml`, `codeql.yml`,
`ai-evaluation.yml`).

| Requirement | Tests | CI job |
|---|---|---|
| Schema, constraints, migrations at head | `tests/test_day2_database.py` | backend |
| Sign-in, sessions, MFA, passwords, lockout, rate limits, production configuration | `tests/test_auth_hardening.py`, `tests/test_day22_auth.py`, `tests/test_mfa_mvp.py`, `tests/test_web_protections.py` | backend |
| Production behaviour end to end (TLS database, startup checks, CSRF, `__Host-` cookie, MFA enrollment) | `scripts/production_smoke.py` | production-mode |
| Every administration route refuses anonymous callers and business users | `tests/test_admin_route_walk.py` | backend |
| Business writes, AI and exports are permission-guarded | `tests/test_business_permissions.py` | backend |
| Organizations never see each other's data | `tests/test_cross_tenant_routes.py`, `tests/test_day35_identity_context.py` | backend |
| Dedicated databases: migrations, routing, schema gate, export and deletion | `tests/test_dedicated_plane.py` | dedicated-plane |
| AI: allowlist, per-organization switch and budget, PII masking, shared rest periods | `tests/test_ai_controls.py`, `tests/test_genai_fallbacks.py`, `tests/test_genai_provider.py` | backend |
| AI answer quality (golden scenarios, model-written) | `scripts/run_real_evaluation.py --gate --require-model` | AI evaluation gate (manual, before release) |
| Tamper-evident audit trail | `tests/test_audit_hash_chain.py` | backend |
| Export, organization deletion, personal-data erasure, trial retention | `tests/test_tenant_data.py`, `tests/test_free_trial.py` | backend |
| Email content, delivery states, notifications | `tests/test_emails.py` | backend |
| Connectors: keys and rotation, outbound safety, sync paging and retries, schedules | `tests/test_connector_key_rotation.py`, `tests/test_connector_api_key.py`, `tests/test_connector_security.py`, `tests/test_connector_outbound_policy.py`, `tests/test_connector_sync.py` | backend |
| Connector contract and simulators | `tests/test_api_connector_contract.py`, `tests/test_persistent_source_simulator.py` | integration |
| Uploads: size limits, virus scanning | `tests/test_object_storage_scan.py`, `tests/test_data_import_path.py` | backend |
| Inbound email webhooks (Svix signatures) | `tests/test_stage3_communication.py` | backend |
| Website pages, legal pages, routing, Markdown safety | `tests/test_site_info.py`, `tests/test_day24_public_navigation.py`, `frontend/src/site/*.test.ts` | backend, frontend |
| Frontend components and formatting | `frontend/src/**/*.test.ts(x)` | frontend |
| Browser workflows and accessibility | `frontend/e2e/*.spec.ts` | browser |
| Dependencies and code | `pip-audit`, `npm audit`, `ruff`, `prettier`, gitleaks, CodeQL, Trivy | security, frontend, codeql, image-scan |
| Every server setting documented | `tests/test_environment_reference.py` | backend |

Failures caused by an unavailable database, browser download, provider credentials or hosted infrastructure are
reported as environment blockers, never converted into passes.
