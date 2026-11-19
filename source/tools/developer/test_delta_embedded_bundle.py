"""Synthetic-only embedded-delta tests: no real game or translated bytes."""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_embedded_bundle as embedded
import delta_onepass_installer as onepass
import delta_onepass_wizard as wizard


def make_fake_zip(root: Path, *, bad_layout: bool = False) -> Path:
    directory = root / embedded.EMBEDDED_DIR
    directory.mkdir(parents=True)
    p = directory / embedded.BUNDLE_NAME
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("bundle.json", '{"synthetic_fixture_only":true}')
        z.writestr("Regeln.xml", "<synthetic-not-game-data />")
        for index in range(19 if bad_layout else 20):
            z.writestr(f"deltas/FAKE_{index:02}.z", b"synthetic-not-real-delta")
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    (directory / embedded.SHA_NAME).write_text(digest + "\n", encoding="ascii")
    return p


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = make_fake_zip(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_embedded_bundle_is_path_independent(self):
        self.assertEqual(embedded.embedded_bundle_path(self.root), self.bundle)
        other = self.root / "D Laufwerk Archiv" / "Spiele & Umlaute ÄÖÜ" / "TEMP"
        other.mkdir(parents=True)
        copied = make_fake_zip(other)
        self.assertEqual(embedded.embedded_bundle_path(other), copied)
        self.assertEqual(copied.read_bytes(), self.bundle.read_bytes())
        # The same SHA is valid at completely different local extraction paths.
        self.assertEqual(onepass.choose_bundle_argument(None, self.root), self.bundle)
        self.assertEqual(onepass.choose_bundle_argument(None, other), copied)

    def test_frozen_child_does_not_get_parent_meipass_bundle_path(self):
        command = wizard.child_command(
            Path(r"C:\Temporary UI\Harvester German.exe"),
            Path("ignored.py"), True,
            Path(r"E:\GOG\Harvester 1996"),
            None,
            Path(r"D:\Games & Mods"),
            execute=True,
        )
        self.assertNotIn("--bundle", command)
        self.assertEqual(command[0], r"C:\Temporary UI\Harvester German.exe")
        self.assertIn("--source", command)
        self.assertIn("--target-parent", command)
        self.assertIn("--execute-onepass", command)

    def test_source_script_requires_external_delta_when_not_frozen(self):
        with self.assertRaisesRegex(ValueError, "Delta-Bundle"):
            wizard.child_command(
                Path("python"), Path("onepass.py"), False,
                Path("gog"), None, Path("parent")
            )
        explicit = self.root / "my-private-delta.zip"
        self.assertEqual(onepass.choose_bundle_argument(explicit, self.root / "no_bundle"), explicit)

    def test_bundled_installer_refuses_override_zip(self):
        with self.assertRaisesRegex(onepass.OnePassError, "eingebaute Delta"):
            onepass.choose_bundle_argument(self.root / "other.zip", self.root)

    def test_missing_delta_and_missing_manifest_both_rejected(self):
        (self.bundle.parent / embedded.SHA_NAME).unlink()
        with self.assertRaisesRegex(embedded.EmbeddedDeltaError, "unvollständig"):
            embedded.embedded_bundle_path(self.root)
        (self.bundle.parent / embedded.SHA_NAME).write_text("a"*64+"\n",encoding="ascii")
        with self.assertRaisesRegex(embedded.EmbeddedDeltaError, "Baunachweis"):
            embedded.embedded_bundle_path(self.root)

    def test_missing_bundle_source_only_returns_none(self):
        empty = self.root / "no-resources"
        empty.mkdir()
        self.assertIsNone(embedded.embedded_bundle_path(empty))
        with self.assertRaisesRegex(onepass.OnePassError, "Kein eingebautes Delta"):
            onepass.choose_bundle_argument(None, empty)

    def test_corrupt_zip_structure_rejected_even_with_updated_sha(self):
        (self.bundle.parent / embedded.SHA_NAME).unlink()
        self.bundle.unlink()
        make_fake_zip(self.root / "bad-layout", bad_layout=True)
        bad = self.root / "bad-layout"
        with self.assertRaisesRegex(embedded.EmbeddedDeltaError, "Layout"):
            embedded.embedded_bundle_path(bad)

    def test_wrong_embedded_hash_format_rejected(self):
        (self.bundle.parent / embedded.SHA_NAME).write_text("NOT_A_SHA\n",encoding="ascii")
        with self.assertRaisesRegex(embedded.EmbeddedDeltaError, "Format"):
            embedded.embedded_bundle_path(self.root)

    def test_explicit_zip_does_not_bypass_mismatched_embedded_manifest(self):
        (self.bundle.parent / embedded.SHA_NAME).write_text("f"*64+"\n",encoding="ascii")
        with self.assertRaises(embedded.EmbeddedDeltaError):
            onepass.choose_bundle_argument(self.root / "other.zip", self.root)

    def test_zip_symlink_is_refused(self):
        # Windows symlink privileges vary; mock symlink classification directly.
        with mock.patch.object(Path, "is_symlink", autospec=True,
                               side_effect=lambda p: p == self.bundle):
            with self.assertRaisesRegex(embedded.EmbeddedDeltaError, "verlinkt"):
                embedded.embedded_bundle_path(self.root)


if __name__ == "__main__":
    unittest.main()
