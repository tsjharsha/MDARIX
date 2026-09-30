"""Authoritative regulatory source metadata.

Only public metadata and links are stored here. Full ISO text must be supplied
under the customer's license and is never bundled into the repository.
"""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class RegulatorySource:
    source_id: str
    authority: str
    title: str
    url: str
    jurisdiction: str
    access_note: str
    text_available: bool = False


OFFICIAL_SOURCES = {
    "FDA-510K": RegulatorySource(
        "FDA-510K",
        "FDA",
        "Premarket Notification 510(k)",
        "https://www.fda.gov/medical-devices/premarket-submissions/premarket-notification-510k",
        "US",
        "Public FDA guidance and submission information.",
    ),
    "EU-MDR-2017-745": RegulatorySource(
        "EU-MDR-2017-745",
        "EUR-Lex",
        "Regulation (EU) 2017/745 on medical devices",
        "https://eur-lex.europa.eu/eli/reg/2017/745/oj",
        "EU",
        "Public EUR-Lex regulation text.",
    ),
    "ISO-13485": RegulatorySource(
        "ISO-13485",
        "ISO",
        "ISO 13485 medical devices quality management systems",
        "https://www.iso.org/standard/59752.html",
        "INTERNATIONAL",
        "Metadata/link only; licensed standard text required for clause ingestion.",
    ),
    "ISO-14971": RegulatorySource(
        "ISO-14971",
        "ISO",
        "ISO 14971 application of risk management to medical devices",
        "https://www.iso.org/standard/72704.html",
        "INTERNATIONAL",
        "Metadata/link only; licensed standard text required for clause ingestion.",
    ),
}


def get_source(source_id: str) -> RegulatorySource:
    try:
        return OFFICIAL_SOURCES[source_id.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown regulatory source: {source_id}") from exc


def verify_citations(citations: list[dict]) -> dict:
    """Validate citation shape and require an approved official source URL."""
    verified = []
    rejected = []
    for citation in citations:
        source_id = str(citation.get("source_id", "")).upper()
        url = str(citation.get("url", ""))
        try:
            source = get_source(source_id)
            parsed = urlparse(url)
            expected = urlparse(source.url)
            if parsed.scheme != "https" or parsed.netloc != expected.netloc:
                raise ValueError("citation URL is not on the registered official domain")
            if not citation.get("clause"):
                raise ValueError("citation clause is required")
            verified.append(
                {
                    **citation,
                    "source_id": source.source_id,
                    "authority": source.authority,
                    "source_title": source.title,
                    "official_url": source.url,
                    "jurisdiction": source.jurisdiction,
                    "traceability_key": f"{source.source_id}:{citation['clause']}",
                    "verified": True,
                }
            )
        except (ValueError, TypeError) as exc:
            rejected.append({"citation": citation, "reason": str(exc)})
    return {"verified": verified, "rejected": rejected, "all_verified": not rejected}


def official_source_manifest() -> list[dict]:
    """Return the source/ licensing manifest used by regulatory workflows.

    ISO standards are deliberately metadata-only: customers must provide the
    licensed clause text or an approved licensed index before ingestion.
    """
    return [
        {
            "source_id": source.source_id,
            "authority": source.authority,
            "title": source.title,
            "official_url": source.url,
            "jurisdiction": source.jurisdiction,
            "ingestion_mode": "PUBLIC_METADATA" if source.text_available else "LICENSED_CUSTOMER_TEXT_REQUIRED",
        }
        for source in OFFICIAL_SOURCES.values()
    ]
