"""What a provider hands the curation tool (art backgrounds plan, D7).

Its own module, so `curate.py` run as a script and the providers it loads share one `Refused`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class Refused(Exception):
    """A provider's refusal of a work: its rights signal or its record does not admit it."""


@dataclass(frozen=True)
class ProviderWork:
    """One work as its provider describes it, with its largest allowed image."""

    provider: str
    object_id: str
    image: bytes
    placard: Mapping[str, str | None]
    rights: Mapping[str, Any]


class Provider(Protocol):
    def fetch(self, object_id: str) -> ProviderWork: ...
