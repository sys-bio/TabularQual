from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit


_CHEBI_COMPACT_ID = re.compile(
    r"^chebi(?::|/)(?:chebi:)?(?P<accession>.+)$",
    re.IGNORECASE,
)
_IDENTIFIERS_ORG_HOSTS = {"identifiers.org", "www.identifiers.org"}


def normalize_compact_identifier(identifier: str) -> str:
    """Return a validator-friendly compact identifier.

    ChEBI is commonly entered as ``chebi:35305`` because ``chebi`` is the
    Identifiers.org namespace. Annotation validators, however, recognize the
    canonical CURIE ``CHEBI:35305``. Legacy slash and embedded-prefix forms are
    normalized at the same time.
    """
    value = identifier.strip()
    match = _CHEBI_COMPACT_ID.fullmatch(value)
    if not match:
        return value

    accession = match.group("accession")
    return f"CHEBI:{accession}"


def normalize_identifiers_url(url: str) -> str:
    """Normalize a compact identifier embedded in an Identifiers.org URL."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return url
    if parsed.netloc.lower() not in _IDENTIFIERS_ORG_HOSTS:
        return url

    compact_id = parsed.path.lstrip("/")
    normalized = normalize_compact_identifier(compact_id)
    if normalized == compact_id:
        return url

    return urlunsplit(
        (parsed.scheme, parsed.netloc, f"/{normalized}", parsed.query, parsed.fragment)
    )


def to_identifiers_url(identifier: str) -> str:
    """Convert an annotation identifier to a normalized Identifiers.org URI."""
    value = identifier.strip()
    if not value:
        return value

    if value.startswith(("http://", "https://")):
        return normalize_identifiers_url(value)
    if value.startswith("ftp://"):
        return value

    urn_prefix = "urn:miriam:"
    if value.lower().startswith(urn_prefix):
        compact_id = value[len(urn_prefix):]
        return urn_prefix + normalize_compact_identifier(compact_id)
    if value.lower().startswith("urn:"):
        return value

    if "/" in value and ":" not in value:
        value = value.replace("/", ":", 1)

    value = normalize_compact_identifier(value)
    return f"https://identifiers.org/{value}"


def url_to_compact_identifier(identifier: str) -> str:
    """Convert an Identifiers.org URI or MIRIAM URN to a normalized CURIE."""
    value = identifier.strip()
    parsed = urlsplit(value)

    if (
        parsed.scheme.lower() in {"http", "https"}
        and parsed.netloc.lower() in _IDENTIFIERS_ORG_HOSTS
    ):
        compact_id = parsed.path.lstrip("/")
        if "/" in compact_id and ":" not in compact_id:
            compact_id = compact_id.replace("/", ":", 1)
        return normalize_compact_identifier(compact_id)

    urn_prefix = "urn:miriam:"
    if value.lower().startswith(urn_prefix):
        return normalize_compact_identifier(value[len(urn_prefix):])

    return value
