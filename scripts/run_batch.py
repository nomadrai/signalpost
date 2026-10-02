#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    implementation = Path(__file__).resolve().with_name("run_batch_impl.py")
    runpy.run_path(str(implementation), run_name="__main__")
