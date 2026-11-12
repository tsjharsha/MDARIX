from validation.csa_package import (
    TESTS,
    build_package,
    build_evidence_manifest,
    render_customer_instructions,
    render_markdown,
    render_validation_summary,
)


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
    assert "SUPERSEDED" in markdown and "MDX-VAL-001" in markdown  # retired by B6b; the regenerated file keeps it


def test_csa_package_has_controlled_evidence_and_customer_handoff():
    package = build_package()
    manifest = build_evidence_manifest(package)
    assert len(manifest["artifacts"]) == len(TESTS)
    assert all(item["status"] == "PENDING_EXECUTION" for item in manifest["artifacts"])
    assert "NO RELEASE DECISION RECORDED" in render_validation_summary(package)
    instructions = render_customer_instructions()
    assert "redacted screenshots" in instructions
    assert "quality and system-owner approval" in instructions
