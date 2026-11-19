"""Synthetic private FIX2 core-shadow staging tests; never invoke real installer."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_core_shadow_installer as shadow
from test_unified_delta_bundle import Fixture


class TestDeltaCoreShadowInstaller(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic_original_gog"
        self.source.mkdir()
        self.fixture = Fixture(self.source)
        self.stage = self.root / "temporary_stage" / "payload"
        a, b = self.fixture.context()
        with a, b:
            self.zip, self.manifest = shadow.bundle.build_bundle_bytes(
                self.source, self.fixture.xml, self.fixture.assets,
                expected_rules_sha=self.fixture.rules_sha,
                check_exe=False,
            )

    def tearDown(self):
        self.tmp.cleanup()

    def stage_once(self, zipped=None):
        first, second = self.fixture.context()
        with first, second:
            return shadow.restore_assets_from_private_zip(
                self.source, zipped if zipped is not None else self.zip,
                self.stage, expected_rules_sha=self.fixture.rules_sha,
                check_exe=False
            )

    def test_18_assets_materialized_only_from_zip_and_originals(self):
        # Remove every full synthetic target asset from the private source
        # directory to PROVE that the shadow stager does not use them.
        expected = self.fixture.targets.copy()
        for f in self.fixture.assets.values():
            f.unlink()
        proof, produced = self.stage_once()
        self.assertEqual(proof["verified_iso_and_xfile_uses"], 48)
        self.assertEqual(proof["reconstructed_unique_pairs"], 20)
        self.assertEqual(len(produced), 18)
        self.assertEqual(set(produced), set(expected))
        self.assertEqual(
            (self.stage / "Regeln.xml").read_bytes(), self.fixture.xml
        )
        for name, data in expected.items():
            self.assertEqual((self.stage / "Daten" / name).read_bytes(), data)
            self.assertEqual(
                hashlib.sha256(data).hexdigest(), produced[name]
            )
        self.assertEqual(
            (self.source / "cloud_saves/DIALOG.RSP").read_bytes(),
            b"PROTECTED-USER-SAVE-DO-NOT-TOUCH",
        )
        for disc, original in self.fixture.original_images.items():
            self.assertEqual((self.source / disc).read_bytes(), original)

    def test_staging_cannot_overwrite_existing_payload(self):
        self.stage.mkdir(parents=True)
        sentinel = self.stage / "KEEP"
        sentinel.write_text("no-overwrite", encoding="utf-8")
        with self.assertRaisesRegex(shadow.ShadowInstallerError, "existiert"):
            self.stage_once()
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "no-overwrite")

    def test_staging_cannot_write_into_original_source(self):
        destination = self.source / "payload"
        a, b = self.fixture.context()
        with a, b, self.assertRaisesRegex(shadow.ShadowInstallerError, "Staging"):
            shadow.restore_assets_from_private_zip(
                self.source, self.zip, destination,
                expected_rules_sha=self.fixture.rules_sha, check_exe=False
            )
        self.assertFalse(destination.exists())

    def test_corrupted_private_zip_rejected_before_staging(self):
        blob = self.zip[:-37] + b"\0"*37
        with self.assertRaises((shadow.bundle.BundleError, zipfile.BadZipFile)):
            self.stage_once(blob)
        self.assertFalse(self.stage.exists())

    def test_source_cd_modified_rejected_before_staging(self):
        cd = self.source / "HARVEST3.DAT"
        cd.write_bytes(cd.read_bytes() + b"BAD")
        with self.assertRaisesRegex(shadow.bundle.BundleError, "CD-SHA-256"):
            self.stage_once()
        self.assertFalse(self.stage.exists())

    def test_default_path_verifier_blocks_existing_target(self):
        source = self.source
        zipfile = self.root / "PRIVATE-DELTA.zip"
        zipfile.write_bytes(self.zip)
        parent = self.root / "new_install_parent"
        parent.mkdir()
        t = parent / shadow.TEST_TARGET_NAME
        t.mkdir()
        with self.assertRaisesRegex(shadow.ShadowInstallerError, "bereits"):
            shadow.verify_paths(source, zipfile, parent, None)
        self.assertTrue(t.is_dir())

    def test_target_inside_original_source_is_forbidden(self):
        file = self.root / "private-deltas.zip"
        file.write_bytes(self.zip)
        with self.assertRaisesRegex(shadow.ShadowInstallerError, "getrennt"):
            shadow.verify_paths(self.source, file, self.source, None)

    def test_missing_or_mislabeled_bundle_rejected(self):
        file = self.root / "missing.zip"
        with self.assertRaisesRegex(shadow.ShadowInstallerError, "fehlt"):
            shadow.verify_paths(self.source, file, None, None)

    def test_preflight_cannot_run_native_core_implicitly(self):
        self.assertFalse(shadow.nested(self.source, self.root / "outside"))
        self.assertTrue(shadow.nested(self.source, self.source / "cloud_saves"))
        # There is no call to subprocess.run in the staging function.
        with mock.patch.object(shadow.subprocess, "run", side_effect=AssertionError(
                "Subprocess must never be called by staging")):
            proof, paths = self.stage_once()
            self.assertEqual(len(paths), 18)
            self.assertEqual(proof["target_asset_count"], 18)

    def test_reference_existing_rc3b_only_readable_and_not_identical_to_source(self):
        file = self.root / "private-deltas.zip"
        file.write_bytes(self.zip)
        existing = self.root / "existing_rc3b"
        existing.mkdir()
        for name in shadow.CORE_CHECK_FILES:
            (existing / name).write_bytes(b"SYNTHETIC-REFERENCE-NO-GAME-DATA")
        with self.assertRaises(shadow.ShadowInstallerError):
            shadow.verify_paths(self.source, file, self.root, self.source)
        s, z, t, ref = shadow.verify_paths(
            self.source, file, self.root, existing
        )
        self.assertEqual(ref, existing.resolve())
        self.assertEqual(t.name, shadow.TEST_TARGET_NAME)
        self.assertFalse(t.exists())

    def test_low_disk_space_aborts_before_core_execution(self):
        # Synthetic ISO files are tiny; force an insufficient free-space
        # condition without ever starting the proprietary executable.
        target_parent = self.root / "new-target"
        target_parent.mkdir()
        target = target_parent / shadow.TEST_TARGET_NAME
        with mock.patch.object(shadow.shutil, "disk_usage",
                               return_value=type("Space", (), {"free": 1})()):
            with self.assertRaisesRegex(shadow.ShadowInstallerError, "Speicherplatz"):
                shadow.check_disk_reserve(self.source, target)
        self.assertFalse(target.exists())

    def test_reference_rc3b_cannot_contain_new_test_target(self):
        file = self.root / "private-deltas.zip"
        file.write_bytes(self.zip)
        reference = self.root / "existing_rc3b"
        reference.mkdir()
        for name in shadow.CORE_CHECK_FILES:
            (reference / name).write_bytes(b"SYNTHETIC-REFERENCE")
        with self.assertRaisesRegex(shadow.ShadowInstallerError, "getrennt"):
            shadow.verify_paths(self.source, file, reference, reference)

    def test_local_stage_output_not_game_or_repo(self):
        proof, paths = self.stage_once()
        self.assertNotIn(str(self.source), str(paths))
        self.assertTrue(self.stage.is_dir())
        self.assertEqual(len(list((self.stage / "Daten").glob("*.bin"))), 18)
        self.assertEqual(
            proof["verified_loose_root_files"], 2
        )


if __name__ == "__main__":
    unittest.main()
