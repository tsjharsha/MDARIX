# AI-R: AI ready, switched off

Version 1, 11 Nov 2026. **DRAFT for the owner.** Nothing here is built. AI-R sits in Lane 2 right after DB-1 (owner, 11 Nov: DB-1 → **AI-R** → E11 → E6 → E2). Decisions marked **⚑** touch patient safety, personal data, customer promises or spend: they need the owner's explicit answer. Each ⚑ says what the build does **if no answer arrives** (always the safer path).

- **Goal (owner, 11 Nov):** build AI fully, so that turning it ON later is a decision, not development. AI stays OFF by default everywhere. "Off" means zero calls to an AI model, proven by tests.
- **Sources:** `complete-plan/MDARIX-complete-plan.md` (AI-R entry, two lanes, Google Cloud billing note of 11 Nov, v2.1 item 7 Definition of done), `b9-markets/spec.md` (format), memory notes on Vertex AI (Gemini on Vertex, Mumbai, chosen 16 Oct) and the golden dataset (v2, 15 scenarios, a real model passes few).
- **Code read** (read-only, `git show` / `git grep` / `git log` only): branch `feat/b8-eu-gb-mir` at `dd1870b7` (VERSION 0.10.94). Every `file:line` is on that branch. Step 0 re-checks every line on Lane 2's tip after DB-1.
- **Not in AI-R:** switching AI on anywhere (that is the owner's later decision, section 9); a live qualification run (needs the owner's OK and a billing account); new AI features beyond the seven below; report narrative drafting for authority forms; any AI that decides.

---

## 1. Purpose, in plain words

MDARIX already has most of an AI layer. It is off today. AI-R finishes it so that one day the owner can switch it on, one feature and one organisation at a time, with evidence that it is safe.

Five promises, in the order they protect the customer:
1. **Off means off.** Three switches, all off by default: the platform, the organisation, the feature. While any one is off, no model is called. Tests prove it.
2. **A person decides.** AI proposes. A person accepts, edits or rejects every output. Nothing is applied by itself. AI never sets reportability, a root cause, closure, a recall or an approval.
3. **Personal data never leaves.** Masking runs on every request (existing). Protected fields never go to the model (existing allowlist).
4. **Every call is on the record.** Which feature, which prompt version (and its hash), which model, what came back, who reviewed it and what they did.
5. **Qualified before use, re-qualified on change.** A golden dataset with separate qualification data, a one-command run with fixed pass criteria, and an automatic stop when the model, the prompt or the settings change.

---

## 2. What exists today

### 2.1 The AI code
| Area | What it does | Where |
|---|---|---|
| Provider boundary | One class sends every model request. Default provider `controlled` = no model | `genai/provider.py:188-219`, default at `:205` |
| The one choke point | `complete()`: redacts secrets, masks personal data, checks the size, returns "no AI was used" when no provider is configured, applies the provider policy, then the organisation's controls, then sends | `genai/provider.py:264-349`; no call when not configured `:295-311`; policy `:312-320`; organisation check `:324` |
| Providers known | groq, cerebras, gemini, openrouter, mistral, anthropic, ollama, omniroute | `genai/provider.py:22-38` |
| Moving model names | Gemini `gemini-flash-latest`, OmniRoute `auto`, Mistral `mistral-small-latest` | `genai/provider.py:26`, `:37`, `:29` |
| Model version | `MDARIX_GENAI_MODEL_VERSION`, default `"unconfigured"` | `genai/provider.py:210` |
| Provider policy | In staging and production only `ollama` or a provider in `MDARIX_GENAI_CONTRACTED_PROVIDERS` with zero data retention (`_ZDR=true`) or accepted retention; free models refused | `genai/policy.py:65-76`, ZDR `:46-58`, start-up problems `:85-115` |
| Organisation controls | Per request: no organisation scope in production = refused; free trial = refused; organisation switch off = refused; monthly token budget | `genai/governance.py:122-151` (trial `:136`, switch `:138`, budget `:140`) |
| Personal data masking | Always on in staging and production | `genai/pii.py:253-259` |
| Protected fields | Allowlist; restricted (email, phone, address, names) and prohibited (secrets) fields never included | `backend/app/ai_boundary.py:9-50`, `:73-93` |
| Prompt-injection defence | Records in delimited blocks; tags inside a record defused | `genai/provider.py:124-149` |
| Advisory wrapper | Model advisory beside the rules result; checks citations, causal or decision wording | `genai/grounding.py:218-291` |
| Trust check | Every saved AI result checked: grounding, restricted claims (root cause, reporting, recall, approval, closure), certainty, provenance, tenant | `trust_engine/auto.py:1-23` |
| Saved AI results | `record_ai_execution` → table `ai_executions` (provider, model, prompt template version, input, output, validation status). No prompt hash, no reviewer, no accept/edit/reject. Model version defaults to `"latest"` | `ai/execution.py:13-58` (`:39`); `backend/app/db/models/foundation.py:565-591` |
| Ask feedback | `ai_interaction_feedback` (Ask only, free JSON) | `backend/app/db/models/stage3.py:45-52` |
| Monthly usage | `ai_usage_monthly` (requests, refused, tokens, cost) | `backend/app/db/models/stage2.py:118-121` |

### 2.2 The features that call a model (all through `complete()`)
| Feature (AI-R name) | Today's code | Call |
|---|---|---|
| Ask MDARIX | `POST /api/v1/interactions`, needs `ai.run` | `backend/app/stage3_workflow_router.py:232`, `:274`, `:355`; `genai/ask.py` |
| Case analysis | Analysis, competing explanations, challenges (case AI run) | `investigator/model_provider.py:228`, `hypothesis_engine/model_engine.py:93`, `challenger/model_engine.py:96`; runner `backend/app/case_ai/runner.py` |
| Drafting | Investigation brief draft | `briefs/model_writer.py:121` |
| Summaries | Signal summary; second-look explanation | `backend/app/signals/insight.py:764-766`; `backend/app/complaint_review/explain.py:140-142` |
| Evidence extraction | Observations from evidence documents | `ai/extractor.py:134`, used by `evidence/services/evidence_service.py:70` |
| Advisory beside a decision | Decision Center advisory | `decision_center/service.py:203-217`; also briefs, challenger, failure chain, hypotheses, investigator services call the same advisory (`genai/grounding.py:218`) |
| Code suggestions | **Not built with AI.** IMDRF codes are suggested from approved mappings (rules), confirmed by a person, with a "Confirm all codes" button. The mapping studio's AI suggestion says `AI_SUGGESTION_NOT_ACTIVE` | `backend/app/authority_reports/router.py:1311`, `:1457`; `backend/app/mapping_catalog_router.py:589` |

No other code calls a model: no `openai`, `anthropic` or Google SDK, and no other chat endpoint outside `genai/provider.py` (git grep). The evidence search uses a **local** embedding model shipped in the image; it never downloads weights and sends nothing out (`retrieval/embedding_provider.py:118`, `:160`).

### 2.3 The three switch levels today
| Level | Today | Where |
|---|---|---|
| Platform | `MDARIX_GENAI_PROVIDER`, default `controlled` (no model) in both templates | `.env.example:11`, `.env.production.example:144`; read at `genai/provider.py:205`; config check reads it at `backend/app/config_check.py:425` (cost rate only, `:421-435`) |
| Organisation | `tenants.ai_processing_allowed`, default false; customer admin switches it with a reason (5+ characters) and an acknowledgement; audited `AI_PROCESSING_SETTING_CHANGED`; free trials refused (409); in production refused until the release gate is met | `backend/app/db/models/foundation.py:72-73`; `backend/app/ai_settings.py:44-48`, `:109-119`, `:129-168` (audit `:153`), platform admin `:182-231` (needs the customer's approved support access, `:191`) |
| Feature | **None.** Every feature follows the organisation switch | — |

### 2.4 The release gate and qualification today
- **Four bars** (`backend/app/ai_release_gate.py:24-30`): contracted provider with zero retention; golden dataset signed by a person; golden evaluation passed 15 of 15 with this model; automatic trust check. Enforced only in production (`:164-168`). The model check compares provider and model name only (`:117-129`), not the prompt or the settings. Today only the trust-check bar is met (`tests/test_ai_release_gate_unit.py:130`).
- **Golden dataset `r1-ai-golden-v2`:** 15 scenarios VS001–VS015, case analysis only, three adversarial (injection canary, personal data, leading question). Qualified for internal synthetic MVP assurance only (`docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md:5-6`, `:13-20`). The lock's reviewer reads "human review pending" (`:38-41`). Neither `evaluation/GOLDEN_DATASET_HUMAN_SIGN_OFF.json` nor `evaluation/AI_RELEASE_RECORD.json` exists on the branch (paths at `evaluation/release_record.py:28-29`).
- **Tests:** dataset integrity, hash lock, adversarial expectations (`tests/test_ai_golden_qualification.py:13-94`); release gate (`tests/test_ai_release_gate_unit.py:49-184`); guardrails: delimiters, injection, causal wording, refusal codes (`tests/test_advisory_guardrails.py:77-163`); organisation off = no model call (`tests/test_ai_controls.py:184-189`); personal data never sent (`:165-172`); OmniRoute needs contract and retention (`tests/test_genai_policy.py:49`).
- **CI live run:** `.github/workflows/ai-evaluation.yml` runs the real pipeline by hand, **weekly (cron, `:24-25`) and on pull requests (`:26`)** when the secret `MDARIX_EVALUATION_API_KEY` is set (`:56`, `:112`). With a paid key that spends money without asking.

### 2.5 Documents today
- `docs/compliance/AI_PROVIDER_REGISTER.md:25-32`: rows for anthropic, groq, cerebras, mistral, gemini, ollama, all `TBD`. **No Vertex row and no OmniRoute row.**
- `docs/runbooks/AI_PROVIDERS.md`: free fallbacks for demos, paid providers for production, OmniRoute section (`:89-100`). No Vertex section on this line.

### 2.6 The two provider branches
| Branch | Tip | Branched from | Ahead | Behind `feat/b8-eu-gb-mir` | State |
|---|---|---|---|---|---|
| `ai/vertex-provider` | `d699dee7` (16 Oct) | `825e96ef`, the 0.10.9 release merge (VERSION 0.10.9) | 1 | **895** | Not on the line (`git cherry` shows `+`) |
| `ai/omniroute` | `e4ecbbc6` (8 Nov) | `c1f232de`, the 0.10.92 release merge | 1 | **307** | **Already on the line** as `4da6a5a9` (`git cherry` shows `-`, same patch). Nothing to merge |

**What bringing Vertex over touches.** `d699dee7` changes 5 files (+139/−6): `genai/provider.py` (Vertex address from project and region, token from the VM's metadata server reused until a minute before expiry, `KEYLESS_PROVIDERS`, bearer header), `scripts/ai_provider_preflight.py`, `tests/test_genai_provider.py` (2 tests), the register row, the runbook section. Since its base, only two of those files changed on the line (`git diff 825e96ef feat/b8-eu-gb-mir`): `genai/provider.py` (+12/−1: OmniRoute entry, two refusal messages, one sentence) and the runbook (+12: OmniRoute). So a **cherry-pick of one commit** with two small text conflicts (the provider list next to `ollama`, and the runbook table), not a merge of 895 commits. Merging the branch would bring the same single change; cherry-pick keeps the history plain.

---

## 3. Features, intended use and risk level

Risk levels (owner's checklist): **High** = AI decides: **none allowed**, refused in code. **Medium** = AI recommends something a person may turn into a record. **Low** = advisory text a person reads.

| Feature key | Intended use | Output | Risk | Never |
|---|---|---|---|---|
| `ask` | Answer a question from the organisation's own records, with citations | Answer text with `[EV-…]` citations | Low | Answer without a cited record; guess when records are silent ("I don't know") |
| `summaries` | Summarise a signal's complaints; explain why a second-look record may be a complaint | Sentences quoting cited records | Low | Say a record is or is not a complaint, or reportable |
| `case_analysis` | Propose an analysis, competing explanations and challenges for an investigation | Statements, hypotheses, challenges with evidence citations | Medium | State a root cause as fact; rank as decided |
| `drafting` | Draft the investigation brief from reviewed analysis | Draft brief sections | Medium | Enter a Decision Brief or report unreviewed |
| `evidence_extraction` | Propose observations from an evidence document | Observations with source anchors | Medium | Become evidence before a person accepts |
| `code_suggestions` (new) | Propose IMDRF codes from the complaint text, from the loaded IMDRF release only | Code + the quoted words it rests on | Medium | Be confirmed by "Confirm all codes" |
| `decision_advisory` | Advisory beside a Decision Center decision | Advisory text | Medium | Be offered at all until the owner says so (AI-D5 ⚑) |

**High risk, refused in code:** reportability conclusions, legal clocks, root cause, CAPA closure, recall or field action, signal raising, approvals and signatures, report submission. A unit test lists every feature and fails if one is declared High; an architecture test fails if a module under `genai/`, `ai/`, `case_ai/` or the feature callers writes to those tables.

---

## 4. Design

### 4.1 Three switches, all off by default
```
platform  MDARIX_GENAI_PROVIDER != controlled          (default controlled)
   AND    feature in MDARIX_AI_FEATURES                 (default empty)
   AND    production: the feature is qualified for this exact fingerprint (4.5)
   AND    tenants.ai_processing_allowed                 (default false)
   AND    tenants.ai_features[feature] = true           (default {})
   AND    not a free trial, budget left                 (existing)
=> only then is a model called
```
- **Platform** stays `MDARIX_GENAI_PROVIDER`. New `MDARIX_AI_FEATURES` (comma list) lets the owner qualify and open features one at a time. Read on every call (the `feature_set.py` pattern, `backend/app/feature_set.py:129-136`).
- **Organisation** stays `ai_processing_allowed` with reason, acknowledgement and audit (existing). Switching on also needs a fresh MFA code, like a signature.
- **Feature, per organisation:** new `tenants.ai_features` JSONB. A customer admin turns a feature on with a reason; audited `AI_FEATURE_SETTING_CHANGED` with the feature, its intended use and risk shown on the screen. Only features the platform allows can be turned on.
- **`complete()` requires `feature=`.** A call without a known feature is refused (`GENAI_FEATURE_UNKNOWN`), so new code cannot bypass the switches by accident.
- **Off = zero calls.** Refusals happen before any network code. `controlled` returns "no AI was used" without a request (`genai/provider.py:295`). Fallbacks only follow a configured primary (`:294`).

### 4.2 Vertex AI as the provider; OmniRoute as backup for development only
- Cherry-pick `d699dee7`. Region default `asia-south1` (Mumbai). Keyless: token from the VM's metadata server.
- **Exact model pinned.** In staging and production the config check refuses a moving name (`-latest`, `auto`, no version) and an `"unconfigured"` model version. The pinned id and its Google retirement date go in the register (AI-D1 ⚑).
- **Region guard.** In production a Vertex address must be in `asia-south1` unless the owner records otherwise; the region goes on every call record.
- **Thinking.** Gemini Flash models may spend output allowance on thinking. A setting `MDARIX_GENAI_VERTEX_REASONING_EFFORT` (default `low`) is sent; thinking tokens (from the usage reply, when given) go on each call record. The first live call checks it (section 9).
- **OmniRoute** is already on the line. It stays for development on synthetic data. It is not a production fallback: its upstreams may sit outside India (AI-D2 ⚑).
- **Zero data retention** is an owner/provider item: Vertex's in-memory cache switched off for the project, and abuse-monitoring prompt logging not applying (invoiced billing) or Google's written exception. Until both are confirmed `MDARIX_GENAI_VERTEX_ZDR` stays unset, so production refuses the provider (`genai/policy.py:76`) (AI-D3 ⚑).

### 4.3 One record per AI call
New table `ai_calls`, written by `complete()` (in the governance session, so row-level security applies) for every request actually sent:
- organisation, user, feature, risk level;
- prompt version and SHA-256 of the prompt template and system text; SHA-256 of the masked content sent (the content itself is not stored, AI-D11 ⚑);
- provider, model id, model version, region, configuration version, retrieval policy version;
- tokens in, out and thinking; latency; outcome (`ANSWERED`, `FAILED`, `INVALID_OUTPUT`);
- the output as returned, and its SHA-256.

Refused requests are counted (existing `ai_usage_monthly.refused`) and write no row. Append-only (update and delete refused by trigger, like the audit table).

### 4.4 A person accepts, edits or rejects every output
New table `ai_output_reviews`: one row per decision on an output (`ACCEPTED`, `EDITED` with the edited text's hash, `REJECTED` with a reason), reviewer, time; linked to the `ai_calls` row and the record shown. Audited `AI_OUTPUT_REVIEWED`. A later review supersedes; nothing is deleted.
- **Nothing downstream uses an unreviewed AI item.** Decision Brief, readiness checks, authority reports, IMDRF code fields and evidence observations read only accepted or edited AI items. Unreviewed items show "AI proposal, not reviewed" (AI-D7 ⚑).
- **No automatic runs.** The case page's automatic AI run on first open (`backend/app/case_ai/router.py:4-8`, `:97-109`) becomes on request only (AI-D6 ⚑).
- **Code suggestions** sit beside the mapping suggestions as "AI suggestion" and are excluded from "Confirm all codes" (`backend/app/authority_reports/router.py:1457`): each is confirmed one by one.
- **Decision advisory provenance fix.** `decision_center/service.py:219-232` saves the advisory as `mdarix-rule-grounded-advisory` even when a model answered. It must name the real provider and model.

### 4.5 Qualification, fingerprint, re-qualification
- **Fingerprint per feature:** prompt version and hash, model id and version, provider and region, retrieval policy version, configuration version, dataset lock hash. The release record (v2) holds one passed fingerprint per feature.
- **Runtime check (production):** a feature whose current fingerprint is not in the release record is refused (`GENAI_FEATURE_NOT_QUALIFIED`). Any model or prompt change therefore stops that feature until it is re-qualified. Today's gate checks provider and model name only (`backend/app/ai_release_gate.py:117-129`).
- **Prompt manifest.** `genai/prompt_manifest.json` pins each prompt's text hash and version. A test fails when a prompt's text changes without a new version.
- **Golden dataset v3**, two strictly separate parts:
  - *Development set* (`evaluation/dev/`): used to write and tune prompts. Anyone may read it.
  - *Qualification set* (`evaluation/qualification/`): never used to write prompts; written or reviewed by a person who did not write the prompts; hash-locked; signed by a named person (AI-D9 ⚑). This follows the draft EU GMP Annex 22 principle that test data stay independent of the data used to build the system (used here as good practice, not as a legal duty for device makers: to confirm with your consultant).
  - A test refuses overlap: no shared ids, no identical text, no near-duplicates (word 5-gram overlap above 0.5).
  - Per feature, at least 12 qualification cases covering: correct, ambiguous, missing evidence, contradictory, out of scope, edge case (each at least once); at least 2 hallucination traps (the answer is not in the records: the right output is "I don't know" or a refusal); at least 1 refusal case (asks for a decision AI may not make); plus the existing injection canary and personal-data cases. VS001–VS015 stay as the case-analysis core.
- **Pass criteria (AI-D8 ⚑):** safety checks 100% (no personal data in any request, no canary, no root-cause or decision claim shown, no invented citation shown, "I don't know" on every hallucination trap and refusal case); content expectations at least 90% per feature and at least 80% in every category; case analysis keeps 15 of 15.
- **One command:** `python scripts/qualify_ai.py --feature all` runs on the fake model (free, used in CI). `--live --confirm-spend --max-tokens N` runs on the real provider: it prints the token estimate, refuses without both flags, stops at the cap, and writes the release record only on a full pass of a signed qualification set (AI-D10 ⚑).

### 4.6 Drift and human-oversight metrics
- Daily job per organisation and feature: share accepted, edited, rejected; trust-check blocks; "I don't know" share; tokens. Compared with the qualification baseline.
- **Threshold:** rejected share 15 points above baseline over 30 days (at least 20 reviewed outputs), or trust-check blocks above 5%. Then: alert to the organisation's admins and the operators, and the feature is paused for that organisation until the owner clears it (AI-D16 ⚑).
- A fingerprint change is not drift: it stops the feature at once (4.5).
- Screens: Security › AI processing shows each feature's metrics; the platform admin sees all organisations.

### 4.7 AI change control
`docs/compliance/AI_CHANGE_CONTROL.md`, tiered:
| Tier | Examples | What it needs |
|---|---|---|
| Minor | Screen wording, logging, a refusal message | Normal review; CHANGELOG |
| Moderate | Prompt wording, retrieval size or ranking, max output, reasoning effort, masking rule | New prompt or config version; re-qualification of the affected feature; owner informed |
| Major | New model or model version (including a vendor retirement), new provider or region, new feature, risk level change | Provider assessment updated; full re-qualification; owner approval recorded |
| Critical | Anything that would let AI decide, auto-apply, see personal data, keep data, or leave India | Not allowed without the owner and your consultant; the build refuses it by default |

Vendor model updates: a pinned id cannot change silently. A retirement notice is a Major change with a planned date.

### 4.8 Documents
- `docs/compliance/AI_PROVIDER_ASSESSMENT_VERTEX.md`: identity, contract (Google Cloud terms and data processing addendum, accepted with the billing account), training on content, retention and the two ZDR conditions, region and whether processing stays in `asia-south1`, sub-processors, certifications, model lifecycle and retirement date, incident notice, exit. Every unknown is marked "to confirm with Google".
- Register: Vertex row (from `d699dee7`) and an OmniRoute row ("development only, synthetic data").
- Runbook: the switch-ON checklist (section 9) and the switch-OFF path.
- User guide: "AI in MDARIX": what each feature is for, its risk level, that a person decides, how to review.
- `.github/workflows/ai-evaluation.yml`: remove the weekly schedule and the pull-request trigger; manual only, with a "confirm spend" input.

---

## 5. Gaps, build steps, migration, switches, cuts

### 5.1 Gap table
| # | Gap | Evidence | Step |
|---|---|---|---|
| G1 | Vertex provider not on the line | `git cherry` `+ d699dee7` | 1 |
| G2 | Moving model names allowed; model version "unconfigured" / "latest" | `genai/provider.py:26`, `:37`, `:210`; `ai/execution.py:39` | 2 |
| G3 | No feature switch; `complete()` does not know the feature | `genai/provider.py:264-274`; `ai_settings.py` has the organisation switch only | 3, 4, 6 |
| G4 | No per-call record; saved results lack prompt hash, region, thinking tokens; Ask answers are not AI executions | `ai/execution.py:13-58`; `trust_engine/auto.py:3-5` | 5, 8 |
| G5 | No accept / edit / reject; AI results flow to the Decision Brief and readiness as saved | `backend/app/case_ai/runner.py` docstring; `foundation.py:565-591` | 5, 9 |
| G6 | Case AI runs by itself on first open | `backend/app/case_ai/router.py:97-109` | 9 |
| G7 | Decision advisory saved under a rules name even when a model answered | `decision_center/service.py:203-232` | 11 |
| G8 | No AI code suggestions; "Confirm all codes" would sweep them in | `authority_reports/router.py:1457`; `mapping_catalog_router.py:589` | 10 |
| G9 | Golden set covers case analysis only; no dev/qualification split; no hallucination or "I don't know" cases per feature | `docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md:8-20` | 13 |
| G10 | Release gate checks provider + model only; no fingerprint; no per-feature record | `ai_release_gate.py:117-129` | 14 |
| G11 | Tests need a fake model per feature that can also misbehave | Today: monkeypatched `urlopen` per test file (`tests/test_ai_controls.py`, `tests/test_genai_provider.py`) | 15 |
| G12 | No drift monitoring or oversight metrics | — | 16 |
| G13 | No AI change control or prompt manifest | — | 17 |
| G14 | No provider assessment; register lacks Vertex and OmniRoute | `AI_PROVIDER_REGISTER.md:25-32` | 18 |
| G15 | CI can spend money weekly and on pull requests | `ai-evaluation.yml:24-26`, `:56` | 18 |
| G16 | No single test proving "off = zero calls" across every feature and every switch level | Only organisation off, one call (`tests/test_ai_controls.py:184-189`) | 7 |

### 5.2 Build steps
Four parts, built in this order: **A Switches and proof of off**, **B A person decides**, **C Qualification and control**, **D Code suggestions** (optional). Hours include targeted tests. "(db)" = database test; "(unit)" = no database. Every test runs on the fake model: no step spends money.

| # | Step | Part | Hours | Targeted tests |
|---|---|---|---|---|
| 0 | Branch from Lane 2's tip after DB-1; one Alembic head; re-check this spec's lines; CHANGELOG; scenarios AI-01..AI-30 in `scenario-register.md` | A | 2 | `alembic heads` = 1 |
| 1 | Cherry-pick `d699dee7`; resolve the two conflicts (provider list, runbook table); `MDARIX_GENAI_VERTEX_REASONING_EFFORT`; region guard; thinking tokens read from the usage reply | A | 4 | `test_genai_provider.py` (the 2 Vertex tests, fake metadata server); new: reasoning effort in the body; non-Mumbai address refused in production; token reused, refreshed after expiry; metadata server down = `GENAI_UNAVAILABLE`, no model call |
| 2 | Model pin rule in `config_check.py`: staging/production refuse `-latest`, `auto`, no version, `MODEL_VERSION` unset; `ai/execution.py` stops defaulting to `"latest"` | A | 3 | `test_config_check*` (unit): each moving name refused; pinned id accepted; development untouched |
| 3 | `genai/features.py`: the seven features with intended use, risk, prompt versions; High refused at import; `complete(feature=…)` required; update the 10 callers (2.2) | A | 6 | (unit) every caller passes a known feature; unknown or missing feature refused before any network code; a High declaration fails the import |
| 4 | `MDARIX_AI_FEATURES` (platform list, default empty), read on every call | A | 2 | (unit) empty = every feature refused; one listed = only that one passes the platform level |
| 5 | Migration (5.3): `tenants.ai_features`, `ai_calls`, `ai_output_reviews`; forced row-level security; append-only triggers | A | 5 | upgrade, downgrade, upgrade; `test_rls_coverage.py`; another organisation's rows unseen; update/delete refused |
| 6 | Organisation feature switches: `PUT /api/v1/admin/ai-settings` gains `features` with reason; fresh MFA to switch AI or a feature on; audited `AI_FEATURE_SETTING_CHANGED`; platform-disallowed features refused; free trial refused (existing rule) | A | 4 | (db) admin only; reason required; audit holds feature, risk and intended use; trial 409; platform admin needs approved support access (existing) |
| 7 | **Proof of off.** A network guard fixture (any socket to a non-local host fails the test) runs every feature's entry point with each level off in turn (platform, feature list, organisation, organisation feature, trial, budget, not qualified in production) | A | 6 | `test_ai_r_zero_calls.py` (db): for 7 levels × 7 features, zero model requests, zero `ai_calls` rows, the rules answer shown with the reason. Also: `controlled` with fallbacks configured = zero calls; local embedding search still works with AI off |
| 8 | Per-call record written in `complete()`: feature, user, prompt version and hashes, model id/version, region, tokens incl. thinking, latency, outcome, output and hash | A | 6 | (db) one row per answered call; none per refusal; masked content never stored, only its hash; a failed call records `FAILED` without output; row-level security |
| 9 | Review: `POST /api/v1/ai-outputs/{id}/review` (accept / edit / reject, reason for edit and reject); audited; Decision Brief, readiness, reports, observations read only reviewed AI items; case auto-run becomes on request only | B | 12 | (db) unreviewed item absent from the Decision Brief and readiness; accepted present; edited shows the person's text and keeps the AI text in history; rejected never used; reviewer recorded; no AI item reaches a report field or a code field unreviewed; opening a case starts no run |
| 10 | *Optional:* AI code suggestions from the loaded IMDRF release only, each with its quoted words; shown as "AI suggestion"; excluded from "Confirm all codes" | D | 8 | (db) codes outside the release dropped; "Confirm all codes" skips AI suggestions; each confirmed singly, audited; AI off = mapping suggestions only, as today |
| 11 | Decision advisory: own feature key, not offered (AI-D5); provenance names the real model | A | 2 | (unit) advisory refused while not offered; when a fake model answers, the saved row names that model |
| 12 | Screens: Security › AI processing (per-feature switches with intended use and risk; metrics); Accept / Edit / Reject on every AI output (case run, Ask answer, signal summary, second look, extraction, codes); "AI proposal, not reviewed" label; platform admin metrics | B | 12 | vitest per screen; `tsc --noEmit`; a feature the platform does not allow is shown off and locked |
| 13 | Golden dataset v3: dev and qualification folders, generator, per-feature cases (4.5), overlap test, hash lock, per-feature pass criteria as data | C | 20 | `test_ai_golden_qualification.py` extended: every feature has every category; overlap refused; changed qualification byte breaks the lock; VS001–VS015 unchanged |
| 14 | `scripts/qualify_ai.py`: one command, fake by default; `--live --confirm-spend --max-tokens`; release record v2 with fingerprints; runtime fingerprint check in production; gate shows a bar per feature | C | 8 | (unit) no flags = no live call; cap stops the run; record written only on a full pass of a signed set; changed prompt or model = feature refused in production; development not enforced (as today, `ai_release_gate.py:164-168`) |
| 15 | Fake model `genai/fake.py` (provider name `fake`): scripted answers per case, good and bad (hallucinates, echoes personal data, obeys the injection, claims a root cause, cites an unknown record, empty, too long, thinking used up the output); refused in staging and production by the config check | C | 4 | (unit) the harness fails each bad script for the right reason; production refuses `fake` at start |
| 16 | Drift job and metrics API; thresholds as settings; pause per organisation and feature; alert | C | 6 | (db) threshold crossed → paused + alert, once; below → nothing; under 20 reviews → nothing |
| 17 | Change control document; prompt manifest and its test; pull-request template checkbox "AI change tier" | C | 4 | (unit) prompt text changed without a version → test fails |
| 18 | Documents: provider assessment (Vertex), register rows (Vertex, OmniRoute), runbook switch-ON / switch-OFF, user guide "AI in MDARIX", `ai-evaluation.yml` manual only | C | 5 | Doc link test; workflow has no `schedule` and no `pull_request` |
| 19 | Targeted suites with AI off (default) and with the fake model on: all `tests/test_ai_*`, `test_genai_*`, `test_advisory_guardrails.py`, `test_ai_golden_qualification.py`, `test_ask_structured.py`, `test_grounded_ask.py`, `test_day26_ask_api.py`, `test_model_*`, `test_signals_ai_*`, `test_second_look_explain_unit.py`, `test_trust_*`, `test_authority_reports_api.py`, `test_rls_coverage.py`; ruff; vitest; one independent read-only review; fixes | A 2, B 2, C 2 | 6 | All green both ways |
| | **Core total** (A 42, B 26, C 49) | | **117** | |
| | **With optional part D** | | **125** | |

At about 7 build hours a day, the core is about 17 working days. Part A alone (42 h) proves "off = zero calls" and can merge first.

### 5.3 Migration
**One additive migration: `tr<N>_trial_ai_ready.py`, revision `tr<N>aiready`, `down_revision` = Lane 2's head at step 0** (after DB-1; today the head is `tr30personaldata` on `feat/b8-eu-gb-mir` and `tr31othercountries` on `feat/b9b-other-countries`). Under the one-head rule it is **re-attached at merge** after whatever lands first.
- `tenants.ai_features JSONB NOT NULL DEFAULT '{}'` (check: a JSON object of known feature keys to booleans).
- `ai_calls` (columns in 4.3), tenant-scoped, forced row-level security, append-only trigger, index on (tenant, feature, created).
- `ai_output_reviews` (columns in 4.4), tenant-scoped, forced row-level security, append-only.
- No data step, no backfill. Downgrade drops the three; it refuses while `ai_calls` has rows (no silent loss of audit records).
- Parts A–D need only this one. If the owner wants no migration, the per-call record and the reviews cannot be built, and AI-R cannot meet its own Definition of done (AI-D13).

### 5.4 Switches
| Switch | Default | Off means |
|---|---|---|
| `MDARIX_GENAI_PROVIDER` | `controlled` | No model anywhere; every feature answers from rules and says so |
| `MDARIX_AI_FEATURES` | empty | No feature may call a model, whatever the organisations say |
| `tenants.ai_processing_allowed` | false | This organisation's content goes to no model |
| `tenants.ai_features[feature]` | absent (off) | This feature calls no model for this organisation |
| `MDARIX_GENAI_VERTEX_ZDR` | unset | Production refuses Vertex (`genai/policy.py:76`) |

The switch-OFF path for an emergency: set `MDARIX_GENAI_PROVIDER=controlled` and restart the API. Step 7 proves it gives zero calls.

### 5.5 What can be cut (in this order)
1. Step 10 (code suggestions). 2. The metrics screens in step 12 (the API and the drift pause stay). 3. Qualification cases down to 8 per feature (each category once, 2 hallucination traps, 1 refusal) — the bar does not drop. 4. Decision advisory stays not offered (no change needed).

**Never cut:** the three switches defaulting off; the zero-calls proof; `feature=` required; the per-call record; a person's review before any downstream use; no automatic runs; High risk refused; masking and the protected fields; the dev/qualification split and the signed lock; the fingerprint stop; the fake model for all tests; live runs only with the owner's OK; the CI spend fix.

### 5.6 Scenarios to add (AI-xx)
Off: AI-01 platform `controlled` = zero calls in every feature; AI-02 feature not in `MDARIX_AI_FEATURES` = zero calls; AI-03 organisation off = zero calls; AI-04 organisation feature off = zero calls; AI-05 free trial = zero calls whatever the switches; AI-06 budget used up = zero calls; AI-07 production, feature not qualified = zero calls; AI-08 unknown feature refused; AI-09 emergency switch-off. Switches: AI-10 customer admin turns a feature on with reason and MFA, audited; AI-11 admin cannot turn on a feature the platform does not allow; AI-12 another organisation's switches and calls unseen. Record: AI-13 one call record per answer with prompt hash and model id; AI-14 no masked content stored; AI-15 personal data in evidence never in a request. Review: AI-16 unreviewed analysis absent from the Decision Brief; AI-17 accepted analysis present; AI-18 edit keeps both texts; AI-19 rejected never used; AI-20 opening a case starts no AI run; AI-21 AI codes not swept by "Confirm all codes"; AI-22 decision advisory not offered. Qualification: AI-23 qualification and dev sets do not overlap; AI-24 hallucination trap answered "I don't know"; AI-25 changed prompt stops the feature in production; AI-26 changed model stops every feature; AI-27 live run refused without the spend flags. Provider: AI-28 Vertex address in Mumbai, keyless token reused; AI-29 a moving model name refused in production. Drift: AI-30 rejected share above threshold pauses the feature and alerts once.

---

## 6. Definition of done (v2.1 item 7), per part
Each part is "complete" only when: (1) this spec is approved; (2) its steps are built; (3) its targeted tests pass on the fake model; (4) security and permission tests pass, including negative cases (wrong role, other organisation, missing MFA, each switch level off, unknown feature, trial, both sides of each threshold); (5) the regression suites in step 19 pass with AI off and with the fake model on; (6) evidence is stored (test output, the zero-calls matrix, the fake qualification report, screenshots) and the user guide, runbook, register and CHANGELOG are updated; (7) the owner's acceptance is recorded in this file. A screen existing is not "complete". Each part also gets one independent read-only review before acceptance. **AI-R complete does not mean AI on:** switching on is section 9, a separate owner decision.

---

## 7. Owner decisions

⚑ = touches patient safety, personal data, customer promises or spend: **needs your explicit answer.** "If no answer" is what the build does meanwhile.

| # | Decision | Recommendation |
|---|---|---|
| AI-D1 ⚑ | Exact model | Pin the Vertex model chosen on 16 Oct (`gemini-2.5-flash`) only if Google still lists it as generally available in `asia-south1` with a retirement date at least 6 months after switch-on; otherwise the current stable Flash model there. Record the id, version and retirement date in the register. The build uses no real model at all. *If no answer:* nothing pinned, so production refuses any provider (AI stays off). |
| AI-D2 ⚑ | Residency and backup | Production AI only in `asia-south1`; no production fallback (if Vertex is down, the rules answer); OmniRoute for development on synthetic data only. *If no answer:* as recommended. |
| AI-D3 ⚑ | Zero data retention (owner and Google) | Set `MDARIX_GENAI_VERTEX_ZDR=true` only after (1) the project cache is confirmed off and (2) abuse-monitoring logging is confirmed not to apply, or Google's written exception; never use `MDARIX_GENAI_ACCEPT_RETENTION` for Vertex. *If no answer:* unset: production refuses Vertex. |
| AI-D4 ⚑ | Intended use and risk per feature | As section 3: no High; Ask and summaries Low; the rest Medium. *If no answer:* every feature stays off the platform list. |
| AI-D5 ⚑ | Decision Center advisory | Not offered in AI-R (it sits beside a human decision; risk of leaning on it). Its provenance is fixed anyway. *If no answer:* not offered. |
| AI-D6 ⚑ | Case AI run on first open | Remove the automatic run: AI runs only when a person asks. *If no answer:* on request only. |
| AI-D7 ⚑ | Downstream use | Decision Brief, readiness, reports, codes and observations use an AI item only after a person accepts or edits it. *If no answer:* as recommended. |
| AI-D8 ⚑ | Pass criteria | Safety 100%; content at least 90% per feature, at least 80% per category; case analysis 15 of 15. *If no answer:* 100% on everything (stricter; AI may stay off longer). |
| AI-D9 ⚑ | Who writes and signs the qualification set | Your co-founder or a QA consultant writes or reviews it; you sign; the build agent writes only the development set. *If no answer:* the agent drafts it marked "not independent", and the sign-off bar stays NOT MET until a person who did not write the prompts signs. |
| AI-D10 ⚑ | Live qualification spend | Only with your OK per run, after the company is registered and billing is upgraded (from 16 Nov the free credit does not cover Gemini); the command needs `--confirm-spend` and a token cap. *If no answer:* no live run. |
| AI-D11 ⚑ | What the call record keeps | The model's output and the hash of the masked content sent, not the content; same retention as the organisation's other records. *If no answer:* as recommended. |
| AI-D12 | Code suggestions | Build last (part D), cut first if late. |
| AI-D13 | Migration | Yes, one additive migration (5.3). |
| AI-D14 | Free trials | AI stays off for free trials (existing rule, `genai/governance.py:136`). |
| AI-D15 | Switching an organisation on | Customer admin with reason, acknowledgement and fresh MFA; the platform admin only with the customer's approved support access (existing). |
| AI-D16 ⚑ | Drift response | Rejected share +15 points over 30 days (20+ reviews) or blocks above 5%: alert and pause that feature for that organisation until you clear it. *If no answer:* as recommended (pause). |
| AI-D17 ⚑ | "Zero AI calls" wording | Means zero calls to an AI model that writes text. The local search model (on MDARIX's server, sends nothing out, writes nothing) is not counted, and the user guide and privacy text say so. *If no answer:* as recommended, with that sentence in every place that says "AI off". |
| AI-D18 | Old provider branches | After the cherry-pick, `ai/vertex-provider` and `ai/omniroute` carry nothing new; you may delete them later (no agent changes git branches). |

**Needing your explicit answer:** AI-D1, D2, D3, D4, D5, D6, D7, D8, D9, D10, D11, D16, D17.

---

## 8. Owner and provider items (not build work)
| Item | Why | When |
|---|---|---|
| Company registration, then Google Cloud billing upgrade | Gemini is not covered by the free credit from 16 Nov; the upgrade needs the registered name | Before any live run |
| Google: cache off, abuse-monitoring exception or invoiced billing, written ZDR confirmation | AI-D3 | Before switch-on |
| Google: model list and retirement date in `asia-south1` | AI-D1 | At switch-on |
| A person for the qualification set (writer or reviewer, then your signature) | AI-D9 | During part C |
| Your consultant: whether draft EU GMP Annex 22 and FDA/notified-body expectations change the risk levels | Section 3 | Before the first customer switch-on |

---

## 9. Switch-ON procedure (checklist, for later)
Nothing here happens in AI-R. Each line is ticked with a date and a name in the runbook.

1. **Owner decision recorded:** which features, which organisations, the date.
2. **Billing:** company registered; billing account upgraded; budget with alerts at 50%, 90% and 100%.
3. **Provider assessment and register row complete** (no `TBD`): contract and data processing addendum acceptance date, no training, ZDR conditions met, region `asia-south1`, model id and retirement date.
4. **Google Cloud project:**
   - enable the Vertex AI API;
   - grant the **Vertex AI User** role to the VM's service account;
   - if the VM lacks the `cloud-platform` access scope or a service account, changing it **stops the VM for about 5 minutes**: owner approval and an announced window first;
   - switch off the project's Gemini cache and check it reads off;
   - no grounding with Google Search or Maps.
5. **Server settings:** `MDARIX_GENAI_PROVIDER=vertex`, `_PROJECT`, `_LOCATION=asia-south1`, `_MODEL=<pinned id>`, `_MODEL_VERSION`, `MDARIX_GENAI_CONTRACTED_PROVIDERS=vertex`, `MDARIX_GENAI_VERTEX_ZDR=true`, `MDARIX_GENAI_COST_PER_1K_TOKENS` (required, `config_check.py:433`), `MDARIX_AI_FEATURES=<qualified features only>`. Run `python scripts/ai_provider_preflight.py`: all PASS.
6. **Qualification passed:** live run with your OK (AI-D10), on a synthetic organisation, on the Google Cloud VM (the keyless token works only there); release record committed with one fingerprint per feature.
7. **Golden set signed** by a named person who did not write the prompts.
8. **Release gate** shows every bar MET, including each feature's bar.
9. **First live call checks** (one synthetic request per feature): an answer is present and not cut off; thinking tokens versus max output (if thinking used half or more of the allowance, or the reply stopped at the length limit, lower the reasoning effort or raise max output: a Moderate change, so re-qualify); the address is Mumbai; a call record is written; the personal-data case shows masks only.
10. **Organisation switch-on:** the customer admin turns AI on, then each feature, with reasons and MFA.
11. **First two weeks:** read the oversight metrics daily.
12. **Switch-off path tested:** `MDARIX_GENAI_PROVIDER=controlled`, restart, zero calls.

---

## 10. What I did not check
- DB-1's branch was not read; its migration head and any changes to the files cited here are unknown. Step 0 re-checks every line on Lane 2's tip.
- Whether the cherry-pick applies with exactly two conflicts: inferred from `git diff 825e96ef feat/b8-eu-gb-mir` on the five files, not tried (no merge or cherry-pick was run).
- Google's current model list, retirement dates, thinking defaults and the OpenAI-compatible reasoning setting on Vertex were not looked up: to confirm at switch-on (AI-D1, section 9 step 9).
- Whether the production VM already has the `cloud-platform` scope (decides whether a VM stop is needed).
- Draft EU GMP Annex 22 was not re-read; the independence principle is cited from memory: to confirm with your consultant.
- Frontend AI screens were located (`frontend/src/features/customer-admin/sections/Security.tsx`, `frontend/src/features/admin/customers/TenantPages.tsx`) but not read; step 12's 12 h is an estimate.
- The `ai/extractor.py` path in daily use, and `failure_chain` (parked under the `mvp` feature set), were not traced end to end.
- No database was queried; no test was run. Hours are estimates from B6a and B9 steps of similar size.

---

## Owner approval (11 Nov 2026)
The owner replied **"approve AI-R spec"**: every recommendation is accepted as written, including all flagged decisions (D1 model pinned only if still offered in Mumbai with >= 6 months to retirement, else the current stable Flash; D2 Mumbai only, no production fallback, OmniRoute for development on synthetic data only; D3 zero data retention only after Google confirms in writing; D4 no AI feature may decide; D5 no AI in the Decision Centre advisory; D6 no automatic case runs; D7 only reviewed AI items feed downstream; D8 safety 100%, content >= 90% per feature, case analysis 15/15; D9 qualification set written or reviewed by Sriharsha or a QA consultant and signed by the owner; D10 live spend only with the owner's OK per run, after the billing upgrade, with a token cap; D11 output plus a hash of what was sent; D16 drift alert and per-organisation pause; D17 local search model wording). Builds in Lane 2 after DB-1. Switch-ON remains a separate owner decision per the §9 checklist.
