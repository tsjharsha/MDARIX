"""Names that MDARIX puts into its own emails: a person's or an organization's name, never a link.

Sign-up and the trial team invitation put the name someone typed into an email sent to an address that person chose.
A web or email address inside that name would let anyone send a genuine MDARIX email carrying their own link, for
phishing (pre-launch review SEC-04), so such a name is refused with a plain message. Mail clients turn a bare domain
such as ``secure-login.com`` into a link, so the common top-level domains count too; a dotted abbreviation such as
"St. Jude" or "Co. Ltd" does not.
"""

from __future__ import annotations

import re

_TLDS = (
    "com|net|org|io|in|co|info|biz|xyz|ru|cn|top|app|dev|me|ly|link|site|online|club|us|uk|de|ai|tk|ml|ga|cf|gq|pw"
    "|cc|tv|ws|su|shop|live|click|page|zip|mov|win|icu|buzz|rest|cam|lol|support|help|email|login|secure"
)
_LINK = re.compile(rf"(?i)(://|www\.|@|\b[a-z0-9-]+\.(?:{_TLDS})\b)")


def looks_like_link(value: object) -> bool:
    """True when the text holds a web address, an email address or a bare domain name."""
    return bool(_LINK.search(str(value or "")))
