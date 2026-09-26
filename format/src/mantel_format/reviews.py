"""The public review ledger (`reviews.json`, schema v2): one record per exact release.

A record binds a verdict to the archive and source bytes a person looked at. Automated tools
may draft records but never fill the human fields; signing requires a record whose verdict
admits the release's distribution.
"""

from __future__ import annotations

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .composition import PackageId
from .encoding import strict_json
from .pack_contracts import Digest, ReleaseVersion

HANDLE = r"^[a-z0-9][a-z0-9.-]{0,38}$"
Verdict = Literal["approved", "preview", "changes-requested", "rejected"]
Status = Literal["pass", "fail", "pending", "not-applicable"]
# Which verdicts let a release be signed into each distribution (D24).
ADMITS: dict[str, frozenset[str]] = {
    "included": frozenset({"approved"}),
    "library": frozenset({"approved", "preview"}),
}


class ReviewStatuses(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity: Status
    structure: Status
    security: Status
    design: Status
    content: Status
    licence: Status
    listening: Status
    fluent: Status


class ReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: PackageId
    version: ReleaseVersion
    kind: Literal["definition", "pack"]
    archive_sha256: Digest
    source_sha256: Digest
    submitter_handle: str = Field(pattern=HANDLE)
    reviewer: str | None = Field(default=None, pattern=HANDLE)
    reviewed_at: datetime.date
    statuses: ReviewStatuses
    verdict: Verdict
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _a_person_decides(self) -> ReviewRecord:
        # Only a preview may stand on automated checks alone; every other verdict is a person's.
        if self.reviewer is None and self.verdict != "preview":
            raise ValueError(f"{self.verdict} needs a named reviewer")
        statuses = set(self.statuses.model_dump().values())
        if self.verdict in {"approved", "preview"} and "fail" in statuses:
            raise ValueError(f"A failed review cannot be {self.verdict}")
        if self.verdict == "approved" and "pending" in statuses:
            raise ValueError("An approved release has no pending review")
        return self


class ReviewLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2]
    records: tuple[ReviewRecord, ...]

    @model_validator(mode="after")
    def _one_record_per_release(self) -> ReviewLedger:
        seen = {(record.id, record.version) for record in self.records}
        if len(seen) != len(self.records):
            raise ValueError("Duplicate review record for a release")
        return self


def read_ledger(data: bytes) -> ReviewLedger:
    return ReviewLedger.model_validate(strict_json(data))


def require_review(
    ledger: ReviewLedger,
    package_id: str,
    version: str,
    *,
    archive_sha256: str,
    source_sha256: str,
    distribution: Literal["included", "library"],
) -> ReviewRecord:
    """The record that lets this exact release be signed, or a sentence saying why not."""
    record = next((r for r in ledger.records if (r.id, r.version) == (package_id, version)), None)
    if record is None:
        raise ValueError(f"No review record for {package_id} {version}")
    if (record.archive_sha256, record.source_sha256) != (archive_sha256, source_sha256):
        raise ValueError(f"The review of {package_id} {version} is for different bytes")
    if record.verdict not in ADMITS[distribution]:
        raise ValueError(
            f"{package_id} {version} is {record.verdict}, which does not admit {distribution}"
        )
    return record
