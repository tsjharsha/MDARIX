"""W1 (0.10.94), P360-06: where a record came from, one rule for every row (backend/app/product360/origin.py)."""

from datetime import datetime, timezone

from backend.app.product360.origin import origin

LOADED = datetime(2026, 11, 2, 9, 30, tzinfo=timezone.utc)


def test_each_source_reads_as_its_chip_and_line():
    assert origin("MDARIX_SAMPLE", "SAMPLE-ORBIT-300", LOADED) | {} == {
        "kind": "SAMPLE",
        "label": "Sample",
        "detail": "Fictional sample data",
        "system": "MDARIX_SAMPLE",
        "external_id": "SAMPLE-ORBIT-300",
        "loaded_at": "2026-11-02",
    }
    for system in ("TRIAL_UPLOAD", "CSV_IMPORT"):
        imported = origin(system, "PUMP-200", LOADED)
        assert (imported["kind"], imported["label"]) == ("IMPORTED", "Your import")
        assert imported["detail"] == "Imported on 2026-11-02 · ID PUMP-200"
    made = origin("MDARIX", None, None, LOADED)
    assert (made["kind"], made["label"], made["detail"]) == ("MDARIX", "Created in MDARIX", "Created on 2026-11-02")
    assert origin(None)["kind"] == "MDARIX" and origin("MDARIX_UI")["kind"] == "MDARIX"
    erp = origin("SAP S/4", "MAT-0042", LOADED)
    assert (erp["kind"], erp["label"], erp["detail"]) == (
        "EXTERNAL",
        "From SAP S/4",
        "ID MAT-0042 · last loaded 2026-11-02",
    )
    assert origin("PLM", None, None)["detail"] == "Loaded from PLM"
    assert origin("CSV_IMPORT")["detail"] == "Imported on an unknown date"
