# AI providers: free fallbacks for demos, paid for production

MDARIX calls one AI model through an OpenAI-compatible chat API (`genai/provider.py`). When that provider is
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

Options include:
- Anthropic Claude: directly, or through AWS Bedrock or Google Vertex AI.
- Azure OpenAI.
- Google Vertex AI (Gemini).
- Groq or Cerebras paid tiers.

Keep a second paid provider as the fallback in production, configured the same way.
