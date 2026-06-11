from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from find_oss.saved_searches import SavedSearchError, SavedSearchStore


DEFAULT_STORE = Path(".find-oss/saved-searches.yaml")
DEFAULT_OUTPUT_DIR = Path("output")


def execute_search(query: str, output_dir: Path) -> None:
    from find_oss.service import run_search

    result = run_search(query, output_dir)
    print(result.summary)
    print(f"Report: {result.output_path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="find_oss")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search")
    search.add_argument("query")

    save = commands.add_parser("save")
    save.add_argument("name")
    save.add_argument("query")

    saved = commands.add_parser("saved")
    saved_commands = saved.add_subparsers(dest="saved_command", required=True)
    saved_commands.add_parser("list")
    run = saved_commands.add_parser("run")
    run.add_argument("name")
    update = saved_commands.add_parser("update")
    update.add_argument("name")
    update.add_argument("query")
    delete = saved_commands.add_parser("delete")
    delete.add_argument("name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    store = SavedSearchStore(args.store)
    try:
        if args.command == "search":
            execute_search(args.query, args.output_dir)
        elif args.command == "save":
            item = store.create(args.name, args.query)
            print(f"Saved '{item.name}' as {item.slug}.")
        elif args.saved_command == "list":
            searches = store.list()
            if not searches:
                print("No saved searches.")
            for item in searches:
                print(f"{item.slug}\t{item.name}\t{item.query}")
        elif args.saved_command == "run":
            execute_search(store.get(args.name).query, args.output_dir)
        elif args.saved_command == "update":
            item = store.update(args.name, args.query)
            print(f"Updated '{item.name}'.")
        elif args.saved_command == "delete":
            store.delete(args.name)
            print(f"Deleted '{args.name}'.")
    except (SavedSearchError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    return 0

