"""One number per thing (0.10.63, quality plan stage 2, J19): the screens, the guides and the website quote the counts
the server has. On 0.10.62 the website and the user guide said eight inspection checks (Readiness has eleven), the
Getting started page said 9 chapters while the story loaded (it has ten), the website said nine, and the Readiness check
that counts complaints past the disposition target was called "Complaints waiting for a disposition", beside a board
whose "waiting" is every complaint without one.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.app.readiness_home import service as readiness
from backend.app.trial import story

FRONTEND = Path(__file__).resolve().parents[1] / "frontend" / "src"
WORDS = {8: "eight", 9: "nine", 10: "ten", 11: "eleven"}


def _text(relative: str) -> str:
    return (FRONTEND / relative).read_text(encoding="utf-8")


def test_the_story_has_one_chapter_count_everywhere():
    assert len(story.CHAPTERS) == 10
    guide = _text("features/help/trialGuide.ts")
    assert re.search(r"export const STORY_CHAPTERS = (\d+);", guide).group(1) == str(len(story.CHAPTERS))
    assert "story.data?.total ?? STORY_CHAPTERS" in _text("features/workspace/sections/GettingStarted.tsx")
    assert f"quality story in {WORDS[len(story.CHAPTERS)]} chapters" in _text("site/content.ts")


def test_the_inspection_checks_are_counted_the_same_in_the_guide_and_the_quality_loop():
    count = len(readiness.CHECKS)
    assert count == 11
    assert f"The {WORDS[count]} checks:" in _text("features/help/userGuide.ts")
    # The quality loop names every check, so the website draws as many stations as Readiness has.
    loop = _text("features/workspace/qualityLoop.ts")
    for check in readiness.CHECKS:
        code = check.__name__.upper()
        assert f'code: "{code}"' in loop, code


def test_the_disposition_check_is_named_for_what_it_counts():
    source = Path(readiness.__file__).read_text(encoding="utf-8")
    assert 'f"Dispositions past the {target}-day target or to review"' in source
    assert '"Complaints waiting for a disposition",' not in source
