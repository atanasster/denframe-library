#!/usr/bin/env python3
"""The denframe-asset-review sandbox runner: the only way the review touches a submission (D23).

Every command that reads submission bytes runs `scripts/container/entry.py` in a container from
the pinned release image (`format/release-environment.json`), with no network, a read-only root
filesystem, a small no-exec tmpfs, a non-root user, no capabilities, no-new-privileges and pid,
memory, CPU, file-size and wall-clock limits. The only mounts are read-only copies staged in a
fresh temporary directory: the hash-locked dependencies, the pinned `denframe_format` source, the
review scripts, the public registry and catalog, and the submission. The private repository,
the home directory, credential stores, agent sockets, the Docker socket and keys are never
mounted. Output comes back on stdout and this runner writes the files.

Host-side commands that use the network never see a submission's contents: `prepare` installs
the locked dependencies (no submission staged), `intake --issue` fetches an issue's attachment
as opaque bytes, and `intake --pr` fetches the tarball of exactly a pull request's head commit,
also as opaque bytes, both with fixed, read-only GitHub calls. `build --intake` then takes the
changed asset sources out of that tarball and builds them, both in the sandbox, into the
archives `review` reads.

Every command first checks where it runs (`policy.checkout_problems`): only in a clone of the
public atanasster/denframe-library repository with no keys in it -- never in the private host
repository. Run it from that clone's root as `python3 .claude/skills/denframe-asset-review/...`.

    sandbox.py [--log FILE] COMMAND ...          (--log appends one line per sandbox run)
    sandbox.py prepare
    sandbox.py probe [--out FILE]
    sandbox.py {validate,inspect,unpack,rebuild} ARCHIVE
    sandbox.py build SOURCE_DIR
    sandbox.py build --intake DIR                    (a pull request's sources -> DIR/built/<slug>)
    sandbox.py intake --issue N --out DIR            (read-only GitHub; archive kept as bytes)
    sandbox.py intake --pr N --out DIR               (read-only GitHub; tarball kept as bytes)
    sandbox.py intake-local --archive F --login L --account N [--issue-text F] --out DIR
    sandbox.py review --intake DIR --out DIR [--notes FILE] [--registry FILE]
    sandbox.py conformance --out DIR
    sandbox.py calibrate [--extra-looks FILE] [--out FILE]
"""

from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
# The skill lives in the public repository, so its checkout root is the library source.
LIBRARY = SKILL.parents[2]
sys.path.insert(0, str(SCRIPTS))
import policy  # noqa: E402

MAX_SUBMISSION = 128 * 1024 * 1024
MAX_OUTPUT = 32 * 1024 * 1024
# `build --intake` returns its archives base64-encoded: room for the largest submission.
OUTPUT_LIMITS = {"build": MAX_SUBMISSION * 3 // 2}
TIMEOUT_SECONDS = {"conformance": 900, "calibrate": 120, "probe": 120}
DEFAULT_TIMEOUT = 300
LIMITS = {
    "memory": "512m",
    "cpus": "1",
    "pids": "64",
    "tmpfs": "64m",
    "nofile": "256",
    "fsize": str(64 * 1024 * 1024),
}
# The commands the container accepts (entry.py keeps the same list). Nothing else runs there.
CONTAINER_COMMANDS = (
    "validate",
    "inspect",
    "unpack",
    "build",
    "rebuild",
    "review",
    "conformance",
    "calibrate",
    "probe",
)
# Attachments GitHub serves for issue uploads; nothing else is fetched at intake.
ATTACHMENT = re.compile(
    r"https://github\.com/user-attachments/files/\d+/[A-Za-z0-9._-]+\.(?:zip|denframepack)"
)
ATTACHMENT_HOSTS = frozenset({"github.com", "objects.githubusercontent.com"})
PUBLIC_REPOSITORY = "atanasster/denframe-library"
# The pull-request route (`intake --pr`): what GitHub's metadata must look like, and the caps on
# the head tarball and on the sources taken from it.
GITHUB_NUMBER = re.compile(r"[1-9][0-9]{0,8}")
HEAD_SHA = re.compile(r"[0-9a-f]{40}")
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
DEFINITION_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,122}\.json")
TARBALL = "head.tar.gz"
MAX_TARBALL = MAX_SUBMISSION
MAX_CHANGED_FILES = 3000
MAX_TEXT = 1024 * 1024


def release_environment(library: Path = LIBRARY) -> dict:
    """The pinned image and platform the public toolchain releases from."""
    return json.loads((library / "format/release-environment.json").read_text())


def cache_root() -> Path:
    """Per-user: a shared /tmp would let another local user plant the toolchain."""
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "denframe-asset-review"


def trusted(path: Path) -> Path:
    """Refuse a cache directory this user does not own, or that others may write."""
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        raise SystemExit(f"Refusing {path}: not owned by this user, or group/world-writable")
    return path


def toolchain_key(library: Path = LIBRARY) -> str:
    environment = release_environment(library)
    digest = hashlib.sha256()
    for part in (environment["image"], environment["platform"]):
        digest.update(part.encode() + b"\0")
    digest.update((library / "format/requirements.lock").read_bytes())
    return digest.hexdigest()[:16]


def site_directory(library: Path = LIBRARY) -> Path:
    return cache_root() / f"toolchain-{toolchain_key(library)}" / "site"


def _open_up(root: Path) -> None:
    """World-readable staging, so the container's unprivileged user can read its mounts."""
    root.chmod(0o755)
    for path in root.rglob("*"):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)


def _copy_tree(source: Path, target: Path, *, skip: tuple[str, ...] = ()) -> None:
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info", "build", *skip)
    shutil.copytree(source, target, ignore=ignore, symlinks=False)


def _copy_file(source: Path, target: Path, limit: int = MAX_SUBMISSION) -> None:
    """A staged copy of one regular file, size-capped; symlinks and specials are refused."""
    if source.is_symlink() or not source.is_file():
        raise SystemExit(f"Not a regular file: {source}")
    with source.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise SystemExit(f"Over the {limit} byte limit: {source}")
    target.write_bytes(data)


def stage(
    *,
    library: Path = LIBRARY,
    files: dict[str, Path] | None = None,
    documents: dict[str, object] | None = None,
    trees: dict[str, Path] | None = None,
    reference: dict[str, Path] | None = None,
) -> Path:
    """A fresh staging directory holding only what one container run may read."""
    root = Path(tempfile.mkdtemp(prefix="stage-", dir=_ensure(cache_root() / "stages")))
    format_dir = root / "toolchain/format"
    format_dir.parent.mkdir(parents=True)
    format_dir.mkdir()
    _copy_tree(library / "format/src", format_dir / "src")
    _copy_tree(library / "format/tools", format_dir / "tools")
    for name in ("release-environment.json", "requirements.lock", "pyproject.toml"):
        shutil.copyfile(library / "format" / name, format_dir / name)
    review = root / "toolchain/review"
    review.mkdir()
    for script in sorted((SCRIPTS / "container").glob("*.py")):
        shutil.copyfile(script, review / script.name)
    # The public tools' catalog-entry builder, so the pull-request route builds a definition
    # exactly as `tools/intake.py` and `tools/rebuild.py` do.
    shutil.copyfile(library / "tools/library_sources.py", review / "library_sources.py")
    ref = root / "reference"
    (ref / "definitions").mkdir(parents=True)
    (ref / "packs").mkdir()
    shutil.copyfile(library / "publishers.json", ref / "publishers.json")
    shutil.copyfile(library / "definitions/catalog.json", ref / "definitions/catalog.json")
    for source in sorted((library / "packs").glob("*/source.json")):
        (ref / "packs" / source.parent.name).mkdir()
        _copy_file(source, ref / "packs" / source.parent.name / "source.json", 1024 * 1024)
    for name, path in (reference or {}).items():
        _copy_file(path, ref / name, 1024 * 1024)
    submission = root / "submission"
    submission.mkdir()
    for name, path in (files or {}).items():
        _copy_file(path, submission / name)
    for name, value in (documents or {}).items():
        (submission / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    for name, path in (trees or {}).items():
        _copy_regular_tree(path, submission / name)
    _open_up(root)
    return root


def _copy_regular_tree(source: Path, target: Path) -> None:
    total = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise SystemExit(f"Symlinks are not staged: {relative}")
        if path.is_dir():
            (target / relative).mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            total += path.stat().st_size
            if total > MAX_SUBMISSION:
                raise SystemExit("The source folder is over 128 MiB")
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            _copy_file(path, target / relative)
    target.mkdir(parents=True, exist_ok=True)


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def docker_command(
    staged: Path,
    site: Path,
    command: str,
    arguments: list[str],
    *,
    name: str,
    library: Path = LIBRARY,
) -> list[str]:
    """The exact `docker run` for one sandboxed command. Tests hold every flag in place."""
    if command not in CONTAINER_COMMANDS:
        raise ValueError(f"Not an allowed sandbox command: {command}")
    environment = release_environment(library)
    mounts = [
        (site, "/toolchain/site"),
        (staged / "toolchain/format", "/toolchain/format"),
        (staged / "toolchain/review", "/toolchain/review"),
        (staged / "reference", "/reference"),
        (staged / "submission", "/submission"),
    ]
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--platform",
        environment["platform"],
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        f"/tmp:rw,noexec,nosuid,nodev,size={LIMITS['tmpfs']},mode=1777",  # noqa: S108
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        LIMITS["pids"],
        "--memory",
        LIMITS["memory"],
        "--memory-swap",
        LIMITS["memory"],
        "--cpus",
        LIMITS["cpus"],
        "--ulimit",
        f"nofile={LIMITS['nofile']}:{LIMITS['nofile']}",
        "--ulimit",
        f"fsize={LIMITS['fsize']}:{LIMITS['fsize']}",
        "--ulimit",
        "core=0:0",
        "--ipc",
        "none",
        "--hostname",
        "review",
        "--workdir",
        "/tmp",  # noqa: S108 - the container's own tmpfs
        "--env",
        "HOME=/tmp",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "PYTHONHASHSEED=0",
        "--env",
        "GPG_KEY=",
        *(
            item
            for source, target in mounts
            for item in (
                "--mount",
                f"type=bind,source={source},target={target},readonly",
            )
        ),
        "--entrypoint",
        "python",
        environment["image"],
        "-I",
        "-B",
        "/toolchain/review/entry.py",
        command,
        *arguments,
    ]


def _docker_environment(canary: str | None = None) -> dict[str, str]:
    """What the docker CLI itself sees: enough to find the daemon, nothing else."""
    keep = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG", "TMPDIR")
    result = {key: os.environ[key] for key in keep if key in os.environ}
    if canary:
        # A value the probe must never see: proves the host environment stays outside.
        result["DENFRAME_REVIEW_CANARY"] = canary
    return result


AUDIT_LOG: list[Path] = []


def audit(entry: dict) -> None:
    """One line per sandbox run, when `--log` names a file: the runner's own record."""
    for log in AUDIT_LOG:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run(
    command: str,
    arguments: list[str] | None = None,
    *,
    library: Path = LIBRARY,
    canary: str | None = None,
    **staging,
) -> tuple[int, str, str]:
    """Stage, run one allow-listed command in the sandbox, clean up; (exit, stdout, stderr)."""
    site = site_directory(library)
    if not (site.parent / "toolchain.json").is_file():
        raise SystemExit("Run `sandbox.py prepare` first: the locked dependencies are not staged")
    for directory in (cache_root(), site.parent, site):
        trusted(directory)
    staged = stage(library=library, **staging)
    name = f"denframe-review-{secrets.token_hex(6)}"
    argv = docker_command(staged, site, command, arguments or [], name=name, library=library)
    started = datetime.datetime.now(datetime.UTC)
    try:
        process = subprocess.run(
            argv,
            capture_output=True,
            timeout=TIMEOUT_SECONDS.get(command, DEFAULT_TIMEOUT),
            env=_docker_environment(canary),
            check=False,
        )
        code, out, err = process.returncode, process.stdout, process.stderr
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", name], capture_output=True, check=False)
        code, out, err = 124, b"", b"The sandbox run hit its time limit and was killed"
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    audit(
        {
            "at": started.isoformat(timespec="seconds"),
            "command": command,
            "arguments": arguments or [],
            "exit": code,
            "image": release_environment(library)["image"],
            "network": "none",
        }
    )
    limit = OUTPUT_LIMITS.get(command, MAX_OUTPUT)
    return code, out[:limit].decode("utf-8", "replace"), err[:65536].decode("utf-8", "replace")


def environment_facts(library: Path = LIBRARY) -> dict:
    environment = release_environment(library)
    return {
        "image": environment["image"],
        "platform": environment["platform"],
        "network": "none (docker --network none)",
        "limits": (
            f"{LIMITS['memory']} memory, {LIMITS['cpus']} CPU, {LIMITS['pids']} pids, "
            f"{LIMITS['tmpfs']} no-exec tmpfs, read-only root, uid 65534, no capabilities, "
            "no-new-privileges"
        ),
    }


# -- Host-side commands ------------------------------------------------------------------------


def prepare(library: Path = LIBRARY) -> Path:
    """Install the hash-locked dependencies once, from the pinned image, with no submission."""
    site = site_directory(library)
    if (site.parent / "toolchain.json").is_file():
        for directory in (cache_root(), site.parent, site):
            trusted(directory)
        return site
    environment = release_environment(library)
    trusted(_ensure(cache_root()))
    cache_root().chmod(0o755)
    work = Path(tempfile.mkdtemp(prefix="prepare-", dir=cache_root()))
    lock = work / "lock"
    lock.mkdir()
    shutil.copyfile(library / "format/requirements.lock", lock / "requirements.lock")
    partial = work / "site"
    partial.mkdir()
    _open_up(work)
    partial.chmod(0o777)
    subprocess.run(
        ["docker", "pull", "--platform", environment["platform"], environment["image"]],
        check=True,
        env=_docker_environment(),
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            environment["platform"],
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--env",
            "HOME=/tmp",
            "--mount",
            f"type=bind,source={lock},target=/lock,readonly",
            "--mount",
            f"type=bind,source={partial},target=/out",
            environment["image"],
            "python",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-cache-dir",
            "--require-hashes",
            "--only-binary=:all:",
            "--target",
            "/out",
            "-r",
            "/lock/requirements.lock",
        ],
        check=True,
        env=_docker_environment(),
    )
    site.parent.mkdir(parents=True, exist_ok=True)
    if site.exists():
        shutil.rmtree(site)
    partial.rename(site)
    _open_up(site)
    (site.parent / "toolchain.json").write_text(
        json.dumps({"image": environment["image"], "key": toolchain_key(library)}) + "\n"
    )
    shutil.rmtree(work, ignore_errors=True)
    return site


def probe(out: Path | None, library: Path = LIBRARY) -> int:
    canary = secrets.token_hex(16)
    settings = {
        "host_home": str(Path.home()),
        "repo": str(library),
        "canary": canary,
        "connect": connect_targets(),
    }
    code, stdout, stderr = run(
        "probe", library=library, canary=canary, documents={"probe.json": settings}
    )
    if code != 0:
        print(stderr, file=sys.stderr)
        return code
    results = json.loads(stdout)
    pinned = release_environment(library)
    lines = [
        f"Sandbox probe, {datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds')}",
        f"Image {pinned['image']} ({pinned['platform']})",
        "Command: "
        + " ".join(
            docker_command(
                Path("<stage>"), Path("<site>"), "probe", [], name="<name>", library=library
            )
        ),
        "",
    ]
    for row in results:
        mark = "ok  " if row["ok"] else "FAIL"
        lines.append(f"{mark} [{row['expect']}] {row['probe']}: {row['detail']}")
    failed = [row for row in results if not row["ok"]]
    lines += ["", f"{len(results) - len(failed)}/{len(results)} expectations held."]
    text = "\n".join(lines) + "\n"
    if out:
        # The recorded copy names no local paths: the checkout and the home directory.
        recorded = text.replace(str(library.resolve()), "<checkout>").replace(str(Path.home()), "~")
        out.write_text(recorded, encoding="utf-8")
    print(text)
    return 1 if failed else 0


def connect_targets() -> list[dict]:
    """Where the probe tries to connect: public hosts, and Docker's own bridge gateway (a
    Docker default, read from `docker network inspect`, never a household address)."""
    targets = [
        {"label": "a public DNS resolver (1.1.1.1:443)", "host": "1.1.1.1", "port": 443},
        {"label": "GitHub (140.82.112.3:443)", "host": "140.82.112.3", "port": 443},
    ]
    gateway = subprocess.run(
        ["docker", "network", "inspect", "bridge", "--format",
         "{{range .IPAM.Config}}{{.Gateway}} {{end}}"],
        capture_output=True, text=True, check=False, env=_docker_environment(),
    ).stdout.split()  # fmt: skip
    targets += [
        {"label": f"the Docker bridge gateway, daemon port {port}", "host": host, "port": port}
        for host in gateway[:1]
        for port in (2375, 22)
    ]
    return targets


def intake_issue(number: int, out: Path) -> None:
    """Fetch one submission issue: fixed read-only GitHub calls; the archive is kept as bytes."""
    out.mkdir(parents=True, exist_ok=False)
    view = subprocess.run(
        ["gh", "issue", "view", str(number), "--repo", PUBLIC_REPOSITORY, "--json",
         "number,title,body,author,url"],
        capture_output=True,
        check=True,
        text=True,
    )  # fmt: skip
    issue = json.loads(view.stdout)
    login = issue["author"]["login"]
    user = subprocess.run(
        ["gh", "api", f"users/{login}", "--jq", ".id"], capture_output=True, check=True, text=True
    )
    links = ATTACHMENT.findall(issue["body"] or "")
    if len(links) != 1:
        raise SystemExit(f"Expected one attached archive, found {len(links)}; fetch it by hand")
    archive = out / ("submission" + Path(urllib.parse.urlparse(links[0]).path).suffix)
    _download(links[0], archive)
    (out / "issue.md").write_text(issue["body"] or "", encoding="utf-8")
    _write_intake(out, archive, login, int(user.stdout.strip()), "issue", number, issue["url"])


class AttachmentRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to GitHub's attachment hosts, and only over HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlparse(newurl)
        if target.scheme != "https" or target.hostname not in ATTACHMENT_HOSTS:
            raise SystemExit(f"Refusing a redirect off GitHub's HTTPS attachments: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, target: Path) -> None:
    opener = urllib.request.build_opener(AttachmentRedirects)
    with opener.open(url, timeout=60) as response:
        data = response.read(MAX_SUBMISSION + 1)
    if len(data) > MAX_SUBMISSION:
        raise SystemExit("The attachment is over 128 MiB")
    target.write_bytes(data)


def _write_intake(
    out: Path,
    archive: Path,
    login: str,
    account: int,
    source: str,
    number: int | None = None,
    url: str | None = None,
    extra: dict | None = None,
) -> dict:
    data = archive.read_bytes()
    intake = {
        "source": source,
        "number": number,
        "url": url,
        "submitter": {"login": login, "id": account},
        "archive": archive.name,
        "archive_sha256": hashlib.sha256(data).hexdigest(),
        "archive_size": len(data),
        "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    (out / "intake.json").write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
    return intake


def intake_local(
    archive: Path, login: str, account: int, issue_text: Path | None, out: Path
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    suffix = ".zip" if archive.suffix == ".zip" else ".denframepack"
    target = out / f"submission{suffix}"
    _copy_file(archive, target)
    if issue_text:
        _copy_file(issue_text, out / "issue.md", 1024 * 1024)
    _write_intake(out, target, login, account, "local")


# -- The pull-request route ----------------------------------------------------------------------


def github_number(text: str) -> int:
    """An issue or pull-request number: plain decimal digits, 1 to 999999999."""
    if not isinstance(text, str) or not GITHUB_NUMBER.fullmatch(text):
        raise argparse.ArgumentTypeError(f"not an issue or pull-request number: {text!r}")
    return int(text)


def _gh_read(argv: list[str]) -> str:
    """One fixed, read-only `gh` call; its output is data."""
    return subprocess.run(argv, capture_output=True, check=True, text=True, timeout=120).stdout


def _fetch_to_file(argv: list[str], target: Path, limit: int) -> None:
    """Stream one fixed `gh` call's binary output into `target`, killed past `limit` bytes."""
    total = 0
    with target.open("xb") as handle, subprocess.Popen(argv, stdout=subprocess.PIPE) as process:
        assert process.stdout is not None
        while chunk := process.stdout.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                process.kill()
                raise SystemExit(f"The head tarball is over {limit} bytes")
            handle.write(chunk)
        if process.wait(timeout=300) != 0:
            raise SystemExit("Fetching the head tarball failed")


def _asset_paths(filenames: list[str]) -> tuple[set[str], set[str], int]:
    """From the changed paths: the `definitions/*.json` names, the pack slugs, and a count of
    everything else (never built). Names that are not plain count as everything else."""
    definitions: set[str] = set()
    slugs: set[str] = set()
    other = 0
    for name in filenames:
        parts = name.split("/")
        if len(parts) == 2 and parts[0] == "definitions" and DEFINITION_FILE.fullmatch(parts[1]):
            definitions.add(parts[1])
        elif len(parts) >= 3 and parts[0] == "packs" and SLUG.fullmatch(parts[1]):
            slugs.add(parts[1])
        else:
            other += 1
    return definitions, slugs, other


def intake_pull_request(number: int, out: Path) -> dict:
    """Fetch the tarball of exactly one pull request's head commit, as opaque bytes.

    Fixed, read-only GitHub calls against atanasster/denframe-library only: the pull request's
    metadata (head sha, author login and numeric id, body), its changed file names (which select
    the sources `build --intake` takes), and the tarball of exactly the head sha. The tarball is
    never opened here; the sandbox reads it."""
    github_number(str(number))
    out.mkdir(parents=True, exist_ok=False)
    pull = json.loads(_gh_read(["gh", "api", f"repos/{PUBLIC_REPOSITORY}/pulls/{number}"]))
    if not isinstance(pull, dict) or pull.get("number") != number:
        raise SystemExit("GitHub's pull-request metadata does not name this pull request")
    head = pull.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not HEAD_SHA.fullmatch(sha):
        raise SystemExit("The pull request's head is not a 40-hex commit sha")
    user = pull.get("user")
    login, account = (user.get("login"), user.get("id")) if isinstance(user, dict) else (None, None)
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        raise SystemExit("The pull request's author login is not a GitHub login")
    if type(account) is not int or account <= 0:
        raise SystemExit("The pull request's author has no numeric account id")
    changed = pull.get("changed_files")
    if type(changed) is not int or not 0 < changed <= MAX_CHANGED_FILES:
        raise SystemExit(f"Review a pull request of 1 to {MAX_CHANGED_FILES} changed files")
    listing = _gh_read(
        ["gh", "api", "--paginate", f"repos/{PUBLIC_REPOSITORY}/pulls/{number}/files",
         "--jq", ".[].filename"]
    )  # fmt: skip
    definitions, slugs, other = _asset_paths(listing.splitlines())
    if not definitions and not slugs:
        raise SystemExit("The pull request changes no asset source (definitions/, packs/<slug>/)")
    tarball = out / TARBALL
    _fetch_to_file(["gh", "api", f"repos/{PUBLIC_REPOSITORY}/tarball/{sha}"], tarball, MAX_TARBALL)
    data = tarball.read_bytes()
    tarball.chmod(0o444)
    body = (pull.get("body") or "").encode("utf-8")[:MAX_TEXT].decode("utf-8", "ignore")
    (out / "issue.md").write_text(body, encoding="utf-8")
    intake = {
        "source": "pull-request",
        "number": number,
        "url": f"https://github.com/{PUBLIC_REPOSITORY}/pull/{number}",
        "head_sha": sha,
        "submitter": {"login": login, "id": account},
        "tarball": TARBALL,
        "tarball_sha256": hashlib.sha256(data).hexdigest(),
        "tarball_size": len(data),
        "selection": {"definitions": sorted(definitions), "packs": sorted(slugs)},
        "changed_files": changed,
        "changes_outside_sources": other,
        "fetched_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
    }
    (out / "intake.json").write_text(json.dumps(intake, indent=2) + "\n", encoding="utf-8")
    return intake


def _build_lines(stdout: str) -> dict[str, list]:
    """The sandbox's JSON lines, gathered; a cut-off or foreign line refuses the build."""
    result: dict[str, list] = {"built": [], "failed": [], "skipped": []}
    for line in stdout.splitlines():
        try:
            document = json.loads(line)
        except ValueError as error:
            raise SystemExit("The sandbox build's output was cut off or is not JSON") from error
        if not isinstance(document, dict) or len(document) != 1:
            raise SystemExit("The sandbox build sent an unexpected line")
        ((key, value),) = document.items()
        if key == "refused":
            raise SystemExit(f"The sandbox refused the head tarball: {value}")
        if key not in result:
            raise SystemExit("The sandbox build sent an unexpected line")
        result[key].append(value)
    return result


def build_pull_request(intake_dir: Path, library: Path = LIBRARY) -> list[Path]:
    """Take a pull-request intake's changed sources out of its head tarball and build them, both
    in the sandbox; one intake folder per archive, `DIR/built/<slug>/`, which `review --intake`
    reads like an issue's."""
    intake = json.loads((intake_dir / "intake.json").read_text(encoding="utf-8"))
    if intake.get("source") != "pull-request" or intake.get("tarball") != TARBALL:
        raise SystemExit("`build --intake` takes the folder `intake --pr` wrote")
    tarball = intake_dir / TARBALL
    if hashlib.sha256(tarball.read_bytes()).hexdigest() != intake.get("tarball_sha256"):
        raise SystemExit("The head tarball differs from the one recorded at intake")
    code, stdout, stderr = run(
        "build",
        [TARBALL, "selection.json"],
        library=library,
        files={TARBALL: tarball},
        documents={"selection.json": intake["selection"]},
    )
    result = _build_lines(stdout)
    if code != 0:
        raise SystemExit(f"The sandbox build failed ({code}): {stderr.strip()[-2000:]}")
    built = _ensure(intake_dir / "built")
    written = []
    for asset in result["built"]:
        slug = asset.get("slug")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise SystemExit("The sandbox named a built asset with an invalid slug")
        data = base64.b64decode(asset["archive"], validate=True)
        if len(data) > MAX_SUBMISSION or hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise SystemExit(f"The built archive for {slug} is over the limit or its hash differs")
        folder = built / slug
        if folder.exists():
            raise SystemExit(f"Two built assets, or an earlier build, share the slug {slug}")
        folder.mkdir()
        archive = folder / "submission.denframepack"
        archive.write_bytes(data)
        if (intake_dir / "issue.md").is_file():
            shutil.copyfile(intake_dir / "issue.md", folder / "issue.md")
        _write_intake(
            folder,
            archive,
            intake["submitter"]["login"],
            intake["submitter"]["id"],
            "pull-request",
            intake["number"],
            intake["url"],
            extra={"head_sha": intake["head_sha"], "built_from": asset["from"]},
        )
        written.append(folder)
    for line in result["skipped"]:
        print(f"skipped {line}")
    for failure in result["failed"]:
        print(f"FAILED {failure['source']}: {failure['error']}", file=sys.stderr)
    if result["failed"] or not written:
        raise SystemExit(
            f"{len(written)} built, {len(result['failed'])} failed: every changed source must "
            "build (ask the author to fix it)"
        )
    return written


def review(
    intake_dir: Path,
    out: Path,
    notes: Path | None = None,
    registry: Path | None = None,
    library: Path = LIBRARY,
) -> dict:
    intake = json.loads((intake_dir / "intake.json").read_text())
    if "archive" not in intake:
        raise SystemExit(
            "A pull-request intake holds sources: run `build --intake` and review each "
            "folder it writes under built/"
        )
    archive = intake_dir / intake["archive"]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != intake["archive_sha256"]:
        raise SystemExit("The staged archive differs from the one recorded at intake")
    files = {intake["archive"]: archive}
    if (intake_dir / "issue.md").is_file():
        files["issue.md"] = intake_dir / "issue.md"
    documents: dict[str, object] = {
        "intake.json": intake,
        "environment.json": environment_facts(library),
    }
    if notes:
        documents["notes.json"] = json.loads(notes.read_text())
    code, stdout, stderr = run(
        "review",
        library=library,
        files=files,
        documents=documents,
        reference={"registry.json": registry} if registry else None,
    )
    if code != 0:
        raise SystemExit(f"The sandbox review failed ({code}): {stderr.strip()[-2000:]}")
    result = json.loads(stdout)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(result["report"], encoding="utf-8")
    (out / "record.json").write_text(
        json.dumps(result["record"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "evidence.json").write_text(
        json.dumps(result["evidence"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return result


def conformance(out: Path, library: Path = LIBRARY) -> list[dict]:
    corpus = library / "contracts/format-fixtures/archives"
    intake = {
        "source": "conformance",
        "submitter": {"login": "conformance-fixture", "id": 1},
        "archive": "archives",
    }
    code, stdout, stderr = run(
        "conformance",
        library=library,
        documents={"intake.json": intake, "environment.json": environment_facts(library)},
        trees={"archives": corpus},
    )
    if code != 0:
        raise SystemExit(f"The sandbox conformance run failed ({code}): {stderr.strip()[-2000:]}")
    results = json.loads(stdout)
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "case": row["case"],
            "recommendation": row["evidence"]["recommendation"],
            "layers": row["evidence"]["layers"],
            "findings": [f["code"] for f in row["evidence"]["findings"]],
        }
        for row in results
    ]
    (out / "conformance-results.json").write_text(json.dumps(rows, indent=1) + "\n")
    return rows


def main(argv: list[str] | None = None) -> int:
    # No abbreviations anywhere: the guard admits argv word for word (policy.py `_runner_form`).
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--log", type=Path, help="append one JSON line per sandbox run")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare", allow_abbrev=False)
    probe_parser = commands.add_parser("probe", allow_abbrev=False)
    probe_parser.add_argument("--out", type=Path)
    for name in ("validate", "inspect", "unpack", "rebuild"):
        commands.add_parser(name, allow_abbrev=False).add_argument("archive", type=Path)
    build = commands.add_parser("build", allow_abbrev=False)
    build_from = build.add_mutually_exclusive_group(required=True)
    build_from.add_argument("source", type=Path, nargs="?")
    build_from.add_argument("--intake", type=Path)
    issue = commands.add_parser("intake", allow_abbrev=False)
    route = issue.add_mutually_exclusive_group(required=True)
    route.add_argument("--issue", type=github_number)
    route.add_argument("--pr", type=github_number)
    issue.add_argument("--out", type=Path, required=True)
    local = commands.add_parser("intake-local", allow_abbrev=False)
    local.add_argument("--archive", type=Path, required=True)
    local.add_argument("--login", required=True)
    local.add_argument("--account", type=int, required=True)
    local.add_argument("--issue-text", type=Path)
    local.add_argument("--out", type=Path, required=True)
    review_parser = commands.add_parser("review", allow_abbrev=False)
    review_parser.add_argument("--intake", type=Path, required=True)
    review_parser.add_argument("--out", type=Path, required=True)
    review_parser.add_argument("--notes", type=Path)
    review_parser.add_argument("--registry", type=Path)
    commands.add_parser("conformance", allow_abbrev=False).add_argument(
        "--out", type=Path, required=True
    )
    calibrate = commands.add_parser("calibrate", allow_abbrev=False)
    calibrate.add_argument("--extra-looks", type=Path)
    calibrate.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    problems = policy.checkout_problems(LIBRARY, Path.cwd())
    if problems:
        raise SystemExit(
            "denframe-asset-review runs only from a clean clone of the public "
            "atanasster/denframe-library repository:\n- " + "\n- ".join(problems)
        )
    if args.log:
        AUDIT_LOG.append(args.log)
    if args.command == "prepare":
        print(prepare())
        return 0
    if args.command == "probe":
        return probe(args.out)
    if args.command in ("validate", "inspect", "unpack", "rebuild"):
        name = "submission.denframepack"
        code, out, err = run(args.command, [name], files={name: args.archive})
        print(out, end="")
        print(err, end="", file=sys.stderr)
        return code
    if args.command == "build" and args.intake:
        for folder in build_pull_request(args.intake):
            print(f"built {folder}: review it with `review --intake {folder}`")
        return 0
    if args.command == "build":
        code, out, err = run("build", trees={"source": args.source})
        print(out, end="")
        print(err, end="", file=sys.stderr)
        return code
    if args.command == "intake" and args.pr:
        intake = intake_pull_request(args.pr, args.out)
        print(
            f"head {intake['head_sha']} ({intake['tarball_size']} bytes; "
            f"{len(intake['selection']['definitions'])} definition files and "
            f"{len(intake['selection']['packs'])} packs changed) -> {args.out}"
        )
        return 0
    if args.command == "intake":
        intake_issue(args.issue, args.out)
        return 0
    if args.command == "intake-local":
        intake_local(args.archive, args.login, args.account, args.issue_text, args.out)
        return 0
    if args.command == "review":
        result = review(args.intake, args.out, args.notes, args.registry)
        evidence = result["evidence"]
        print(f"{evidence['release']['id']} {evidence['release']['version']}: "
              f"{evidence['recommendation']} -> {args.out / 'report.md'}")  # fmt: skip
        return 0
    if args.command == "conformance":
        rows = conformance(args.out)
        print(f"Reviewed {len(rows)} conformance archives -> {args.out}")
        return 0
    extra = {"extra-looks.json": args.extra_looks} if args.extra_looks else None
    code, out, err = run("calibrate", reference=extra)
    if args.out and code == 0:
        args.out.write_text(out, encoding="utf-8")
    print(out, end="")
    print(err, end="", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
