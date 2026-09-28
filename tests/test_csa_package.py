from validation.csa_package import TESTS, build_package, render_markdown


def test_csa_package_has_iq_oq_pq_traceability():
    package = build_package()
    assert {test["phase"] for test in package["tests"]} == {"IQ", "OQ", "PQ"}
    requirement_ids = {item["id"] for item in package["requirements"]}
    assert all(test.requirement_id in requirement_ids for test in TESTS)
    assert package["status"] == "READY_FOR_EXECUTION"


def test_csa_package_renders_acceptance_and_evidence():
    markdown = render_markdown(build_package())
    assert "## IQ/OQ/PQ tests" in markdown
    assert "Acceptance:" in markdown
    assert "Evidence:" in markdown
