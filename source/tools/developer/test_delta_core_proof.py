"""Synthetic-only tests of variable FIX2 XML proofs; never use game assets."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_core_proof as proof


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class TargetSpecificProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "synthetic original gog"
        self.source.mkdir()
        self.dest = self.root / "Harvester GOG Deutsch"
        self.dest.mkdir()
        for n in proof.CORE_FILES:
            f = self.dest / n
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(("synthetic-only:" + n).encode("ascii"))
        (self.dest / "cloud_saves").mkdir()
        (self.dest / "cloud_saves" / "TEST.SAV").write_bytes(b"synthetic save")
        self.build_proof()

    def tearDown(self):
        self.tmp.cleanup()

    def build_proof(self, *, destination=None, original=None, rules=None):
        self.xml = ET.Element("HarvesterDeutschInstallation", {
            "original": str(original or self.source),
            "ziel": str(destination or self.dest),
            "regeln_sha256": rules or proof.RULES_SHA256,
        })
        for f in sorted(self.dest.rglob("*")):
            if f.is_file() and f.name != proof.PROOF_FILE:
                ET.SubElement(self.xml, "Datei", {
                    "pfad": str(f.relative_to(self.dest)).replace("/", "\\"),
                    "sha256": digest(f.read_bytes()),
                })
        self.save_proof()

    def save_proof(self):
        (self.dest / proof.PROOF_FILE).write_bytes(
            ET.tostring(self.xml, encoding="utf-8", xml_declaration=True)
        )

    def test_native_target_specific_proof_passes_strict_verification(self):
        expected = proof.verify_core_proof(self.source, self.dest)
        self.assertEqual(expected, digest((self.dest / proof.PROOF_FILE).read_bytes()))

    def test_same_core_bytes_in_two_destinations_produce_distinct_valid_proofs(self):
        digest_first = proof.verify_core_proof(self.source, self.dest)
        second = self.root / "Other Fresh Private Parent" / self.dest.name
        second.mkdir(parents=True)
        for f in self.dest.rglob("*"):
            if f.is_file():
                dest = second / f.relative_to(self.dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(f.read_bytes())
        xml2 = ET.parse(second / proof.PROOF_FILE)
        xml2.getroot().set("ziel", str(second))
        xml2.write(second / proof.PROOF_FILE, encoding="utf-8", xml_declaration=True)
        digest_second = proof.verify_core_proof(self.source, second)
        self.assertNotEqual(digest_first, digest_second)

    def test_new_gog_and_new_target_paths_with_identical_contents_are_valid(self):
        # The full XML changes on purpose when either location changes.
        # A fixed whole-XML digest would incorrectly reject this GOG install.
        original_sha = proof.verify_core_proof(self.source, self.dest)
        other_source = self.root / "GOG auf beliebigem Laufwerk" / "Ältere Spiele" / "Harvester"
        other_source.mkdir(parents=True)
        other_target = self.root / "Neue Festplatte" / "Mod Ordner & Spiele" / "Harvester GOG Deutsch"
        other_target.mkdir(parents=True)
        for f in self.dest.rglob("*"):
            if f.is_file():
                target = other_target / f.relative_to(self.dest)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
        # Copying the old proof untouched is NOT acceptable: its paths differ.
        with self.assertRaises(proof.ProofError):
            proof.verify_core_proof(other_source, other_target)
        # A native patcher at the new location writes the newly chosen paths
        # and the SAME SHA-256 values for unchanged produced game content.
        updated = ET.parse(other_target / proof.PROOF_FILE)
        updated.getroot().set("original", str(other_source.resolve()))
        updated.getroot().set("ziel", str(other_target.resolve()))
        updated.write(other_target / proof.PROOF_FILE, encoding="utf-8",
                      xml_declaration=True)
        new_sha = proof.verify_core_proof(other_source, other_target)
        self.assertNotEqual(original_sha, new_sha)
        self.assertEqual(new_sha, digest((other_target / proof.PROOF_FILE).read_bytes()))
        # Now damage a single produced game file. The new path must not
        # weaken any individual content integrity check.
        (other_target / "HARVEST.DAT").write_bytes(b"synthetic corruption")
        with self.assertRaisesRegex(proof.ProofError, "SHA-256"):
            proof.verify_core_proof(other_source, other_target)

    def test_registered_core_file_tamper_rejected(self):
        (self.dest / "HARVEST3.DAT").write_bytes(b"TAMPERED")
        with self.assertRaisesRegex(proof.ProofError, "SHA-256"):
            proof.verify_core_proof(self.source, self.dest)

    def test_registered_save_tamper_rejected(self):
        (self.dest / "cloud_saves" / "TEST.SAV").write_bytes(b"tampered save")
        with self.assertRaises(proof.ProofError):
            proof.verify_core_proof(self.source, self.dest)

    def test_root_wrong_destination_is_rejected(self):
        self.xml.set("ziel", str(self.root / "Some other destination"))
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Zielordner"):
            proof.verify_core_proof(self.source, self.dest)

    def test_root_wrong_original_is_rejected(self):
        self.xml.set("original", str(self.root / "Other original"))
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Originalordner"):
            proof.verify_core_proof(self.source, self.dest)

    def test_wrong_rules_digest_is_rejected(self):
        self.xml.set("regeln_sha256", "0" * 64)
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Regeln"):
            proof.verify_core_proof(self.source, self.dest)

    def test_unknown_extra_file_is_rejected_without_overwriting_it(self):
        extras = self.dest / "unexpected.bin"
        extras.write_bytes(b"do not delete or alter")
        with self.assertRaisesRegex(proof.ProofError, "Nicht registrierte"):
            proof.verify_core_proof(self.source, self.dest)
        self.assertEqual(extras.read_bytes(), b"do not delete or alter")

    def test_duplicate_registered_path_is_rejected(self):
        node = list(self.xml)[0]
        ET.SubElement(self.xml, "Datei", dict(node.attrib))
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Doppelter"):
            proof.verify_core_proof(self.source, self.dest)

    def test_path_traversal_is_rejected(self):
        ET.SubElement(self.xml, "Datei", {
            "pfad": r"..\outside.txt", "sha256": "0"*64
        })
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Dateipfad"):
            proof.verify_core_proof(self.source, self.dest)

    def test_unknown_root_attribute_rejected(self):
        self.xml.set("untrusted_override", "yes")
        self.save_proof()
        with self.assertRaisesRegex(proof.ProofError, "Metadaten"):
            proof.verify_core_proof(self.source, self.dest)

    def test_known_partial_video_extra_allowed_only_with_explicit_progress(self):
        f = self.dest / proof.PROOF_FILE
        start = f.read_bytes()
        temp = self.dest / "_DELTA_VIDEO_ARBEITSVERZEICHNIS"
        temp.mkdir()
        (temp / "state.json").write_bytes(b"synthetic state")
        marker = self.dest / "DELTA_VIDEO_INSTALLATION_UNVOLLSTAENDIG.txt"
        marker.write_bytes(b"synthetic incomplete")
        video = self.dest / "VideoUntertitel" / "10px" / "HARVEST.DAT"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"synthetic progress")
        with self.assertRaises(proof.ProofError):
            proof.verify_core_proof(self.source, self.dest)
        self.assertEqual(
            proof.verify_core_proof(self.source, self.dest, allow_video_progress=True),
            digest(start),
        )

    def test_unknown_partial_video_extra_still_rejected(self):
        (self.dest / "foreign_game.bin").write_bytes(b"unexpected")
        with self.assertRaisesRegex(proof.ProofError, "Nicht registrierte"):
            proof.verify_core_proof(self.source, self.dest, allow_video_progress=True)


if __name__ == "__main__":
    unittest.main()
