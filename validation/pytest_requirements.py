"""B6b B4: copy each ``requirement(<scenario ID>)`` marker into the test's JUnit properties.

``tests/conftest.py`` imports the hook below, so ``pytest --junitxml=...`` writes one
``<property name="requirement" value="<scenario ID>"/>`` per scenario a test proves. The validation-pack generator
(``scripts/validation_pack.py``) reads them to link tests to scenarios and requirements."""

from __future__ import annotations


def pytest_runtest_setup(item) -> None:
    for marker in item.iter_markers("requirement"):
        for scenario in marker.args:
            if ("requirement", scenario) not in item.user_properties:
                item.user_properties.append(("requirement", scenario))
