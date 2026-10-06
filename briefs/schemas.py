import uuid
from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, model_validator

from genai.epistemic import AIEpistemicLabel, AIFallbackNotice, ai_label_field, fallback_notice


class BriefCreateRequest(BaseModel):
    temporal_mode: Literal["current", "event", "known"] = "current"
    as_of: datetime | None = None
    generated_by: str = "MDARIX-Controlled-Brief-Assembler"


class BriefResponse(BaseModel):
    id: uuid.UUID
    business_id: str | None = None
    investigation_id: uuid.UUID
    investigation_business_id: str | None = None
    brief_version: int
    status: str
    title: str
    temporal_mode: str
    temporal_cutoff: datetime | None
    human_review_state: str
    content: dict[str, Any]
    provenance: dict[str, Any]
    limitations: dict[str, Any] | None
    created_at: datetime | None
    # Phase 4 (additive): what this brief is, and why AI did not contribute when rules assembled it (read from the
    # brief's own ai_brief and ai_advisory content, which stay unchanged).
    epistemic: AIEpistemicLabel = ai_label_field()
    ai_notice: AIFallbackNotice | None = None

    @model_validator(mode="after")
    def _ai_notice(self):
        if self.ai_notice is None and isinstance(self.content, dict):
            brief = self.content.get("ai_brief")
            provenance = dict(brief) if isinstance(brief, dict) else {}
            provenance["live_provider_advisory"] = self.content.get("ai_advisory")
            self.ai_notice = fallback_notice("brief", provenance)
        return self


class BriefListResponse(BaseModel):
    briefs: list[BriefResponse]
