"""The automated phases of an asset review (SKILL.md phases 1-6), run inside the sandbox.

Everything read from the submission is untrusted data. Nothing here executes, imports or
evaluates submission content: archives go through `mantel_format`'s bounded validator, and
text is only matched against patterns and quoted back, neutralised, as evidence.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import tempfile
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import palette as looks
from mantel_format.authoring import read_source, unpack
from mantel_format.themes import BUILTIN_THEMES, look_palette
from mantel_format.validation import inspect_archive

AREAS = ("identity", "structure", "security", "design", "content", "licence", "listening", "fluent")
SEVERITIES = ("critical", "major", "minor", "note")
# The recommendation a finding's severity leads to (SKILL.md phase 7). A person decides.
RECOMMEND_REJECT = "recommend reject"
CHANGES_REQUESTED = "changes requested"
RECOMMEND_APPROVE = "recommend approve"
MAX_SUBMISSION = 128 * 1024 * 1024
MAX_QUOTE = 160
# identity.md: handles nobody may register, because they pass as Mantel, a platform, a vendor
# or a role. Person names cannot be listed; a person checks those.
RESERVED_HANDLES = frozenset(
    {
        "mantel", "local", "official", "admin", "administrator", "support", "security", "staff",
        "team", "moderator", "root", "system", "library", "review", "reviewer", "verified",
        "anthropic", "claude", "github", "google", "nest", "chromecast", "android", "apple",
        "homekit", "amazon", "alexa", "microsoft", "samsung", "sonos", "spotify", "netflix",
        "disney", "home-assistant", "homeassistant", "nabucasa", "firebase", "tuf", "pypi",
    }
)  # fmt: skip
TEXT_SKIP_KEYS = frozenset(
    {"sha256", "archive_sha256", "definition_sha256", "digest", "path", "image", "resource"}
)


@dataclass(frozen=True)
class Finding:
    code: str
    area: str
    severity: str
    title: str
    evidence: str = ""


def neutral(value: object, limit: int = MAX_QUOTE) -> str:
    """Untrusted text made inert for a report: controls and bidi marks shown as escapes,
    backticks and pipes replaced, one line, bounded."""
    text = str(value)
    out = []
    for char in text:
        category = unicodedata.category(char)
        if char in "`|":
            out.append("'" if char == "`" else "/")
        elif category in {"Cc", "Cf", "Zl", "Zp"}:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    joined = "".join(out)
    return joined if len(joined) <= limit else joined[: limit - 1] + "…"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# -- Phase 1: intake --------------------------------------------------------------------------


def unwrap(data: bytes, scratch: Path) -> tuple[bytes, str | None]:
    """The archive itself: the website's `.zip` copy holds exactly one `*.mantelpack` entry."""
    if not data.startswith(b"PK\x03\x04"):
        return data, None
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as wrapper:
            entries = wrapper.infolist()
            if (
                len(entries) == 1
                and entries[0].filename.endswith(".mantelpack")
                and "/" not in entries[0].filename
                and entries[0].file_size <= MAX_SUBMISSION
                and entries[0].compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            ):
                with wrapper.open(entries[0]) as source:
                    inner = source.read(MAX_SUBMISSION + 1)
                if len(inner) <= MAX_SUBMISSION:
                    (scratch / "unwrapped.mantelpack").write_bytes(inner)
                    return inner, entries[0].filename
    except (zipfile.BadZipFile, OSError, ValueError, NotImplementedError):
        pass
    return data, None


# -- Phase 4: security (structure of the bytes) -----------------------------------------------


def zip_layout(data: bytes) -> list[Finding]:
    """Polyglot and appended-data checks: the archive is a ZIP from its first byte to its last,
    with no gaps between entries, the central directory and the end record."""
    findings: list[Finding] = []
    if not data.startswith(b"PK\x03\x04"):
        findings.append(
            Finding(
                "SEC-POLYGLOT",
                "security",
                "critical",
                "The file does not start with a ZIP entry",
                f"first bytes {data[:8].hex()}",
            )
        )
        return findings
    end = data.rfind(b"PK\x05\x06")
    if end < 0 or end != len(data) - 22:
        findings.append(
            Finding(
                "SEC-APPENDED-DATA",
                "security",
                "critical",
                "Bytes follow the ZIP end record",
                f"end record at {end}, file length {len(data)}",
            )
        )
        return findings
    _, _, _, _, _, size, offset, _ = struct.unpack("<4s4H2IH", data[end : end + 22])
    if offset + size != end:
        findings.append(
            Finding(
                "SEC-APPENDED-DATA",
                "security",
                "critical",
                "A gap sits between the central directory and the end record",
                f"directory {offset}+{size}, end record at {end}",
            )
        )
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            position = 0
            for info in sorted(archive.infolist(), key=lambda item: item.header_offset):
                if info.header_offset != position:
                    findings.append(
                        Finding(
                            "SEC-APPENDED-DATA",
                            "security",
                            "critical",
                            "Hidden bytes sit between ZIP entries",
                            f"entry {neutral(info.filename)} at {info.header_offset}, "
                            f"expected {position}",
                        )
                    )
                    break
                name_length, extra_length = struct.unpack(
                    "<HH", data[info.header_offset + 26 : info.header_offset + 30]
                )
                position = info.header_offset + 30 + name_length + extra_length + info.compress_size
                if info.flag_bits & 0x08:
                    position += 16 if data[position : position + 4] == b"PK\x07\x08" else 12
            if not findings and position != offset:
                findings.append(
                    Finding(
                        "SEC-APPENDED-DATA",
                        "security",
                        "critical",
                        "Hidden bytes sit before the central directory",
                        f"entries end at {position}, directory at {offset}",
                    )
                )
    except (zipfile.BadZipFile, struct.error, ValueError, OSError):
        pass  # The validator's archive layer reports a ZIP it cannot read.
    return findings


def png_end(body: bytes) -> int:
    """Where a PNG ends: just after its *first* IEND chunk, walking chunk by chunk (a later
    IEND after hidden chunks must not count)."""
    position = 8
    while position + 12 <= len(body):
        length = struct.unpack(">I", body[position : position + 4])[0]
        kind = body[position + 4 : position + 8]
        position += 12 + length
        if kind == b"IEND":
            return position
    return len(body)


def media_trailers(data: bytes) -> list[Finding]:
    """Picture resources end where their format ends: nothing hides after IEND, EOI or RIFF."""
    findings: list[Finding] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError, ValueError):
        return findings
    with archive:
        for info in archive.infolist():
            if not info.filename.startswith("assets/") or info.file_size > 16 * 1024 * 1024:
                continue
            body = archive.read(info)
            extra = 0
            if body.startswith(b"\x89PNG\r\n\x1a\n"):
                extra = len(body) - png_end(body)
            elif body.startswith(b"\xff\xd8"):
                marker = body.rfind(b"\xff\xd9")
                extra = len(body) - (marker + 2) if marker >= 0 else 0
            elif body.startswith(b"RIFF") and len(body) >= 8:
                extra = len(body) - (8 + struct.unpack("<I", body[4:8])[0])
            if extra > 0:
                findings.append(
                    Finding(
                        "SEC-APPENDED-DATA",
                        "security",
                        "critical",
                        "Data follows the end of a picture",
                        f"{neutral(info.filename)}: {extra} bytes after the image ends",
                    )
                )
    return findings


# -- Phase 4: text scan ----------------------------------------------------------------------

# Wording that only an attempt on the reviewer uses: critical, recommend reject.
INJECTION = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(ignore|disregard|forget)\b.{0,20}\b(all|any|previous|prior|above|earlier|your)\b"
        r".{0,20}\b(instructions?|rules|prompts?|guidelines)\b",
        r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?"
        r"(reviewers?|ai|assistant|agent|model|claude|llm)\b",
        r"\b(reviewers?|claude|llm|the ai|ai reviewer|language model)\b.{0,60}"
        r"\b(must|should|shall|please|is (told|instructed|authori[sz]ed))\b",
        r"\b(pre-?approved|already approved|auto-?approve|"
        r"approved by (the )?(owner|maintainer|mantel))\b",
        r"\brecommend(ed)?\s+approv",
        r"~/\.ssh|\.ssh/|\bid_(rsa|ed25519|ecdsa)\b|authorized_keys|known_hosts",
        r"\b(print|dump|echo|output|reveal)\b.{0,30}\b(env|environ|environment( variables?)?"
        r"|access tokens?|credentials?|api keys?|private keys?)\b",
        r"\b(printenv|os\.environ|process\.env)\b",
        r"(^|[\s`'\"(;&|])gh\s+(issue|pr|api|auth|repo|release|secret|workflow|run|gist)\b",
        r"\b(curl|wget)\s+\S+|\bbash\s+-c\b|\bsh\s+-c\b|\$\(",
        r"\bsystem prompt\b|\bjailbreak\b|\bdeveloper mode\b",
    )
]
# Ordinary words that an attempt could also use ("set ... pass", "run ... script"): a minor
# finding a person judges, never a rejection on its own.
SUSPECT = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(assistant|agent|model)\b.{0,60}\b(must|should|shall|please)\b",
        r"\b(mark|set|record)\b.{0,40}\b(pass|passed|approved)\b",
        r"\b(run|execute|exec|call|invoke|type)\b.{0,30}"
        r"\b(command|script|shell|terminal|bash|sh|curl|wget|gh)\b",
        r"\bignore\b.{0,40}\b(instructions?|rules|guidelines|checks?)\b",
        r"\b(print|dump|echo|list|reveal)\b.{0,30}\bsecrets?\b",
        r"\$\{?[A-Z_]{3,}\}?|\benv\s*(\||>|$)",
    )
]
URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE = re.compile(r"(?<![\w.])\+?\d[\d ()\-]{7,}\d(?![\w.])")
# A year range or a date is not a phone number.
NOT_PHONE = re.compile(r"\d{4}\s*[-–]\s*\d{2,4}(\s*[-–]\s*\d{2})?")
HOUSEHOLD = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:10|127)(?:\.\d{1,3}){3}\b|\b192\.168(?:\.\d{1,3}){2}\b"
        r"|\b172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}\b",
        r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b",
        r"-?\d{1,2}\.\d{4,},\s*-?\d{1,3}\.\d{4,}",
        r"\b(wifi|wi-fi|ssid|password|passcode|alarm code|door code)\b",
        r"\.local\b|\bhome\.arpa\b",
    )
]
SECRET = [
    re.compile(pattern)
    for pattern in (
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
        r"\bsk-[A-Za-z0-9_-]{20,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.",
        r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*\S{8,}",
    )
]


def strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Every string in a JSON document with its path, skipping digests and resource paths."""
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        found.append((path, value))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in TEXT_SKIP_KEYS:
                found.extend(strings(item, f"{path}.{key}" if path else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(strings(item, f"{path}[{index}]"))
    return found


def phone(candidate: str) -> bool:
    """Nine digits or more, and not a date or a year range."""
    digits = sum(char.isdigit() for char in candidate)
    return digits >= 9 and not NOT_PHONE.fullmatch(candidate.strip())


def scan_text(texts: list[tuple[str, str]], *, submitter_words: bool) -> list[Finding]:
    """URLs, contact details, household data, secrets and prompt injection. The submitter's
    own issue text may link sources and name people; the asset's text may not."""
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    def add(
        code: str, severity: str, title: str, where: str, match: str, quote: str | None = None
    ) -> None:
        if (code, where) in seen:
            return
        seen.add((code, where))
        shown = quote if quote is not None else f"`{neutral(match)}`"
        findings.append(Finding(code, "security", severity, title, f"{where}: {shown}"))

    for where, text in texts:
        for code, patterns, severity, title in (
            (
                "SEC-PROMPT-INJECTION",
                INJECTION,
                "critical",
                "Text addressed to the reviewer (reported, not followed)",
            ),
            (
                "SEC-PROMPT-SUSPECT",
                SUSPECT,
                "minor",
                "Wording that may address the reviewer (reported, not followed; a person judges)",
            ),
        ):
            hit = next((h for p in patterns if (h := p.search(text))), None)
            if hit:
                window = text[max(0, hit.start() - 40) : hit.end() + 40]
                add(code, severity, title, where, window)
                break
        for pattern in SECRET:
            hit = pattern.search(text)
            if hit:
                # Never the value: its first four characters and its length locate it.
                masked = f"`{neutral(hit.group()[:4])}…` ({len(hit.group())} characters)"
                add("SEC-TEXT-SECRET", "critical", "A credential-like string", where, "", masked)
        if submitter_words:
            continue
        for code, pattern, severity, title in (
            ("SEC-TEXT-URL", URL, "minor", "A web address in the asset's text"),
            ("SEC-TEXT-EMAIL", EMAIL, "major", "An email address in the asset's text"),
            ("SEC-TEXT-PHONE", PHONE, "major", "A phone number in the asset's text"),
        ):
            hits = [
                h for h in pattern.finditer(text) if code != "SEC-TEXT-PHONE" or phone(h.group())
            ]
            if hits:
                add(code, severity, title, where, hits[0].group())
        for pattern in HOUSEHOLD:
            hit = pattern.search(text)
            if hit:
                add(
                    "SEC-TEXT-HOUSEHOLD",
                    "major",
                    "Household-looking data in the asset's text",
                    where,
                    hit.group(),
                )
                break
    return findings


# -- Phase 2: identity ------------------------------------------------------------------------


def folded(handle: str) -> str:
    """The site's look-alike folding (frontend/site/src/submit/submission.ts), kept in step."""
    text = re.sub(r"[.-]", "", handle)
    for old, new in (("rn", "m"), ("vv", "w"), ("cl", "d")):
        text = text.replace(old, new)
    for old, new in (
        ("0", "o"),
        ("1", "l"),
        ("i", "l"),
        ("|", "l"),
        ("5", "s"),
        ("3", "e"),
        ("4", "a"),
    ):
        text = text.replace(old, new)
    return text


def edits(left: str, right: str, limit: int) -> int:
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        row = [i]
        for j, b in enumerate(right, 1):
            row.append(min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = row
    return previous[-1]


def passes_as(handle: str, others: list[str]) -> str | None:
    mine = folded(handle)
    for other in others:
        if other == handle:
            continue
        theirs = folded(other)
        if (
            mine == theirs
            or (len(theirs) >= 4 and edits(mine, theirs, 1) <= 1)
            or (len(theirs) >= 5 and theirs in mine)
        ):
            return other
    return None


def release_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) if part.isdigit() else -1 for part in version.split("."))


SCRIPTS = ("LATIN", "CYRILLIC", "GREEK")


def mixed_script(text: str) -> bool:
    """Latin mixed with Cyrillic or Greek letters in one word: the classic confusable spoof.
    Other scripts (Arabic, Hebrew, CJK, emoji) mix freely in names."""
    for word in re.findall(r"\w+", text):
        scripts = set()
        for char in word:
            if char.isalpha():
                name = unicodedata.name(char, "")
                scripts |= {script for script in SCRIPTS if name.startswith(script)}
        if len(scripts) > 1:
            return True
    return False


def identity(
    package_id: str,
    version: str,
    names: list[tuple[str, str]],
    submitter: dict,
    reference: dict,
) -> list[Finding]:
    findings: list[Finding] = []
    handle, _, slug = package_id.partition("/")
    registry = {entry["handle"]: entry for entry in reference["publishers"]}
    account = submitter.get("id")
    login = neutral(submitter.get("login", "?"), 40)

    def registered_to(name: str) -> bool:
        entry = registry.get(name)
        return entry is not None and account in entry.get("github_account_ids", [])

    catalog = reference["catalog"]
    listed = catalog.get(package_id)
    if handle == "mantel" and not registered_to("mantel"):
        findings.append(
            Finding(
                "ID-RESERVED",
                "identity",
                "critical",
                "mantel/ is reserved for the signed Mantel catalog",
                f"{package_id} submitted by {login} (account {account}), who is not a Mantel "
                "publisher account",
            )
        )
        if listed:
            findings.append(
                Finding(
                    "ID-IMPOSTOR",
                    "identity",
                    "critical",
                    "The id is a catalog item's: an impostor",
                    f"{package_id} is Mantel's own {neutral(listed['name'])} "
                    f"{listed['version']}; an unsigned claim is refused (D19)",
                )
            )
        return findings
    if handle == "local":
        findings.append(
            Finding(
                "ID-LOCAL",
                "identity",
                "major",
                "local/ marks a household's own file, not a publication",
                f"{package_id}: rebuild under the submitter's own handle",
            )
        )
        return findings
    if handle in registry:
        if registered_to(handle):
            findings.append(
                Finding(
                    "ID-HANDLE-REGISTERED",
                    "identity",
                    "note",
                    "The handle is registered to the submitting account",
                    f"{handle} lists account {account} ({login})",
                )
            )
        else:
            findings.append(
                Finding(
                    "ID-HANDLE-UNREGISTERED-USE",
                    "identity",
                    "critical",
                    "A registered handle used by an account it does not list",
                    f"{handle} is registered to {neutral(registry[handle]['display_name'])}; "
                    f"{login} (account {account}) is not one of its accounts",
                )
            )
    else:
        findings.append(
            Finding(
                "ID-HANDLE-NEW",
                "identity",
                "note",
                "A new handle: registered to the submitting account if accepted",
                f"{handle} for {login} (account {account}); a person checks identity.md's "
                "rules on brand and person names",
            )
        )
        if handle in RESERVED_HANDLES:
            findings.append(
                Finding(
                    "ID-HANDLE-RESERVED-WORD",
                    "identity",
                    "major",
                    "The handle is a brand, platform or role name",
                    handle,
                )
            )
        # Publishers are compared by the website's look-alike rules; reserved words only by
        # folded equality (`beam` is not `team`).
        twin = passes_as(handle, sorted({"mantel", *registry})) or next(
            (word for word in sorted(RESERVED_HANDLES) if folded(word) == folded(handle)), None
        )
        if twin:
            findings.append(
                Finding(
                    "ID-HANDLE-LOOKALIKE",
                    "identity",
                    "major",
                    "The handle reads like another publisher's or a reserved name",
                    f"{handle} passes as {twin}",
                )
            )
    if (
        listed
        and handle != "mantel"
        and registered_to(handle)
        and release_tuple(version) <= release_tuple(listed["version"])
    ):
        findings.append(
            Finding(
                "ID-VERSION-NOT-BUMPED",
                "identity",
                "major",
                "An update must raise the catalog version",
                f"{version} is not above the catalog's {listed['version']}",
            )
        )
    if not listed:
        twins = sorted(other for other in catalog if other.partition("/")[2] == slug)
        if twins:
            findings.append(
                Finding(
                    "ID-SAME-NAME",
                    "identity",
                    "minor",
                    "The id's name repeats a catalog item's",
                    f"{package_id} beside {', '.join(twins)}",
                )
            )
    for where, text in names:
        if mixed_script(text):
            findings.append(
                Finding(
                    "ID-CONFUSABLE-NAME",
                    "identity",
                    "major",
                    "A name mixes Latin with Cyrillic or Greek letters",
                    f"{where}: `{neutral(text)}`",
                )
            )
    return findings


# -- Validator verdicts -> findings ------------------------------------------------------------


def layer_findings(layers: dict[str, str], error: str | None) -> list[Finding]:
    """The validator's first failing layer (and a capability warning) as review findings."""
    message = neutral((error or "").splitlines()[0] if error else "", 200)
    lowered = (error or "").lower()
    findings: list[Finding] = []
    if layers.get("capabilities") == "warning":
        findings.append(
            Finding(
                "STRUCT-CAPABILITY-EXTRA",
                "structure",
                "minor",
                "The manifest declares capabilities the definition does not need",
                "declare only the minimum a host must support",
            )
        )
    failed = next((layer for layer, verdict in layers.items() if verdict == "fail"), None)
    if failed is None:
        return findings
    evidence = f"{failed} layer: {message}"
    if failed == "archive":
        code, area, severity, title = (
            "SEC-ZIP-PROFILE",
            "security",
            "critical",
            "The archive breaks the ZIP profile mantel-author writes",
        )
    elif failed == "json":
        code, area, severity, title = (
            "SEC-TEXT-ENCODING",
            "security",
            "major",
            "A document is not plain, strict UTF-8 JSON",
        )
    elif failed == "contrast" or (failed == "schema" and "contrast" in lowered):
        code, area, severity, title = (
            "DES-CONTRAST",
            "design",
            "major",
            "Theme colours fail the contrast gate",
        )
    elif failed == "schema" and ("attribution" in lowered or "license" in lowered):
        code, area, severity, title = (
            "LIC-INVALID",
            "licence",
            "major",
            "The licence or its attribution is not allowed as given",
        )
    elif failed == "schema":
        code, area, severity, title = (
            "STRUCT-SCHEMA",
            "structure",
            "major",
            "The documents do not match the published schema",
        )
    elif failed == "capabilities":
        code, area, severity, title = (
            "STRUCT-CAPABILITIES",
            "structure",
            "major",
            "The manifest leaves out a capability the definition needs",
        )
    elif "animation" in lowered:
        code, area, severity, title = (
            "DES-MOTION",
            "design",
            "major",
            "An animated picture cannot honour prefers-reduced-motion",
        )
    elif "metadata" in lowered:
        code, area, severity, title = (
            "SEC-MEDIA-METADATA",
            "security",
            "major",
            "Media carries metadata",
        )
    else:
        code, area, severity, title = (
            "SEC-MEDIA-INVALID",
            "security",
            "major",
            "Media does not decode as declared",
        )
    findings.append(Finding(code, area, severity, title, evidence))
    return findings


# -- Phase 5: design --------------------------------------------------------------------------


def catalog_looks(reference: dict) -> dict[str, dict[str, str]]:
    """Every look in the catalog, resolved: each catalogued theme, plus any built-in look no
    catalogued theme already paints exactly (today the six themes are the six built-ins)."""
    result = {
        package_id: look_palette(entry["look"], entry.get("tokens", {}))
        for package_id, entry in reference["catalog"].items()
        if entry["kind"] == "theme" and entry.get("look")
    }
    painted = [dict(sorted(tokens.items())) for tokens in result.values()]
    for item in BUILTIN_THEMES:
        if dict(sorted(item["tokens"].items())) not in painted:
            result[item["look"]] = dict(item["tokens"])
    return result


def distinctness(
    definition: dict, reference: dict, package_id: str = ""
) -> tuple[dict, list[Finding]]:
    if definition.get("kind") != "theme":
        return {"applies": False}, []
    tokens = definition.get("appearance", {}).get("tokens", {})
    palette = look_palette(definition.get("look", "modern"), tokens)
    # An update is not compared with the release it replaces.
    others = {k: v for k, v in catalog_looks(reference).items() if k != package_id}
    ranked = looks.nearest(palette, others)
    nearest = ranked[0]
    evidence = {
        "applies": True,
        "threshold": looks.THRESHOLD,
        "nearest": ranked[:3],
        "look": definition.get("look", "modern"),
        "background": definition.get("appearance", {}).get("background", "theme"),
        "layout": definition.get("appearance", {}).get("layout", "flow"),
    }
    findings = []
    if nearest["distance"] < looks.THRESHOLD:
        findings.append(
            Finding(
                "DES-NOT-DISTINCT",
                "design",
                "major",
                "The look is too close to a catalog look",
                f"ΔE {nearest['distance']} from {nearest['look']} (minimum {looks.THRESHOLD}, "
                "largest role difference dropped)",
            )
        )
    return evidence, findings


def motion(definition: dict) -> list[Finding]:
    """The format carries no animation code: `background_motion` is the renderer's own slow
    pan, stopped under prefers-reduced-motion (display.css). Animated media fails the media
    layer (DES-MOTION there)."""
    if definition.get("appearance", {}).get("background_motion") is True:
        return [
            Finding(
                "DES-MOTION-RENDERER",
                "design",
                "note",
                "Background motion is on: the renderer's pan, which reduced motion stops",
                "appearance.background_motion = true; check the preview with reduced motion on",
            )
        ]
    return []


def names_taken(name: str, reference: dict) -> list[Finding]:
    taken = [
        package_id
        for package_id, entry in reference["catalog"].items()
        if entry["name"].casefold() == name.casefold()
    ]
    if not taken:
        return []
    return [
        Finding(
            "DES-NAME-TAKEN",
            "design",
            "minor",
            "The name repeats a catalog item's",
            f"`{neutral(name)}` is also {', '.join(taken)}",
        )
    ]


# -- Phase 6: content (packs) -----------------------------------------------------------------


def pack_content(definition: dict) -> tuple[dict, list[Finding]]:
    findings = []
    locales = definition.get("locales", [])
    audio = [r for r in definition.get("resources", []) if r.get("media_type") == "audio/mpeg"]
    images = [
        r for r in definition.get("resources", []) if r.get("media_type", "").startswith("image/")
    ]
    weak_alt = []
    for item in definition.get("items", []):
        for locale, translation in item.get("translations", {}).items():
            for phase in ("prompt", "reveal"):
                face = translation.get(phase, {})
                alt = (face.get("alt_text") or "").strip()
                if face.get("image") and (
                    len(alt.split()) < 2 or alt.lower().startswith("assets/")
                ):
                    weak_alt.append(f"{item.get('id')}/{locale}/{phase}")
    if weak_alt:
        findings.append(
            Finding(
                "CON-ALT-TEXT",
                "content",
                "minor",
                "Pictures without meaningful alternative text",
                ", ".join(neutral(x, 60) for x in weak_alt[:8]),
            )
        )
    if audio:
        findings.append(
            Finding(
                "CON-LISTENING-NEEDED",
                "listening",
                "note",
                "A person listens to every sound before approval",
                f"{len(audio)} audio resources",
            )
        )
    foreign = [locale for locale in locales if not locale.lower().startswith("en")]
    if foreign:
        findings.append(
            Finding(
                "CON-FLUENT-NEEDED",
                "fluent",
                "note",
                "A fluent reader checks every non-English string",
                ", ".join(foreign),
            )
        )
    credits = sorted(
        {
            f"{neutral(r['credit'].get('creator', ''), 60)} ({r['credit'].get('license', '')})"
            for r in definition.get("resources", [])
            if isinstance(r.get("credit"), dict)
        }
    )
    summary = {
        "locales": locales,
        "items": len(definition.get("items", [])),
        "images": len(images),
        "audio": len(audio),
        "credits": credits,
    }
    return summary, findings


# -- The whole automated review ---------------------------------------------------------------


def unpack_and_rebuild(path: Path, scratch: Path, data: bytes) -> dict:
    """Phase 3: the archive unpacks to a source that rebuilds, ideally byte for byte."""
    try:
        source = unpack(path, scratch / "unpacked")
        _, _, rebuilt = read_source(source)
    except (ValueError, OSError, RecursionError) as exc:
        return {"status": "failed", "error": neutral(str(exc).splitlines()[0], 200)}
    return {
        "status": "identical" if rebuilt == data else "differs",
        "rebuilt_sha256": sha256(rebuilt),
        "rebuilt_size": len(rebuilt),
        "source_sha256": sha256(source.read_bytes()),
    }


def raw_manifest(data: bytes) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("manifest.json")
            if info.file_size > 65536:
                return {}
            value = json.loads(archive.read(info))
            return value if isinstance(value, dict) else {}
    except (KeyError, zipfile.BadZipFile, ValueError, OSError):
        return {}


def statuses_for(findings: list[Finding], *, valid: bool, kind: str, content: dict) -> dict:
    """The ledger's eight statuses as tools can settle them: structure and security by
    evidence, any failure where it was found, and everything a person judges `pending`."""
    failing = {f.area for f in findings if f.severity in ("critical", "major")}
    result = {}
    for area in AREAS:
        if area in failing:
            result[area] = "fail"
        elif area == "structure":
            result[area] = "pass" if valid else "fail"
        elif area == "security":
            result[area] = "pass" if valid else "pending"
        elif area == "listening":
            result[area] = (
                "pending" if kind == "pack" and content.get("audio") else "not-applicable"
            )
        elif area == "fluent":
            foreign = [x for x in content.get("locales", []) if not x.lower().startswith("en")]
            result[area] = "pending" if kind == "pack" and foreign else "not-applicable"
        else:
            result[area] = "pending"
    return result


def recommendation(findings: list[Finding]) -> str:
    severities = {finding.severity for finding in findings}
    if "critical" in severities:
        return RECOMMEND_REJECT
    if "major" in severities:
        return CHANGES_REQUESTED
    return RECOMMEND_APPROVE


def review(path: Path, intake: dict, reference: dict, issue_text: str | None) -> dict:
    """Run every automated phase over one staged submission and return the evidence."""
    raw = path.read_bytes()[: MAX_SUBMISSION + 1]
    if len(raw) > MAX_SUBMISSION:
        raise ValueError("The submission is over 128 MiB")
    findings: list[Finding] = []
    # The sandbox's /tmp is its only writable, no-exec scratch space.
    with tempfile.TemporaryDirectory(prefix="review-") as temp:
        scratch = Path(temp)
        data, wrapped_as = unwrap(raw, scratch)
        archive = scratch / "submission.mantelpack"
        archive.write_bytes(data)
        inspection = inspect_archive(archive)
        summary = inspection.summary()
        layers = summary["layers"]
        manifest = summary["manifest"] or raw_manifest(data)
        definition = summary["definition"] or {}
        findings += zip_layout(data)
        findings += media_trailers(data)
        findings += layer_findings(layers, summary["error"])
        rebuild = (
            unpack_and_rebuild(archive, scratch, data)
            if inspection.valid
            else {"status": "not run", "error": "the archive does not validate"}
        )
    if rebuild["status"] == "differs":
        findings.append(
            Finding(
                "STRUCT-REBUILD-DIFFERS",
                "structure",
                "note",
                "Unpacked and rebuilt, the archive has different bytes; the release would be "
                "the rebuild",
                f"submitted {sha256(data)[:12]}…, rebuilt {rebuild['rebuilt_sha256'][:12]}…",
            )
        )
    elif rebuild["status"] == "failed":
        findings.append(
            Finding(
                "STRUCT-UNPACK",
                "structure",
                "major",
                "The archive does not unpack to a buildable source",
                rebuild["error"],
            )
        )
    package_id = str(manifest.get("id", ""))
    version = str(manifest.get("version", ""))
    kind = definition.get("kind") or ("pack" if manifest.get("schema_version") == 2 else "")
    names = [("definition.name", str(definition.get("name", "")))]
    names += [("manifest.publisher", str(manifest.get("publisher", "")))]
    if package_id and "/" in package_id:
        findings += identity(package_id, version, names, intake.get("submitter", {}), reference)
    else:
        findings.append(
            Finding(
                "ID-UNREADABLE",
                "identity",
                "major",
                "No readable id and version",
                "the manifest did not parse",
            )
        )
    texts = strings(manifest, "manifest") + strings(definition, "definition")
    findings += scan_text(texts, submitter_words=False)
    if issue_text:
        findings += scan_text([("issue", issue_text[:65536])], submitter_words=True)
    distinct, found = (
        distinctness(definition, reference, package_id) if inspection.valid else ({}, [])
    )
    findings += found
    if inspection.valid:
        findings += motion(definition)
        findings += names_taken(str(definition.get("name", "")), reference)
    content: dict = {}
    if kind == "pack" and inspection.valid:
        content, found = pack_content(definition)
        findings += found
    size = len(data)
    if (kind != "pack" and size > 32 * 1024) or (
        kind == "pack" and content.get("items") and size / content["items"] > 1024 * 1024
    ):
        findings.append(
            Finding(
                "SEC-SIZE",
                "security",
                "minor",
                "The archive is large for what it holds",
                f"{size} bytes",
            )
        )
    findings.append(
        Finding(
            "DES-PREVIEWS-PENDING",
            "design",
            "note",
            "Previews at 1920x1080, 1080x1920 and 1024x768 are rendered by us and looked at "
            "by a person",
            "not rendered inside the review sandbox",
        )
    )
    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (order[f.severity], AREAS.index(f.area), f.code))
    statuses = statuses_for(findings, valid=inspection.valid, kind=kind, content=content)
    release_sha = rebuild.get("rebuilt_sha256", sha256(data))
    return {
        "submission": {
            "sha256": sha256(raw),
            "size": len(raw),
            "archive_sha256": sha256(data),
            "archive_size": size,
            "unwrapped_from_zip": neutral(wrapped_as) if wrapped_as else None,
            "submitter": {
                "login": neutral(intake.get("submitter", {}).get("login", ""), 40),
                "id": intake.get("submitter", {}).get("id"),
            },
            "source": intake.get("source"),
            "number": intake.get("number"),
        },
        "release": {
            "id": neutral(package_id, 120),
            "version": neutral(version, 40),
            "kind": kind,
            "ledger_kind": "pack" if kind == "pack" else "definition",
            "name": neutral(definition.get("name", ""), 100),
            "license": neutral(manifest.get("license", ""), 40),
            "publisher": neutral(manifest.get("publisher", ""), 100),
            "attribution": neutral(manifest.get("attribution", ""), 500),
            "release_sha256": release_sha,
        },
        "layers": layers,
        "validator_error": neutral((summary["error"] or "").splitlines()[0], 200)
        if summary["error"]
        else None,
        "rebuild": rebuild,
        "distinctness": distinct,
        "content": content,
        # Every string in the asset, neutralised and bounded, for the reviewer to read: the
        # scan's patterns are not exhaustive, and a person (or the agent) judges the rest.
        "texts": [
            {"where": neutral(where, 120), "text": neutral(text)} for where, text in texts[:300]
        ],
        "findings": [asdict(f) for f in findings],
        "automated_findings": [f.code for f in findings],
        "reviewer_findings": [],
        "statuses": statuses,
        "recommendation": recommendation(findings),
    }


def reference_from(root: Path, registry_override: Path | None = None) -> dict:
    """The trusted reference data: the publisher registry and the catalog's ids and looks."""
    registry = json.loads((registry_override or root / "publishers.json").read_text())
    catalog: dict[str, dict] = {}
    for item in json.loads((root / "definitions/catalog.json").read_text()):
        definition = item["definition"]
        catalog[item["id"]] = {
            "name": definition["name"],
            "version": item["version"],
            "kind": definition["kind"],
            "look": definition.get("look"),
            "tokens": definition.get("appearance", {}).get("tokens", {}),
        }
    for source in sorted((root / "packs").glob("*/source.json")):
        item = json.loads(source.read_text())
        catalog[item["id"]] = {
            "name": item["definition"]["name"],
            "version": item["version"],
            "kind": "pack",
        }
    return {"publishers": registry["publishers"], "catalog": catalog}
