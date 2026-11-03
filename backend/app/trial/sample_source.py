"""The sample's own source (``source_system``): every sample record carries it. An imported record carries its
import's source (TRIAL_UPLOAD or another), so "sample" is this value only, never "any source" (0.10.81)."""

SAMPLE_SOURCE = "MDARIX_SAMPLE"


def is_sample(source_system: str | None) -> bool:
    return source_system == SAMPLE_SOURCE
