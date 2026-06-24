#!/usr/bin/env python3
"""Tests for stale diagnostic cleanup in build.py.

Uses temporary diagnostic directories to verify dry-run, force, and
current-artifact preservation behavior without touching the real
diagnostic/ directory.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make build.py importable from the project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build import find_stale_diagnostic_artifacts, run_diagnostic_cleanup


class StaleDiagnosticCleanupTests(unittest.TestCase):
    """Test suite for --diagnostic-cleanup functionality."""

    def setUp(self):
        """Create a temporary diagnostic directory with sample artifacts."""
        self.tmpdir = tempfile.TemporaryDirectory()
        self.diag_dir = Path(self.tmpdir.name)

        # Create artifacts for several commits
        self.commits = {
            "aaaa0001": ["build-aaaa0001.logd", "build-aaaa0001.json"],
            "aaaa0002": [
                "build-aaaa0002.logd",
                "build-aaaa0002.json",
                "build-aaaa0002-part001.logd",
                "build-aaaa0002-part002.logd",
            ],
            "aaaa0003": ["build-aaaa0003.logd", "build-aaaa0003.json"],
        }

        for commit_id, filenames in self.commits.items():
            for filename in filenames:
                filepath = self.diag_dir / filename
                filepath.write_text(f"diagnostic data for {commit_id}\n", encoding="utf-8")

        # Current commit is aaaa0003
        self.current_commit = "aaaa0003"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_find_stale_excludes_current_commit(self):
        """Current commit artifacts must never appear in the stale list."""
        stale = find_stale_diagnostic_artifacts(self.diag_dir, self.current_commit)
        stale_names = {p.name for p in stale}

        # Current commit artifacts should NOT be stale
        for name in self.commits["aaaa0003"]:
            self.assertNotIn(name, stale_names, f"Current commit artifact {name} should not be stale")

    def test_find_stale_includes_other_commits(self):
        """Artifacts from other commits should be reported as stale."""
        stale = find_stale_diagnostic_artifacts(self.diag_dir, self.current_commit)
        stale_names = {p.name for p in stale}

        # All non-current commit artifacts should be stale
        expected_stale = set()
        for commit_id in ["aaaa0001", "aaaa0002"]:
            expected_stale.update(self.commits[commit_id])

        self.assertEqual(stale_names, expected_stale)

    def test_find_stale_empty_directory(self):
        """An empty diagnostic directory should return no stale artifacts."""
        empty_dir = Path(tempfile.mkdtemp())
        try:
            stale = find_stale_diagnostic_artifacts(empty_dir, "aaaa0003")
            self.assertEqual(stale, [])
        finally:
            empty_dir.rmdir()

    def test_find_stale_nonexistent_directory(self):
        """A non-existent directory should return no stale artifacts."""
        nonexistent = Path("/tmp/this-should-not-exist-xyz-123")
        stale = find_stale_diagnostic_artifacts(nonexistent, "aaaa0003")
        self.assertEqual(stale, [])

    def test_find_stale_ignores_non_matching_files(self):
        """Files that don't match the build-XXXXXXXX pattern should be ignored."""
        # Add some non-matching files
        (self.diag_dir / "readme.txt").write_text("not a diagnostic", encoding="utf-8")
        (self.diag_dir / "build-short.logd").write_text("too short", encoding="utf-8")
        (self.diag_dir / "random.json").write_text("{}", encoding="utf-8")

        stale = find_stale_diagnostic_artifacts(self.diag_dir, self.current_commit)
        stale_names = {p.name for p in stale}

        self.assertNotIn("readme.txt", stale_names)
        self.assertNotIn("build-short.logd", stale_names)
        self.assertNotIn("random.json", stale_names)

    def test_dry_run_does_not_delete(self):
        """Dry-run mode should list stale artifacts without deleting them."""
        # Capture output by redirecting stdout
        import io
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            count = run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=False)
        finally:
            sys.stdout = old_stdout

        # Should have found stale artifacts
        self.assertGreater(count, 0)

        # All files should still exist
        for commit_id, filenames in self.commits.items():
            for filename in filenames:
                self.assertTrue(
                    (self.diag_dir / filename).exists(),
                    f"Dry-run should not delete {filename}",
                )

    def test_force_actually_deletes(self):
        """Force mode should delete stale artifacts but preserve current commit ones."""
        import io
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            count = run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=True)
        finally:
            sys.stdout = old_stdout

        # Should have found and deleted stale artifacts
        self.assertGreater(count, 0)

        # Stale artifacts should be gone
        for commit_id in ["aaaa0001", "aaaa0002"]:
            for filename in self.commits[commit_id]:
                self.assertFalse(
                    (self.diag_dir / filename).exists(),
                    f"Force mode should delete stale artifact {filename}",
                )

        # Current commit artifacts should still exist
        for filename in self.commits["aaaa0003"]:
            self.assertTrue(
                (self.diag_dir / filename).exists(),
                f"Force mode should preserve current commit artifact {filename}",
            )

    def test_no_stale_artifacts(self):
        """When all artifacts belong to the current commit, nothing is stale."""
        # Remove all non-current commit artifacts
        for commit_id in ["aaaa0001", "aaaa0002"]:
            for filename in self.commits[commit_id]:
                (self.diag_dir / filename).unlink()

        stale = find_stale_diagnostic_artifacts(self.diag_dir, self.current_commit)
        self.assertEqual(stale, [])

    def test_dry_run_returns_correct_count(self):
        """Dry-run should return the exact count of stale artifacts."""
        import io
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            count = run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=False)
        finally:
            sys.stdout = old_stdout

        # aaaa0001: 2 files, aaaa0002: 4 files = 6 total stale
        expected_count = len(self.commits["aaaa0001"]) + len(self.commits["aaaa0002"])
        self.assertEqual(count, expected_count)

    def test_force_returns_correct_count(self):
        """Force mode should return the same count as dry-run for the same directory."""
        import io

        # Dry-run first
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            dry_count = run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=False)
        finally:
            sys.stdout = old_stdout

        # Force on a fresh copy
        self.setUp()
        captured = io.StringIO()
        sys.stdout = captured
        try:
            force_count = run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=True)
        finally:
            sys.stdout = old_stdout

        self.assertEqual(dry_count, force_count)

    def test_chunked_logd_parts_are_stale(self):
        """Chunked .logd parts (build-XXXXXXXX-partNNN.logd) from stale commits should be detected."""
        stale = find_stale_diagnostic_artifacts(self.diag_dir, self.current_commit)
        stale_names = {p.name for p in stale}

        # aaaa0002 has chunked parts
        self.assertIn("build-aaaa0002-part001.logd", stale_names)
        self.assertIn("build-aaaa0002-part002.logd", stale_names)

    def test_current_commit_chunked_parts_preserved(self):
        """Chunked .logd parts for the current commit should be preserved even in force mode."""
        # Add chunked parts for the current commit
        (self.diag_dir / "build-aaaa0003-part001.logd").write_text("chunk1", encoding="utf-8")
        (self.diag_dir / "build-aaaa0003-part002.logd").write_text("chunk2", encoding="utf-8")

        import io
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured

        try:
            run_diagnostic_cleanup(self.diag_dir, self.current_commit, force=True)
        finally:
            sys.stdout = old_stdout

        # Current commit chunked parts should still exist
        self.assertTrue((self.diag_dir / "build-aaaa0003-part001.logd").exists())
        self.assertTrue((self.diag_dir / "build-aaaa0003-part002.logd").exists())
        # Current commit main artifacts should still exist
        self.assertTrue((self.diag_dir / "build-aaaa0003.logd").exists())
        self.assertTrue((self.diag_dir / "build-aaaa0003.json").exists())


if __name__ == "__main__":
    unittest.main()
