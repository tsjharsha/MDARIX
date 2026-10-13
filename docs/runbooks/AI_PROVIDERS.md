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
| Ollama (self-hosted) | `ollama` | `http://127.0.0.1:11434/v1/chat/completions` | `llama3.2` |

Anthropic example (`.env` on the server):

```dotenv
MDARIX_GENAI_PROVIDER=anthropic
MDARIX_GENAI_API_KEY=<anthropic key>
MDARIX_GENAI_MODEL=claude-sonnet-5-5
MDARIX_GENAI_CONTRACTED_PROVIDERS=anthropic
MDARIX_GENAI_ANTHROPIC_ZDR=true   # only once zero data retention is confirmed for the account
```

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

1. **A contracted provider with zero data retention**: configured as above and allowed by the provider policy.
2. **The golden dataset signed off by a person**: after reviewing the 15 scenarios, the reviewer runs, themselves:

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

## Refusals people see

When no model may answer, MDARIX answers from rules and says why with a stable code
(`genai/provider.py` `REFUSAL_MESSAGES`): `GENAI_DISABLED_FOR_ORGANIZATION` (AI switched off for the organization),
`GENAI_MONTHLY_BUDGET_REACHED` (monthly allowance used up), `GENAI_PROVIDER_NOT_ALLOWED` (no provider cleared for
customer data here) and `GENAI_UNAVAILABLE` (provider down, rate-limited or the request too large). Customer
administrators are told when their organization reaches 80% and 100% of its monthly allowance; operators get an
alert (`MDARIX_ALERT_WEBHOOK` / `MDARIX_ALERT_EMAIL`) at 100%.
