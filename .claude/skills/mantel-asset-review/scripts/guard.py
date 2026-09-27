#!/usr/bin/env python3
"""PreToolUse hook for a review session: deny every tool call `policy.decide` refuses.

Registered in the frontmatter of the skill (`SKILL.md`) and of the reviewer agent
(`agents/reviewer.md`), so it is active exactly while a review runs. Claude Code passes the
call as JSON on stdin; exit 2 with a reason on stderr blocks it, exit 0 lets the normal
permission rules decide. Outside a clean public checkout it blocks everything but the
passthrough tools, so a review cannot start next to keys.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import policy


def verdict(payload: dict) -> str | None:
    """The reason a call is denied, or None."""
    tool = str(payload.get("tool_name", ""))
    data = payload.get("tool_input") or {}
    cwd = Path(payload["cwd"]) if payload.get("cwd") else None
    if tool in policy.PASSTHROUGH:
        return None
    problems = policy.checkout_problems(policy.ROOT)
    if problems:
        return "Not a review checkout: " + "; ".join(problems)
    return policy.decide(tool, data if isinstance(data, dict) else {}, cwd)


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("mantel-asset-review guard: unreadable hook input", file=sys.stderr)
        return 2
    reason = verdict(payload if isinstance(payload, dict) else {})
    if reason:
        print(f"mantel-asset-review guard: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
