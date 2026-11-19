"""No game bytes: verify release archive cannot accidentally ship dev contents."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_package_audit as audit


class ReleaseArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.folder=self.root/"package_contents"
        self.folder.mkdir()
        self.exe=self.folder/audit.EXE_NAME
        self.exe.write_bytes(b"MZ" + b"SYNTHETIC RELEASE BINARY" * 40)
        (self.folder/audit.README_NAME).write_text(
            "HARVESTER – DEUTSCHE FANÜBERSETZUNG\nINSTALLATION\nsynthetic only",
            encoding="utf-8")
        (self.folder/audit.HASH_NAME).write_bytes(
            audit.expected_checksum_line(audit.sha256_file(self.exe)).encode("ascii"))
        self.zip=self.root/audit.ZIP_NAME
        self.make_zip()

    def tearDown(self):
        self.tmp.cleanup()

    def make_zip(self, names=None):
        with zipfile.ZipFile(self.zip,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for name in (names if names is not None else sorted(audit.ALLOWED)):
                if name in audit.ALLOWED:
                    z.write(self.folder/name,name)
                else:
                    z.writestr(name,b"SYNTHETIC UNWANTED EXTRA")

    def test_exactly_three_friendly_files_pass(self):
        result=audit.verify_release_package(self.folder,self.zip)
        self.assertEqual(result["member_count"],3)
        self.assertEqual(result["setup_exe_sha256"],audit.sha256_file(self.exe))

    def test_source_test_report_in_folder_is_blocker(self):
        (self.folder/"test_delta_core_proof.py").write_bytes(b"not shipped")
        with self.assertRaisesRegex(audit.ReleaseAuditError,"unzulässige"):
            audit.verify_release_package(self.folder,self.zip)

    def test_json_report_in_zip_is_blocker(self):
        self.make_zip([*sorted(audit.ALLOWED),"Harvester_Delta_OnePass_TEST.json"])
        with self.assertRaisesRegex(audit.ReleaseAuditError,"Test-"):
            audit.verify_release_package(self.folder,self.zip)

    def test_dev_scripts_or_backup_in_zip_are_blockers(self):
        for extra in ("tools/developer/patch.py","private_delta.bundle.zip",
                      "LIES_MICH_SPIELSTART.txt","old_rc3b_backup.dat"):
            with self.subTest(extra=extra):
                self.make_zip([*sorted(audit.ALLOWED),extra])
                with self.assertRaises(audit.ReleaseAuditError):
                    audit.verify_release_package(self.folder,self.zip)

    def test_changed_exe_checksum_file_is_blocker(self):
        self.exe.write_bytes(self.exe.read_bytes()+b"tampered")
        with self.assertRaisesRegex(audit.ReleaseAuditError,"SHA-256"):
            audit.verify_release_package(self.folder,self.zip)

    def test_extra_renamed_exe_is_blocker(self):
        self.make_zip([audit.EXE_NAME,audit.README_NAME,"Testversion.exe"])
        with self.assertRaises(audit.ReleaseAuditError):
            audit.verify_release_package(self.folder,self.zip)

    def test_zip_exe_must_be_byte_identical_to_exe_on_disk(self):
        self.exe.write_bytes(self.exe.read_bytes()+b"tampered")
        (self.folder/audit.HASH_NAME).write_bytes(
            audit.expected_checksum_line(audit.sha256_file(self.exe)).encode("ascii"))
        with self.assertRaisesRegex(audit.ReleaseAuditError,"weicht"):
            audit.verify_release_package(self.folder,self.zip)

    def test_missing_readme_is_blocker(self):
        (self.folder/audit.README_NAME).unlink()
        with self.assertRaises(audit.ReleaseAuditError):
            audit.verify_release_package(self.folder,self.zip)


if __name__ == "__main__":
    unittest.main()
