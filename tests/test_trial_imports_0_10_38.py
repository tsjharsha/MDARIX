"""Release 0.10.38, NEW-4: a large import writes its records' evidence in batches, with the same result as before.

A trial import of 5,000 complaints took about 3 minutes: each row cost about 13 statements (its complaint read and
flushed, its evidence row read, its links deleted and added, its chunks read, deleted and added). The complaints a file
names are now read at once, and their evidence, links and chunks are written together
(retrieval/record_evidence.py upsert_record_evidences). These tests run each import twice in one organization, rolled
back in between: once as before, with the evidence written one record at a time (upsert_record_evidence), and once as
now. Both must leave the same complaints, evidence rows, links and chunks, after a first import and after a re-import
that updates some rows; and a record whose text did not change keeps its chunks (and their embeddings).
"""

import uuid

from backend.app.db.models.evidence_intelligence import EvidenceChunk, EvidenceEntityLink
from backend.app.db.models.foundation import Capa, Complaint, Evidence, LotBatch, Product, ProductVersion
from backend.app.db.models.retrieval_intelligence import EvidenceChunkEmbedding
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.trial import business_imports, imports
from retrieval import record_evidence
from retrieval.record_evidence import RecordEvidence, upsert_record_evidence, upsert_record_evidences
from tests.test_support_problems import two_active_tenants


def _one_at_a_time(db, tenant_id, items):
    """The evidence as imports wrote it before 0.10.38: one upsert_record_evidence call per record."""
    return [
        upsert_record_evidence(
            db,
            tenant_id,
            kind=item.kind,
            identifier=item.identifier,
            title=item.title,
            content=item.content,
            links=item.links,
            source=item.source,
            investigation_id=item.investigation_id,
        )
        for item in items
    ]


def _names(db, tenant_id) -> dict:
    """Record ids to (type, identifier), so two runs with different ids compare."""
    names = {}
    for model, column, label in (
        (Complaint, Complaint.complaint_identifier, "Complaint"),
        (Product, Product.product_identifier, "Product"),
        (ProductVersion, ProductVersion.version_identifier, "ProductVersion"),
        (LotBatch, LotBatch.lot_identifier, "LotBatch"),
        (Capa, Capa.capa_identifier, "Capa"),
    ):
        for record_id, identifier in db.query(model.id, column).filter(model.tenant_id == tenant_id):
            names[record_id] = (label, identifier)
    return names


def _evidence(db, tenant_id, marker: str) -> tuple[dict, dict]:
    """The record evidence whose identifier holds ``marker``: its fields, links and chunks (and, apart, chunk ids)."""
    names = _names(db, tenant_id)
    state, chunk_ids = {}, {}
    rows = db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.contains(marker))
    for evidence in rows:
        links = sorted(
            (
                link.entity_type,
                names.get(link.entity_id, str(link.entity_id)),
                link.raw_reference,
                link.resolution_status,
            )
            for link in db.query(EvidenceEntityLink).filter(
                EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.evidence_id == evidence.id
            )
        )
        chunks = (
            db.query(EvidenceChunk)
            .filter(EvidenceChunk.tenant_id == tenant_id, EvidenceChunk.evidence_id == evidence.id)
            .order_by(EvidenceChunk.sequence_number)
            .all()
        )
        state[evidence.evidence_identifier] = {
            "type": evidence.evidence_type,
            "title": evidence.title,
            "content": evidence.content,
            "source_reference": evidence.source_reference,
            "reliability": evidence.reliability_status,
            "fact_type": evidence.fact_type,
            "source": (evidence.source_system, evidence.source_identifier),
            "investigation": names.get(evidence.investigation_id, evidence.investigation_id),
            "links": links,
            "chunks": [(c.sequence_number, c.text_content, c.source_anchor, c.token_count, c.checksum) for c in chunks],
        }
        chunk_ids[evidence.evidence_identifier] = [chunk.id for chunk in chunks]
    return state, chunk_ids


def _complaints(db, tenant_id, marker: str) -> dict:
    names = _names(db, tenant_id)
    columns = [c.key for c in Complaint.__table__.columns if c.key not in {"id", "tenant_id", "created_at"}]
    out = {}
    for complaint in db.query(Complaint).filter(
        Complaint.tenant_id == tenant_id, Complaint.complaint_identifier.contains(marker)
    ):
        row = {}
        for column in columns:
            value = getattr(complaint, column)
            if column in {"product_id", "product_version_id", "lot_batch_id"}:
                value = names.get(value, value)
            if column in {"updated_at", "recorded_timestamp", "ingestion_timestamp"}:
                continue  # the time of the run
            row[column] = value
        out[complaint.complaint_identifier] = row
    return out


def _csv(rows) -> bytes:
    header = "complaint_id,product_id,product_name,description,version,lot_id,event_date,received_date,status,severity"
    return ("\n".join([header, *(",".join(row) for row in rows)]) + "\n").encode()


def _files(marker: str) -> tuple[bytes, bytes]:
    """A first complaints file (new products, versions and lots) and a second that updates some rows and adds two."""
    product, other = f"P{marker}", f"Q{marker}"
    first = [
        [
            f"C{marker}-{n:03d}",
            product if n % 3 else other,
            "Infusion pump" if n % 3 else "Monitor",
            f"Pressure alarm during priming on unit {n}.",
            "Rev A" if n % 2 else "Rev B",
            f"L{marker}-{'Q' if n % 3 == 0 else 'P'}{n % 2}",  # each lot belongs to one product
            "2026-09-01",
            "2026-09-03",
            "open",
            "Minor",
        ]
        for n in range(1, 31)
    ]
    second = [list(row) for row in first]
    for n in (2, 5, 9):  # new text: re-chunked
        second[n][3] = f"Updated after the field visit to unit {n + 1}."
    second[7][5] = f"L{marker}-9"  # another lot (the link changes, the text too)
    second[11][9] = ""  # severity cleared
    second += [
        [
            f"C{marker}-{n:03d}",
            product,
            "Infusion pump",
            f"New complaint {n}.",
            "Rev C",
            "",
            "2026-09-10",
            "",
            "open",
            "",
        ]
        for n in (31, 32)
    ]
    return _csv(first), _csv(second)


def _import_twice(tenant_id, files, marker: str, monkeypatch, one_at_a_time: bool, entity: str = "complaints"):
    """Import ``files`` in turn in one organization, rolled back at the end; the state after each import."""
    if one_at_a_time:
        monkeypatch.setattr(record_evidence, "upsert_record_evidences", _one_at_a_time)
        monkeypatch.setattr(business_imports, "upsert_record_evidences", _one_at_a_time)
    states = []
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        try:
            for raw in files:
                result = imports.import_file(db, tenant_id, entity, raw)
                evidence, chunk_ids = _evidence(db, tenant_id, marker)
                states.append(
                    {
                        "result": {k: result.get(k) for k in ("created", "updated", "rows", "also_created")},
                        "complaints": _complaints(db, tenant_id, marker),
                        "evidence": evidence,
                        "chunk_ids": chunk_ids,
                    }
                )
        finally:
            db.rollback()
    monkeypatch.undo()
    return states


def _without_ids(states):
    return [{key: value for key, value in state.items() if key != "chunk_ids"} for state in states]


def test_a_complaints_import_and_reimport_leave_the_same_records_as_one_row_at_a_time(monkeypatch):
    tenant_id = two_active_tenants()[0].id
    marker = uuid.uuid4().hex[:8].upper()
    files = _files(marker)
    before = _import_twice(tenant_id, files, marker, monkeypatch, one_at_a_time=True)
    now = _import_twice(tenant_id, files, marker, monkeypatch, one_at_a_time=False)

    assert _without_ids(now) == _without_ids(before)
    first, second = now
    assert first["result"] == {
        "created": 30 + 2 + 4 + 4,  # complaints, then the products, versions and lots they name
        "updated": 0,
        "rows": 30,
        "also_created": {"products": 2, "versions": 4, "lots": 4},
    }
    assert second["result"] == {
        "created": 2 + 1 + 1,  # two complaints, version Rev C, lot 9
        "updated": 5,  # the rows that changed a field (0.10.62, J9); the other 25 are as the file had them
        "rows": 32,
        "also_created": {"versions": 1, "lots": 1},
    }
    # One evidence row per complaint, linked to the complaint, its product, version and lot (when it names one).
    evidence = second["evidence"]
    assert len(evidence) == 32 and len(second["complaints"]) == 32
    row = evidence[f"RECORD:COMPLAINT:C{marker}-008"]
    assert [link[:2] for link in row["links"]] == [
        ("Complaint", ("Complaint", f"C{marker}-008")),
        ("LotBatch", ("LotBatch", f"L{marker}-9")),
        ("Product", ("Product", f"P{marker}")),
        ("ProductVersion", ("ProductVersion", "Rev B")),
    ]
    assert row["chunks"][0][1] == row["content"] and "Lot: L" in row["content"]
    assert second["complaints"][f"C{marker}-012"]["severity"] is None
    # A complaint whose text did not change keeps its chunks; one whose text changed is chunked again.
    for n, rechunked in ((1, False), (3, True), (6, True), (8, True), (10, True), (12, True), (20, False)):
        key = f"RECORD:COMPLAINT:C{marker}-{n:03d}"
        assert (first["chunk_ids"][key] != second["chunk_ids"][key]) is rechunked, key


def test_a_business_import_writes_the_same_evidence_as_one_record_at_a_time(monkeypatch):
    tenant_id = two_active_tenants()[0].id
    marker = uuid.uuid4().hex[:8].upper()
    header = "capa_id,title,status,action_type\n"
    first = header + "".join(f"K{marker}-{n},Restore margin {n},open,Corrective\n" for n in range(1, 6))
    second = first.replace("Restore margin 2,open", "Restore the alarm margin 2,open") + f"K{marker}-6,New,open,\n"
    files = (first.encode(), second.encode())
    before = _import_twice(tenant_id, files, marker, monkeypatch, one_at_a_time=True, entity="capas")
    now = _import_twice(tenant_id, files, marker, monkeypatch, one_at_a_time=False, entity="capas")

    assert _without_ids(now) == _without_ids(before)
    assert len(now[1]["evidence"]) == 6
    assert now[1]["result"]["created"] == 1 and now[1]["result"]["updated"] == 1  # only K-2 changed (J9)
    kept, changed = f"RECORD:CAPA:K{marker}-1", f"RECORD:CAPA:K{marker}-2"
    assert now[0]["chunk_ids"][kept] == now[1]["chunk_ids"][kept]
    assert now[0]["chunk_ids"][changed] != now[1]["chunk_ids"][changed]
    assert "Restore the alarm margin 2" in now[1]["evidence"][changed]["title"]


def _items(marker: str, product_id, version_id, texts: dict[int, str], links_for=None) -> list[RecordEvidence]:
    return [
        RecordEvidence(
            kind="COMPLAINT",
            identifier=f"E{marker}-{n}",
            title=f"Complaint E{marker}-{n}",
            content=text,
            links=(links_for or {}).get(
                n, [("Product", product_id), ("ProductVersion", version_id), ("LotBatch", None)]
            ),
            source="TEST",
        )
        for n, text in texts.items()
    ]


def _embed(db, tenant_id, marker: str) -> None:
    """A stand-in embedding for every chunk of the marked evidence, as the background indexing adds them."""
    rows = (
        db.query(EvidenceChunk)
        .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
        .filter(EvidenceChunk.tenant_id == tenant_id, Evidence.evidence_identifier.contains(marker))
    )
    for chunk in rows:
        db.add(
            EvidenceChunkEmbedding(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_id=chunk.evidence_id,
                chunk_id=chunk.id,
                chunk_checksum=chunk.checksum or "",
                provider="test",
                embedding_model="test",
                model_version="1",
                embedding_dimension=3,
                pipeline_version="1",
                indexing_status="FAILED",
                failure_reason="test stand-in",
            )
        )
    db.flush()


def _embedded(db, tenant_id, marker: str) -> dict[str, int]:
    rows = (
        db.query(Evidence.evidence_identifier, EvidenceChunkEmbedding.id)
        .join(EvidenceChunkEmbedding, EvidenceChunkEmbedding.evidence_id == Evidence.id)
        .filter(Evidence.tenant_id == tenant_id, Evidence.evidence_identifier.contains(marker))
    )
    counts: dict[str, int] = {}
    for identifier, _ in rows:
        counts[identifier] = counts.get(identifier, 0) + 1
    return counts


def test_the_batch_upsert_matches_one_call_per_record_including_repeats_and_embeddings():
    tenant_id = two_active_tenants()[0].id
    marker = uuid.uuid4().hex[:8].upper()
    long_text = "\n\n".join(f"Paragraph {n}: " + "pressure alarm " * 40 for n in range(3))
    results = []
    for write in (_one_at_a_time, upsert_record_evidences):
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            try:
                product, version = uuid.uuid4(), uuid.uuid4()
                write(
                    db, tenant_id, _items(marker, product, version, {1: "First.", 2: long_text, 3: "Third.", 4: "4."})
                )
                first, first_ids = _evidence(db, tenant_id, marker)
                _embed(db, tenant_id, marker)
                # Record 1 unchanged, 2 changed, 3 changed and back again in one batch, 4 with other links, 5 new.
                second_items = _items(
                    marker,
                    product,
                    version,
                    {1: "First.", 2: long_text + "\n\nMore.", 3: "Third, edited.", 4: "4.", 5: "Five."},
                    {4: [("Product", product)]},
                ) + _items(marker, product, version, {3: "Third."})
                returned = write(db, tenant_id, second_items)
                second, second_ids = _evidence(db, tenant_id, marker)
                results.append(
                    {
                        "first": first,
                        "second": second,
                        "rechunked": {key: first_ids[key] != second_ids[key] for key in first_ids},
                        "embedded": _embedded(db, tenant_id, marker),
                        "returned": len({getattr(evidence, "id", evidence) for evidence in returned}),
                        "product": product,
                    }
                )
            finally:
                db.rollback()
    one, batch = results
    # The record ids differ between the two runs only through the random product and version ids.
    for state in (one, batch):
        for snapshot in (state["first"], state["second"]):
            for row in snapshot.values():
                row["links"] = [
                    (kind, "product" if target == str(state["product"]) else "other", *rest)
                    for kind, target, *rest in row["links"]
                ]
        del state["product"]
    assert batch == one
    assert len(batch["first"][f"RECORD:COMPLAINT:E{marker}-2"]["chunks"]) == 3
    assert batch["rechunked"] == {
        f"RECORD:COMPLAINT:E{marker}-1": False,
        f"RECORD:COMPLAINT:E{marker}-2": True,
        f"RECORD:COMPLAINT:E{marker}-3": True,
        f"RECORD:COMPLAINT:E{marker}-4": False,
    }
    # The embeddings of a record chunked again are deleted with its old chunks; the others are kept.
    assert batch["embedded"] == {f"RECORD:COMPLAINT:E{marker}-1": 1, f"RECORD:COMPLAINT:E{marker}-4": 1}
    assert [link[0] for link in batch["second"][f"RECORD:COMPLAINT:E{marker}-4"]["links"]] == ["Product"]
    assert upsert_record_evidences(None, tenant_id, []) == []
