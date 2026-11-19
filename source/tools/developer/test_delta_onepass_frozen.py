"""Private frozen-payload self-test, never uses real GOG media."""
from __future__ import annotations
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest import mock
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_onepass_installer as onepass


class FrozenShellTests(unittest.TestCase):
    def test_source_payload_check_is_read_only(self):
        capture=io.StringIO()
        with redirect_stdout(capture):
            result=onepass.packaged_preflight()
        self.assertEqual(result["manifest_locations"],196)
        self.assertEqual(result["film_count"],66)
        self.assertFalse(result["legal_clearance"])
        self.assertIn("Quellcode-Vorprüfung PASS",capture.getvalue())

    def _fake_payload(self,root):
        p=root/"payload"
        p.mkdir()
        for name in ("Regeln.xml","VideoManifest.xml",onepass.core.CORE_EXE):
            (p/name).write_bytes(b"SYNTHETIC-PAYLOAD")
        return p

    def _patches(self,root):
        def hashed(path):
            if path.name=="Regeln.xml":
                return onepass.audit.EXPECTED_RULES_SHA256
            if path.name=="VideoManifest.xml":
                return onepass.rc3.MANIFEST_HASH
            return "a"*64
        return (
            mock.patch.object(onepass,"REPO_ROOT",root),
            mock.patch.object(onepass.sys,"frozen",True,create=True),
            mock.patch.object(onepass.core,"hash_file",side_effect=hashed),
            mock.patch.object(onepass.core,"check_verified_core"),
            mock.patch.object(onepass.video,"validate_video_inputs",
                return_value=[{"film_id":f"F{i%66:03d}"} for i in range(196)])
        )

    def test_synthetic_frozen_payload_without_full_fix2_targets_passes(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            self._fake_payload(root)
            ps=self._patches(root)
            with ps[0],ps[1],ps[2],ps[3],ps[4]:
                result=onepass.packaged_preflight()
            self.assertEqual(result["film_count"],66)
            self.assertFalse(result["full_FIX2_asset_files_bundled"])

    def test_frozen_refuses_full_fix2_bin_data_folder(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            p=self._fake_payload(root)
            (p/"Daten").mkdir()
            (p/"Daten"/("0"*64+".bin")).write_bytes(b"PROHIBITED")
            ps=self._patches(root)
            with ps[0],ps[1],ps[2],ps[3],ps[4]:
                with self.assertRaisesRegex(onepass.OnePassError,"UNZULÄSSIGE"):
                    onepass.packaged_preflight()

    def test_frozen_refuses_missing_native_core_patcher(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            p=self._fake_payload(root)
            (p/onepass.core.CORE_EXE).unlink()
            ps=self._patches(root)
            with ps[0],ps[1],ps[2],ps[3],ps[4]:
                with self.assertRaisesRegex(onepass.OnePassError,"Fehlende"):
                    onepass.packaged_preflight()

    def test_frozen_refuses_modified_rules(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            self._fake_payload(root)
            ps=self._patches(root)
            with ps[0],ps[1],ps[3],ps[4]:
                with mock.patch.object(onepass.core,"hash_file",return_value="0"*64):
                    with self.assertRaisesRegex(onepass.OnePassError,"Regeln-SHA"):
                        onepass.packaged_preflight()

    def test_packaged_preflight_cli_needs_no_original_cd(self):
        with mock.patch.object(onepass,"packaged_preflight",return_value={}):
            with mock.patch.object(onepass.sys,"argv",["onepass","--packaged-preflight"]):
                self.assertEqual(onepass.main(),0)

    def test_default_cli_requires_source_bundle_and_target_parent(self):
        with mock.patch.object(onepass.sys,"argv",["onepass"]):
            with self.assertRaises(SystemExit) as caught:
                onepass.main()
            self.assertEqual(caught.exception.code,2)


if __name__=="__main__":
    unittest.main()
