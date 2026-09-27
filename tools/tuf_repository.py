"""The Mantel Library's online TUF repository: one root, separate roles, consistent snapshots.

The public repository mirrors this file as `tools/tuf_repository.py` and its daily job runs it, so
it depends only on `tuf`, `securesystemslib` and `cryptography`, never on the host.

A repository directory is served as it is:

    metadata/N.root.json      every root, kept forever: clients follow the chain from the root
                              they ship, one version at a time (there is no mutable `root.json`)
    metadata/N.targets.json   targets, signed by the offline targets key
    metadata/N.snapshot.json  snapshot, signed by the online key
    metadata/timestamp.json   the one mutable file, signed by the online key
    targets/<prefix>/<sha256>.<name>   immutable blobs under `definitions/`, `packs/`, `previews/`

Roles: root has two offline keys (a primary and a spare) at threshold 1; targets one offline key;
snapshot and timestamp share one online key, the only key the daily job holds. Targets carries a
signed `revoked` list of `{id, version, reason, date}` entries.

Every operation signs and verifies all its metadata in memory first, then writes blobs, targets,
snapshot, root (for a rotation) and the timestamp last, each file complete or not at all and never
over an existing one; so a client never sees a timestamp whose files are missing. An interrupted
operation leaves only unreferenced files: new versions are numbered past them, and running the
same command again finishes it.

Keys are PEM private keys. Production keys must be passphrase-encrypted; the passphrase comes
from an environment variable named on the command line or an interactive prompt. Unencrypted
throwaway keys are accepted only for a repository whose root says `channel: dev`, and a dev
repository refuses every operation that does not say `--dev` (and the reverse).
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from securesystemslib.signer import CryptoSigner, Key, SSlibKey
from tuf.api.exceptions import UnsignedMetadataError
from tuf.api.metadata import (
    Metadata,
    MetaFile,
    Root,
    Snapshot,
    TargetFile,
    Targets,
    Timestamp,
)

# D28's expiry schedule, in days.
EXPIRY_DAYS = {"timestamp": 7, "snapshot": 30, "targets": 365, "root": 730}
# `status` fails this many days before targets or root lapse, so the owner has time to sign.
WARNING_DAYS = {"targets": 60, "root": 90}
# D32: once targets metadata passes 1 MB, it is split into hash-bin delegations. This tool does
# not make delegations yet, so signing a larger top-level targets file is refused (a host would
# download all of it on every check), and `status` fails when the current one nears the limit.
HASH_BIN_THRESHOLD = 1024 * 1024
HASH_BIN_WARNING = 0.8
PREFIXES = ("definitions", "packs", "previews")
PUBLIC_KEY_ROLES = ("root", "targets", "online")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}")
_ID = re.compile(r"[a-z0-9][a-z0-9._/-]{0,199}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?")

Prompt = Callable[[str], str]


class RepositoryError(Exception):
    """An operation refused, with a sentence that says why. It never carries key material."""


# ---------------------------------------------------------------------------------------------
# Keys


@dataclass(frozen=True)
class KeySource:
    """Where a private key comes from: a file, or an environment variable holding the PEM (a CI
    secret). `passphrase_env` names the variable holding its passphrase; without one an
    encrypted key asks interactively."""

    path: Path | None = None
    env: str | None = None
    passphrase_env: str | None = None

    @property
    def label(self) -> str:
        return f"the key in ${self.env}" if self.env else f"key file {self.path}"


def interactive_passphrase(label: str) -> str:
    """Ask for a passphrase on the terminal, never echoing it."""
    if not sys.stdin.isatty():
        raise RepositoryError(
            f"The passphrase for {label} is needed: run interactively, or name the environment "
            "variable that holds it."
        )
    return getpass.getpass(f"Passphrase for {label}: ")


def load_signer(
    source: KeySource,
    *,
    allow_unencrypted: bool,
    prompt: Prompt = interactive_passphrase,
) -> CryptoSigner:
    """A signer for `source`. An unencrypted key is refused unless `allow_unencrypted`, and a
    wrong or missing passphrase fails with a sentence."""
    if source.env:
        pem = os.environ.get(source.env, "").encode()
        if not pem.strip():
            raise RepositoryError(f"The environment variable {source.env} holds no key.")
    elif source.path:
        try:
            pem = source.path.read_bytes()
        except OSError as error:
            raise RepositoryError(f"Cannot read {source.label}.") from error
    else:
        raise RepositoryError("No key was given.")
    try:
        key = load_pem_private_key(pem, password=None)
    except TypeError:
        key = None  # encrypted
    except ValueError as error:
        raise RepositoryError(f"{source.label} is not a PEM private key.") from error
    if key is not None:
        if not allow_unencrypted:
            raise RepositoryError(
                f"{source.label} is not passphrase-encrypted; production keys must be."
            )
        return CryptoSigner(key)
    if source.passphrase_env:
        passphrase = os.environ.get(source.passphrase_env, "")
        if not passphrase:
            raise RepositoryError(
                f"The passphrase variable {source.passphrase_env} is not set for {source.label}."
            )
    else:
        passphrase = prompt(source.label)
    if not passphrase:
        raise RepositoryError(f"No passphrase was given for {source.label}.")
    try:
        key = load_pem_private_key(pem, password=passphrase.encode())
    except ValueError as error:
        raise RepositoryError(f"The passphrase for {source.label} is wrong.") from error
    return CryptoSigner(key)


def public_key_entry(name: str, key: Key) -> dict[str, Any]:
    """One entry of a public-keys file: a name, the key id and the public key only."""
    return {"name": name, "keyid": key.keyid, **key.to_dict()}


def read_public_keys(path: Path) -> tuple[dict[str, list[Key]], str]:
    """The `root`, `targets` and `online` public keys of a key ceremony's public-keys file, and
    its channel (`dev` or `production`). Each key id is recomputed from its public key, so a file
    cannot name one key and carry another."""
    try:
        document = json.loads(path.read_text())
        channel = document["channel"]
        groups = document["keys"]
        result: dict[str, list[Key]] = {}
        for role in PUBLIC_KEY_ROLES:
            keys = []
            for entry in groups[role]:
                if entry["keytype"] != "ed25519" or entry["scheme"] != "ed25519":
                    raise RepositoryError(f"{path.name}: {role} keys must be Ed25519.")
                raw = bytes.fromhex(entry["keyval"]["public"])
                key = SSlibKey.from_crypto(Ed25519PublicKey.from_public_bytes(raw))
                if key.keyid != entry["keyid"]:
                    raise RepositoryError(f"{path.name}: a {role} key id does not match its key.")
                keys.append(key)
            result[role] = keys
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise RepositoryError(f"{path} is not a readable public-keys file.") from error
    if channel not in ("dev", "production"):
        raise RepositoryError(f"{path.name} must say channel dev or production.")
    if len(result["root"]) != 2 or len(result["targets"]) != 1 or len(result["online"]) != 1:
        raise RepositoryError(
            f"{path.name} must list two root keys (primary and spare), one targets key and one "
            "online key."
        )
    ids = [key.keyid for keys in result.values() for key in keys]
    if len(set(ids)) != len(ids):
        raise RepositoryError(f"{path.name}: every role needs its own key.")
    return result, channel


def require_key_channel(path: Path, channel: str, *, development: bool) -> None:
    """A dev key set only ever starts or rotates a dev repository, and a production one never."""
    if (channel == "dev") != development:
        raise RepositoryError(
            f"{path.name} is a {channel} key set; "
            + ("--dev refuses it." if development else "only --dev accepts it.")
        )


# ---------------------------------------------------------------------------------------------
# Repository state


@dataclass
class State:
    """A repository's verified metadata: the root chain and the current top-level roles.

    `pending` is a newer root that an interrupted `rotate-root` wrote before re-signing the
    files its key change affects; re-running the same rotation finishes it."""

    directory: Path
    roots: list[Metadata[Root]]
    targets: Metadata[Targets] | None
    snapshot: Metadata[Snapshot] | None
    timestamp: Metadata[Timestamp] | None
    pending: Metadata[Root] | None = None

    @property
    def root(self) -> Metadata[Root]:
        return self.roots[-1]

    @property
    def metadata(self) -> Path:
        return self.directory / "metadata"

    @property
    def development(self) -> bool:
        return self.root.signed.unrecognized_fields.get("channel") == "dev"


def _now(now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)


def _expires(role: str, now: datetime) -> datetime:
    return now + timedelta(days=EXPIRY_DAYS[role])


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _verify(root: Metadata[Root], role: str, metadata: Metadata[Any], name: str) -> None:
    try:
        root.verify_delegate(role, metadata)
    except UnsignedMetadataError as error:
        raise RepositoryError(f"{name} is not signed by the repository's {role} key.") from error


def _parse(data: bytes, name: str, kind: type) -> Metadata[Any]:
    try:
        metadata = Metadata.from_bytes(data)
    except Exception as error:  # the deserializer raises several types
        raise RepositoryError(f"{name} is not valid TUF metadata.") from error
    if not isinstance(metadata.signed, kind):
        raise RepositoryError(f"{name} holds the wrong role.")
    return metadata


def _bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise RepositoryError(f"{path.name} is missing.") from error


def _linked(meta: MetaFile, data: bytes, name: str) -> None:
    try:
        meta.verify_length_and_hashes(data)
    except Exception as error:
        raise RepositoryError(f"{name} does not match the metadata that points at it.") from error


def _highest(metadata: Path, role: str) -> int:
    """The highest `N.<role>.json` on disk, referenced or not: new versions go beyond it, so an
    interrupted operation's unreferenced leftovers never block the next one."""
    pattern = re.compile(rf"([0-9]+)\.{role}\.json")
    if not metadata.is_dir():
        return 0
    found = (pattern.fullmatch(path.name) for path in metadata.iterdir())
    return max((int(match.group(1)) for match in found if match), default=0)


def _mutable(
    metadata: Path, root: Metadata[Root]
) -> tuple[Metadata[Targets], Metadata[Snapshot], Metadata[Timestamp]]:
    """Timestamp, the snapshot it names and the targets that names, verified against `root`."""
    timestamp = _parse(_bytes(metadata / "timestamp.json"), "timestamp.json", Timestamp)
    _verify(root, "timestamp", timestamp, "timestamp.json")
    snapshot_name = f"{timestamp.signed.snapshot_meta.version}.snapshot.json"
    snapshot_bytes = _bytes(metadata / snapshot_name)
    _linked(timestamp.signed.snapshot_meta, snapshot_bytes, snapshot_name)
    snapshot = _parse(snapshot_bytes, snapshot_name, Snapshot)
    _verify(root, "snapshot", snapshot, snapshot_name)
    targets_meta = snapshot.signed.meta["targets.json"]
    targets_name = f"{targets_meta.version}.targets.json"
    targets_bytes = _bytes(metadata / targets_name)
    _linked(targets_meta, targets_bytes, targets_name)
    targets = _parse(targets_bytes, targets_name, Targets)
    _verify(root, "targets", targets, targets_name)
    return targets, snapshot, timestamp


def load(directory: Path) -> State:
    """Read and verify a repository: every root from 1.root.json on, each signed by its
    predecessor's root threshold and its own; then timestamp, snapshot and targets against the
    current root. Expiry is not enforced here: `renew` exists to fix a lapse, and `status`
    reports it.

    When the published files satisfy only the root before the newest, the newest is the pending
    root of an interrupted rotation: it is set aside as `pending`, not trusted as current."""
    metadata = directory / "metadata"
    roots: list[Metadata[Root]] = []
    while (metadata / f"{len(roots) + 1}.root.json").exists():
        name = f"{len(roots) + 1}.root.json"
        root = _parse(_bytes(metadata / name), name, Root)
        if root.signed.version != len(roots) + 1:
            raise RepositoryError(f"{name} carries version {root.signed.version}.")
        _verify(roots[-1] if roots else root, "root", root, name)
        _verify(root, "root", root, name)
        roots.append(root)
    if not roots:
        raise RepositoryError(f"{directory} has no 1.root.json; run init first.")
    if not (metadata / "timestamp.json").exists():
        return State(directory, roots, None, None, None)
    try:
        return State(directory, roots, *_mutable(metadata, roots[-1]))
    except RepositoryError:
        if len(roots) < 2:
            raise
        try:
            published = _mutable(metadata, roots[-2])
        except RepositoryError:
            pass
        else:
            return State(directory, roots[:-1], *published, pending=roots[-1])
        raise


def _settled(state: State) -> None:
    if state.pending is not None:
        raise RepositoryError(
            f"An interrupted rotation left {state.pending.signed.version}.root.json; run the "
            "same rotate-root again to finish it."
        )


def _channel(state: State, *, development: bool) -> None:
    """A dev repository is only ever touched as dev, and a production one never as dev."""
    if state.development and not development:
        raise RepositoryError(
            "This repository's root is labelled channel: dev; its throwaway keys never sign "
            "production. Pass --dev for development work."
        )
    if development and not state.development:
        raise RepositoryError("This is a production repository; --dev operations are refused.")


def _require(root: Metadata[Root], role: str, signer: CryptoSigner, what: str) -> None:
    if signer.public_key.keyid not in root.signed.roles[role].keyids:
        raise RepositoryError(f"The {what} key given is not this repository's {role} key.")


# ---------------------------------------------------------------------------------------------
# Writing: everything is signed and verified in memory first, then written in publish order.


def _link(path: Path, data: bytes) -> bool:
    """Write `path` complete or not at all, never over an existing file. False when it exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).chmod(0o644)
        try:
            path.hardlink_to(temporary)
        except FileExistsError:
            return False
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def _replace(path: Path, data: bytes) -> None:
    """Replace a mutable file atomically, so a reader sees the old bytes or the new ones."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).chmod(0o644)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _blob_path(directory: Path, target: TargetFile) -> Path:
    folder, name = target.path.split("/")
    return directory / "targets" / folder / f"{target.hashes['sha256']}.{name}"


@dataclass
class _Plan:
    """What an operation writes: blobs, then versioned metadata in order, then the timestamp."""

    blobs: list[tuple[Path, bytes]] = field(default_factory=list)
    versioned: list[tuple[Path, bytes]] = field(default_factory=list)
    timestamp: bytes | None = None


def _commit(state: State, plan: _Plan) -> None:
    """Write a plan. Every destination is checked first, so a refusal writes nothing; an
    interruption leaves only complete, unreferenced files that the next run steps over."""
    for path, data in plan.blobs:
        if path.exists() and path.read_bytes() != data:
            raise RepositoryError(f"{path.name} exists with other bytes.")
    for path, _ in plan.versioned:
        if path.exists():
            raise RepositoryError(f"{path.name} already exists; versions only move forward.")
    for path, data in plan.blobs:
        if not _link(path, data) and path.read_bytes() != data:
            raise RepositoryError(f"{path.name} exists with other bytes.")
    for path, data in plan.versioned:
        if not _link(path, data):
            raise RepositoryError(f"{path.name} already exists; versions only move forward.")
    if plan.timestamp is not None:
        _replace(state.metadata / "timestamp.json", plan.timestamp)


def _stage_chain(
    state: State,
    root: Metadata[Root],
    online: CryptoSigner,
    now: datetime,
    plan: _Plan,
    targets: Metadata[Targets] | None = None,
    targets_signer: CryptoSigner | None = None,
    after: int = 0,
) -> State:
    """Sign, against `root`, new targets (when given), a new snapshot and a timestamp that names
    that exact snapshot; add them to `plan` and verify them before anything is written. Snapshot
    and timestamp are numbered past `after` too: the versions the website already serves, which
    the daily renewal may have moved past this directory's (`library_served.py`)."""
    _require(root, "snapshot", online, "online")
    _require(root, "timestamp", online, "online")
    targets_versioned: list[tuple[Path, bytes]] = []
    if targets is not None:
        if targets_signer is None:
            raise RepositoryError("Signing targets needs the targets key.")
        _require(root, "targets", targets_signer, "targets")
        targets.signatures.clear()
        targets.sign(targets_signer)
        target_bytes = targets.to_bytes()
        _within_hash_bin_threshold(targets, len(target_bytes))
        targets_versioned.append(
            (state.metadata / f"{targets.signed.version}.targets.json", target_bytes)
        )
    elif state.targets is None:
        raise RepositoryError("Nothing is published yet; run publish first.")
    else:
        targets = state.targets
        target_bytes = _bytes(state.metadata / f"{targets.signed.version}.targets.json")
    version = max(
        state.snapshot.signed.version if state.snapshot else 0,
        _highest(state.metadata, "snapshot"),
        after,
    )
    snapshot = Metadata(
        Snapshot(
            version=version + 1,
            expires=_expires("snapshot", now),
            meta={
                "targets.json": MetaFile(
                    targets.signed.version, len(target_bytes), {"sha256": _sha256(target_bytes)}
                )
            },
        )
    )
    snapshot.sign(online)
    snapshot_bytes = snapshot.to_bytes()
    timestamp = Metadata(
        Timestamp(
            version=max(state.timestamp.signed.version if state.timestamp else 0, after) + 1,
            expires=_expires("timestamp", now),
            snapshot_meta=MetaFile(
                snapshot.signed.version, len(snapshot_bytes), {"sha256": _sha256(snapshot_bytes)}
            ),
        )
    )
    timestamp.sign(online)
    for role, metadata in (("targets", targets), ("snapshot", snapshot), ("timestamp", timestamp)):
        _verify(root, role, metadata, role)
    plan.versioned += [
        *targets_versioned,
        (state.metadata / f"{snapshot.signed.version}.snapshot.json", snapshot_bytes),
    ]
    plan.timestamp = timestamp.to_bytes()
    return State(state.directory, state.roots, targets, snapshot, timestamp)


def _within_hash_bin_threshold(targets: Metadata[Targets], length: int) -> None:
    """D32: a top-level targets file past the threshold needs hash-bin delegations first."""
    if length > HASH_BIN_THRESHOLD and targets.signed.delegations is None:
        raise RepositoryError(
            f"targets v{targets.signed.version} would be {length:,} bytes, over D32's "
            f"{HASH_BIN_THRESHOLD:,}-byte limit for one targets file: split it into hash-bin "
            "delegations before publishing more (docs/operations/LIBRARY_TUF_OPERATIONS.md)."
        )


def _next_targets(state: State, now: datetime) -> Metadata[Targets]:
    """The next targets version: the current targets and revocations, freshly dated, numbered
    beyond any targets file already on disk."""
    current = state.targets.signed if state.targets else None
    version = max(current.version if current else 0, _highest(state.metadata, "targets"))
    targets = Metadata(
        Targets(
            version=version + 1,
            expires=_expires("targets", now),
            targets=dict(current.targets) if current else {},
        )
    )
    targets.signed.unrecognized_fields["revoked"] = list(revocations(state))
    return targets


def revocations(state: State) -> list[dict[str, str]]:
    """The signed `revoked` list of the current targets."""
    if state.targets is None:
        return []
    return [dict(entry) for entry in state.targets.signed.unrecognized_fields.get("revoked", [])]


def _assign_keys(root: Root, public_keys: dict[str, list[Key]]) -> None:
    """The role layout: both root keys, the targets key, and the online key for snapshot and
    timestamp."""
    for key in public_keys["root"]:
        root.add_key(key, "root")
    root.add_key(public_keys["targets"][0], "targets")
    for role in ("snapshot", "timestamp"):
        root.add_key(public_keys["online"][0], role)


# ---------------------------------------------------------------------------------------------
# Operations


def init(
    directory: Path,
    public_keys: dict[str, list[Key]],
    root_signers: Iterable[CryptoSigner],
    *,
    development: bool = False,
    now: datetime | None = None,
) -> Metadata[Root]:
    """Write 1.root.json: two root keys at threshold 1, one targets key, and the online key for
    both snapshot and timestamp, with consistent snapshots on."""
    metadata = directory / "metadata"
    if metadata.exists() and any(metadata.iterdir()):
        raise RepositoryError(f"{metadata} already holds metadata; init starts a new repository.")
    moment = _now(now)
    root = Metadata(Root(version=1, expires=_expires("root", moment), consistent_snapshot=True))
    if development:
        root.signed.unrecognized_fields["channel"] = "dev"
    _assign_keys(root.signed, public_keys)
    signers = list(root_signers)
    if not signers:
        raise RepositoryError("init needs a root key to sign 1.root.json.")
    for signer in signers:
        _require(root, "root", signer, "root")
        root.sign(signer, append=True)
    if not _link(metadata / "1.root.json", root.to_bytes()):
        raise RepositoryError("1.root.json already exists.")
    return root


def _target_files(source: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise RepositoryError(f"{relative} is a symbolic link; publish only plain files.")
        if not path.is_file():
            continue
        parts = relative.parts
        if len(parts) != 2 or parts[0] not in PREFIXES or not _NAME.fullmatch(parts[1]):
            raise RepositoryError(
                f"{relative} is not a publishable target: use definitions/, packs/ or previews/ "
                "and a plain file name."
            )
        files[relative.as_posix()] = path.read_bytes()
    if not files:
        raise RepositoryError(f"{source} has no files under definitions/, packs/ or previews/.")
    return files


def _open(directory: Path, *, development: bool) -> State:
    state = load(directory)
    _channel(state, development=development)
    _settled(state)
    return state


def publish(
    directory: Path,
    source: Path,
    targets_signer: CryptoSigner,
    online: CryptoSigner,
    *,
    development: bool = False,
    now: datetime | None = None,
) -> State:
    """Add or replace the targets in `source`: blobs first, then targets, snapshot, timestamp."""
    state = _open(directory, development=development)
    moment = _now(now)
    files = _target_files(source)
    targets = _next_targets(state, moment)
    plan = _Plan()
    for path, data in files.items():
        target = TargetFile.from_data(path, data, ["sha256"])
        plan.blobs.append((_blob_path(directory, target), data))
        targets.signed.targets[path] = target
    result = _stage_chain(state, state.root, online, moment, plan, targets, targets_signer)
    _commit(state, plan)
    return result


def revoke(
    directory: Path,
    entry: dict[str, str],
    targets_signer: CryptoSigner,
    online: CryptoSigner,
    *,
    development: bool = False,
    now: datetime | None = None,
    after: int = 0,
) -> State:
    """Add `{id, version, reason, date}` to the signed revoked list, then re-sign targets,
    snapshot and timestamp (numbered past `after`, see `_stage_chain`). Entries are never
    removed."""
    state = _open(directory, development=development)
    if state.targets is None:
        raise RepositoryError("Nothing is published yet; run publish first.")
    moment = _now(now)
    entry = {
        "id": entry.get("id") or "",
        "version": entry.get("version") or "",
        "reason": " ".join((entry.get("reason") or "").split()),
        "date": entry.get("date") or moment.date().isoformat(),
    }
    if not _ID.fullmatch(entry["id"]) or not _VERSION.fullmatch(entry["version"]):
        raise RepositoryError("A revocation needs an asset id and an exact version.")
    if not 1 <= len(entry["reason"]) <= 240:
        raise RepositoryError("A revocation needs a one-line reason of at most 240 characters.")
    try:
        date.fromisoformat(entry["date"])
    except ValueError as error:
        raise RepositoryError("The revocation date must be YYYY-MM-DD.") from error
    current = revocations(state)
    if any((item["id"], item["version"]) == (entry["id"], entry["version"]) for item in current):
        raise RepositoryError(f"{entry['id']}@{entry['version']} is already revoked.")
    targets = _next_targets(state, moment)
    targets.signed.unrecognized_fields["revoked"] = sorted(
        [*current, entry], key=lambda item: (item["id"], item["version"])
    )
    plan = _Plan()
    result = _stage_chain(state, state.root, online, moment, plan, targets, targets_signer, after)
    _commit(state, plan)
    return result


def renew(
    directory: Path,
    online: CryptoSigner,
    *,
    development: bool = False,
    now: datetime | None = None,
) -> State:
    """The daily job: a new snapshot of the unchanged current targets, then a timestamp for that
    exact snapshot. Only the online key is needed."""
    state = _open(directory, development=development)
    plan = _Plan()
    result = _stage_chain(state, state.root, online, _now(now), plan)
    _commit(state, plan)
    return result


def _same_keys(one: Root, other: Root) -> bool:
    return set(one.keys) == set(other.keys) and all(
        set(one.roles[role].keyids) == set(other.roles[role].keyids)
        and one.roles[role].threshold == other.roles[role].threshold
        for role in ("root", "targets", "snapshot", "timestamp")
    )


def rotate_root(
    directory: Path,
    public_keys: dict[str, list[Key]],
    root_signers: Iterable[CryptoSigner],
    *,
    targets_signer: CryptoSigner | None = None,
    online: CryptoSigner | None = None,
    development: bool = False,
    now: datetime | None = None,
) -> State:
    """Write N+1.root.json with the key set in `public_keys`, signed by the current root
    threshold and the new one. A key any earlier root held and the current one dropped never
    comes back. When the targets or online key changes, the metadata it signs is re-signed with
    the new key in the same operation: new targets and snapshot first, then the root, then the
    timestamp, so a client never meets a root the published files do not satisfy. Everything is
    signed and verified before the first write; re-running an interrupted rotation finishes it."""
    state = load(directory)
    _channel(state, development=development)
    moment = _now(now)
    old = state.root
    new = Metadata(
        Root(
            version=old.signed.version + 1,
            expires=_expires("root", moment),
            consistent_snapshot=True,
            unrecognized_fields=dict(old.signed.unrecognized_fields),
        )
    )
    _assign_keys(new.signed, public_keys)
    name = f"{new.signed.version}.root.json"
    if state.pending is not None:
        if not _same_keys(state.pending.signed, new.signed):
            raise RepositoryError(
                f"{name}, from an interrupted rotation, has another key set; re-run that same "
                "rotation to finish it."
            )
        new = state.pending  # already signed by both thresholds, and verified by load
    else:
        current = set(old.signed.keys)
        retired = {keyid for root in state.roots for keyid in root.signed.keys} - current
        returning = retired & set(new.signed.keys)
        if returning:
            raise RepositoryError(
                "A key an earlier root removed cannot return: " + ", ".join(sorted(returning)) + "."
            )
        for signer in root_signers:
            keyid = signer.public_key.keyid
            if keyid not in {*old.signed.roles["root"].keyids, *new.signed.roles["root"].keyids}:
                raise RepositoryError("A root key given is neither a current nor a new root key.")
            new.sign(signer, append=True)
        try:
            old.verify_delegate("root", new)
            new.verify_delegate("root", new)
        except UnsignedMetadataError as error:
            raise RepositoryError(
                f"{name} needs a signature from a current root key and from a new root key."
            ) from error
    targets_changed = new.signed.roles["targets"].keyids != old.signed.roles["targets"].keyids
    online_changed = new.signed.roles["snapshot"].keyids != old.signed.roles["snapshot"].keyids
    plan = _Plan()
    rotated = State(directory, [*state.roots, new], state.targets, state.snapshot, state.timestamp)
    if state.timestamp is not None and (targets_changed or online_changed):
        if online is None:
            raise RepositoryError("Re-signing after this rotation needs the new online key.")
        if targets_changed:
            if targets_signer is None:
                raise RepositoryError("The targets key changes: give the new targets key.")
            rotated = _stage_chain(
                rotated, new, online, moment, plan, _next_targets(rotated, moment), targets_signer
            )
        else:
            rotated = _stage_chain(rotated, new, online, moment, plan)
    if state.pending is None:
        plan.versioned.append((state.metadata / name, new.to_bytes()))
    _commit(state, plan)
    return State(
        directory, [*state.roots, new], rotated.targets, rotated.snapshot, rotated.timestamp
    )


@dataclass(frozen=True)
class RoleStatus:
    role: str
    version: int
    expires: datetime
    days: float


def status(
    directory: Path, *, development: bool = False, now: datetime | None = None
) -> tuple[list[RoleStatus], list[str]]:
    """Each role's version and time to expiry, and the problems the daily job alerts on: a lapsed
    timestamp or snapshot, or targets or root inside their warning window."""
    state = load(directory)
    _channel(state, development=development)
    moment = _now(now)
    problems = []
    if state.pending is not None:
        problems.append(
            f"An interrupted rotation left {state.pending.signed.version}.root.json; run the "
            "same rotate-root again."
        )
    roles = [("root", state.root)]
    roles += [
        (name, meta)
        for name, meta in (
            ("targets", state.targets),
            ("snapshot", state.snapshot),
            ("timestamp", state.timestamp),
        )
        if meta is not None
    ]
    rows = [
        RoleStatus(
            name,
            meta.signed.version,
            meta.signed.expires,
            (meta.signed.expires - moment).total_seconds() / 86400,
        )
        for name, meta in roles
    ]
    if state.timestamp is None:
        problems.append("Nothing is published yet.")
    if state.targets is not None and state.targets.signed.delegations is None:
        size = (state.metadata / f"{state.targets.signed.version}.targets.json").stat().st_size
        if size > HASH_BIN_THRESHOLD * HASH_BIN_WARNING:
            problems.append(
                f"targets is {size:,} bytes, {size * 100 // HASH_BIN_THRESHOLD}% of D32's "
                f"{HASH_BIN_THRESHOLD:,}-byte limit; add hash-bin delegations before the next "
                "publish crosses it (publish refuses past it)."
            )
    for row in rows:
        if row.days <= 0:
            problems.append(f"{row.role} expired on {row.expires.isoformat()}.")
        elif row.role in WARNING_DAYS and row.days <= WARNING_DAYS[row.role]:
            problems.append(
                f"{row.role} expires in {int(row.days)} days; sign a new {row.role} before "
                f"{row.expires.date().isoformat()}."
            )
    return rows, problems


# ---------------------------------------------------------------------------------------------
# Command line


def _key(args: argparse.Namespace, role: str) -> KeySource | None:
    path = getattr(args, f"{role}_key", None)
    env = getattr(args, f"{role}_key_env", None)
    if path is None and env is None:
        return None
    return KeySource(path, env, getattr(args, f"{role}_passphrase_env", None))


def _optional_signer(args: argparse.Namespace, role: str) -> CryptoSigner | None:
    source = _key(args, role)
    return None if source is None else load_signer(source, allow_unencrypted=args.dev)


def _signer(args: argparse.Namespace, role: str) -> CryptoSigner:
    signer = _optional_signer(args, role)
    if signer is None:
        raise RepositoryError(f"Give the {role} key (--{role}-key).")
    return signer


def _public_keys(args: argparse.Namespace) -> dict[str, list[Key]]:
    keys, channel = read_public_keys(args.public_keys)
    require_key_channel(args.public_keys, channel, development=args.dev)
    return keys


def _root_signers(args: argparse.Namespace) -> list[CryptoSigner]:
    return [
        load_signer(KeySource(path), allow_unencrypted=args.dev) for path in args.root_key or []
    ]


def _add_key(parser: argparse.ArgumentParser, role: str, *, env: bool = False) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument(f"--{role}-key", type=Path, help=f"the {role} private key (PEM)")
    if env:
        group.add_argument(
            f"--{role}-key-env", metavar="NAME", help=f"environment variable holding the {role} key"
        )
    parser.add_argument(
        f"--{role}-passphrase-env",
        metavar="NAME",
        help=f"environment variable holding the {role} key's passphrase (else a prompt)",
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    result.add_argument("--repository", type=Path, required=True, help="the repository directory")
    result.add_argument(
        "--dev", action="store_true", help="a development repository with throwaway keys"
    )
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("init", help="write 1.root.json")
    command.add_argument("--public-keys", type=Path, required=True)
    command.add_argument("--root-key", type=Path, action="append", required=True)
    command = commands.add_parser("publish", help="add or replace targets from a directory")
    command.add_argument("--source", type=Path, required=True)
    _add_key(command, "targets")
    _add_key(command, "online", env=True)
    command = commands.add_parser("revoke", help="add a signed revocation")
    command.add_argument("--id", required=True)
    command.add_argument("--version", required=True)
    command.add_argument("--reason", required=True)
    command.add_argument("--date", help="YYYY-MM-DD (default today)")
    _add_key(command, "targets")
    _add_key(command, "online", env=True)
    command = commands.add_parser("renew", help="new snapshot and timestamp (online key only)")
    _add_key(command, "online", env=True)
    command = commands.add_parser("rotate-root", help="write N+1.root.json with a new key set")
    command.add_argument("--public-keys", type=Path, required=True)
    command.add_argument("--root-key", type=Path, action="append", required=True)
    _add_key(command, "targets")
    _add_key(command, "online", env=True)
    commands.add_parser("status", help="versions and expiry; nonzero on a lapse or warning")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        directory: Path = args.repository
        if args.command == "init":
            state = init(
                directory,
                _public_keys(args),
                _root_signers(args),
                development=args.dev,
            )
            print(f"Wrote 1.root.json{' (channel: dev)' if args.dev else ''}.")
        elif args.command == "publish":
            state = publish(
                directory,
                args.source,
                _signer(args, "targets"),
                _signer(args, "online"),
                development=args.dev,
            )
            print(_summary(state))
        elif args.command == "revoke":
            state = revoke(
                directory,
                {"id": args.id, "version": args.version, "reason": args.reason, "date": args.date},
                _signer(args, "targets"),
                _signer(args, "online"),
                development=args.dev,
            )
            print(_summary(state))
        elif args.command == "renew":
            state = renew(directory, _signer(args, "online"), development=args.dev)
            print(_summary(state))
        elif args.command == "rotate-root":
            state = rotate_root(
                directory,
                _public_keys(args),
                _root_signers(args),
                targets_signer=_optional_signer(args, "targets"),
                online=_optional_signer(args, "online"),
                development=args.dev,
            )
            print(f"Wrote {state.root.signed.version}.root.json. {_summary(state)}")
        else:
            rows, problems = status(directory, development=args.dev)
            print(f"Mantel Library repository, channel: {'dev' if args.dev else 'production'}")
            for row in rows:
                print(
                    f"{row.role:<10} v{row.version:<6} expires {row.expires.isoformat()} "
                    f"({row.days:.1f} days)"
                )
            for problem in problems:
                print(f"PROBLEM: {problem}")
            return 1 if problems else 0
    except RepositoryError as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    return 0


def _summary(state: State) -> str:
    if state.timestamp is None or state.snapshot is None or state.targets is None:
        return "Nothing is published yet."
    return (
        f"targets v{state.targets.signed.version}, snapshot v{state.snapshot.signed.version}, "
        f"timestamp v{state.timestamp.signed.version}."
    )


if __name__ == "__main__":
    sys.exit(main())
