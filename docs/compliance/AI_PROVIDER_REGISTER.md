# AI provider register

Every AI provider that may receive customer content in staging or production is recorded here **before** it is
named in `MDARIX_GENAI_CONTRACTED_PROVIDERS`. The register is the evidence behind that setting: auditors and
customers can see which contract covers each provider, whether it trains on the content, how long it keeps it,
where it processes it, and when the entry was last reviewed.

How the settings enforce it (`genai/policy.py`, checked at start-up by `backend/app/config_check.py` and on every
model request by `genai/provider.py`):

- Only `ollama` (self-hosted) and providers listed in `MDARIX_GENAI_CONTRACTED_PROVIDERS` may receive customer
  content. Free models (OpenRouter names ending `:free`) are refused even when listed.
- A listed provider must also have its retention cleared: `MDARIX_GENAI_<NAME>_ZDR=true` once zero data retention
  is confirmed in writing (contract or account setting), or `MDARIX_GENAI_ACCEPT_RETENTION=true` when the data
  processing agreement accepts the provider's limited retention. Record which one applies in the table below.
- Personal information is masked before every request (`genai/pii.py`), and each organization's AI switch and
  monthly allowance apply (`genai/governance.py`). AI processing is off for a new organization until its
  administrator switches it on and acknowledges the provider named in its settings.

## Register

Replace every `TBD` before the provider goes live. An entry without a contract reference may not be listed in
`MDARIX_GENAI_CONTRACTED_PROVIDERS`.

| Provider (setting name) | Contract / DPA reference | Training on customer content | Retention / ZDR | `_ZDR` or accepted retention | Processing region | Owner | Last review | Next review |
|---|---|---|---|---|---|---|---|---|
| Anthropic (`anthropic`) | TBD (commercial terms + DPA reference) | TBD (commercial API terms: confirm "no training" clause) | TBD (zero data retention addendum, or standard retention period) | TBD (`MDARIX_GENAI_ANTHROPIC_ZDR=true` or `MDARIX_GENAI_ACCEPT_RETENTION=true`) | TBD | TBD | TBD | TBD |
| Groq paid tier (`groq`) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Cerebras paid tier (`cerebras`) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Mistral paid plan (`mistral`) | TBD | TBD | TBD | TBD | TBD (EU) | TBD | TBD | TBD |
| Google Cloud Vertex AI, Gemini (`vertex`) | TBD (Google Cloud Terms of Service + Cloud Data Processing Addendum, accepted with the billing account; record the billing account and acceptance date) | None: the Service Specific Terms forbid training on customer content without permission (confirm at review) | Zero data retention once (1) the project's 24-hour in-memory cache is switched off and (2) abuse-monitoring prompt logging does not apply (invoiced billing account) or Google has granted the exception; no grounding with Google Search or Maps | TBD (`MDARIX_GENAI_VERTEX_ZDR=true` only once both are confirmed) | asia-south1 (Mumbai, India) | TBD | TBD | TBD |
| Google Gemini API paid tier (`gemini`) | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| Ollama, self-hosted (`ollama`) | Not applicable: runs on MDARIX's own server | None: nothing leaves the server | Not applicable | Not required | Same as the MDARIX server | TBD | TBD | TBD |

Providers that are **never** listed for customer content: free tiers of any service (they may keep requests or use
them to train models), OpenRouter `:free` models, and GitHub Models (retired 30 July 2026).

## Free-trial chain (sample data only)

Owner amendment of 14 Nov 2026 (decisions AI-D14a, AI-D2a, AI-D19, T1-T8): an organization on the Free Trial plan
may use AI **on the sample data only** (a trial's own records get "AI available on paid plans" and no call), through
`MDARIX_AI_TRIAL_CHAIN` (empty by default = off; intended `freellmapi,omniroute,groq`). Paid organizations and pilots
never use this chain, and the chain never holds a paid provider. Sample data may leave India here (decision T7).

The machine-readable register is `genai/vetted_providers.json` (read by the code, under AI change control: a new or
changed row is a Major change). An upstream may answer only when commercial use is allowed, it does not train on the
data (or an opt-out is confirmed), and its terms were checked less than 12 months ago (a warning from 6 months,
decision T8). A reply whose actual upstream (FreeLLMAPI's `X-Routed-Via`, OmniRoute's `X-OmniRoute-Provider` and `X-OmniRoute-Model` headers; a cached OmniRoute reply is discarded) is not vetted is
discarded unread. Free-model results never count as qualification.

| Provider | Kind | Terms link | Commercial use | Trains on data | Region | Date checked | Checked by |
|---|---|---|---|---|---|---|---|
| FreeLLMAPI (`freellmapi`) | Gateway on the MDARIX server, 127.0.0.1 only; only vetted upstream keys entered; MDARIX's key scoped to vetted models | Not applicable (self-hosted software; pinned version, dependency review at each upgrade) | n/a | n/a | Loopback | TBD | TBD |
| OmniRoute (`omniroute`) | Gateway on the MDARIX server, 127.0.0.1 only; only vetted upstreams in its combo | Not applicable (self-hosted) | n/a | n/a | Loopback | TBD | TBD |
| Groq free tier (`groq`), last in the chain | Upstream, called directly | TBD | TBD | TBD | TBD | TBD | TBD |
| Each upstream behind FreeLLMAPI or OmniRoute | Upstream | TBD (one row each, added before its key is entered) | TBD | TBD | TBD | TBD | TBD |

Until the owner fills a row (link, date, yes/no answers), that provider is not vetted and the code refuses it.

## Review procedure

1. Before go-live, and at least every 12 months or when the provider changes its terms: confirm the contract and
   DPA references, the training opt-out, the retention period (or ZDR) and the processing region, and update the
   row and the review dates.
2. If retention changes (for example a ZDR addendum ends), change `MDARIX_GENAI_<NAME>_ZDR` the same day; the API
   then refuses the provider until the register and the setting agree again.
3. A new provider, model family or region is a material AI change: run the AI evaluation gate
   (`.github/workflows/ai-evaluation.yml`, `docs/validation/AI_GOLDEN_DATASET_QUALIFICATION.md`) before promoting it.
4. Keep superseded rows in the document history (git), not in the table.

See also `docs/runbooks/AI_PROVIDERS.md` (configuration) and `docs/runbooks/ENVIRONMENT_VARIABLES.md` (settings).

## Provider assessment: Gemini on Google Cloud Vertex AI (paid organizations; DRAFT for the owner, 16 Nov 2026)

What MDARIX enforces in code (tested on fakes; no provider called): the Mumbai region (`asia-south1`) is the only one
accepted in staging and production; the model must be pinned with its version (no moving names); the keyless
service-account token from the metadata server is reused until it expires; tokens used for thinking are counted;
every request is masked and recorded in `ai_calls` with hashes, not content; the provider is refused in production
until `MDARIX_GENAI_VERTEX_ZDR` is set.

| Question | Answer today | Owner item |
|---|---|---|
| Commercial use allowed | Yes, under the Google Cloud terms of the billing account | Confirm on the account once billing is upgraded |
| Trains on customer data | Google states it does not train on customer data sent to Vertex AI | Record the link and date checked |
| Retention | In-memory cache and abuse-monitoring logging may apply | Switch the cache off for the project; get the written exception or invoiced billing; then set `MDARIX_GENAI_VERTEX_ZDR` |
| Region | Mumbai (`asia-south1`), enforced | None |
| Contract | Google Cloud terms and data processing addendum | Accept on the company's account after registration |
| Qualification | Not qualified: Part C (golden dataset v3, `qualify_ai.py`) not built | Decide after #25 |

Conclusion: usable only after the owner items above and AI qualification. Until then every paid organization's AI
stays off.
