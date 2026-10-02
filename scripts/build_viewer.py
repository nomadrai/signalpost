#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.viewer import build_viewer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a static Signalpost profile viewer")
    parser.add_argument("source", help="Envelope JSONL, JSON, or result directory")
    parser.add_argument("output", help="Output directory")
    args = parser.parse_args()
    print(json.dumps(build_viewer(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
