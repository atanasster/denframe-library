"""The standalone mantel-author command line."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

from .authoring import new_source, read_source, unpack, write_new
from .themes import BUILTIN_THEMES
from .validation import inspect_archive


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="mantel-author", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create an authorable source document")
    new.add_argument("kind", choices=["theme", "block", "content", "pack"])
    new.add_argument("id")
    new.add_argument("output", type=Path)
    new.add_argument("--name", required=True)
    new.add_argument("--publisher", default="Local author")
    new.add_argument("--look", choices=[t["look"] for t in BUILTIN_THEMES], default="modern")
    new.add_argument("--blocks", default="clock")
    for name in ("validate", "build", "unpack", "inspect"):
        command = commands.add_parser(name)
        command.add_argument("source", type=Path)
        if name in ("build", "unpack"):
            command.add_argument("output", type=Path)
        if name == "build":
            command.add_argument("--check", action="store_true", help="Compare an existing output")
        if name == "validate":
            command.add_argument("--json", action="store_true", help="Print per-layer verdicts")
    return result


def main(argv: list[str] | None = None) -> int:
    # Files and command output share the format's UTF-8 encoding, independent of the locale.
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")
    args = parser().parse_args(argv)
    try:
        if args.command == "new":
            item = new_source(args.kind, args.id, args.name, args.look, args.blocks, args.publisher)
            write_new(args.output, (json.dumps(item, ensure_ascii=False, indent=2) + "\n").encode())
            print(args.output)
        elif args.command == "build":
            _, _, data = read_source(args.source)
            if args.check:
                if args.output.read_bytes() != data:
                    raise ValueError("Built archive differs from the existing output")
                print(f"Identical: {args.output}")
            else:
                write_new(args.output, data)
                print(args.output)
        elif args.command == "unpack":
            print(unpack(args.source, args.output))
        elif args.command == "validate" and args.source.suffix == ".json":
            item, definition, archive = read_source(args.source)
            if args.json:
                # Source validation builds first; inspect that exact build for the same report.
                import tempfile

                with tempfile.TemporaryDirectory(prefix="mantel-inspect-") as temporary:
                    path = Path(temporary) / "archive.mantelpack"
                    path.write_bytes(archive)
                    print(json.dumps(inspect_archive(path).summary(), ensure_ascii=False))
            else:
                print(
                    f"Valid {definition.kind}: {item['id']}@{item['version']} "
                    f"({len(archive)} bytes)"
                )
                print("Publisher trust: not checked")
        else:
            inspection = inspect_archive(args.source)
            if args.command == "inspect" or args.json:
                print(json.dumps(inspection.summary(), ensure_ascii=False))
            else:
                for layer, verdict in inspection.layers.items():
                    print(f"{layer}: {verdict}")
                if inspection.error:
                    print(inspection.error, file=sys.stderr)
            return 0 if inspection.valid else 1
    except (ValueError, OSError, RecursionError) as exc:
        print(f"mantel-author: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
