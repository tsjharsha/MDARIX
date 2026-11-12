"""B6b B4: copy each ``requirement(<scenario ID>)`` marker into the test's JUnit properties.

``tests/conftest.py`` imports the hook below, so ``pytest --junitxml=...`` writes one
``<property name="requirement" value="<scenario ID>"/>`` per scenario a test proves by its own marker, and
``requirement_file`` for a marker set on the whole file or class (owner decision O24). The validation-pack generator
(``scripts/validation_pack.py``) reads them to link tests to scenarios and requirements."""

from __future__ import annotations


def pytest_runtest_setup(item) -> None:
    # Owner decision O24: a marker on the test function itself is "requirement"; one inherited from the module or
    # class (pytestmark) is "requirement_file", which never verifies a class-A requirement.
    own = {id(m) for m in getattr(item, "own_markers", [])}
    for marker in item.iter_markers("requirement"):
        name = "requirement" if id(marker) in own else "requirement_file"
        for scenario in marker.args:
            if (name, scenario) not in item.user_properties:
                item.user_properties.append((name, scenario))
