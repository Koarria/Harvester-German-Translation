"""Synthetic-only guard: player-facing release cannot regress to old test labels."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_core_proof as core_proof
import delta_onepass_installer as onepass
import delta_onepass_wizard as wizard

ROOT = Path(__file__).resolve().parents[2]


class ReleasePlayerSurfaceTests(unittest.TestCase):
    def test_installer_window_does_not_show_old_test_statuses(self):
        text = (ROOT/"tools/developer/delta_onepass_wizard.py").read_text("utf-8")
        for forbidden in (
            "Testkopie", "Testspielkopie", "Testziel:",
            "Installer-Kandidat", "privater Ein-Datei-Installer-Kandidat",
            "PRIVATER ENTWICKLUNGSSTAND", "Private Delta-Installation fertig",
            "Erweiterte Test- und", "RC3b als SHA-Referenz",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        self.assertIn('"Deutsch installieren"', text)
        self.assertNotIn("2. Deutsch installieren", text)
        self.assertNotIn("1. Nur prüfen (SHA-256)", text)
        self.assertIn('"Nur prüfen (SHA-256) – ohne Installation"', text)
        self.assertIn("self.advanced_frame, text=\"Nur prüfen", text)
        self.assertNotIn("if execute and config != self.preflight_signature", text)
        self.assertIn("SHA-256-Sicherheitscheck läuft automatisch", text)
        self.assertIn('Harvester GOG Deutsch', text)
        self.assertIn('Die Originalinstallation bleibt unverändert.', text)

    def test_default_report_has_no_dev_test_filename_or_status_fields(self):
        text = (ROOT/"tools/developer/delta_onepass_installer.py").read_text("utf-8")
        self.assertEqual(onepass.REPORT_SCHEMA,
                         "harvester-gog-deutsch-installationsbericht-v1")
        self.assertIn("Harvester_Deutsch_Installation_", text)
        self.assertNotIn("Harvester_Delta_OnePass_TEST_", text)
        self.assertNotIn('"private_onepass_developer_test": True', text)
        self.assertNotIn('"in_game_test_completed": False', text)
        self.assertNotIn('"legal_clearance": False,', text)

    def test_installed_video_proof_release_marker_is_clean(self):
        self.assertEqual(core_proof.VIDEO_RELEASE, "HARVESTER_GOG_DEUTSCH_VIDEO_V1")
        text = (ROOT/"installer.py").read_text("utf-8")
        self.assertNotIn("RC3_PYTHON_LOCAL_RENDER_TESTKANDIDAT", text)
        self.assertNotIn("PYTHON_LOCAL_RENDER_RC3_TESTKANDIDAT", text)
        self.assertGreaterEqual(text.count(core_proof.VIDEO_RELEASE), 3)

    def test_release_readme_and_description_exist_without_rc_labels(self):
        for path in ("release/LIES_MICH.txt",
                     "release/GITHUB_RELEASE_TEXT_ENTWURF.md"):
            content = (ROOT/path).read_text("utf-8")
            self.assertIn("Harvester", content)
            self.assertNotIn("RC3b", content)
            self.assertNotIn("TESTKANDIDAT", content)
        self.assertEqual(
            wizard.planned_target_label("C:/Spiele"),
            "Zielordner: " + str(Path("C:/Spiele") / onepass.core.TEST_TARGET_NAME)
        )


if __name__ == "__main__":
    unittest.main()
