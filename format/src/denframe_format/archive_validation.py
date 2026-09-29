"""Bounded ZIP structure validation shared by library packages and activity packs."""

from __future__ import annotations

import io
import stat
import struct
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass(frozen=True)
class ArchiveLimits:
    archive_bytes: int
    expanded_bytes: int
    files: int
    compression_ratio: int = 100
    archive_error: str = "Archive exceeds limit"
    expanded_error: str = "Expanded archive exceeds limit"


@dataclass(frozen=True)
class ArchiveIndex:
    archive: zipfile.ZipFile
    entries: list[zipfile.ZipInfo]
    expanded_bytes: int

    @property
    def names(self) -> list[str]:
        return [entry.filename for entry in self.entries]

    def read(self, name: str, limit: int) -> bytes:
        entry = self.archive.getinfo(name)
        with self.archive.open(entry) as source:
            value = source.read(limit + 1)
            if len(value) > limit or len(value) != entry.file_size:
                raise ValueError("Document exceeds limit")
            return value


def check_archive_end(raw: IO[bytes], limits: ArchiveLimits) -> None:
    """Bound directory allocation before any ZipFile reader sees untrusted bytes."""
    raw.seek(0, 2)
    size = raw.tell()
    if size > limits.archive_bytes:
        raise ValueError(limits.archive_error)
    # Check the fixed end record before ZipFile allocates the central directory.
    # ZIP64, split archives, comments and oversized directory metadata are unsupported.
    if size < 22:
        raise ValueError("Invalid ZIP end record")
    if size >= 42:
        raw.seek(-42, 2)
        if raw.read(4) == b"PK\x06\x07":
            raise ValueError("ZIP64 archives are unsupported")
    raw.seek(-22, 2)
    signature, disk, central_disk, count, total_count, central_size, offset, comment = (
        struct.unpack("<4s4H2IH", raw.read(22))
    )
    if (
        signature != b"PK\x05\x06"
        or disk
        or central_disk
        or comment
        or count != total_count
        or count > limits.files
        or central_size > limits.files * 256
        or offset + central_size != size - 22
    ):
        raise ValueError("Unsupported ZIP directory")


@contextmanager
def validated_archive(source: Path | bytes, limits: ArchiveLimits) -> Iterator[ArchiveIndex]:
    with source.open("rb") if isinstance(source, Path) else io.BytesIO(source) as raw:
        check_archive_end(raw, limits)
        with zipfile.ZipFile(raw) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > limits.files or len(set(names)) != len(names):
                raise ValueError("Duplicate entries or too many files")
            if len({name.casefold() for name in names}) != len(names):
                raise ValueError("Colliding entry names")
            total = sum(entry.file_size for entry in entries)
            if total > limits.expanded_bytes:
                raise ValueError(limits.expanded_error)
            for entry in entries:
                mode = entry.external_attr >> 16
                if (
                    entry.orig_filename != entry.filename
                    or entry.extra
                    or entry.comment
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or entry.flag_bits & 1
                    or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or entry.file_size > max(1, entry.compress_size) * limits.compression_ratio
                ):
                    raise ValueError("Unsupported archive entry")
            yield ArchiveIndex(archive, entries, total)
