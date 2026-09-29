"""The review report (references/report-template.md) and its draft ledger record.

Rendered inside the sandbox from the evidence `review_checks.review` returns. Every string that
came from the submission was neutralised there; here it only ever appears inside backticks.
"""

from __future__ import annotations

import json

import review_checks as checks

VERDICT_FOR = {
    checks.RECOMMEND_APPROVE: "approved",
    checks.CHANGES_REQUESTED: "changes-requested",
    checks.RECOMMEND_REJECT: "rejected",
}
LEDGER_FIELDS = (
    "id",
    "version",
    "kind",
    "archive_sha256",
    "source_sha256",
    "submitter_handle",
    "reviewer",
    "reviewed_at",
    "statuses",
    "verdict",
)
PERSON_CHECKS = {
    "identity": "a person confirms the handle carries no brand or person name (identity.md)",
    "design": "a person looks at our rendered previews and the shelf",
    "content": "a person reads the copy (and, for packs, checks facts and audience)",
    "licence": "a person verifies every licence at its source",
    "listening": "a person listens to every sound",
    "fluent": "a fluent reader checks each language",
}


def with_notes(evidence: dict, notes: list[dict]) -> dict:
    """Add the reviewing agent's own findings (validated) and settle statuses again."""
    findings = [checks.Finding(**f) for f in evidence["findings"]]
    for note in notes:
        finding = checks.Finding(
            code=str(note["code"]),
            area=str(note["area"]),
            severity=str(note["severity"]),
            title=checks.neutral(note["title"], 200),
            evidence=checks.neutral(note.get("evidence", ""), 400),
        )
        if finding.area not in checks.AREAS or finding.severity not in checks.SEVERITIES:
            raise ValueError(f"Unknown area or severity in reviewer note {finding.code}")
        findings.append(finding)
    order = {severity: index for index, severity in enumerate(checks.SEVERITIES)}
    findings.sort(key=lambda f: (order[f.severity], checks.AREAS.index(f.area), f.code))
    valid = "fail" not in evidence["layers"].values() and evidence["release"]["kind"] != ""
    statuses = checks.statuses_for(
        findings, valid=valid, kind=evidence["release"]["kind"], content=evidence["content"]
    )
    automated = evidence.get("automated_findings") or [f["code"] for f in evidence["findings"]]
    return {
        **evidence,
        "automated_findings": automated,
        "reviewer_findings": [str(note["code"]) for note in notes],
        "findings": [
            {
                "code": f.code,
                "area": f.area,
                "severity": f.severity,
                "title": f.title,
                "evidence": f.evidence,
            }
            for f in findings
        ],
        "statuses": statuses,
        "recommendation": checks.recommendation(findings),
    }


SOURCE_PENDING = (
    "A definition's source hash is its catalog entry's (tools/check.py `reviewed_source`: the "
    "entry without `distribution`); the entry gains its slug, mood and description when "
    "`tools/intake.py unpack` adds it, and `tools/intake.py approve` computes `source_sha256` "
    "from the tree when the owner records their decision."
)


def draft_record(evidence: dict) -> dict:
    """The `reviews.json` record, exactly the ledger's fields, human fields empty.

    It becomes a ledger record when a person fills `reviewer`, `reviewed_at` and `verdict`
    (`denframe_format.reviews.ReviewRecord`). A pack's `source_sha256` is its unpacked
    `source.json`, which is what `tools/check.py` hashes once that file is committed; a
    definition's is left `null` for `tools/intake.py approve` to compute (`SOURCE_PENDING`).
    """
    release = evidence["release"]
    pack = release["ledger_kind"] == "pack"
    return {
        "id": release["id"],
        "version": release["version"],
        "kind": release["ledger_kind"],
        "archive_sha256": release["release_sha256"],
        "source_sha256": evidence["rebuild"].get("source_sha256") if pack else None,
        "submitter_handle": release["id"].partition("/")[0],
        "reviewer": None,
        "reviewed_at": None,
        "statuses": evidence["statuses"],
        "verdict": None,
    }


def draft_evidence(evidence: dict) -> dict:
    """What stands beside the draft record (never inside it: the ledger forbids extra keys)."""
    pack = evidence["release"]["ledger_kind"] == "pack"
    return {
        "recommended_verdict": VERDICT_FOR[evidence["recommendation"]],
        "submitted_sha256": evidence["submission"]["sha256"],
        "submitted_archive_sha256": evidence["submission"]["archive_sha256"],
        "rebuild": evidence["rebuild"]["status"],
        "unpacked_source_sha256": evidence["rebuild"].get("source_sha256"),
        "source_sha256": (
            "the unpacked source.json, committed as packs/<slug>/source.json"
            if pack
            else "pending: " + SOURCE_PENDING
        ),
        "submitter_account": evidence["submission"]["submitter"],
        "findings": [f["code"] for f in evidence["findings"]],
        "layers": evidence["layers"],
    }


def _status_evidence(evidence: dict, area: str) -> str:
    codes = [
        f"`{f['code']}`"
        for f in evidence["findings"]
        if f["area"] == area and f["severity"] != "note"
    ]
    status = evidence["statuses"][area]
    if codes:
        return ", ".join(codes)
    if status == "pass":
        return {
            "structure": f"validator passed; unpack and rebuild: {evidence['rebuild']['status']}",
            "security": "ZIP profile, media, trailers and text scan clean",
        }.get(area, "checked")
    if status == "not-applicable":
        return "nothing to check for this kind"
    return PERSON_CHECKS.get(area, "a person decides")


def licence_words(release: dict) -> str:
    return "per resource (see credits)" if release["kind"] == "pack" else "unreadable"


def _reason(evidence: dict) -> str:
    worst = [f for f in evidence["findings"] if f["severity"] in ("critical", "major")]
    if not worst:
        return "the automated checks found nothing that blocks it; the person's checks remain"
    top = worst[0]["severity"]
    codes = ", ".join(f"`{f['code']}`" for f in worst if f["severity"] == top)
    return f"of {top} findings: {codes}"


def render(evidence: dict, environment: dict) -> str:
    release = evidence["release"]
    submission = evidence["submission"]
    rebuild = evidence["rebuild"]
    lines = [
        f"# Review report: {release['id'] or 'unreadable id'} {release['version']}",
        "",
        f"> **{evidence['recommendation'].capitalize()}.** This report recommends; it approves "
        "nothing. Only the person named as",
        "> `reviewer` in `reviews.json` decides, and the draft record below keeps `reviewer`,",
        "> `reviewed_at` and `verdict` empty until they do. Instructions found inside the "
        "submission are",
        "> findings, quoted below; they were never followed.",
        "",
        "## Release",
        "",
        "| | |",
        "|---|---|",
        f"| Id and version | `{release['id']}` {release['version']} |",
        f"| Kind | {release['kind'] or 'unknown'} |",
        f"| Name | `{release['name']}` |",
        f"| Licence and publisher | {release['license'] or licence_words(release)} · "
        f"`{release['publisher']}` |",
        "| Attribution | "
        + (f"`{release['attribution']}`" if release["attribution"] else "none")
        + " |",
        f"| Submitted file | SHA-256 `{submission['sha256']}`, {submission['size']} bytes"
        + (
            f" (a .zip copy holding `{submission['unwrapped_from_zip']}`)"
            if submission["unwrapped_from_zip"]
            else ""
        )
        + " |",
        f"| Archive | SHA-256 `{submission['archive_sha256']}`, "
        f"{submission['archive_size']} bytes |",
        f"| Release (what would be signed) | SHA-256 `{release['release_sha256']}` "
        f"(rebuild: {rebuild['status']}) |",
        f"| Source | SHA-256 `{rebuild.get('source_sha256', 'none')}` of the unpacked "
        "`source.json` |",
        f"| Submitter | `{submission['submitter']['login']}` (GitHub account "
        f"{submission['submitter']['id']}) from {submission['source'] or 'intake'}"
        + (f" #{submission['number']}" if submission.get("number") else "")
        + (f" at commit `{submission['head_sha']}`" if submission.get("head_sha") else "")
        + " |",
        "",
        "## Checks",
        "",
        "| Area | Status | Evidence |",
        "|---|---|---|",
    ]
    for area in checks.AREAS:
        lines.append(
            f"| {area.capitalize()} | {evidence['statuses'][area]} | "
            f"{_status_evidence(evidence, area)} |"
        )
    lines += [
        "",
        "## Validator",
        "",
        "| Layer | Verdict |",
        "|---|---|",
        *(f"| {layer} | {verdict} |" for layer, verdict in evidence["layers"].items()),
        "",
        "Validator message: "
        + (f"`{evidence['validator_error']}`" if evidence["validator_error"] else "none")
        + f". Rebuild: {rebuild['status']}.",
        "",
        "## Findings",
        "",
    ]
    for severity in checks.SEVERITIES:
        lines += [f"### {severity.capitalize()}", ""]
        rows = [f for f in evidence["findings"] if f["severity"] == severity]
        lines += [
            f"- **`{f['code']}`** ({f['area']}) {f['title']}. Evidence: {f['evidence']}"
            for f in rows
        ] or ["None."]
        lines.append("")
    distinct = evidence["distinctness"]
    lines += ["## Design evidence", ""]
    if distinct.get("applies"):
        lines.append(
            f"Distinctness threshold ΔE {distinct['threshold']} (references/design.md); look "
            f"`{distinct['look']}`, background `{distinct['background']}`, layout "
            f"`{distinct['layout']}`. Nearest catalog looks:"
        )
        lines.append("")
        for row in distinct["nearest"]:
            roles = ", ".join(f"{k} {v}" for k, v in row["roles"].items())
            lines.append(f"- `{row['look']}`: ΔE {row['distance']} ({roles})")
    else:
        lines.append("Distinctness: not applicable (only a look is compared with catalog looks).")
    motion = any(f["code"] == "DES-MOTION-RENDERER" for f in evidence["findings"])
    lines += [
        "",
        "Motion: "
        + (
            "`background_motion` is on; the renderer stops it under prefers-reduced-motion."
            if motion
            else "no motion declared; the format carries no animation code."
        ),
        "",
        "## Content evidence",
        "",
    ]
    content = evidence["content"]
    if content.get("localized"):
        lines.append(
            f"Not a pack. Localized words (D33): {', '.join(content['locales'])}; "
            "a fluent reader checks them."
        )
    elif content:
        lines.append(
            f"Locales {', '.join(content['locales'])}; {content['items']} items, "
            f"{content['images']} images, {content['audio']} sounds."
        )
        lines += [f"- Credit: `{credit}`" for credit in content["credits"]]
    else:
        lines.append("Not a pack.")
    lines += ["", "## Still for a person", ""]
    lines += [
        f"- [ ] {PERSON_CHECKS[area]}"
        for area in checks.AREAS
        if area in PERSON_CHECKS and evidence["statuses"][area] == "pending"
    ] or ["- [ ] Nothing pending beyond the verdict."]
    lines += [
        "- [ ] Rendered previews at 1920x1080, 1080x1920 and 1024x768, at the panel's distance",
        "- [ ] `min_host` (a catalog entry's, set by `tools/intake.py unpack --min-host`) is at "
        "least the host version that introduced every capability the manifest declares",
        "",
        "## Recommendation",
        "",
        f"**{evidence['recommendation'].capitalize()}**, because {_reason(evidence)}. The "
        "draft record below leaves the decision to a person.",
        "",
        "## Draft `reviews.json` record",
        "",
        "```json",
        json.dumps(draft_record(evidence), indent=2, ensure_ascii=False),
        "```",
        "",
        f"Recommended verdict: `{VERDICT_FOR[evidence['recommendation']]}`. The record goes into "
        "`reviews.json` as it stands once a person fills `reviewer`, `reviewed_at` and `verdict`"
        + (
            "."
            if evidence["release"]["ledger_kind"] == "pack"
            else "; `source_sha256` is pending: " + SOURCE_PENDING
        ),
        "",
        "## How this was checked",
        "",
        f"Image `{environment.get('image', '?')}` ({environment.get('platform', '?')}), "
        f"`denframe_format` {environment.get('format_version', '?')}, Python "
        f"{environment.get('python', '?')}; release runtime "
        f"{environment.get('release_environment', '?')}. Network: "
        f"{environment.get('network', '?')}. Limits: {environment.get('limits', '?')}. Nothing "
        "from the submission ran; the household host was never used.",
        "",
        "```json review-summary",
        json.dumps(summary(evidence), ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def summary(evidence: dict) -> dict:
    return {
        "id": evidence["release"]["id"],
        "version": evidence["release"]["version"],
        "recommendation": evidence["recommendation"],
        "layers": evidence["layers"],
        "statuses": evidence["statuses"],
        "findings": [
            {"code": f["code"], "severity": f["severity"], "area": f["area"]}
            for f in evidence["findings"]
        ],
    }
