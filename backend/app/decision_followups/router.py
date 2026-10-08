"""The routes of what follows a signed decision: follow-ups, impact assessments and the closure check of a case."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.decision_followups import closure, followups, impact

router = APIRouter()
router.include_router(followups.router)
router.include_router(impact.router)
router.include_router(closure.router)
