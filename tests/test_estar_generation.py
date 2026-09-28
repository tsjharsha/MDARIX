from zipfile import ZipFile
from io import BytesIO

from regulatory_intelligence.estar import generate_estar_package, validate_estar_xml


def test_estar_xml_and_package_validate():
    result = generate_estar_package(
        tenant_id="tenant-a",
        title="510(k) preparation",
        sections=[{"claim_id": "A1", "text": "Risk control evidence is available.", "confidence": "HIGH", "citation_ids": ["c1"]}],
        citations={"verified": [{"citation_id": "c1"}], "rejected": [], "all_verified": True},
    )
    assert result["validation"]["valid"] is True
    with ZipFile(BytesIO(result["content"])) as package:
        xml = package.read("estar-preparation.xml")
        assert package.read("estar-preparation.pdf").startswith(b"%PDF")
        assert "manifest.json" in package.namelist()
    assert validate_estar_xml(xml)["valid"] is True


def test_estar_xml_rejects_wrong_root():
    assert validate_estar_xml(b"<wrong />")["valid"] is False
