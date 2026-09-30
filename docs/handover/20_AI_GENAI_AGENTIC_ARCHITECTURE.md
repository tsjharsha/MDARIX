# AI, GenAI and Agentic Architecture

MDARIX separates deterministic intelligence, retrieval, provider calls and human decisions.

## Provider layer

`genai/provider.py` abstracts provider execution. The local product supports Ollama and Groq configuration with timeout/retry behavior, deterministic fallback, structured output, secret filtering, no hidden chain-of-thought persistence and human-review-required output.

## Intelligence modules

- `ai`: orchestration and shared context boundaries.
- `retrieval`: authorized structured/vector retrieval.
- `investigator`: investigation analysis.
- `hypothesis_engine`: competing hypotheses.
- `challenger`: adversarial/alternative explanation checks.
- `unknowns`: explicit evidence gaps.
- `failure_chain`: bounded failure-chain structures.
- `scenario_intelligence` and `counterfactual`: comparison and what-if support.
- `trust_engine` and `evaluation`: assurance, evaluation and release evidence.
- `ask_mdarix`: authenticated question/session workflow.

## Safety boundary

AI is advisory. It cannot override authorization, establish root cause, make regulatory determinations, approve decisions, sign records or perform uncontrolled external writes. Context must be tenant-filtered, field-policy filtered, temporal, provenance-aware and explicit about contradictions, unknowns and retrieval gaps.

## Status

Provider abstraction and deterministic safety foundations are implemented. Complete production-scale vector validation, hosted provider monitoring, cost reconciliation and every browser workflow remain environment-dependent.
