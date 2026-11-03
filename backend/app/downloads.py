"""The ``Content-Disposition`` header of every download (0.10.81, the security review's F3).

A header is Latin-1 on the wire: a stored file named with an en dash or Devanagari made the download answer 500. The
header now carries an ASCII ``filename=`` for every browser and, when the name is not plain ASCII, the name itself
as UTF-8 in ``filename*=`` (RFC 6266 and RFC 8187), which browsers prefer.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import quote

NAME_MAX = 200


def _clean(name: object) -> str:
    """The file's own name: no folders, quotes, backslashes or control characters, no leading or trailing dots."""
    base = re.split(r"[\\/]", str(name or ""))[-1]
    return re.sub(r'[\x00-\x1f\x7f"]', "", base).strip(" .")[:NAME_MAX]


def attachment(name: object, fallback: str = "download") -> str:
    """``attachment; filename="…"`` with an ASCII name, plus ``filename*=UTF-8''…`` when the name is not ASCII."""
    clean = _clean(name) or fallback
    plain = unicodedata.normalize("NFKD", clean).encode("ascii", "ignore").decode()
    plain = " ".join(re.sub(r"[^A-Za-z0-9 ._()\-]", "_", plain).split()).strip(" .") or fallback
    if plain == clean:
        return f'attachment; filename="{clean}"'
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(clean, safe='')}"
