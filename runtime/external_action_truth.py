from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


_CLAUSE_BOUNDARY = re.compile(r"[.!?;:,]|\b(?:but|however|yet)\b")
_NEGATION = re.compile(r"\b(?:no|not|never|without)\b")


def no_asserted_external_action(value: Mapping[str, Any], markers: Iterable[str]) -> bool:
    """Reject asserted execution markers without treating explicit denials as execution."""
    rendered = json.dumps(dict(value), sort_keys=True).casefold()
    for marker in markers:
        offset = 0
        while True:
            index = rendered.find(marker, offset)
            if index < 0:
                break
            prefix = rendered[max(0, index - 120) : index]
            clause = _CLAUSE_BOUNDARY.split(prefix)[-1]
            if not _NEGATION.search(clause):
                return False
            offset = index + len(marker)
    return True
