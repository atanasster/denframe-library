"""The online Denframe Library as the website serves it: the one source of truth (D28).

The public repository mirrors this file as `tools/library_served.py`, beside
`tools/tuf_repository.py`; its daily `Renew library metadata` workflow runs it there. It depends
only on the standard library, `tuf`, `securesystemslib` and `cryptography`
(`tools/requirements-release.lock`), never on the host.

The repository hosts verify is the one the website serves under `/library/metadata/` and
`/library/targets/` (`smart-home-cec89`, `https://smart.meggy.com`). Two writers keep it:

- **a release** (`scripts/library-release.py`, on the owner's key machine) signs targets, snapshot
  and timestamp into `library/online` and the site is deployed from the committed tree. Before it
  signs, it `pull`s what the site serves, refuses unless that chain verifies from the repository's
  own roots and targets, and numbers its snapshot and timestamp past the served versions (with a
  margin, so the daily renewals made before the deploy never reach them);
- **the daily renewal** (the public workflow) `pull`s the served metadata, verifies it from the
  pinned root, renews snapshot then timestamp with the online key (`tuf_repository.py renew`) and
  `publish`es only the new `N.snapshot.json` and `timestamp.json` to Firebase Hosting: it clones
  the live release's version without its `timestamp.json`, adds the two files through the Hosting
  REST API (`versions.clone`, `populateFiles`, upload, finalize, `releases.create`), and checks
  the site then serves them. It never redeploys the site.

Whole-site promotions (`scripts/deploy-desktop-site.py`, `make deploy-site`) refuse a preview
whose timestamp would take the live one backwards, so neither writer undoes the other.

    python tools/library_served.py pull --origin https://smart.meggy.com \\
        --root-sha256 HEX --repository served
    python tools/tuf_repository.py --repository served renew --online-key-env NAME ...
    python tools/tuf_repository.py --repository served --test renew    # channel: test
    python tools/library_served.py publish --origin https://smart.meggy.com \\
        --site smart-home-cec89 --repository served --service-account-env NAME

The Hosting API is called with plain HTTPS (`urllib`), authorised by an OAuth access token minted
from a service-account key (an RS256 JWT signed with `cryptography`, exchanged at Google's token
endpoint), scoped to Firebase Hosting only. No credential is printed.
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from tuf.api.metadata import Metadata, Snapshot, Timestamp

try:
    from scriptlib import tuf_repository as tuf
except ImportError:  # the public repository's tools/, run as a script beside tuf_repository.py
    import tuf_repository as tuf  # type: ignore[no-redef]  # pyright: ignore[reportMissingImports]

ORIGIN = "https://smart.meggy.com"
SITE = "smart-home-cec89"
METADATA = "/library/metadata/"
# The host client's own caps (`online_catalog.py`), so the job never trusts more than a host would.
CAPS = {"root": 512 * 1024, "timestamp": 16 * 1024, "snapshot": 1024 * 1024}
TARGETS_CAP = 4 * 1024 * 1024
MAX_ROOTS = 256
# Versioned files the site may hold past the ones the timestamp names (an interrupted local run's
# leftovers, deployed): the renewal numbers past them, as `tuf_repository` does on disk.
PROBE_AHEAD = 32
HOSTING_API = "https://firebasehosting.googleapis.com/v1beta1/"
HOSTING_UPLOAD = "https://upload-firebasehosting.googleapis.com/upload/"
TOKEN_URI = "https://oauth2.googleapis.com/token"
HOSTING_SCOPE = "https://www.googleapis.com/auth/firebase.hosting"
SERVED_RECORD = "served.json"
_ORIGIN = re.compile(r"https://[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
_VERSION_NAME = re.compile(r"(?:projects/[^/]+/)?sites/([a-z0-9-]+)/versions/([A-Za-z0-9_-]+)")

Fetch = Callable[[str, int], "bytes | None"]


class ServedError(Exception):
    """A refusal with a sentence. It never carries a credential or key material."""


# ---------------------------------------------------------------------------------------------
# Reading what the site serves


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # a redirect is answered as the 3xx it is, and refused


def origin_url(origin: str) -> str:
    """A bare HTTPS origin: no port, path, query or credentials."""
    if not _ORIGIN.fullmatch(origin):
        raise ServedError(f"{origin!r} is not a bare https:// origin.")
    return origin


def https_fetch(url: str, cap: int) -> bytes | None:
    """GET `url` over HTTPS with no redirects, revalidating any cache; None for a 404."""
    if not url.startswith("https://"):
        raise ServedError(f"Only HTTPS is fetched: {url}")
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    opener = urllib.request.build_opener(_NoRedirects)
    try:
        with opener.open(request, timeout=20) as response:
            data = response.read(cap + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise ServedError(f"{url} answered {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise ServedError(f"{url} could not be fetched ({error}).") from error
    if len(data) > cap:
        raise ServedError(f"{url} is larger than {cap:,} bytes.")
    return data


@dataclass(frozen=True)
class Served:
    """What the site serves, verified: the chain `tuf_repository.load` accepts, and the bytes."""

    state: tuf.State
    files: dict[str, bytes]
    probed: dict[str, bytes]

    @property
    def timestamp(self) -> bytes:
        return self.files["timestamp.json"]

    @property
    def versions(self) -> int:
        """The highest snapshot or timestamp version the site serves or holds."""
        assert self.state.timestamp is not None and self.state.snapshot is not None
        held = [
            int(name.split(".", 1)[0]) for name in self.probed if name.endswith(".snapshot.json")
        ]
        return max(self.state.timestamp.signed.version, self.state.snapshot.signed.version, *held)


def _version_of(data: bytes, name: str, kind: type) -> int:
    try:
        metadata = Metadata.from_bytes(data)
    except Exception as error:  # the deserializer raises several types
        raise ServedError(f"The served {name} is not TUF metadata.") from error
    if not isinstance(metadata.signed, kind):
        raise ServedError(f"The served {name} holds the wrong role.")
    return metadata.signed.version


def pull(
    origin: str,
    destination: Path,
    *,
    trusted_root: bytes | None = None,
    root_sha256: str | None = None,
    fetch: Fetch = https_fetch,
) -> Served | None:
    """Download the served metadata into `destination/metadata/` and verify it with tuf's public
    metadata API from the pinned root: `trusted_root`'s exact bytes, or the `root_sha256` of
    `1.root.json`. Returns None when the site serves no library yet. Expiry is not enforced, so a
    lapsed site can be renewed; signatures, thresholds, the root chain and every link are."""
    if (trusted_root is None) == (root_sha256 is None):
        raise ServedError("Pin the root: give its bytes or its SHA-256, exactly one.")
    base = origin_url(origin) + METADATA
    first = fetch(base + "1.root.json", CAPS["root"])
    if first is None:
        if fetch(base + "timestamp.json", CAPS["timestamp"]) is not None:
            raise ServedError(f"{origin} serves a timestamp but no 1.root.json.")
        return None
    if trusted_root is not None and first != trusted_root:
        raise ServedError(f"{origin} serves another 1.root.json than the pinned root.")
    if root_sha256 is not None and hashlib.sha256(first).hexdigest() != root_sha256.lower():
        raise ServedError(f"{origin}'s 1.root.json does not have the pinned SHA-256.")
    files = {"1.root.json": first}
    for version in range(2, MAX_ROOTS + 1):
        data = fetch(base + f"{version}.root.json", CAPS["root"])
        if data is None:
            break
        files[f"{version}.root.json"] = data
    else:
        raise ServedError(f"{origin} serves more than {MAX_ROOTS} roots.")
    timestamp = fetch(base + "timestamp.json", CAPS["timestamp"])
    if timestamp is None:
        raise ServedError(f"{origin} serves roots but no timestamp.json.")
    files["timestamp.json"] = timestamp
    snapshot_version = _snapshot_version(timestamp)
    snapshot = _required(fetch, base, f"{snapshot_version}.snapshot.json", CAPS["snapshot"])
    files[f"{snapshot_version}.snapshot.json"] = snapshot
    try:
        signed = Metadata.from_bytes(snapshot).signed
        if not isinstance(signed, Snapshot):
            raise TypeError(signed.type)
        targets_version = signed.meta["targets.json"].version
    except Exception as error:  # the deserializer raises several types
        raise ServedError("The served snapshot is not TUF metadata naming a targets.") from error
    files[f"{targets_version}.targets.json"] = _required(
        fetch, base, f"{targets_version}.targets.json", TARGETS_CAP
    )
    probed = {}
    for version in range(snapshot_version + 1, snapshot_version + 1 + PROBE_AHEAD):
        data = fetch(base + f"{version}.snapshot.json", CAPS["snapshot"])
        if data is None:
            break
        probed[f"{version}.snapshot.json"] = data
    metadata = destination / "metadata"
    if metadata.exists() and any(metadata.iterdir()):
        raise ServedError(f"{metadata} is not empty; pull into a new directory.")
    metadata.mkdir(parents=True, exist_ok=True)
    for name, data in {**files, **probed}.items():
        (metadata / name).write_bytes(data)
    try:
        state = tuf.load(destination)
    except tuf.RepositoryError as error:
        raise ServedError(f"The metadata {origin} serves does not verify: {error}") from error
    if state.pending is not None:
        raise ServedError(f"{origin} serves a root its other metadata does not satisfy.")
    record = {
        "origin": origin,
        "timestamp_sha256": hashlib.sha256(timestamp).hexdigest(),
        "timestamp_version": _version_of(timestamp, "timestamp.json", Timestamp),
    }
    (destination / SERVED_RECORD).write_text(json.dumps(record, indent=2) + "\n")
    return Served(state, files, probed)


def _snapshot_version(timestamp: bytes) -> int:
    try:
        metadata = Metadata.from_bytes(timestamp)
    except Exception as error:
        raise ServedError("The served timestamp.json is not TUF metadata.") from error
    if not isinstance(metadata.signed, Timestamp):
        raise ServedError("The served timestamp.json holds the wrong role.")
    return metadata.signed.snapshot_meta.version


def _required(fetch: Fetch, base: str, name: str, cap: int) -> bytes:
    data = fetch(base + name, cap)
    if data is None:
        raise ServedError(f"The site's timestamp chain names {name}, which it does not serve.")
    return data


def consistent_with(repository: Path, served: Served) -> int:
    """For a release: the served chain belongs to this repository -- the same channel, every
    served root byte for byte one of ours (no root this repository lacks), its targets one of
    ours, and any served snapshot we also hold the same bytes. Returns the version the release
    must number past."""
    local = tuf.load(repository)
    if local.channel != served.state.channel:
        raise ServedError("The site serves another channel's repository than this one.")
    metadata = repository / "metadata"
    for name, data in {**served.files, **served.probed}.items():
        path = metadata / name
        if name == "timestamp.json":
            continue
        if name.endswith((".root.json", ".targets.json")):
            if not path.is_file() or path.read_bytes() != data:
                raise ServedError(
                    f"The site serves a {name} this repository does not hold: restore "
                    "library/online from the commit that was deployed before signing."
                )
        elif path.is_file() and path.read_bytes() != data:
            raise ServedError(
                f"The site serves another {name} than this repository's (a release signed after "
                "a renewal it did not pull): restore library/online from the deployed commit."
            )
    local_timestamp = metadata / "timestamp.json"
    served_version = _version_of(served.timestamp, "timestamp.json", Timestamp)
    if local_timestamp.is_file():
        local_version = _version_of(local_timestamp.read_bytes(), "timestamp.json", Timestamp)
        if local_version == served_version and local_timestamp.read_bytes() != served.timestamp:
            raise ServedError(
                f"The site serves another timestamp v{served_version} than this repository's."
            )
    return served.versions


# ---------------------------------------------------------------------------------------------
# Firebase Hosting, through its REST API


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def service_account_token(
    account: dict[str, Any],
    *,
    token_uri: str = TOKEN_URI,
    now: float | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> str:
    """An OAuth access token for `account` (a service-account key file's JSON), scoped to Firebase
    Hosting: a JWT signed RS256 with the account's key, exchanged at `token_uri` -- always
    Google's, never one the key file names."""
    try:
        if account["type"] != "service_account":
            raise ValueError
        email = str(account["client_email"])
        key = serialization.load_pem_private_key(account["private_key"].encode(), password=None)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ServedError("The service account is not a readable key file.") from error
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ServedError("The service account's key is not an RSA key.")
    issued = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    if account.get("private_key_id"):
        header["kid"] = str(account["private_key_id"])
    claims = {
        "iss": email,
        "scope": HOSTING_SCOPE,
        "aud": token_uri,
        "iat": issued,
        "exp": issued + 3600,
    }
    unsigned = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
    signature = key.sign(unsigned.encode(), padding.PKCS1v15(), hashes.SHA256())
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": f"{unsigned}.{_b64(signature)}",
        }
    ).encode()
    request = urllib.request.Request(
        token_uri, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with (opener or urllib.request.build_opener(_NoRedirects)).open(
            request, timeout=30
        ) as response:
            answer = json.loads(response.read(64 * 1024))
        token = answer["access_token"]
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        raise ServedError("The service account could not get an access token.") from error
    if not isinstance(token, str) or not token:
        raise ServedError("The service account could not get an access token.")
    return token


class Hosting:
    """The few Firebase Hosting REST calls a renewal needs. The access token is sent only to the
    API base and to upload URLs under the upload base."""

    def __init__(
        self,
        site: str,
        token: str,
        *,
        api: str = HOSTING_API,
        upload: str = HOSTING_UPLOAD,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not re.fullmatch(r"[a-z0-9-]{1,63}", site):
            raise ServedError(f"{site!r} is not a Hosting site id.")
        self.site, self.token, self.api, self.upload_base, self.sleep = (
            site,
            token,
            api,
            upload,
            sleep,
        )
        self.opener = urllib.request.build_opener(_NoRedirects)

    def call(
        self,
        method: str,
        url: str,
        body: bytes | dict | None = None,
        content_type: str = "application/json",
    ) -> dict:
        if not url.startswith((self.api, self.upload_base)):
            raise ServedError("Refusing to send the Hosting token to another address.")
        data = json.dumps(body).encode() if isinstance(body, dict) else body
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": content_type},
        )
        try:
            with self.opener.open(request, timeout=60) as response:
                raw = response.read(1024 * 1024)
        except urllib.error.HTTPError as error:
            raise ServedError(
                f"Firebase Hosting answered {error.code} to {method} {_redact(url)}."
            ) from error
        except (urllib.error.URLError, OSError) as error:
            raise ServedError(f"Firebase Hosting could not be reached ({error}).") from error
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError as error:
            raise ServedError(
                f"Firebase Hosting sent no JSON to {method} {_redact(url)}."
            ) from error

    def live_version(self) -> str:
        channel = self.call("GET", f"{self.api}sites/{self.site}/channels/live")
        name = (channel.get("release") or {}).get("version", {}).get("name", "")
        return self._version(name)

    def _version(self, name: str) -> str:
        match = _VERSION_NAME.fullmatch(name or "")
        if not match or match[1] != self.site:
            raise ServedError("Firebase Hosting did not name a version of this site.")
        return f"sites/{self.site}/versions/{match[2]}"

    def clone(self, source: str, *, without: list[str]) -> str:
        """A new, unfinalized version holding the source version's files and configuration (its
        headers among them) except the paths in `without`."""
        body = {
            "sourceVersion": source,
            "finalize": False,
            "exclude": {"regexes": [f"^{re.escape(path)}$" for path in without]},
        }
        operation = self.call("POST", f"{self.api}sites/{self.site}/versions:clone", body)
        for _ in range(120):
            if operation.get("done"):
                break
            self.sleep(2)
            operation = self.call("GET", f"{self.api}{operation.get('name', '')}")
        else:
            raise ServedError("Firebase Hosting did not finish cloning the live version.")
        if operation.get("error"):
            raise ServedError("Firebase Hosting refused to clone the live version.")
        return self._version((operation.get("response") or {}).get("name", ""))

    def add_files(self, version: str, files: dict[str, bytes]) -> None:
        """populateFiles, then upload the gzipped bytes of every file it asks for."""
        compressed = {path: gzip.compress(data, mtime=0) for path, data in files.items()}
        digests = {path: hashlib.sha256(data).hexdigest() for path, data in compressed.items()}
        answer = self.call("POST", f"{self.api}{version}:populateFiles", {"files": digests})
        required = set(answer.get("uploadRequiredHashes") or [])
        upload_url = answer.get("uploadUrl", "")
        if required - set(digests.values()):
            raise ServedError("Firebase Hosting asked for a file this renewal did not add.")
        if required and not upload_url.startswith(self.upload_base):
            raise ServedError("Firebase Hosting named an unexpected upload address.")
        for path, digest in digests.items():
            if digest in required:
                self.call(
                    "POST", f"{upload_url}/{digest}", compressed[path], "application/octet-stream"
                )

    def finalize(self, version: str) -> None:
        answer = self.call(
            "PATCH", f"{self.api}{version}?updateMask=status", {"status": "FINALIZED"}
        )
        if answer.get("status") not in (None, "FINALIZED"):
            raise ServedError("Firebase Hosting did not finalize the new version.")

    def release(self, version: str, message: str) -> None:
        query = urllib.parse.urlencode({"versionName": version})
        self.call(
            "POST",
            f"{self.api}sites/{self.site}/channels/live/releases?{query}",
            {"message": message},
        )

    def recent_releases(self) -> list[str]:
        """The live channel's last two released versions, newest first."""
        answer = self.call("GET", f"{self.api}sites/{self.site}/channels/live/releases?pageSize=2")
        releases = answer.get("releases") or []
        return [self._version((item.get("version") or {}).get("name", "")) for item in releases]


def _redact(url: str) -> str:
    return url.split("?", 1)[0]


def _unchanged_since_pull(fetch: Fetch, base: str, record: dict) -> None:
    live = fetch(base + "timestamp.json", CAPS["timestamp"])
    if live is None or hashlib.sha256(live).hexdigest() != record.get("timestamp_sha256"):
        raise ServedError("The site's timestamp changed since the pull; the next run starts again.")


def publish(
    repository: Path,
    hosting: Hosting,
    *,
    origin: str,
    fetch: Fetch = https_fetch,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Put the renewed snapshot and timestamp on the live site, and nothing else. Refuses when
    the site changed since the pull, when it already serves that snapshot, or when a deploy lands
    while the new version is being made; then checks the site serves the new timestamp."""
    state = tuf.load(repository)
    # The live site takes a production repository, and the public test key's (`channel: test`)
    # until the real launch; never a dev one (`tuf_repository.LIVE_CHANNELS`).
    if state.channel not in tuf.LIVE_CHANNELS:
        raise ServedError("Dev-signed metadata never goes to the live site.")
    if state.timestamp is None or state.snapshot is None:
        raise ServedError(f"{repository} has nothing to publish.")
    try:
        record = json.loads((repository / SERVED_RECORD).read_text())
    except (OSError, ValueError) as error:
        raise ServedError(f"{repository} was not made by pull.") from error
    base = origin_url(origin) + METADATA
    snapshot_name = f"{state.snapshot.signed.version}.snapshot.json"
    metadata = repository / "metadata"
    new = {
        METADATA + snapshot_name: (metadata / snapshot_name).read_bytes(),
        METADATA + "timestamp.json": (metadata / "timestamp.json").read_bytes(),
    }
    if state.timestamp.signed.version <= int(record.get("timestamp_version", 0)):
        raise ServedError("Nothing was renewed since the pull.")
    # The live version is read before the served timestamp is compared with the pull, so a
    # deploy landing at any moment after this read is caught by one of the checks below, and a
    # release deployed before it is seen as a changed timestamp -- never cloned and rolled back.
    before = hosting.live_version()
    _unchanged_since_pull(fetch, base, record)
    if fetch(base + snapshot_name, CAPS["snapshot"]) is not None:
        raise ServedError(f"The site already serves {snapshot_name}; versions only move forward.")
    version = hosting.clone(before, without=[METADATA + "timestamp.json"])
    hosting.add_files(version, new)
    hosting.finalize(version)
    if hosting.live_version() != before:
        raise ServedError("The site was deployed while the renewal ran; the next run starts again.")
    _unchanged_since_pull(fetch, base, record)
    hosting.release(
        version,
        f"Renew library snapshot v{state.snapshot.signed.version} and timestamp "
        f"v{state.timestamp.signed.version}",
    )
    # The one window left: a deploy released between the recheck above and this release. Ours
    # must directly follow the version it was cloned from; otherwise that deploy is put back.
    recent = hosting.recent_releases()
    if recent[:1] == [version] and recent[1:2] != [before]:
        if len(recent) > 1:
            hosting.release(recent[1], "Restore the deploy a library renewal overtook")
        raise ServedError(
            "A deploy landed just before the renewal's release; it was restored and the next run "
            "starts again."
        )
    wanted = new[METADATA + "timestamp.json"]
    for attempt in range(6):
        if fetch(base + "timestamp.json", CAPS["timestamp"]) == wanted:
            return (
                f"Published {snapshot_name} and timestamp v{state.timestamp.signed.version} "
                f"as {version} (cloned from {before})."
            )
        sleep(5 * (attempt + 1))
    raise ServedError(f"{origin} does not serve the new timestamp after the release.")


# ---------------------------------------------------------------------------------------------
# Command line


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = result.add_subparsers(dest="command", required=True)
    command = commands.add_parser("pull", help="download and verify the served metadata")
    command.add_argument("--origin", default=ORIGIN)
    command.add_argument("--repository", type=Path, required=True, help="a new directory")
    command.add_argument("--root-sha256", required=True, help="SHA-256 of the pinned 1.root.json")
    command = commands.add_parser("publish", help="put the renewed files on the live site")
    command.add_argument("--origin", default=ORIGIN)
    command.add_argument("--site", default=SITE)
    command.add_argument("--repository", type=Path, required=True)
    command.add_argument(
        "--service-account-env",
        metavar="NAME",
        required=True,
        help="environment variable holding the service account's JSON key",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "pull":
            if not re.fullmatch(r"[0-9a-fA-F]{64}", args.root_sha256 or ""):
                raise ServedError("--root-sha256 must be the 64-hex SHA-256 of 1.root.json.")
            served = pull(args.origin, args.repository, root_sha256=args.root_sha256)
            if served is None:
                raise ServedError(f"{args.origin} serves no online library.")
            state = served.state
            assert state.timestamp is not None and state.snapshot is not None
            print(
                f"Verified {args.origin}: root v{state.root.signed.version}, snapshot "
                f"v{state.snapshot.signed.version}, timestamp v{state.timestamp.signed.version}."
            )
        else:
            raw = os.environ.get(args.service_account_env, "")
            try:
                account = json.loads(raw)
            except ValueError as error:
                raise ServedError(
                    f"The environment variable {args.service_account_env} holds no key file."
                ) from error
            hosting = Hosting(args.site, service_account_token(account))
            print(publish(args.repository, hosting, origin=args.origin))
    except (ServedError, tuf.RepositoryError) as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
