"""Denied-access probes, run inside the review sandbox (`sandbox.py probe`).

Each probe tries something a submission must never be able to reach -- the owner's keys, the
private repository, the Docker socket, credential stores, the host's environment, writes
outside the scratch space, and the network -- and records whether it was denied. Two controls
show the probes are live: the scratch space is writable and the trusted toolchain is readable.
"""

# The probes name raw paths on purpose: they are the paths an attacker would try.
# ruff: noqa: S108, PTH108, PTH111, PTH123, PTH208

from __future__ import annotations

import os
import resource
import socket
import subprocess
import threading
import urllib.request
from pathlib import Path

EXPECTED_MOUNTS = {"/toolchain/site", "/toolchain/format", "/toolchain/review", "/reference"}
EXPECTED_MOUNTS |= {"/submission", "/tmp", "/etc/hosts", "/etc/hostname", "/etc/resolv.conf"}


def _read(path: str) -> tuple[bool, str]:
    """(denied, detail) for reading a file or listing a directory."""
    try:
        target = Path(path)
        if target.is_dir():
            return False, f"listed {len(list(target.iterdir()))} entries"
        with target.open("rb") as handle:
            return False, f"read {len(handle.read(64))} bytes"
    except OSError as exc:
        return True, type(exc).__name__


def _write(path: str) -> tuple[bool, str]:
    try:
        with open(path, "xb") as handle:
            handle.write(b"probe")
        os.unlink(path)
        return False, "written"
    except OSError as exc:
        return True, type(exc).__name__


def _connect(host: str, port: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=3):
            return False, "connected"
    except OSError as exc:
        return True, type(exc).__name__


def _status(field: str) -> str:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def _cgroup(name: str) -> str:
    try:
        return Path("/sys/fs/cgroup", name).read_text().strip()
    except OSError:
        return "unreadable"


def probes(host_home: str, repo: str, canary: str, connect: list[dict]) -> list[dict]:
    results: list[dict] = []

    def record(name: str, ok: bool, detail: str, kind: str = "denied") -> None:
        # `ok`: the expectation held -- denied for a probe, allowed for a control.
        results.append({"probe": name, "expect": kind, "ok": ok, "detail": detail})

    # Filesystem: secrets, the repository, sockets and credential stores are not there.
    for path in (
        f"{host_home}/.ssh",
        f"{host_home}/.ssh/id_ed25519",
        "/root/.ssh",
        os.path.expanduser("~/.ssh"),
        repo,
        f"{repo}/.git/config",
        f"{repo}/backend/data",
        f"{repo}/backend/.denframe-runtime",
        "/var/run/docker.sock",
        "/run/docker.sock",
        f"{host_home}/.docker/config.json",
        f"{host_home}/.config/gh/hosts.yml",
        f"{host_home}/.gitconfig",
        f"{host_home}/.gnupg",
        f"{host_home}/Library/Keychains",
        "/Users",
        "/run/host-services/ssh-auth.sock",
        os.environ.get("SSH_AUTH_SOCK") or "/tmp/ssh-agent.sock",
    ):
        denied, detail = _read(path)
        record(f"read {path}", denied, detail)
    # Writes outside the scratch space fail: the root filesystem and every mount are read-only.
    for path in (
        "/probe",
        "/etc/probe",
        "/usr/local/lib/probe",
        "/toolchain/review/probe",
        "/toolchain/site/probe",
        "/reference/probe",
        "/submission/probe",
    ):
        denied, detail = _write(path)
        record(f"write {path}", denied, detail)
    # The scratch space holds data, never programs.
    script = Path("/tmp/probe.sh")
    script.write_text("#!/bin/sh\necho ran\n")
    script.chmod(0o755)
    try:
        subprocess.run([str(script)], check=True, capture_output=True, timeout=5)
        record("execute a file written to /tmp", False, "ran")
    except (OSError, subprocess.SubprocessError) as exc:
        record("execute a file written to /tmp", True, type(exc).__name__)
    finally:
        script.unlink()
    # Environment: nothing from the host process, no secrets.
    environment = dict(os.environ)
    try:
        environment_1 = Path("/proc/1/environ").read_bytes().decode(errors="replace")
    except OSError:
        environment_1 = ""
    leaked = canary in "".join(environment.values()) or canary in environment_1
    record("host environment canary visible", not leaked, "absent" if not leaked else "LEAKED")
    secretive = sorted(
        key
        for key in environment
        if any(word in key.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "AUTH", "SSH"))
        or key.upper().startswith(("GH_", "GITHUB_", "AWS_", "ANTHROPIC", "DOCKER_"))
    )
    record(
        "secret-looking environment variables",
        not secretive,
        "none" if not secretive else ", ".join(secretive),
    )
    # Network: no interface but loopback, no DNS, no route out.
    up = sorted(
        path.name
        for path in Path("/sys/class/net").iterdir()
        if (path / "flags").is_file()
        and int((path / "flags").read_text(), 16) & 0x1
        and path.name != "lo"
    )
    record("network interfaces up besides loopback", not up, ", ".join(up) or "none")
    routes = Path("/proc/net/route").read_text().splitlines()[1:]
    record("an IPv4 route out", not routes, f"{len(routes)} routes")
    for host in ("github.com", "pypi.org", "host.docker.internal", "gateway.docker.internal"):
        try:
            socket.getaddrinfo(host, 443)
            record(f"resolve {host}", False, "resolved")
        except OSError as exc:
            record(f"resolve {host}", True, type(exc).__name__)
    # The runner names the targets: public hosts, and Docker's own bridge gateway read from
    # `docker network inspect` -- a Docker default, not a household address. Labels only are
    # recorded, so no address lands in the committed probe output.
    for target in connect:
        denied, detail = _connect(target["host"], int(target["port"]))
        record(f"connect to {target['label']}", denied, detail)
    try:
        urllib.request.urlopen("https://api.github.com/", timeout=3)
        record("HTTPS to api.github.com", False, "fetched")
    except OSError as exc:
        record("HTTPS to api.github.com", True, type(exc).__name__)
    # Privileges: not root, no capabilities, no way back up.
    record("running as root", os.getuid() != 0 and os.geteuid() != 0, f"uid {os.getuid()}")
    record("effective capabilities", _status("CapEff") == "0000000000000000", _status("CapEff"))
    record("bounding capabilities", _status("CapBnd") == "0000000000000000", _status("CapBnd"))
    record("no-new-privileges", _status("NoNewPrivs") == "1", f"NoNewPrivs {_status('NoNewPrivs')}")
    try:
        os.setuid(0)
        record("setuid(0)", False, "became root")
    except OSError as exc:
        record("setuid(0)", True, type(exc).__name__)
    # Only the staged mounts exist.
    mounts = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split()
        mounts.append((fields[4], fields[3]))
    binds = sorted(
        point
        for point, root in mounts
        if root != "/" and not point.startswith(("/proc", "/sys", "/dev"))
    )
    unexpected = [point for point in binds if point not in EXPECTED_MOUNTS]
    record("mounts beyond the staged toolchain and submission", not unexpected, ", ".join(binds))
    mounted_private = any(repo in root or host_home in root for _, root in mounts)
    record(
        "a mount from the checkout or home",
        not mounted_private,
        "present" if mounted_private else "none",
    )
    # Limits: processes, memory and file size are capped.
    pids = _cgroup("pids.max")
    memory = _cgroup("memory.max")
    record("pids limit", pids.isdigit() and int(pids) <= 128, f"pids.max {pids}")
    record(
        "memory limit",
        memory.isdigit() and int(memory) <= 1024 * 1024 * 1024,
        f"memory.max {memory}",
    )
    started = []
    stop = threading.Event()
    try:
        for _ in range(200):
            thread = threading.Thread(target=stop.wait, daemon=True)
            thread.start()
            started.append(thread)
        record("start 200 threads", False, "all started")
    except RuntimeError:
        record("start 200 threads", True, f"refused after {len(started)}")
    finally:
        stop.set()
    fsize = resource.getrlimit(resource.RLIMIT_FSIZE)[0]
    record("file size limit", 0 < fsize <= 256 * 1024 * 1024, f"RLIMIT_FSIZE {fsize}")
    other = [p for p in os.listdir("/proc") if p.isdigit()]
    record("other processes visible", len(other) <= 3, f"{len(other)} pids in /proc")
    # Controls: the probe is live.
    denied, detail = _write("/tmp/control")
    record("control: write the scratch space", not denied, detail, kind="allowed")
    denied, detail = _read("/toolchain/format/src/denframe_format/__init__.py")
    record("control: read the trusted toolchain", not denied, detail, kind="allowed")
    return results
