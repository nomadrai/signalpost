#!/usr/bin/env python3
"""Preserve the starter CLI while using the same supervised bounded runner."""
import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("run_batch.py")), run_name="__main__")
