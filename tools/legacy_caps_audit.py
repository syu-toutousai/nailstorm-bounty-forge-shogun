#!/usr/bin/env python3
"""Audit script enforcing uppercase LEGACY comment rule across the repository.
"""
"""LEGACY uppercase enforcement audit script.

Rule: Every file containing the word 'legacy' (case-insensitive)
must also contain 'LEGACY' in all caps somewhere in a comment.

Bounty #61
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {'.git', 'diagnostic', '__pycache__', 'node_modules', 'build', 'target'}
EXCLUDE_EXTENSIONS = {'.pyc', '.tsbuildinfo', '.logd', '.lock', '.sum', '.wasm', '.bin'}


def find_violations() -> list[str]:
    violations = []
    for filepath in ROOT.rglob('*'):
        if not filepath.is_file():
            continue
        parts = set(filepath.parts)
        if parts & EXCLUDE_DIRS:
            continue
        if filepath.suffix.lower() in EXCLUDE_EXTENSIONS:
            continue
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            continue
        has_legacy_lower = bool(re.search(r'legacy', content, re.IGNORECASE))
        if not has_legacy_lower:
            continue
        has_legacy_upper = 'LEGACY' in content
        if not has_legacy_upper:
            rel = filepath.relative_to(ROOT)
            violations.append(str(rel))
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print(f"VIOLATIONS: {len(violations)} file(s) contain 'legacy' without 'LEGACY':")
        for v in violations:
            print(f"  - {v}")
        return 1
    else:
        print("PASS: All files containing 'legacy' also contain 'LEGACY'.")
        return 0


if __name__ == '__main__':
    sys.exit(main())
