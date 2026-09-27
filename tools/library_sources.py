"""What the public checks, the rebuild gate, the intake command and the pull-request gate share:
how a catalog entry builds, the source hash a review names, and the publisher registry's rules
(D19, D24). Every function takes its paths or documents as arguments, so tests can point it at
a copy of the repository.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from mantel_format.authoring import source_manifest
from mantel_format.elements import Definition, Manifest, build_element, build_package
from mantel_format.encoding import canonical

ROOT = Path(__file__).resolve().parents[1]
# The review skill's identity checks hold the reserved words and the look-alike folding the
# website's submit page also uses (identity.md); the registry is held to the same ones.
SKILL_CHECKS = ROOT / ".claude/skills/mantel-asset-review/scripts/container"

DISTRIBUTIONS = ("included", "library")
# A definition catalog entry, in the order the file keeps its keys. `min_host` is catalog
# metadata (D30); `manifest` carries an author's explicit manifest (publisher, licence,
# attribution) when the default one would not rebuild the submitted archive byte for byte.
ENTRY_KEYS = ("slug", "id", "version", "distribution", "mood", "description")
OPTIONAL_ENTRY_KEYS = ("min_host", "manifest")
# The manifest fields the entry does not repeat: `source_manifest` fills them from the entry.
DERIVED_MANIFEST_KEYS = ("id", "version", "definition_sha256")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
MIN_HOST = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
HANDLE = re.compile(r"[a-z0-9][a-z0-9-]{0,38}")
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]")
MAINTAINERS = "mantel"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, document):
    """The repository's JSON style: two-space indent, UTF-8 as written, one final newline."""
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def handle_of(package_id):
    return package_id.split("/", 1)[0]


def reviewed_source(item):
    """The SHA-256 a review record names for a catalog entry: the entry without its
    `distribution`, so moving a release between distributions needs no new review of its
    bytes -- only a verdict that admits the new one."""
    return sha256(canonical({key: value for key, value in item.items() if key != "distribution"}))


def definition_archive(item):
    """The archive a definition catalog entry builds: with the entry's own `manifest` when it
    has one (as `mantel-author build` builds a source document), else the default manifest."""
    definition = Definition.model_validate(item["definition"])
    if "manifest" in item:
        values = source_manifest(item, definition, item["manifest"])
        return build_element(Manifest.model_validate(values), definition)
    return build_package(item["id"], item["version"], definition)


def plain_text(value, limit, where):
    """One line of plain text, 1..limit characters, no control or bidi formatting."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit or CONTROL.search(value):
        raise ValueError(f"{where}: must be plain text of 1 to {limit} characters")
    return value


def check_entry(item, where="definitions/catalog.json"):
    """A definition catalog entry's shape: its known keys, slug, editorial words and min_host."""
    unknown = set(item) - {*ENTRY_KEYS, *OPTIONAL_ENTRY_KEYS, "definition"}
    missing = {*ENTRY_KEYS, "definition"} - set(item)
    ident = item.get("id", "?")
    if unknown or missing:
        raise ValueError(f"{where} {ident}: unknown {sorted(unknown)} or missing {sorted(missing)} fields")
    if not isinstance(item["slug"], str) or not SLUG.fullmatch(item["slug"]):
        raise ValueError(f"{where} {ident}: invalid slug {item['slug']!r}")
    if item["distribution"] not in DISTRIBUTIONS:
        raise ValueError(f"{where} {ident}: distribution must be one of {', '.join(DISTRIBUTIONS)}")
    plain_text(item["mood"], 60, f"{where} {ident} mood")
    plain_text(item["description"], 240, f"{where} {ident} description")
    if "min_host" in item and not (
        isinstance(item["min_host"], str) and MIN_HOST.fullmatch(item["min_host"])
    ):
        raise ValueError(f"{where} {ident}: min_host must be a version such as 1.4.0")
    if "manifest" in item and (
        not isinstance(item["manifest"], dict) or set(item["manifest"]) & set(DERIVED_MANIFEST_KEYS)
    ):
        raise ValueError(f"{where} {ident}: manifest must be an object without id, version or hash")


# ---------------------------------------------------------------------------------------------
# The publisher registry (D19)


def _identity_rules():
    """`RESERVED_HANDLES`, `folded` and `passes_as` from the review skill's identity checks."""
    if str(SKILL_CHECKS) not in sys.path:
        sys.path.insert(0, str(SKILL_CHECKS))
    import review_checks

    return review_checks.RESERVED_HANDLES, review_checks.folded, review_checks.passes_as


def read_registry(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def registry_problems(document):
    """Every way `publishers.json` breaks D19 and identity.md, as sentences (none: valid).

    One entry per handle: {handle, github_account_ids (numbers -- logins change), github_logins,
    display_name}. Handles are unique, never a reserved word (but `mantel`, which must be there),
    and never pass as another registered handle."""
    if not isinstance(document, dict) or set(document) != {"schema_version", "publishers"}:
        return ["publishers.json must be {schema_version: 1, publishers: [...]}"]
    if document["schema_version"] != 1 or not isinstance(document["publishers"], list):
        return ["publishers.json must be {schema_version: 1, publishers: [...]}"]
    reserved, folded, passes_as = _identity_rules()
    problems, handles = [], []
    fields = {"handle", "github_account_ids", "github_logins", "display_name"}
    for entry in document["publishers"]:
        if not isinstance(entry, dict) or set(entry) != fields:
            problems.append(f"each publisher has exactly {sorted(fields)}")
            continue
        handle = entry["handle"]
        if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
            problems.append(f"invalid handle {handle!r}")
            continue
        if handle in handles:
            problems.append(f"{handle} is registered twice")
        handles.append(handle)
        ids, logins = entry["github_account_ids"], entry["github_logins"]
        if (
            not isinstance(ids, list)
            or not ids
            or any(type(value) is not int or value <= 0 for value in ids)
            or len(set(ids)) != len(ids)
        ):
            problems.append(f"{handle}: github_account_ids must be distinct positive numbers")
        if (
            not isinstance(logins, list)
            or not isinstance(ids, list)
            or len(logins) != len(ids)
            or any(not isinstance(login, str) or not LOGIN.fullmatch(login) for login in logins)
        ):
            problems.append(f"{handle}: github_logins must be one GitHub login per account id")
        try:
            plain_text(entry["display_name"], 80, f"{handle} display_name")
        except ValueError as error:
            problems.append(str(error))
        if handle != MAINTAINERS and any(folded(word) == folded(handle) for word in reserved):
            problems.append(f"{handle} is a reserved word (identity.md)")
    if MAINTAINERS not in handles:
        problems.append("publishers.json must register the mantel handle")
    for handle in handles:
        twin = passes_as(handle, [other for other in handles if other != handle])
        if twin and handles.index(twin) < handles.index(handle):
            problems.append(f"{handle} passes as the registered {twin} (identity.md)")
    return problems


def publishers_by_handle(document):
    return {entry["handle"]: entry for entry in document["publishers"]}


def maintainer_logins(document):
    """The logins that may name themselves `reviewer` in reviews.json: the mantel handle's."""
    entry = publishers_by_handle(document).get(MAINTAINERS, {})
    return {login.casefold() for login in entry.get("github_logins", [])}
