# AI providers: free fallbacks for demos, paid for production

MDARIX calls one AI model through an OpenAI-compatible chat API, or Anthropic's own Messages API for
`anthropic` (`genai/provider.py`). When that provider is
rate-limited or down, MDARIX tries the **fallback providers** in order. If none answers, the investigator uses its
**rule-based answer**, so a page never fails because of the AI.

```text
Groq ─(limit / outage)→ Cerebras ─→ Gemini ─→ OpenRouter ─→ local Ollama ─→ rule-based answer
```

A provider that hits its limit **rests** for `MDARIX_GENAI_RATE_LIMIT_REST_SECONDS` (default 15 min); one that is
down rests for `MDARIX_GENAI_OUTAGE_REST_SECONDS` (default 60 s). A resting provider is not waited on: it is tried
last. Every AI run records which provider answered. AI Control Center → Overview lists the chain and each
provider's state.

## Free options (check each provider's current terms: free limits change often)

| Provider | Setting name | Why it fits | Watch out |
|---|---|---|---|
| **Cerebras** | `cerebras` | Very fast; serves the same open model as today (gpt-oss-120b) on a free tier with generous daily tokens | Free-tier limits per minute and per day |
| **Google Gemini API** (AI Studio key) | `gemini` | Strong free tier on Gemini Flash models; supports JSON output | On the free tier Google may use requests to improve its models, so use synthetic data only |
| **OpenRouter** | `openrouter` | One key for many models; models ending `:free` cost nothing | Small daily request cap without credits; free models come and go |
| **Mistral** ("Experiment" plan) | `mistral` | Free plan with rate limits; EU provider | Requests may be used for training on the free plan |
| **Ollama** (local) | `ollama` | Runs on the demo laptop: no limits, no internet, no data leaves the machine | Needs free memory (about 3 GB for `llama3.2`, about 1.5 GB for `llama3.2:1b`); smaller models give weaker answers; the first request loads the model, so it gets 120 s |

GitHub Models (`github`) was retired by GitHub on 30 July 2026. A retired or misspelt name in
`MDARIX_GENAI_FALLBACKS` is skipped: the API logs a warning and AI Control Center shows it as **Not used** with the
reason.

Default models (checked 3 October 2026): Gemini `gemini-flash-latest` (follows Google's current Flash model),
OpenRouter `nvidia/nemotron-3-super-120b-a12b:free`, Mistral `mistral-small-latest`. Free OpenRouter models are often
rate-limited upstream and come and go; pick another from https://openrouter.ai/models?max_price=0 with
`MDARIX_GENAI_OPENROUTER_MODEL` if needed.

**Recommended for demos:** Groq, then Cerebras (same model family, so answers stay alike), then Gemini, then
Ollama as the offline safety net.

## Setup

1. Create a free account and an API key with each provider you choose.
2. Add them to `.env` on the server:

```dotenv
MDARIX_GENAI_PROVIDER=groq
MDARIX_GENAI_API_KEY=<groq key>
MDARIX_GENAI_MODEL=openai/gpt-oss-120b

MDARIX_GENAI_FALLBACKS=cerebras,gemini,ollama
MDARIX_GENAI_CEREBRAS_API_KEY=<cerebras key>
MDARIX_GENAI_GEMINI_API_KEY=<gemini key>
# Optional per provider: MDARIX_GENAI_<NAME>_MODEL, _BASE_URL, _TIMEOUT_SECONDS, _MAX_RETRIES
```

3. For Ollama, install it, run `ollama pull llama3.2` (or a larger model), and it serves on `127.0.0.1:11434`.
4. Restart the API. Check AI Control Center → Overview → Fallback providers: each should read **Ready**.

Default models live in `OPENAI_COMPATIBLE` in `genai/provider.py`; override them with `MDARIX_GENAI_<NAME>_MODEL`
when a provider renames them.

## MVP and production: a paid provider

Free tiers are for demonstrations on synthetic data. With real customer quality data (complaints, investigations),
use a paid provider under a contract that covers:
- no training on your data;
- limited or zero retention;
- a data processing agreement, and a BAA where health data is involved;
- the region you need.

Record each one in `docs/compliance/AI_PROVIDER_REGISTER.md` (contract reference, training opt-out, retention,
region, review date) before naming it in `MDARIX_GENAI_CONTRACTED_PROVIDERS`.

In staging and production the API refuses to start, and every model request skips the provider, unless:
1. the provider is named in `MDARIX_GENAI_CONTRACTED_PROVIDERS` (or is `ollama` on your own server), and
2. its retention is cleared: `MDARIX_GENAI_<NAME>_ZDR=true` once the contract or account setting confirms zero data
   retention, or `MDARIX_GENAI_ACCEPT_RETENTION=true` when the data processing agreement accepts the provider's
   limited retention (for example 30 days for abuse monitoring). Leave both unset until one is true.

Supported provider names:

| Provider | Setting name | Endpoint used | Default model |
|---|---|---|---|
| **Anthropic Claude** (direct API) | `anthropic` | `https://api.anthropic.com/v1/messages` (Messages API: `x-api-key` and `anthropic-version: 2023-06-01` headers, system prompt as its own field, no temperature) | `claude-sonnet-5-5` |
| Groq (paid tier) | `groq` | `https://api.groq.com/openai/v1/chat/completions` | `openai/gpt-oss-20b` |
| Cerebras (paid tier) | `cerebras` | `https://api.cerebras.ai/v1/chat/completions` | `gpt-oss-120b` |
| Mistral (paid plan, EU) | `mistral` | `https://api.mistral.ai/v1/chat/completions` | `mistral-small-latest` |
| Google Gemini API (paid tier) | `gemini` | Gemini's OpenAI-compatible endpoint | `gemini-flash-latest` |
| **Google Cloud Vertex AI** (Gemini) | `vertex` | `https://<region>-aiplatform.googleapis.com/v1/projects/<project>/locations/<region>/endpoints/openapi/chat/completions`, built from `MDARIX_GENAI_PROJECT` and `MDARIX_GENAI_LOCATION` (default `asia-south1`); no API key: an access token from the VM's metadata server | `google/gemini-2.5-flash` |
| Ollama (self-hosted) | `ollama` | `http://127.0.0.1:11434/v1/chat/completions` | `llama3.2` |
| OmniRoute (self-hosted gateway) | `omniroute` | `http://127.0.0.1:20128/v1/chat/completions` (override with `MDARIX_GENAI_OMNIROUTE_BASE_URL`) | `auto` (set `MDARIX_GENAI_OMNIROUTE_MODEL` to your OmniRoute model or combo) |

OmniRoute is a router, not a model provider: the request goes on to whichever upstream providers are configured in it.
It is **not** treated as self-hosted. In staging and production, name `omniroute` in `MDARIX_GENAI_CONTRACTED_PROVIDERS`
and set `MDARIX_GENAI_OMNIROUTE_ZDR=true` **only when every upstream it can route to** is under contract with zero data
retention and recorded in `docs/compliance/AI_PROVIDER_REGISTER.md`. With free upstreams, use synthetic data only.

```dotenv
MDARIX_GENAI_PROVIDER=omniroute
MDARIX_GENAI_OMNIROUTE_API_KEY=<key created in the OmniRoute dashboard>
MDARIX_GENAI_OMNIROUTE_MODEL=<model or combo name>
```

Anthropic example (`.env` on the server):

```dotenv
MDARIX_GENAI_PROVIDER=anthropic
MDARIX_GENAI_API_KEY=<anthropic key>
MDARIX_GENAI_MODEL=claude-sonnet-5-5
MDARIX_GENAI_CONTRACTED_PROVIDERS=anthropic
MDARIX_GENAI_ANTHROPIC_ZDR=true   # only once zero data retention is confirmed for the account
```

Vertex AI example (`.env` on the Google Cloud VM):

```dotenv
MDARIX_GENAI_PROVIDER=vertex
MDARIX_GENAI_PROJECT=<google cloud project id>
MDARIX_GENAI_LOCATION=asia-south1          # Mumbai: processing stays in India
MDARIX_GENAI_MODEL=google/gemini-2.5-flash # check the region's model list before changing it
MDARIX_GENAI_CONTRACTED_PROVIDERS=vertex
MDARIX_GENAI_VERTEX_ZDR=true               # only once the cache is off and abuse logging does not apply
```

Before it is used, in the Google Cloud project: enable the Vertex AI API; give the VM a service account with the
`Vertex AI User` role and the `cloud-platform` access scope (changing either needs the VM stopped); switch off the
project's Gemini input cache; and confirm abuse-monitoring logging does not apply (invoiced billing account) or ask
Google for the exception. The token is read from the metadata server, so Vertex only works on a Google Cloud VM;
elsewhere, set `MDARIX_GENAI_BASE_URL` and an `MDARIX_GENAI_API_KEY` access token yourself.

Claude through AWS Bedrock or Google Vertex AI, and Azure OpenAI, need their own request signing and are not
supported by `genai/provider.py` today.

Keep a second paid provider as the fallback in production, configured the same way (its own
`MDARIX_GENAI_<NAME>_ZDR`).

## The AI release gate: before AI is switched on for a pilot

AI stays off for pilots until four bars are met (`backend/app/ai_release_gate.py`). In production
(`MDARIX_ENV=production`) switching AI processing on for an organization is refused with `AI_RELEASE_GATE_NOT_MET`
until they are; staging shows the gate without enforcing it, so the rehearsal can run. Administrators see the four
bars under Security › AI processing; MDARIX staff see them, with what to do, in the AI Control Center overview
(`GET /api/v1/ai/release-gate`).

1. **A contracted provider with zero data retention**: configured as above, listed in
   `MDARIX_GENAI_CONTRACTED_PROVIDERS` with its ZDR setting (read from those settings, never from the development
   policy, which allows any provider). `python scripts/ai_provider_preflight.py` checks every setting, sends nothing
   and says what to fix.
2. **The golden dataset signed off by a person**: `python scripts/golden_review_pack.py` writes the review pack
   (`artifacts/golden-dataset-review-pack.md`: each scenario's question, evidence, expected findings, forbidden
   conclusions and adversarial check, with a checklist; about two minutes a scenario). After reviewing it, the
   reviewer runs, themselves:

   ```bash
   python scripts/qualify_ai_golden_dataset.py --human-sign-off --name "First Last" --role "Head of Quality" --confirm
   ```

   This writes `evaluation/GOLDEN_DATASET_HUMAN_SIGN_OFF.json`, bound to the lock's hashes; a changed dataset needs a
   new sign-off. Names that read as a tool, an agent or a team are refused. Nobody signs on someone else's behalf.
3. **The golden evaluation passed with this model**: on staging, with the contracted provider configured:

   ```bash
   python scripts/run_real_evaluation.py --pause 5 --gate --require-model --switch-ai-on --release-record
   ```

   Only a run where all 15 scenarios pass, every analysis written by the model, on the signed-off dataset, writes
   `evaluation/AI_RELEASE_RECORD.json` with the provider and model. Production accepts only that model: changing the
   provider or the model needs a new passing run.
4. **Every AI result checked automatically**: built in (`trust_engine/auto.py`). Every AI result is checked as it is
   saved (sources exist, no stated cause or decision, no asserted certainty, provenance) and shows its trust check.

Commit the sign-off and the release record with the release; the API image ships them. An organization that already
had AI on keeps it; the screens show the gate's state.

## Switches, all off by default (AI ready, switched off)

A model is called only when every level allows it:

| Switch | Default | Off means |
|---|---|---|
| `MDARIX_GENAI_PROVIDER` (paid organizations) | `controlled` | No model for paid organizations |
| `MDARIX_AI_TRIAL_CHAIN` (free trials) | empty | No model for free trials (a trial's switch-on is refused with 409) |
| `MDARIX_AI_FEATURES` (platform feature list) | empty | No feature calls a model |
| Organization: `tenants.ai_processing_allowed` | off | This organization's content goes to no model |
| Organization feature: `tenants.ai_features[feature]` | absent | This feature calls no model for this organization |
| Person (free trials only): `auth_users.ai_access` | ACTIVE | INACTIVE: "AI is not enabled for your account" |

Every request names its feature (`genai/features.py`); the decision advisory is not offered. Each request sent writes
one `ai_calls` row (hashes of what was sent, never the content; the gateway and the provider and model that actually
answered; tokens; outcome). A person accepts, edits or rejects AI results (`POST /api/v1/ai-outputs/{id}/review`);
the Decision Center uses a model's result only after that. Opening a case never starts an AI run.

**Emergency off:** `MDARIX_GENAI_PROVIDER=controlled` (everyone) or an empty `MDARIX_AI_TRIAL_CHAIN` (trials only),
then restart the API. `tests/test_ai_r_zero_calls.py` proves each level gives zero calls.

## Free-trial chain (sample data only; owner amendment 14 Nov 2026)

- Order: FreeLLMAPI -> OmniRoute -> Groq. Set `MDARIX_AI_TRIAL_CHAIN=freellmapi,omniroute,groq` and each
  provider's `MDARIX_GENAI_<NAME>_API_KEY` (FreeLLMAPI and OmniRoute keys are their own gateway keys; upstream keys are
  entered only in each gateway's own key store, never in MDARIX's settings). Only names vetted in
  `genai/vetted_providers.json` are used; in staging and production the gateways must be on 127.0.0.1.
- Failover: connection failure, timeout, 408 or 5xx -> next, rests 60 s; 429 -> next at once, rests 15 min;
  401/403 -> next, rests 1 hour, operator alert; empty or invalid structured answer -> next; reply from an upstream
  not vetted (or none named) -> discarded, next, the gateway rests 1 hour, alert; 400/413 -> stop, rules answer.
  Timeouts: FreeLLMAPI 30 s, others 20 s; no retries; 60 s in total; then the rules answer.
- Sample data only: every request lists the records it carries; each must be this trial's own unedited sample
  record (`source_system = MDARIX_SAMPLE`, text still matching the sample). Typed text (the Ask question) is capped
  at 300 characters. No request may write the sample marker (422).
- The trial's owner switches AI on with a second acknowledgement (sample data only, free AI services, possibly
  outside India); a Platform Administrator sets each user's switch (`PUT /api/v1/platform-admin/trial-organizations/{id}/
  users/{user_id}/ai-access`, or `.../trial-organizations/{id}/ai-access` for everyone; body `{active, reason}`),
  audited `TRIAL_USER_AI_ACCESS_CHANGED`; switching AI on (trial owner or Platform Administrator) needs the password
  and an authenticator code.
- Owner items before any trial sees AI: provider terms checked and recorded in the register; the trial agreement,
  terms, privacy policy and sub-processor list updated (they promise AI off in trials today); the production pause
  lifted for installing FreeLLMAPI beside MDARIX (loopback only, pinned version).

## Trial AI gateways on the server

FreeLLMAPI (3011) and OmniRoute (20128) run on the VM itself, bound to the host's `127.0.0.1`, and MDARIX calls them
only at `http://127.0.0.1:3011` and `http://127.0.0.1:20128` (the staging and production loopback check is unchanged).
Inside a container `127.0.0.1` is the container, so `docker-compose.prod.yml` adds three small forwarders
(`scripts/ai_loopback_forwarder.py`, 64 MB each, no published ports):

- `ai-loopback-api` and `ai-loopback-background` share the network namespace of `api` and `background` and listen on
  their `127.0.0.1:3011` and `:20128` only.
- They pass each connection to `10.99.211.1`, the gateway address of the `ai-host` network (`10.99.211.0/29`, host
  bridge `mdarix-ai`), where `ai-host-bridge` (host network) listens, and only there, never on `0.0.0.0` or a public
  address. It passes the connection on to the gateway on the host's `127.0.0.1`.
- Without the gateways everything still starts: each call is closed at once (the forwarder logs "not reachable") and
  the trial chain moves on. The gateways may start before or after the stack; nothing is cached between connections.

Firewall: never open 3011 or 20128 on the VM's firewall or the cloud firewall. The host firewall must let the
`mdarix-ai` bridge reach the forwarder (with `ufw`'s default deny the calls are dropped otherwise):

```bash
sudo ufw allow in on mdarix-ai to 10.99.211.1 port 3011,20128 proto tcp
# Oracle images without ufw (STAGING_ORACLE.md section 3.1): above the REJECT line N, then save the rules as there
sudo iptables -I INPUT N -i mdarix-ai -d 10.99.211.1 -p tcp -m multiport --dports 3011,20128 -j ACCEPT
```

Smoke check, from inside the API container (any HTTP status, 401 included, means the gateway answered):

```bash
docker compose exec api python -c "
import urllib.error, urllib.request
for port in (3011, 20128):
    try:
        status = urllib.request.urlopen(f'http://127.0.0.1:{port}/v1/models', timeout=5).status
    except urllib.error.HTTPError as error:
        status = error.code
    print(port, status)"
```

If it fails: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3011/v1/models` on the host (gateway running?);
`docker compose logs ai-host-bridge ai-loopback-api` ("not reachable" names the hop that failed); the firewall rule
above; `docker compose ps` shows `ai-loopback-*` unhealthy after `api` or `background` restarted on its own, then
`docker compose up -d --force-recreate ai-loopback-api ai-loopback-background`. Repeat the check with `background`.

## Refusals people see

When no model may answer, MDARIX answers from rules and says why with a stable code
(`genai/provider.py` `REFUSAL_MESSAGES`): `GENAI_DISABLED_FOR_ORGANIZATION` (AI switched off for the organization),
`GENAI_MONTHLY_BUDGET_REACHED` (monthly allowance used up), `GENAI_PROVIDER_NOT_ALLOWED` (no provider cleared for
customer data here) and `GENAI_UNAVAILABLE` (provider down, rate-limited or the request too large). Customer
administrators are told when their organization reaches 80% and 100% of its monthly allowance; operators get an
alert (`MDARIX_ALERT_WEBHOOK` / `MDARIX_ALERT_EMAIL`) at 100%.
