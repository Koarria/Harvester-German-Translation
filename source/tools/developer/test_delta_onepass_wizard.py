"""Private UI control-plane tests. No GOG data, no GUI windows, no installation."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_onepass_installer as onepass
import delta_onepass_wizard as wizard


class DeltaWizardSafetyTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Nur echte Windows-Tk-Oberfläche")
    def test_windows_tk_layout_can_expand_and_collapse_advanced(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest("Keine GUI-Sitzung auf diesem Runner: " + str(exc))
        root.withdraw()
        try:
            with mock.patch.object(wizard.rc3,"detect_gog",return_value=None):
                gui=wizard.DeltaWizard(root)
            self.assertEqual(gui.advanced_frame.winfo_manager(), "")
            self.assertEqual(str(gui.install_button.cget("state")), "normal")
            self.assertEqual(gui.preflight_button.winfo_manager(), "grid")
            self.assertEqual(gui.preflight_button.master, gui.advanced_frame)
            gui.advanced_open.set(True)
            gui.toggle_advanced()
            self.assertEqual(gui.advanced_frame.winfo_manager(), "pack")
            gui.advanced_open.set(False)
            gui.toggle_advanced()
            self.assertEqual(gui.advanced_frame.winfo_manager(), "")
            self.assertIn(onepass.core.TEST_TARGET_NAME,
                          wizard.planned_target_label("C:/synthetic-parent"))
        finally:
            root.destroy()

    def test_target_preview_uses_separate_fixed_test_folder(self):
        parent=str(Path("synthetic-parent"))
        label=wizard.planned_target_label(parent)
        self.assertEqual(
            label, "Zielordner: " + str(Path(parent) / onepass.core.TEST_TARGET_NAME)
        )
        self.assertIn("Bitte zuerst", wizard.planned_target_label("   "))

    def test_advanced_settings_never_hidden_if_nondefault(self):
        check=wizard.advanced_options_active
        self.assertFalse(check("", "auto", False, False))
        for kwargs in (
            ("C:/private-rc3b", "auto", False, False),
            ("", "2", False, False),
            ("", "auto", True, False),
            ("", "auto", False, True),
        ):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(check(*kwargs))

    def test_collapse_refuses_to_hide_active_resume(self):
        from types import SimpleNamespace
        target=SimpleNamespace(
            advanced_open=mock.Mock(), advanced_frame=mock.Mock(),
            reference=mock.Mock(), workers=mock.Mock(), resume=mock.Mock(),
            continue_core=mock.Mock(), root=mock.Mock(),
        )
        target.advanced_open.get.return_value=False
        target.reference.get.return_value=""
        target.workers.get.return_value="auto"
        target.resume.get.return_value=True
        target.continue_core.get.return_value=False
        with mock.patch.object(wizard.messagebox,"showwarning") as warning:
            wizard.DeltaWizard.toggle_advanced(target)
        target.advanced_open.set.assert_called_once_with(True)
        target.advanced_frame.pack_forget.assert_not_called()
        warning.assert_called_once()

    def test_path_change_disables_stale_shortcut_but_not_oneclick_install(self):
        from types import SimpleNamespace
        target=SimpleNamespace(
            preflight_signature=("old",), running=False,
            finished_target=Path("old-successful-private-target"),
            install_button=mock.Mock(), open_button=mock.Mock(),
        )
        wizard.DeltaWizard.invalidate(target)
        self.assertIsNone(target.preflight_signature)
        self.assertIsNone(target.finished_target)
        target.install_button.configure.assert_called_with(state="normal")
        target.open_button.configure.assert_called_with(state="disabled")

    def test_one_click_install_needs_no_separate_sha_preflight_button(self):
        from types import SimpleNamespace
        cfg=(r"E:\Spiele mit Leerzeichen\Harvester GOG",
             "", r"D:\Neues Ziel", "", None, False, False)
        fake=SimpleNamespace(
            running=False,
            preflight_signature=None,  # no prior manual verification
            snapshot=mock.Mock(return_value=cfg),
            _args=mock.Mock(return_value=["Installer.exe", "--execute-onepass"]),
            status=mock.Mock(), root=mock.Mock(),
            log_line=mock.Mock(), set_busy=mock.Mock(), run_child=mock.Mock()
        )
        with mock.patch.object(wizard.simpledialog, "askstring", return_value="JA") as ask:
            with mock.patch.object(wizard.threading, "Thread") as spawn:
                wizard.DeltaWizard.start(fake, True)
        fake.snapshot.assert_called_once_with()
        fake._args.assert_called_once_with(cfg, True)
        self.assertIn("SHA-256-Sicherheitscheck", ask.call_args.args[1])
        self.assertIn(r"D:\Neues Ziel", ask.call_args.args[1])
        fake.set_busy.assert_called_once_with(True)
        self.assertIn("AUTOMATISCHE VORPRÜFUNG",
                      fake.log_line.call_args.args[0])
        spawn.assert_called_once_with(
            target=fake.run_child,
            args=(["Installer.exe", "--execute-onepass"], cfg, True),
            daemon=True
        )
        spawn.return_value.start.assert_called_once_with()

    def test_one_click_cancellation_does_not_start_child(self):
        from types import SimpleNamespace
        cfg=(r"E:\GOG\Harvester", "", r"F:\Neue Spiele", "", None, False, False)
        fake=SimpleNamespace(
            running=False, preflight_signature=None,
            snapshot=mock.Mock(return_value=cfg),
            _args=mock.Mock(return_value=["installer.exe", "--execute-onepass"]),
            status=mock.Mock(), root=mock.Mock(),
            log_line=mock.Mock(), set_busy=mock.Mock(), run_child=mock.Mock(),
        )
        with mock.patch.object(wizard.simpledialog, "askstring", return_value=None):
            with mock.patch.object(wizard.threading, "Thread") as spawn:
                wizard.DeltaWizard.start(fake, True)
        spawn.assert_not_called()
        fake.set_busy.assert_not_called()
        fake.status.set.assert_called_once()
        self.assertIn("nicht bestätigt", fake.status.set.call_args.args[0])

    def test_default_options_collapse_without_modal(self):
        from types import SimpleNamespace
        target=SimpleNamespace(
            advanced_open=mock.Mock(), advanced_frame=mock.Mock(),
            reference=mock.Mock(), workers=mock.Mock(), resume=mock.Mock(),
            continue_core=mock.Mock(), root=mock.Mock(),
        )
        target.advanced_open.get.return_value=False
        target.reference.get.return_value=""
        target.workers.get.return_value="auto"
        target.resume.get.return_value=False
        target.continue_core.get.return_value=False
        with mock.patch.object(wizard.messagebox,"showwarning") as warning:
            wizard.DeltaWizard.toggle_advanced(target)
        target.advanced_frame.pack_forget.assert_called_once_with()
        warning.assert_not_called()

    def test_utf8_python_output_with_umlauts_preserved(self):
        raw="Nur SHA-256-/Manifest-/Ressourcen-/Speicher-VORPRÜFUNG PASS.\n".encode("utf-8")
        self.assertEqual(wizard.decode_log_output(raw), raw.decode("utf-8"))

    def test_native_oem_850_output_with_umlauts_preserved(self):
        raw="Speicher-Vorprüfung: frei.\r\n".encode("cp850")
        self.assertEqual(wizard.decode_log_output(raw), "Speicher-Vorprüfung: frei.\r\n")

    def test_ascii_log_line_and_unknown_codec_fallback(self):
        self.assertEqual(wizard.decode_log_output(b"PASS: onepass\n"), "PASS: onepass\n")
        raw="Umlaut: ü".encode("cp850")
        self.assertEqual(wizard.decode_log_output(raw, fallback="not-a-codec"), "Umlaut: ü")

    def test_frozen_child_reuses_the_same_exe_without_shell(self):
        cmd=wizard.child_command(
            Path(r"C:\Private Test\Harvester.exe"),
            Path(r"C:\Unused\delta_onepass_installer.py"), True,
            Path(r"C:\GOG\Harvester"),Path(r"D:\Local Deltas\bundle.zip"),
            Path(r"D:\Different Parent"),Path(r"E:\Existing RC3b"),
            workers=2,execute=True
        )
        self.assertEqual(cmd[0],r"C:\Private Test\Harvester.exe")
        self.assertNotIn("delta_onepass_installer.py",cmd)
        self.assertEqual(cmd.count("--execute-onepass"),1)
        self.assertIn("--reference-rc3b",cmd)
        self.assertIn("--workers",cmd)
        self.assertEqual(cmd[cmd.index("--workers")+1],"2")

    def test_source_child_uses_python_and_the_source_script(self):
        cmd=wizard.child_command(
            Path("python"),Path("delta_onepass_installer.py"),False,
            Path("gog"),Path("local.zip"),Path("new_parent"),
        )
        self.assertEqual(cmd[:2],["python","delta_onepass_installer.py"])
        self.assertNotIn("--execute-onepass",cmd)
        self.assertNotIn("--resume-video",cmd)

    def test_explicit_resume_never_implies_core_install(self):
        cmd=wizard.child_command(
            Path("private.exe"),Path("unused.py"),True,
            Path("gog"),Path("bundle.zip"),Path("parent"),
            resume=True,execute=True
        )
        self.assertIn("--resume-video",cmd)
        self.assertIn("--execute-onepass",cmd)

    def test_explicit_core_continuation_is_separate_cli_mode(self):
        cmd=wizard.child_command(
            Path("private.exe"),Path("unused.py"),True,
            Path("gog"),Path("bundle.zip"),Path("parent"),
            continue_verified_core=True,execute=True
        )
        self.assertIn("--continue-verified-core",cmd)
        self.assertNotIn("--resume-video",cmd)
        self.assertIn("--execute-onepass",cmd)

    def test_conflicting_resume_modes_rejected_before_spawn(self):
        with self.assertRaises(ValueError):
            wizard.child_command(
                Path("private.exe"),Path("unused.py"),True,
                Path("gog"),Path("bundle.zip"),Path("parent"),
                continue_verified_core=True,resume=True,execute=True
            )

    def test_workers_out_of_range_rejected(self):
        for count in (0,5,-1):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    wizard.child_command(
                        Path("executable"),Path("script"),True,
                        Path("source"),Path("bundle"),Path("parent"),
                        workers=count
                    )

    def test_success_requires_all_expected_starters_and_video_cds(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            parent=Path(tmp)
            target=parent/onepass.core.TEST_TARGET_NAME
            target.mkdir()
            names=(
                "HARVEST.EXE", *wizard.rc3.DISCS, "Deutsch_Pruefnachweis.xml",
                "LIES_MICH_SPIELSTART.txt",
                *onepass.video.STARTERS,*onepass.video.CONFIGS,*onepass.video.OUTPUT_CDS
            )
            for name in names:
                f=target/name
                f.parent.mkdir(parents=True,exist_ok=True)
                f.write_bytes(b"synthetic")
            self.assertTrue(wizard.finished_installation(parent))
            onepass.video.video_marker(target).write_bytes(b"incomplete")
            self.assertFalse(wizard.finished_installation(parent))
            onepass.video.video_marker(target).unlink()
            (target/onepass.video.OUTPUT_CDS[-1]).unlink()
            self.assertFalse(wizard.finished_installation(parent))

    def test_gui_flag_only_opens_wizard_no_gog_required(self):
        with mock.patch.object(onepass.sys,"argv",["onepass","--gui"]):
            with mock.patch.object(wizard,"launch_gui",return_value=0) as launch:
                self.assertEqual(onepass.main(),0)
                launch.assert_called_once_with()

    def test_wizard_module_preflight_cli_imports_without_opening_gui(self):
        with mock.patch.object(onepass.sys,"argv",["onepass","--wizard-module-preflight"]):
            with mock.patch.object(wizard,"launch_gui",side_effect=AssertionError("GUI MUST NOT OPEN")):
                self.assertEqual(onepass.main(),0)

    def test_double_click_frozen_exe_opens_wizard(self):
        with mock.patch.object(onepass.sys,"argv",["Harvester_Wizard.exe"]):
            with mock.patch.object(onepass.sys,"frozen",True,create=True):
                with mock.patch.object(wizard,"launch_gui",return_value=0) as launch:
                    self.assertEqual(onepass.main(),0)
                    launch.assert_called_once_with()

    def test_gui_cannot_be_combined_with_install_flag(self):
        with mock.patch.object(onepass.sys,"argv",[
            "onepass","--gui","--execute-onepass"
        ]):
            with self.assertRaises(SystemExit) as ctx:
                onepass.main()
            self.assertEqual(ctx.exception.code,2)


if __name__ == "__main__":
    unittest.main()
