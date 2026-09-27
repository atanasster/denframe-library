"""Maintainer intake: an accepted submission becomes canonical source in a pull request (D24).

After the `mantel-asset-review` skill has reviewed a submission (its `.review/<n>/` holds
`evidence.json`, `record.json` and `report.md`), a maintainer runs, from a clean checkout on a
new branch:

    python tools/intake.py unpack .review/42/intake/submission.mantelpack \\
        --evidence .review/42/evidence.json --mood "..." --description "..."
    python tools/intake.py register --evidence .review/42/evidence.json --display-name "Brook"
    # open the pull request; after reading the report, the owner decides:
    python tools/intake.py approve --draft .review/42/record.json \\
        --evidence .review/42/evidence.json --reviewer atanasster --verdict approved \\
        --status identity=pass --status design=pass --status content=pass --status licence=pass

`unpack` writes the source (a definition entry in `definitions/catalog.json`, or
`packs/<slug>/` and its `packs/catalog.json` line), refusing an id or version already listed
and any source that does not rebuild the submitted archive byte for byte. `register` adds a
first-time handle to `publishers.json`, bound to the numeric GitHub account id the skill's
intake read from the issue or pull request (GitHub's metadata, never the submission). `approve`
turns the skill's draft record into a ledger record in `reviews.json` once the owner names
their verdict and statuses: it never invents a reviewer, and never approves over a pending or
failed status. Nothing here signs, publishes or talks to the network.
"""

import argparse
import datetime
import io
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from library_sources import (  # noqa: E402
    DERIVED_MANIFEST_KEYS,
    DISTRIBUTIONS,
    HANDLE,
    LOGIN,
    MIN_HOST,
    SLUG,
    check_entry,
    definition_archive,
    handle_of,
    maintainer_logins,
    plain_text,
    publishers_by_handle,
    read_registry,
    registry_problems,
    reviewed_source,
    sha256,
    write_json,
)
from mantel_format.authoring import read_source, unpack  # noqa: E402
from mantel_format.elements import build_package  # noqa: E402
from mantel_format.pack_contracts import PackDefinition  # noqa: E402
from mantel_format.reviews import ReviewRecord, read_ledger, require_review  # noqa: E402
from mantel_format.validation import inspect_archive  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AREAS = ("identity", "structure", "security", "design", "content", "licence", "listening", "fluent")
# Tools settle these two (SKILL.md, Statuses); a person does not overrule them.
TOOL_AREAS = ("structure", "security")
STATUSES = ("pass", "fail", "pending", "not-applicable")
# Verdicts that go into the ledger with a source in the tree. Changes requested or rejected is
# said on the issue; a source only enters the catalog with a verdict that admits it.
LEDGER_VERDICTS = ("approved", "preview")


class Refused(Exception):
    """The command refused, with a sentence that says why."""


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Refused(f"{path} is not a readable JSON file.") from error


# ---------------------------------------------------------------------------------------------
# What the tree already lists


def listed_definitions(root):
    return json.loads((root / "definitions/catalog.json").read_text(encoding="utf-8"))


def listed_packs(root):
    """(slug, id, version, source path) for every pack source directory."""
    for source in sorted((root / "packs").glob("*/source.json")):
        item = json.loads(source.read_text(encoding="utf-8"))
        yield source.parent.name, item.get("id"), item.get("version"), source


def releases_in_tree(root):
    """Every release the tree lists: (id, version) -> (kind, slug, the archive it builds)."""
    found = {}
    for item in listed_definitions(root):
        found[(item["id"], item["version"])] = ("definition", item["slug"], lambda i=item: definition_archive(i))
    for slug, package_id, version, source in listed_packs(root):
        found[(package_id, version)] = ("pack", slug, lambda s=source: read_source(s)[2])
    return found


def source_for(root, package_id, version):
    """The tree's source for one release: (kind, archive bytes, source SHA-256, distribution)."""
    for item in listed_definitions(root):
        if (item["id"], item["version"]) == (package_id, version):
            return "definition", definition_archive(item), reviewed_source(item), item["distribution"]
    placed = {entry["slug"]: entry["distribution"] for entry in _json(root / "packs/catalog.json")}
    for slug, found_id, found_version, source in listed_packs(root):
        if (found_id, found_version) == (package_id, version):
            if slug not in placed:
                raise Refused(f"packs/{slug} is not listed in packs/catalog.json.")
            _, _, archive = read_source(source)
            return "pack", archive, sha256(source.read_bytes()), placed[slug]
    raise Refused(f"The tree has no source for {package_id} {version}; run unpack first.")


# ---------------------------------------------------------------------------------------------
# unpack


MAX_ARCHIVE = 128 * 1024 * 1024


def submitted_archive(path, evidence):
    """The archive the review read, as bytes: the file given, or the one `.mantelpack` inside
    the `.zip` copy a Submit an asset issue attaches (the skill unwrapped the same one)."""
    raw = Path(path).read_bytes()
    submission = evidence.get("submission") or {}
    reviewed = submission.get("archive_sha256")
    data = raw
    if sha256(raw) != reviewed and submission.get("unwrapped_from_zip") and sha256(raw) == submission.get("sha256"):
        with zipfile.ZipFile(io.BytesIO(raw)) as wrapper:
            members = [info for info in wrapper.infolist() if not info.is_dir()]
            if len(members) != 1 or not members[0].filename.endswith(".mantelpack") or members[0].file_size > MAX_ARCHIVE:
                raise Refused("The .zip copy must hold exactly one .mantelpack.")
            data = wrapper.read(members[0])
    if sha256(data) != reviewed:
        raise Refused(
            "This archive is not the one the review read (its SHA-256 differs from "
            "evidence.json's submission.archive_sha256)."
        )
    rebuild = (evidence.get("rebuild") or {}).get("status")
    if rebuild != "identical":
        raise Refused(
            "The review found that this archive does not rebuild from its own source "
            f"(rebuild: {rebuild}); request changes rather than publishing other bytes."
        )
    return data


def _collisions(root, package_id, version, slug, data):
    ledger = read_ledger((root / "reviews.json").read_bytes())
    existing = releases_in_tree(root)
    if (package_id, version) in existing:
        kind, _, build = existing[(package_id, version)]
        if build() == data:
            raise Refused(f"{package_id} {version} is already listed as a {kind}; nothing to add.")
        raise Refused(
            f"{package_id} {version} is already listed with other bytes: published bytes never "
            "change, so the author must raise the version."
        )
    for record in ledger.records:
        if (record.id, record.version) == (package_id, version) and record.archive_sha256 != sha256(data):
            raise Refused(
                f"reviews.json already holds a record for {package_id} {version} with other bytes; "
                "the author must raise the version."
            )
    if slug in {value[1] for value in existing.values()} or (root / "packs" / slug).exists():
        raise Refused(f"The slug {slug} is taken; pass another with --slug.")
    kinds = {value[0] for key, value in existing.items() if key[0] == package_id}
    return kinds


def unpack_submission(root, archive, evidence, *, slug=None, mood=None, description=None,
                      distribution="library", min_host=None):
    """Write the canonical source of one reviewed archive into the tree at `root`, and return
    (kind, slug, source SHA-256). Nothing is written unless the source rebuilds the exact
    archive."""
    data = submitted_archive(archive, evidence)
    with tempfile.TemporaryDirectory(prefix="mantel-intake-") as temporary:
        copy = Path(temporary) / "submission.mantelpack"
        copy.write_bytes(data)
        return _unpack_archive(root, copy, data, slug, mood, description, distribution, min_host)


def _unpack_archive(root, archive, data, slug, mood, description, distribution, min_host):
    result = inspect_archive(archive)
    if not result.valid or result.manifest is None or result.definition is None:
        raise Refused(f"The archive does not validate: {result.error or 'invalid'}.")
    package_id, version = result.manifest.id, result.manifest.version
    if handle_of(package_id) == "local":
        raise Refused("local/ marks a household's own export; the author rebuilds it under a handle.")
    if distribution not in DISTRIBUTIONS:
        raise Refused(f"distribution must be one of {', '.join(DISTRIBUTIONS)}.")
    if min_host is not None and not MIN_HOST.fullmatch(min_host):
        raise Refused("--min-host must be a version such as 1.4.0.")
    slug = slug or package_id.split("/", 1)[1].replace(".", "-")
    if not SLUG.fullmatch(slug):
        raise Refused(f"{slug!r} is not a slug (lowercase letters, digits and hyphens).")
    kinds = _collisions(root, package_id, version, slug, data)
    is_pack = isinstance(result.definition, PackDefinition)
    if kinds and kinds != {"pack" if is_pack else "definition"}:
        raise Refused(f"{package_id} is already listed as another kind of asset.")
    if is_pack:
        return "pack", slug, _unpack_pack(root, archive, data, slug, distribution, min_host)
    return "definition", slug, _unpack_definition(
        root, result, data, slug, mood, description, distribution, min_host
    )


def _unpack_definition(root, result, data, slug, mood, description, distribution, min_host):
    if mood is None or description is None:
        raise Refused("A design needs --mood and --description (the card's words, from the issue).")
    manifest = result.manifest
    definition = result.definition.model_dump(mode="json")
    item = {
        "slug": slug,
        "id": manifest.id,
        "version": manifest.version,
        "distribution": distribution,
        "mood": " ".join(mood.split()),
        "description": " ".join(description.split()),
    }
    if min_host is not None:
        item["min_host"] = min_host
    if build_package(manifest.id, manifest.version, result.definition) != data:
        # The author's own manifest (publisher, licence, attribution): kept so the entry
        # rebuilds these bytes; id, version and the definition hash come from the entry.
        item["manifest"] = {
            key: value
            for key, value in manifest.model_dump(mode="json").items()
            if key not in DERIVED_MANIFEST_KEYS
        }
    item["definition"] = definition
    try:
        check_entry(item)
    except ValueError as error:
        raise Refused(str(error)) from error
    if definition_archive(item) != data:
        raise Refused(
            f"{manifest.id} {manifest.version}: its catalog entry would not rebuild the "
            "submitted archive byte for byte."
        )
    entries = listed_definitions(root)
    entries.append(item)
    write_json(root / "definitions/catalog.json", entries)
    return reviewed_source(item)


def _unpack_pack(root, archive, data, slug, distribution, min_host):
    if min_host is not None:
        raise Refused("A pack's min_host is not catalog metadata yet; leave --min-host out.")
    destination = root / "packs" / slug
    with tempfile.TemporaryDirectory(prefix="mantel-intake-") as temporary:
        source = unpack(archive, Path(temporary) / "source")
        _, _, rebuilt = read_source(source)
        if rebuilt != data:
            raise Refused(f"packs/{slug}: the unpacked source does not rebuild the submitted archive.")
        shutil.copytree(source.parent, destination)
    placed = _json(root / "packs/catalog.json")
    placed.append({"slug": slug, "distribution": distribution})
    write_json(root / "packs/catalog.json", placed)
    return sha256((destination / "source.json").read_bytes())


def checklist(kind, slug, package_id, version, source_sha256, handle_known):
    """The pull request's checklist, printed for the maintainer to paste."""
    lines = [
        f"Add {package_id} {version} ({kind}, slug {slug}).",
        "",
        f"- [ ] Source written: {'definitions/catalog.json' if kind == 'definition' else f'packs/{slug}/ and packs/catalog.json'}; "
        f"source_sha256 {source_sha256}.",
        "- [ ] `python tools/check.py` and `python tools/rebuild.py` pass (the rebuild equals the reviewed archive).",
        "- [ ] Handle: " + ("already registered to the submitting account." if handle_known else "first-time: run `tools/intake.py register` (the issue author's account id)."),
        "- [ ] The review report (`.review/<n>/report.md`) is linked from the pull request, not committed.",
        "- [ ] `min_host` covers the declared capabilities (the report's checklist).",
        "- [ ] Previews: the owner captures them on the host before signing (LIBRARY_PUBLISHING.md).",
        "- [ ] The owner's record: `tools/intake.py approve` after reading the report; CI stays red until it is in.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------
# register


def submitter_account(evidence, login=None, account_id=None):
    """(login, numeric account id): from the skill's intake, which read them from GitHub's
    issue or pull-request author metadata, or given explicitly by the maintainer (who read them
    with `gh api users/<login> --jq .id`). Never from the submission itself."""
    if login is not None or account_id is not None:
        if login is None or account_id is None:
            raise Refused("Give both --login and --account-id, or neither.")
        return login, account_id
    submission = evidence.get("submission") or {}
    submitter = submission.get("submitter") or {}
    if submission.get("source") not in ("issue", "pr"):
        raise Refused(
            "This review's intake was local, so it holds no GitHub author metadata: give "
            "--login and --account-id from `gh api users/<login> --jq .id`."
        )
    return submitter.get("login"), submitter.get("id")


def register_handle(root, handle, login, account_id, display_name):
    """Add a first-time handle bound to one GitHub account. Returns False when the handle is
    already registered to that account (nothing to do)."""
    if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        raise Refused(f"{handle!r} is not a handle.")
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        raise Refused(f"{login!r} is not a GitHub login.")
    if type(account_id) is not int or account_id <= 0:
        raise Refused("The GitHub account id must be a positive number.")
    try:
        plain_text(display_name, 80, "--display-name")
    except ValueError as error:
        raise Refused(str(error)) from error
    registry = read_registry(root / "publishers.json")
    known = publishers_by_handle(registry).get(handle)
    if known is not None:
        if account_id in known["github_account_ids"]:
            return False
        raise Refused(
            f"{handle} is registered to other accounts; a transfer follows identity.md "
            "(a pull request approved from a listed account, or the owner after 30 days)."
        )
    registry["publishers"].append(
        {
            "handle": handle,
            "github_account_ids": [account_id],
            "github_logins": [login],
            "display_name": " ".join(display_name.split()),
        }
    )
    problems = registry_problems(registry)
    if problems:
        raise Refused("publishers.json would break its rules: " + "; ".join(problems))
    write_json(root / "publishers.json", registry)
    return True


# ---------------------------------------------------------------------------------------------
# approve


def parse_statuses(values):
    statuses = {}
    for value in values or []:
        area, _, status = value.partition("=")
        if area not in AREAS or status not in STATUSES:
            raise Refused(f"--status {value!r}: use AREA=STATUS, areas {', '.join(AREAS)}.")
        statuses[area] = status
    return statuses


def approve(root, draft, evidence, *, reviewer, verdict, statuses=None, notes=None, date=None):
    """Turn the skill's draft record into the owner's ledger record, and add it to
    reviews.json. Returns the record written."""
    registry = read_registry(root / "publishers.json")
    if not reviewer or reviewer.casefold() not in maintainer_logins(registry):
        raise Refused(
            "The reviewer must be the person deciding, a login registered to the mantel handle; "
            "the tools never name one."
        )
    if verdict not in LEDGER_VERDICTS:
        raise Refused(
            f"A {verdict} verdict is said on the issue; remove the source from the pull request. "
            "Only approved or preview enter the ledger beside a source."
        )
    for field in ("reviewer", "reviewed_at", "verdict"):
        if draft.get(field) is not None:
            raise Refused(f"The draft already has a {field}: start from the skill's record.json.")
    package_id, version = draft.get("id"), draft.get("version")
    submitted = ((evidence.get("submission") or {}).get("archive_sha256"),
                 (evidence.get("release") or {}).get("id"))
    if submitted != (draft.get("archive_sha256"), package_id):
        raise Refused(
            "The draft does not name the submitted archive (its hash or id differs from "
            "evidence.json): parity with the submission cannot be shown."
        )
    kind, archive, source_sha256, distribution = source_for(root, package_id, version)
    if kind != draft.get("kind"):
        raise Refused(f"The draft is for a {draft.get('kind')}; the tree holds a {kind}.")
    if sha256(archive) != draft["archive_sha256"]:
        raise Refused(
            f"The tree's source for {package_id} {version} builds other bytes than the reviewed "
            "archive; unpack it again from the submission."
        )
    if draft.get("source_sha256") not in (None, source_sha256):
        raise Refused("The draft names another source hash than the tree's source.")
    changes = parse_statuses(statuses) if not isinstance(statuses, dict) else statuses
    settled = dict(draft.get("statuses") or {})
    for area, status in changes.items():
        if area in TOOL_AREAS and settled.get(area) != status:
            raise Refused(f"{area} is settled by the tools ({settled.get(area)}); it is not overruled.")
        settled[area] = status
    pending = sorted(area for area, status in settled.items() if status == "pending")
    failed = sorted(area for area, status in settled.items() if status == "fail")
    if failed:
        raise Refused(f"{', '.join(failed)} failed; a failed review is never {verdict}.")
    if verdict == "approved" and pending:
        raise Refused(f"An approval settles every status; still pending: {', '.join(pending)}.")
    registered = publishers_by_handle(registry)
    if draft.get("submitter_handle") != handle_of(package_id) or handle_of(package_id) not in registered:
        raise Refused(
            f"The submitter handle must be {handle_of(package_id)}, registered in publishers.json "
            "(run register for a first-time handle)."
        )
    record = {
        "id": package_id,
        "version": version,
        "kind": kind,
        "archive_sha256": draft["archive_sha256"],
        "source_sha256": source_sha256,
        "submitter_handle": draft["submitter_handle"],
        "reviewer": reviewer,
        "reviewed_at": date or datetime.date.today().isoformat(),
        "statuses": settled,
        "verdict": verdict,
        "notes": notes or "Owner review of the exact submitted archive from the mantel-asset-review report.",
    }
    try:
        ReviewRecord.model_validate(record)
    except ValueError as error:
        raise Refused(f"The record is not valid: {error}") from error
    path = root / "reviews.json"
    ledger = json.loads(path.read_text(encoding="utf-8"))
    if any((item["id"], item["version"]) == (package_id, version) for item in ledger["records"]):
        raise Refused(f"reviews.json already holds a record for {package_id} {version}.")
    ledger["records"].append(record)
    try:
        require_review(
            read_ledger(json.dumps(ledger).encode()),
            package_id,
            version,
            archive_sha256=sha256(archive),
            source_sha256=source_sha256,
            distribution=distribution,
        )
    except ValueError as error:
        raise Refused(str(error)) from error
    write_json(path, ledger)
    return record


# ---------------------------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("unpack", help="write a reviewed archive's canonical source")
    one.add_argument("archive", type=Path)
    one.add_argument("--evidence", type=Path, required=True)
    one.add_argument("--slug")
    one.add_argument("--mood")
    one.add_argument("--description")
    one.add_argument("--distribution", default="library", choices=DISTRIBUTIONS)
    one.add_argument("--min-host")
    two = commands.add_parser("register", help="add a first-time handle to publishers.json")
    two.add_argument("--evidence", type=Path, required=True)
    two.add_argument("--display-name", required=True)
    two.add_argument("--login")
    two.add_argument("--account-id", type=int)
    three = commands.add_parser("approve", help="the owner's ledger record from the draft")
    three.add_argument("--draft", type=Path, required=True)
    three.add_argument("--evidence", type=Path, required=True)
    three.add_argument("--reviewer", required=True)
    three.add_argument("--verdict", required=True, choices=("approved", "preview", "changes-requested", "rejected"))
    three.add_argument("--status", action="append", default=[], metavar="AREA=STATUS")
    three.add_argument("--notes")
    three.add_argument("--date")
    args = parser.parse_args(argv)
    root = args.root
    try:
        evidence = _json(args.evidence)
        if args.command == "unpack":
            kind, slug, source_sha256 = unpack_submission(
                root,
                args.archive,
                evidence,
                slug=args.slug,
                mood=args.mood,
                description=args.description,
                distribution=args.distribution,
                min_host=args.min_host,
            )
            release = evidence.get("release") or {}
            handle = handle_of(release.get("id", ""))
            known = handle in publishers_by_handle(read_registry(root / "publishers.json"))
            print(checklist(kind, slug, release.get("id"), release.get("version"), source_sha256, known))
        elif args.command == "register":
            handle = handle_of((evidence.get("release") or {}).get("id", ""))
            login, account_id = submitter_account(evidence, args.login, args.account_id)
            added = register_handle(root, handle, login, account_id, args.display_name)
            print(f"Registered {handle} to account {account_id} ({login})." if added else
                  f"{handle} is already registered to account {account_id}; nothing to add.")
        else:
            record = approve(
                root,
                _json(args.draft),
                evidence,
                reviewer=args.reviewer,
                verdict=args.verdict,
                statuses=args.status,
                notes=args.notes,
                date=args.date,
            )
            print(f"Recorded {record['verdict']} for {record['id']} {record['version']} by {record['reviewer']}.")
    except Refused as error:
        print(f"Refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
