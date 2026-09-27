"""The pull-request route inside the sandbox: take a pull request's changed asset sources out of
its head tarball and build them into the archives the review reads.

`sandbox.py intake --pr N` keeps the tarball of exactly the head commit as opaque bytes, beside
the selection GitHub's metadata gives (the changed `definitions/*.json` names and pack slugs).
`sandbox.py build --intake DIR` stages both read-only at `/submission` and runs `entry.py build
head.tar.gz selection.json`, which calls `build_head` here. Only in the sandbox is the tarball
read: its entries are checked (one top-level directory, no absolute or `..` path anywhere; among
the selected sources only regular files with plain names, within the caps), and the selected
files are written by this module -- never by `tarfile`'s extraction -- into the sandbox's own
`/tmp`, one pack at a time. A catalog is read in memory.

It builds with the published toolchain only -- `tools/library_sources.py` (`check_entry`,
`definition_archive`, the same functions `tools/intake.py` and `tools/rebuild.py` build with,
staged beside these scripts) and `mantel_format.authoring.read_source` -- so what is reviewed is
what the repository would build. Nothing from the sources is imported or run: a pack's
`draw.py`, if any, is only a file beside its `source.json`.

Only what the reviewer's checkout does not already hold is built: a catalog entry that is not
identical to one of the public catalog's, a pack whose `source.json` differs from the public
one of the same slug (or is new). Output is one JSON line per result -- `{"built": {...}}` with
the archive base64-encoded, `{"failed": {...}}` or `{"skipped": "..."}` -- so no more than one
archive is held at a time; the runner checks each archive's hash and writes it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import tarfile
from collections.abc import Iterator
from pathlib import Path

from mantel_format.authoring import read_source
from mantel_format.encoding import strict_json
from review_checks import neutral

MAX_DOCUMENT = 4 * 1024 * 1024
BUILD_ERRORS = (ValueError, TypeError, KeyError, OSError)
# The caps on the head tarball and on the sources taken from it. One pack is written into the
# sandbox's 64 MiB `/tmp` (sandbox.py `LIMITS`) to be built, so it is capped below that, with room
# left for the build.
MAX_TAR_MEMBERS = 50_000
MAX_SOURCE_FILES = 4096
MAX_SOURCE_FILE = 64 * 1024 * 1024
MAX_SOURCES = 128 * 1024 * 1024
MAX_PACK = 48 * 1024 * 1024
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
SOURCE_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class Refused(Exception):
    """The head tarball or the selection is refused as a whole; nothing is built."""


def _document(data: bytes, name: str) -> object:
    if len(data) > MAX_DOCUMENT:
        raise ValueError(f"{name} is over {MAX_DOCUMENT} bytes")
    return strict_json(data)


def _built(kind: str, slug: object, origin: str, item: dict, data: bytes) -> dict:
    return {
        "kind": kind,
        "slug": slug,
        "from": origin,
        "id": item.get("id"),
        "version": item.get("version"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "archive": base64.b64encode(data).decode("ascii"),
    }


def selection_from(document: object) -> tuple[set[str], set[str]]:
    """The changed definition file names and pack slugs, checked again here."""
    if not isinstance(document, dict):
        raise Refused("The selection is not an object")
    definitions, packs = document.get("definitions"), document.get("packs")
    if not isinstance(definitions, list) or not isinstance(packs, list):
        raise Refused("The selection names no definitions and packs lists")
    for name in definitions:
        if not isinstance(name, str) or not name.endswith(".json"):
            raise Refused("The selection names a definition file that is not a .json name")
        if not SOURCE_PART.fullmatch(name):
            raise Refused("The selection names a definition file that is not a plain name")
    for slug in packs:
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise Refused("The selection names a pack that is not a plain slug")
    if not definitions and not packs:
        raise Refused("The selection is empty")
    return set(definitions), set(packs)


def scan(
    archive: tarfile.TarFile, definitions: set[str], slugs: set[str]
) -> dict[tuple[str, ...], list[tarfile.TarInfo]]:
    """The selected sources' entries, grouped as `("definitions",)` or `("packs", slug)`.

    Every entry's path is checked, selected or not: no absolute, empty, `.` or `..` part, no
    backslash, one top-level directory. Among the selected sources: regular files only (a link,
    device or other special file refuses the whole tarball), plain names, each path once, and
    the caps (a pack's own below the sandbox's scratch space)."""
    groups: dict[tuple[str, ...], list[tarfile.TarInfo]] = {}
    seen: set[str] = set()
    folders: set[str] = set()
    sizes: dict[tuple[str, ...], int] = {}
    top: str | None = None
    members = files = total = 0
    for member in archive:
        members += 1
        if members > MAX_TAR_MEMBERS:
            raise Refused(f"The head tarball has over {MAX_TAR_MEMBERS} entries")
        name = member.name
        parts = name.split("/")
        if name.startswith("/") or "\\" in name or any(p in ("", ".", "..") for p in parts):
            raise Refused(f"Refusing the head tarball: an unsafe path {neutral(name, 200)}")
        if top is None:
            top = parts[0]
        elif parts[0] != top:
            raise Refused("Refusing the head tarball: more than one top-level directory")
        relative = parts[1:]
        if len(relative) == 2 and relative[0] == "definitions" and relative[1] in definitions:
            group: tuple[str, ...] = ("definitions",)
        elif len(relative) >= 3 and relative[0] == "packs" and relative[1] in slugs:
            group = ("packs", relative[1])
        else:
            continue
        where = "/".join(relative)
        if member.isdir():
            continue
        if not member.isreg():
            raise Refused(f"Refusing a link or special file in the sources: {neutral(where, 200)}")
        if not all(SOURCE_PART.fullmatch(part) for part in relative):
            raise Refused(f"Refusing a source file name: {neutral(where, 200)}")
        files += 1
        total += member.size
        if member.size > MAX_SOURCE_FILE or total > MAX_SOURCES:
            raise Refused("The changed sources are over the size limit")
        if files > MAX_SOURCE_FILES:
            raise Refused(f"The changed sources have over {MAX_SOURCE_FILES} files")
        parents = {"/".join(relative[:end]) for end in range(1, len(relative))}
        if where in seen or where in folders or parents & seen:
            raise Refused(f"Refusing the head tarball: {neutral(where, 200)} is there twice")
        seen.add(where)
        folders |= parents
        sizes[group] = sizes.get(group, 0) + member.size
        if group[0] == "packs" and sizes[group] > MAX_PACK:
            raise Refused(
                f"packs/{group[1]} is over {MAX_PACK // (1024 * 1024)} MiB of sources, more than "
                "the review sandbox can build"
            )
        groups.setdefault(group, []).append(member)
    if not groups:
        raise Refused("The head holds none of the changed asset sources")
    return groups


def _read(archive: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = archive.extractfile(member)
    data = handle.read(member.size + 1) if handle else b""
    if len(data) != member.size:
        raise Refused(f"A truncated entry in the head tarball: {neutral(member.name, 200)}")
    return data


def _write(archive: tarfile.TarFile, members: list[tarfile.TarInfo], scratch: Path) -> None:
    """The members as plain files under `scratch`, the tarball's top-level directory dropped."""
    for member in members:
        relative = member.name.split("/")[1:]
        path = scratch.joinpath(*relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as out:
            out.write(_read(archive, member))
        path.chmod(0o644)


def _definitions(
    archive: tarfile.TarFile, members: list[tarfile.TarInfo], reference: Path
) -> Iterator[dict]:
    """Catalog entries the public catalog does not hold as they stand."""
    from library_sources import (  # pyright: ignore[reportMissingImports]
        check_entry,
        definition_archive,
    )

    public = reference / "definitions/catalog.json"
    known = json.loads(public.read_text(encoding="utf-8")) if public.is_file() else []
    for member in sorted(members, key=lambda item: item.name):
        name = member.name.rsplit("/", 1)[-1]
        origin = f"definitions/{name}"
        if name != "catalog.json":
            yield {"skipped": neutral(f"{origin}: not an asset catalog (a maintainer's file)", 200)}
            continue
        try:
            if member.size > MAX_DOCUMENT:
                raise ValueError(f"{name} is over {MAX_DOCUMENT} bytes")
            entries = _document(_read(archive, member), name)
            if not isinstance(entries, list):
                raise ValueError("the catalog is not a list")
        except BUILD_ERRORS as error:
            yield {"failed": {"source": origin, "error": neutral(error, 400)}}
            continue
        for item in entries:
            if item in known:
                continue
            ident = item.get("id") if isinstance(item, dict) else None
            try:
                if not isinstance(item, dict):
                    raise ValueError("a catalog entry is not an object")
                check_entry(item, origin)
                data = definition_archive(item)
            except BUILD_ERRORS as error:
                where = f"{origin} {neutral(ident, 80)}"
                yield {"failed": {"source": where, "error": neutral(error, 400)}}
                continue
            yield {"built": _built("definition", item["slug"], origin, item, data)}


def _pack(folder: Path, reference: Path) -> dict:
    """A pack source that is new, or whose `source.json` differs from the public one."""
    origin = f"packs/{folder.name}"
    source = folder / "source.json"
    if not source.is_file():
        return {"skipped": neutral(f"{origin}: no source.json", 200)}
    public = reference / "packs" / folder.name / "source.json"
    try:
        mine = _document(source.read_bytes(), "source.json")
        if public.is_file() and _document(public.read_bytes(), "source.json") == mine:
            return {"skipped": neutral(f"{origin}: source.json unchanged from the public catalog")}
        item, _, data = read_source(source)
    except BUILD_ERRORS as error:
        return {"failed": {"source": origin, "error": neutral(error, 400)}}
    return {"built": _built("pack", folder.name, origin, item, data)}


def build_head(tarball: Path, selection: object, reference: Path, scratch: Path) -> Iterator[dict]:
    """One result per changed source: definitions first, then each pack, written into `scratch`
    (which must not exist), built and removed before the next. Raises `Refused` before building
    anything when the tarball or the selection is refused."""
    definitions, slugs = selection_from(selection)
    with tarfile.open(tarball, "r:gz") as archive:
        groups = scan(archive, definitions, slugs)
        yield from _definitions(archive, groups.get(("definitions",), []), reference)
        for slug in sorted(slugs):
            members = groups.get(("packs", slug))
            if not members:
                yield {"skipped": neutral(f"packs/{slug}: not in the head (removed)", 200)}
                continue
            scratch.mkdir()
            try:
                try:
                    _write(archive, members, scratch)
                except OSError as error:
                    yield {"failed": {"source": f"packs/{slug}", "error": neutral(error, 400)}}
                    continue
                yield _pack(scratch / "packs" / slug, reference)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
