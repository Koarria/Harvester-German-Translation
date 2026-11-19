"""Synthetic control-plane tests for private one-pass Delta-Core + RC3b Video.

Never calls native Harvester FIX2 patcher or renders any proprietary videos.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_onepass_installer as onepass


class TestPrivateOnePass(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.src=self.root/"synthetic_english_gog"
        self.src.mkdir()
        self.parent=self.root/"private_new_target_parent"
        self.parent.mkdir()
        self.dest=self.parent/onepass.core.TEST_TARGET_NAME
        self.zip=self.root/"private_bundle.zip"
        self.zip.write_bytes(b"PRIVATE-SYNTHETIC-BUNDLE")
        self.report=self.root/"reports"
        self.base_report={
            "real_core_test": True,
            "original_source_sha256_unchanged": True,
            "existing_rc3b_modified": False,
            "reconstructed_assets": 18,
            "optional_reference_comparison": {},
        }
        self.fake_video={
            "real_video_addon_test": True,
            "source_gog_original_sha256_unchanged": True,
            "delta_core_base_sha256_unchanged": True,
            "video_original_sources": 66,
            "subtitle_rendered_variants": 132,
            "video_iso_image_count": 6,
            "launcher_count": 3,
            "launcher_config_count": 3,
            "manifest_fst_locations": 196,
            "files_sha256": {p: "a"*64 for p in onepass.video.VIDEO_FILES},
            "sha256_equal_to_existing_rc3b": {},
            "patched_exe_sha256": "b"*64,
            "patched_cd_sha256": {x:"c"*64 for x in onepass.video.DISC_NAMES},
            "final_fix2_proof_sha256": "d"*64,
            "existing_rc3b_modified":False,
            "game_saves_modified_by_addon":False,
        }
        self.bundle_proof={
            "verified_original_cd_sha256":3,
            "verified_iso_and_xfile_uses":48,
            "reconstructed_unique_pairs":20,
            "target_asset_count":18,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def fake_preflight(self,*args,**kwargs):
        return self.src,self.zip,self.dest,None,[],self.bundle_proof

    def new_core(self,*args,**kwargs):
        self.assertFalse(self.dest.exists())
        self.dest.mkdir()
        return dict(self.base_report)

    def fake_render(self,*args,**kwargs):
        self.assertTrue(self.dest.is_dir())
        (self.dest/onepass.video.WORKDIR).mkdir()
        onepass.video.video_marker(self.dest).write_text(
            "SYNTHETIC PRIVATE INCOMPLETE",encoding="utf-8"
        )
        return dict(self.fake_video)

    def test_report_contains_only_whitelisted_counts_and_no_paths(self):
        output=onepass.make_report(self.base_report,self.fake_video,self.bundle_proof,False)
        self.assertEqual(output["bundle_variants_verified"],20)
        self.assertEqual(output["iso_xfile_uses_verified"],48)
        self.assertEqual(output["video_result"]["subtitle_rendered_variants"],132)
        self.assertTrue(output["is_new_full_delta_installation_from_one_start"])
        self.assertFalse(output["is_python_free_player_installer"])
        self.assertNotIn("legal_clearance", output)
        self.assertNotIn("in_game_test_completed", output)
        self.assertNotIn("private_onepass_developer_test", output)
        self.assertNotIn("real_video_addon_test", output["video_result"])
        self.assertNotIn("sha256_equal_to_existing_rc3b", output["video_result"])
        self.assertNotIn("existing_rc3b_modified", output["video_result"])
        self.assertNotIn("reference_video_sha256_matches", output)
        self.assertNotIn("matched_reference_core_files", output["core_result"])
        self.assertEqual(output["schema"], "harvester-gog-deutsch-installationsbericht-v1")
        self.assertNotIn(str(self.root),json.dumps(output))

    def test_report_flags_real_frozen_bundle_only_if_both_conditions_hold(self):
        with mock.patch.object(onepass.embedded, "embedded_bundle_path",
                               return_value=self.zip):
            with mock.patch.object(onepass.sys, "frozen", True, create=True):
                result=onepass.make_report(self.base_report,self.fake_video,
                                           self.bundle_proof,False)
                self.assertTrue(result["is_python_free_player_installer"])
            with mock.patch.object(onepass.sys, "frozen", False, create=True):
                result=onepass.make_report(self.base_report,self.fake_video,
                                           self.bundle_proof,False)
                self.assertFalse(result["is_python_free_player_installer"])

    def test_strict_twelve_file_comparison_rejects_a_false(self):
        video=dict(self.fake_video)
        video["sha256_equal_to_existing_rc3b"]={p:True for p in onepass.video.VIDEO_FILES}
        video["sha256_equal_to_existing_rc3b"][onepass.video.VIDEO_FILES[-1]]=False
        with self.assertRaisesRegex(onepass.OnePassError,"RC3b-Vergleich"):
            onepass.make_report(self.base_report,video,self.bundle_proof,False)

    def test_strict_twelve_file_comparison_accepts_all_true(self):
        video=dict(self.fake_video)
        video["sha256_equal_to_existing_rc3b"]={p:True for p in onepass.video.VIDEO_FILES}
        output=onepass.make_report(self.base_report,video,self.bundle_proof,False)
        self.assertEqual(output["reference_video_sha256_matches"],12)

    def test_missing_or_unexpected_manifest_count_is_blocker(self):
        video=dict(self.fake_video)
        video["subtitle_rendered_variants"]=131
        with self.assertRaisesRegex(onepass.OnePassError,"unvollständig"):
            onepass.make_report(self.base_report,video,self.bundle_proof,False)

    def test_invalid_bundle_count_cannot_be_ignored(self):
        b=dict(self.bundle_proof)
        b["reconstructed_unique_pairs"]=19
        with self.assertRaisesRegex(onepass.OnePassError,"Bundle"):
            onepass.make_report(self.base_report,self.fake_video,b,False)

    def test_one_click_install_rejects_bad_auto_preflight_before_any_write(self):
        # The GUI no longer requires a separate SHA click. The CLI still
        # enforces complete source/bundle/disk verification first.
        with mock.patch.object(onepass, "preflight",
                               side_effect=onepass.OnePassError("SHA-256 falsch")) as audit:
            with mock.patch.object(onepass.core, "core_only_install",
                                   side_effect=AssertionError("MUST NOT PATCH CORE")) as core_install:
                with mock.patch.object(onepass.video, "run_video_addon",
                                       side_effect=AssertionError("MUST NOT RENDER VIDEO")) as render:
                    with self.assertRaisesRegex(onepass.OnePassError,"SHA-256 falsch"):
                        onepass.perform(self.src,self.zip,self.parent,
                                        report_dir=self.report,execute=True)
        audit.assert_called_once()
        core_install.assert_not_called()
        render.assert_not_called()
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.report.exists())

    def test_read_only_default_does_not_call_either_installer(self):
        with mock.patch.object(onepass,"preflight",side_effect=self.fake_preflight):
            with mock.patch.object(onepass.core,"core_only_install",
                                   side_effect=AssertionError("CORE MUST NOT RUN")):
                with mock.patch.object(onepass.video,"run_video_addon",
                                       side_effect=AssertionError("VIDEO MUST NOT RUN")):
                    result=onepass.perform(
                        self.src,self.zip,self.parent,None,
                        report_dir=self.report,execute=False
                    )
        self.assertIsNone(result)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.report.exists())

    def test_one_start_does_core_then_video_then_report_then_marker_cleanup(self):
        calls=[]
        def core_fn(*args,**kwargs):
            calls.append("core")
            return self.new_core()
        def video_fn(*args,**kwargs):
            calls.append("video")
            return self.fake_render()
        with mock.patch.object(onepass,"preflight",side_effect=self.fake_preflight):
            with mock.patch.object(onepass.core,"core_only_install",side_effect=core_fn):
                with mock.patch.object(onepass.video,"run_video_addon",side_effect=video_fn):
                    out=onepass.perform(
                        self.src,self.zip,self.parent,None,workers=1,
                        report_dir=self.report,execute=True
                    )
        self.assertEqual(calls,["core","video"])
        self.assertTrue(out["is_new_full_delta_installation_from_one_start"])
        self.assertEqual(len(list(self.report.glob("Harvester_Deutsch_Installation_*.json"))),1)
        self.assertFalse(onepass.video.video_marker(self.dest).exists())
        self.assertFalse((self.dest/onepass.video.WORKDIR).exists())

    def test_video_failure_preserves_private_checkpoint_and_does_not_report_pass(self):
        def fail_video(*args,**kwargs):
            self.fake_render()
            raise onepass.video.DeltaVideoError("Synthetic renderer exception")
        with mock.patch.object(onepass,"preflight",side_effect=self.fake_preflight):
            with mock.patch.object(onepass.core,"core_only_install",
                                   side_effect=self.new_core):
                with mock.patch.object(onepass.video,"run_video_addon",
                                       side_effect=fail_video):
                    with self.assertRaisesRegex(onepass.video.DeltaVideoError,"exception"):
                        onepass.perform(
                            self.src,self.zip,self.parent,None,report_dir=self.report,
                            execute=True
                        )
        self.assertTrue(onepass.video.video_marker(self.dest).is_file())
        self.assertFalse(self.report.exists())

    def test_explicit_resume_runs_video_only_never_reruns_core(self):
        self.dest.mkdir()
        with mock.patch.object(onepass,"preflight",side_effect=self.fake_preflight):
            with mock.patch.object(onepass.core,"core_only_install",
                                   side_effect=AssertionError("RESUME MUST NOT TOUCH CORE")):
                with mock.patch.object(onepass.video,"run_video_addon",
                                       side_effect=self.fake_render):
                    out=onepass.perform(
                        self.src,self.zip,self.parent,None,report_dir=self.report,
                        resume_video=True,execute=True
                    )
        self.assertTrue(out["resumed_video_only"])
        self.assertFalse(out["is_new_full_delta_installation_from_one_start"])
        self.assertFalse(onepass.video.video_marker(self.dest).exists())

    def test_resume_rejected_without_own_video_marker(self):
        self.dest.mkdir()
        with self.assertRaisesRegex(onepass.OnePassError,"Checkpoint"):
            onepass.inspect_paths(self.src,self.zip,self.parent,None,True)

    def test_unexpected_existing_target_not_overwritten(self):
        self.dest.mkdir()
        existing=self.dest/"SAVE.SAV"
        existing.write_bytes(b"LEAVE-ALONE")
        with self.assertRaises((onepass.core.ShadowInstallerError,onepass.OnePassError)):
            onepass.inspect_paths(self.src,self.zip,self.parent,None,False)
        self.assertEqual(existing.read_bytes(),b"LEAVE-ALONE")

    def test_report_path_must_not_be_inside_target_or_repo(self):
        with self.assertRaisesRegex(onepass.OnePassError,"außerhalb"):
            onepass.validate_report_location(
                self.src,self.dest,None,self.dest/"reports"
            )
        with self.assertRaises(onepass.audit.AuditError):
            onepass.validate_report_location(
                self.src,self.dest,None,onepass.audit.REPO/"temp_report"
            )

    def test_existing_core_continuation_checks_proof_before_any_write(self):
        self.dest.mkdir()
        with mock.patch.object(onepass.video,"validate_source_and_test_copy",
                               return_value=(self.src,self.dest,None)):
            with mock.patch.object(onepass.video.core_proof,"verify_core_proof",
                                   return_value="f"*64) as check:
                got=onepass.inspect_paths(self.src,self.zip,self.parent,None,False,True)
        self.assertEqual(got[2],self.dest)
        check.assert_called_once_with(self.src,self.dest)

    def test_existing_core_continuation_rejects_video_work_or_marker(self):
        self.dest.mkdir()
        onepass.video.video_marker(self.dest).write_bytes(b"incomplete")
        with self.assertRaisesRegex(onepass.OnePassError,"Core-Fortsetzung"):
            onepass.inspect_paths(self.src,self.zip,self.parent,None,False,True)

    def test_no_simultaneous_video_and_core_continuation(self):
        with self.assertRaises(onepass.OnePassError):
            onepass.perform(self.src,self.zip,self.parent,
                            report_dir=self.report,execute=False,
                            resume_video=True,continue_verified_core=True)

    def test_continued_verified_core_never_runs_native_core_again(self):
        self.dest.mkdir()
        with mock.patch.object(onepass,"preflight",side_effect=self.fake_preflight):
            with mock.patch.object(onepass.core,"core_only_install",
                                   side_effect=AssertionError("MUST NOT RERUN CORE")):
                with mock.patch.object(onepass.video,"run_video_addon",
                                       side_effect=self.fake_render):
                    out=onepass.perform(
                        self.src,self.zip,self.parent,None,workers=1,
                        report_dir=self.report,execute=True,
                        continue_verified_core=True
                    )
        self.assertTrue(out["continued_preverified_core_only"])
        self.assertFalse(out["is_new_full_delta_installation_from_one_start"])
        self.assertFalse(out["resumed_video_only"])
        self.assertFalse(onepass.video.video_marker(self.dest).exists())

    def test_pinned_rc3b_video_manifest_66_132_196_still_passes(self):
        records=onepass.video.validate_video_inputs(onepass.audit.REPO)
        self.assertEqual(len(records),196)
        self.assertEqual(len({r["film_id"] for r in records}),66)
        self.assertEqual(set(r["mode"] for r in records),{"10px","11px"})


if __name__=="__main__":
    unittest.main()
