"""The AI release gate: the four bars AI must pass before it is switched on for a pilot (MDARIX Final Lightweight MVP
Plan, "AI analysis that earns trust").

1. ``PROVIDER_CONTRACTED``: a provider is configured and allowed here (contracted, zero data retention or retention
   accepted; genai.policy).
2. ``DATASET_SIGNED_OFF``: a named person signed off the golden dataset lock (evaluation/release_record.py).
3. ``GOLDEN_EVALUATION_PASSED``: the full golden evaluation (15 of 15, the model writing every analysis) passed with
   the configured model, on that signed-off dataset (evaluation/AI_RELEASE_RECORD.json).
4. ``TRUST_CHECK_AUTOMATIC``: every AI result is checked as it is saved (trust_engine/auto.py).

In production (``MDARIX_ENV=production``), switching AI processing on for an organization is refused until every bar
is met (``backend/app/ai_settings.py``); elsewhere the gate is shown, not enforced, so staging can rehearse. An
organization that already has AI on keeps its setting; the screens show the gate's state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.request_context import get_request_context

router = APIRouter(prefix="/api/v1/ai", tags=["AI settings"])

MET, NOT_MET = "MET", "NOT_MET"
BAR_TITLES = {
    "PROVIDER_CONTRACTED": "A contracted AI provider with zero data retention",
    "DATASET_SIGNED_OFF": "The golden dataset signed off by a person",
    "GOLDEN_EVALUATION_PASSED": "The golden evaluation passed: 15 of 15 with this model",
    "TRUST_CHECK_AUTOMATIC": "Every AI result checked automatically",
}


def _models() -> list[dict]:
    from backend.app.ai_settings import _models_in_use

    return _models_in_use()


def _bar(code: str, met: bool, detail: str, action: str | None = None) -> dict:
    return {
        "code": code,
        "title": BAR_TITLES[code],
        "status": MET if met else NOT_MET,
        "detail": detail,
        "action": action,
    }


def status(models: list[dict] | None = None, files: tuple | None = None) -> dict:
    """The four bars and whether AI may be switched on for a pilot. ``models``: the configured, allowed models
    (ai_settings._models_in_use); ``files``: (lock, sign-off, record), read from evaluation/ when not given."""
    from evaluation.release_record import load, record_problem, sign_off_problem
    from trust_engine.auto import POLICY

    models = _models() if models is None else models
    lock, sign_off, record = load() if files is None else files
    primary = models[0] if models else None
    bars = []
    if primary:
        bars.append(_bar("PROVIDER_CONTRACTED", True, f"{primary['provider']} {primary['model']}"))
    else:
        bars.append(
            _bar(
                "PROVIDER_CONTRACTED",
                False,
                "No AI provider is configured and allowed here.",
                "Sign the provider contract (zero data retention), then set MDARIX_GENAI_PROVIDER, "
                "MDARIX_GENAI_CONTRACTED_PROVIDERS and the provider's ZDR setting (docs/runbooks/AI_PROVIDERS.md).",
            )
        )
    sign_off_issue = sign_off_problem(lock, sign_off)
    if sign_off_issue is None:
        bars.append(
            _bar(
                "DATASET_SIGNED_OFF",
                True,
                f"Signed off by {sign_off['approved_by']} ({sign_off['role']}) on {str(sign_off['approved_at'])[:10]}.",
            )
        )
    else:
        bars.append(
            _bar(
                "DATASET_SIGNED_OFF",
                False,
                sign_off_issue,
                "A person reviews the 15 scenarios, then runs python scripts/qualify_ai_golden_dataset.py "
                '--human-sign-off --name "First Last" --role "Their role" --confirm and commits the file.',
            )
        )
    record_issue = record_problem(record, lock, sign_off)
    if (
        record_issue is None
        and primary
        and (record["provider"], record["model"])
        != (
            primary["provider"],
            primary["model"],
        )
    ):
        record_issue = (
            f"The evaluation passed with {record['provider']} {record['model']}, not with the model configured here "
            f"({primary['provider']} {primary['model']})."
        )
    if record_issue is None and record is not None and primary:
        evaluation = record.get("evaluation") or {}
        bars.append(
            _bar(
                "GOLDEN_EVALUATION_PASSED",
                True,
                f"{evaluation.get('passed')} of {evaluation.get('total')} with {record['provider']} {record['model']} "
                f"on {str(record.get('released_at'))[:10]}.",
            )
        )
    else:
        bars.append(
            _bar(
                "GOLDEN_EVALUATION_PASSED",
                False,
                record_issue or "Configure the provider first; the evaluation runs with it.",
                "Run python scripts/run_real_evaluation.py --pause 5 --gate --require-model --switch-ai-on "
                "--release-record on staging with the contracted provider, and commit evaluation/AI_RELEASE_RECORD.json.",
            )
        )
    bars.append(_bar("TRUST_CHECK_AUTOMATIC", True, f"Every AI result is checked as it is saved (policy {POLICY})."))
    ready = all(bar["status"] == MET for bar in bars)
    return {
        "ready": ready,
        "met": sum(1 for bar in bars if bar["status"] == MET),
        "total": len(bars),
        "enforced": enforced(),
        "bars": bars,
        "message": "AI may be switched on for a pilot."
        if ready
        else "AI stays off for pilots until every bar is met; every feature works from the records meanwhile.",
    }


def enforced() -> bool:
    """The gate refuses switching AI on only in production."""
    from backend.app.runtime_env import PRODUCTION, environment

    return environment() == PRODUCTION


def require_for_switch_on(switching_on: bool) -> None:
    """Refuse switching AI processing on in production while a bar is not met (409 AI_RELEASE_GATE_NOT_MET)."""
    if not switching_on or not enforced():
        return
    gate = status()
    if gate["ready"]:
        return
    missing = [bar["title"] for bar in gate["bars"] if bar["status"] != MET]
    raise HTTPException(
        409,
        detail={
            "code": "AI_RELEASE_GATE_NOT_MET",
            "message": "AI cannot be switched on yet: " + "; ".join(missing) + ".",
            "gate": gate,
        },
    )


@router.get("/release-gate", dependencies=[Depends(get_request_context)])
def release_gate():
    """The AI release gate's four bars (any signed-in user): what AI must pass before it is switched on for a pilot."""
    return status()
