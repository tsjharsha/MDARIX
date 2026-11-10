"""B4 step 7 (DT-33, RR-06, RR-18): a rule may not change without a new register version. The floors' content hash
(checked by the loader), the US eMDR rule book's file hash, and the syntax tree (without comments and docstrings) of
the pinned regulatory functions. No database."""

from __future__ import annotations

import json

import pytest

from backend.app.rule_register import register

PINNED = {
    "conclusion-starter-1",
    "conclusion-clock-starter-1",
    "counting-starter-1",
    "facts-needed-starter-1",
    "awareness-starter-1",
    "routine-basis-1",
}


def test_every_pin_holds():
    assert {code for code, entry in register.load().items() if entry.get("pinned")} == PINNED
    assert register.pin_problems() == []


def test_a_comment_or_docstring_does_not_move_a_pin_but_code_does(tmp_path, monkeypatch):
    module = tmp_path / "pinned_example.py"
    monkeypatch.syspath_prepend(str(tmp_path))
    module.write_text('def rule(x):\n    """Docs."""\n    return x + 1  # one\n', encoding="utf-8")
    first = register.code_hash("pinned_example:rule")
    module.write_text('def rule(x):\n    """Other docs."""\n    # a new comment\n    return x + 1\n', encoding="utf-8")
    __import__("importlib").invalidate_caches()
    __import__("sys").modules.pop("pinned_example", None)
    assert register.code_hash("pinned_example:rule") == first
    module.write_text("def rule(x):\n    return x + 2\n", encoding="utf-8")
    __import__("sys").modules.pop("pinned_example", None)
    assert register.code_hash("pinned_example:rule") != first


def test_a_changed_pinned_function_or_rule_book_names_the_file(tmp_path, monkeypatch):
    for name in ("counting-starter-1", "emdr-rule-book-1"):
        entry = json.loads((register.DATA / f"{name}.json").read_text(encoding="utf-8"))
        if name == "counting-starter-1":
            entry["code_hash"] = "sha256:0"
        else:
            entry["content"]["sha256"] = "0" * 64
            entry["content_hash"] = register.content_hash(entry["content"])
        (tmp_path / f"{name}.json").write_text(json.dumps(entry), encoding="utf-8")
    monkeypatch.setattr(register, "_DIRECTORY", tmp_path)
    assert register.pin_problems() == [
        "counting-starter-1.json: backend.app.reportability.deadlines:count changed without a new version",
        "emdr-rule-book-1.json: backend/app/authority_reports/rules/us_emdr.csv changed without a new version",
    ]


@pytest.mark.parametrize("code", sorted(PINNED))
def test_each_pinned_rule_names_a_function_that_exists(code):
    assert register.code_hash(register.get(code)["implementation"]).startswith("sha256:")
