#!/usr/bin/env python
import os

from dotenv import load_dotenv

from find_oss.cli import main


def run() -> int:
    load_dotenv()
    os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
    return main()


if __name__ == "__main__":
    raise SystemExit(run())
