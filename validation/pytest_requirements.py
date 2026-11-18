"""B6b B4: copy each ``requirement(<scenario ID>)`` marker into the test's JUnit properties.

``tests/conftest.py`` imports the hook and the fixture below, so ``pytest --junitxml=...`` writes one
``<property name="requirement" value="<scenario ID>"/>`` per scenario a test proves by its own marker, and
``requirement_file`` for a marker set on the whole file or class (owner decision O24). The test suite itself carries
the commit it ran on, whether tracked files differed from that commit, ``hook_version`` (the marker semantics), and
the Python and key package versions (the test environment's IQ), so a JUnit file is bound to its code. The validation-pack generator (``scripts/validation_pack.py``) reads them to link
tests to scenarios and requirements, and refuses a JUnit of another commit, a changed tree or an older hook."""

from __future__ import annotations

import platform
import subprocess
from importlib import metadata
from pathlib import Path

import pytest

from validation.pack import HOOK_VERSION

ROOT = Path(__file__).resolve().parents[1]


def tree_state(root: Path = ROOT) -> tuple[str, str]:
    """(commit, "clean" / "dirty" / "unknown"): tracked files only; untracked files never change a test result here."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        status = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
                                capture_output=True, text=True, check=True)  # fmt: skip
    except (OSError, subprocess.CalledProcessError):
        return "unknown", "unknown"
    return commit.stdout.strip(), "dirty" if status.stdout.strip() else "clean"


def pytest_runtest_setup(item) -> None:
    # Owner decision O24: a marker on the test function itself is "requirement"; one inherited from the module or
    # class (pytestmark) is "requirement_file", which never verifies a class-A requirement.
    own = {id(m) for m in getattr(item, "own_markers", [])}
    for marker in item.iter_markers("requirement"):
        name = "requirement" if id(marker) in own else "requirement_file"
        for scenario in marker.args:
            if (name, scenario) not in item.user_properties:
                item.user_properties.append((name, scenario))


KEY_PACKAGES = ("fastapi", "SQLAlchemy", "alembic", "pydantic", "pg8000", "uvicorn", "cryptography", "pytest")


def tool_versions() -> tuple[str, str]:
    """(Python version, "name version; ..." of the key packages): the test environment's IQ (VMP-R45, VMP-R77)."""
    found = []
    for name in KEY_PACKAGES:
        try:
            found.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            found.append(f"{name} not installed")
    return platform.python_version(), "; ".join(found)


@pytest.fixture(scope="session", autouse=True)
def _junit_release_identity(record_testsuite_property) -> None:
    commit, tree = tree_state()
    record_testsuite_property("commit", commit)
    record_testsuite_property("tree", tree)
    record_testsuite_property("hook_version", HOOK_VERSION)
    python, packages = tool_versions()
    record_testsuite_property("python", python)
    record_testsuite_property("packages", packages)
