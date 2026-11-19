"""Synthetic-only delta video add-on tests: no game files, no real video rendering."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import hashlib
import json
import unittest
import xml.etree.ElementTree as ET

from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import delta_video_addon as video


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DeltaVideoAddonTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.src=self.root/"original_gog"
        self.src.mkdir()
        self.target=self.root/video.NAME
        self.target.mkdir()
        self.ref=self.root/"known_rc3b_reference"
        self.ref.mkdir()
        (self.src/"DOSBOX").mkdir()
        (self.src/"DOSBOX"/"DOSBox.exe").write_bytes(b"SYNTHETIC")
        (self.src/"dosbox_harvester_single.conf").write_text("source", encoding="utf-8")
        source_config=(
            '[autoexec]\n'
            'mount C "..\\cloud_saves" -t overlay\n'
            'imgmount d -t iso -fs iso "..\\HARVEST.DAT" '
            '"..\\HARVEST3.DAT" "..\\HARVEST4.DAT"\n'
            'harvest.exe\n'
        )
        (self.target/"dosbox_harvester_single.conf").write_bytes(source_config.encode("cp1252"))
        (self.target/"cloud_saves").mkdir()
        (self.target/"cloud_saves"/"USER.SAV").write_bytes(b"NEVER-TOUCH-SAVED-GAME")
        self.hashes={}
        for n in video.EXPECTED_BASE:
            content=("SYNTHETIC-CORE:"+n).encode("ascii")
            (self.src/n).write_bytes(("SYNTHETIC-EN:"+n).encode("ascii"))
            (self.target/n).write_bytes(content)
            (self.ref/n).write_bytes(content)
            self.hashes[n]=sha(content)
        # Native FIX2 proof binds the original/target paths and every core
        # file's SHA. A fixed whole-XML digest from a different target is invalid.
        (self.target/"goglog.ini").write_text("SYNTHETIC GOG INI",encoding="utf-8")
        (self.target/"Harvester_Deutsch_starten.cmd").write_bytes(b"synthetic starter")
        proof=ET.Element("HarvesterDeutschInstallation",{
            "original":str(self.src.resolve()),
            "ziel":str(self.target.resolve()),
            "regeln_sha256":video.audit.EXPECTED_RULES_SHA256,
        })
        for name in sorted(self.target.rglob("*")):
            if name.is_file():
                ET.SubElement(proof,"Datei",{
                    "pfad":str(name.relative_to(self.target)).replace("/", "\\"),
                    "sha256":sha(name.read_bytes()),
                })
        self.proof_xml=ET.tostring(proof,encoding="utf-8",xml_declaration=True)
        (self.target/"Deutsch_Pruefnachweis.xml").write_bytes(self.proof_xml)
        self.p1=mock.patch.dict(video.EXPECTED_BASE,self.hashes,clear=True)
        self.p1.start()

    def tearDown(self):
        self.p1.stop()
        self.tmp.cleanup()

    def test_installed_video_release_marker_matches_proof_and_is_not_candidate(self):
        self.assertEqual(video.core_proof.VIDEO_RELEASE,
                         "HARVESTER_GOG_DEUTSCH_VIDEO_V1")
        self.assertIn(video.core_proof.VIDEO_RELEASE,
                      video.rc3.update_proof.__code__.co_consts)
        self.assertNotIn("TESTKANDIDAT",
                         " ".join(str(x) for x in video.rc3.update_proof.__code__.co_consts))

    def test_video_manifest_preflight_196_locations_66_films_132_srt(self):
        with mock.patch.object(
            video.audit,"read_replacement",side_effect=AssertionError(
                "Full FIX2 payload/Daten must not be needed for Video-only preflight"
            )
        ):
            rows=video.validate_video_inputs(video.audit.REPO)
        self.assertEqual(len(rows),196)
        self.assertEqual(
            sorted(set(r["mode"] for r in rows)),["10px","11px"])
        self.assertEqual(len({r["film_id"] for r in rows}),66)

    def test_wrong_video_manifest_hash_rejected(self):
        with mock.patch.object(video.rc3,"MANIFEST_HASH","0"*64):
            with self.assertRaisesRegex(video.DeltaVideoError,"VideoManifest.xml"):
                video.validate_video_inputs(video.audit.REPO)

    def test_core_test_destination_only_and_sha_pins(self):
        src,dst,ref=video.validate_source_and_test_copy(
            self.src,self.target,video.audit.REPO
        )
        self.assertEqual(src,self.src.resolve())
        self.assertEqual(dst,self.target.resolve())
        self.assertIsNone(ref)
        other=self.root/"Not Approved Test Target"
        other.mkdir()
        with self.assertRaisesRegex(video.DeltaVideoError,"Nur eine zuvor"):
            video.validate_source_and_test_copy(
                self.src,other,video.audit.REPO)
        (self.target/"HARVEST3.DAT").write_bytes(b"CHANGED")
        with self.assertRaisesRegex(video.DeltaVideoError,"Basisinstallation"):
            video.validate_source_and_test_copy(
                self.src,self.target,video.audit.REPO)

    def test_rc3b_reference_is_only_read_and_must_be_separate(self):
        for f in video.VIDEO_FILES:
            out=self.ref/f
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(("REFERENCE:"+f).encode())
        src,dst,ref=video.validate_source_and_test_copy(
            self.src,self.target,video.audit.REPO,self.ref
        )
        self.assertEqual(ref,self.ref.resolve())
        with self.assertRaisesRegex(video.DeltaVideoError,"überschneiden"):
            video.validate_source_and_test_copy(
                self.src,self.target,video.audit.REPO,self.target)

    def test_resume_marker_created_and_reused_only_for_own_tag(self):
        w,resumed=video.initialize_or_resume(
            self.src.resolve(),self.target.resolve(),video.audit.REPO
        )
        self.assertFalse(resumed)
        self.assertEqual(w,(self.target/video.WORKDIR).resolve())
        self.assertTrue(video.video_marker(self.target).is_file())
        w2,resumed2=video.initialize_or_resume(
            self.src.resolve(),self.target.resolve(),video.audit.REPO
        )
        self.assertEqual(w2,w)
        self.assertTrue(resumed2)
        state=video.state_file(self.target)
        data=json.loads(state.read_text("utf-8"))
        data["tag"]="INVALID"
        state.write_text(json.dumps(data),encoding="utf-8")
        with self.assertRaisesRegex(video.DeltaVideoError,"inkonsistenter"):
            video.initialize_or_resume(
                self.src.resolve(),self.target.resolve(),video.audit.REPO
            )

    def test_unknown_preexisting_video_folder_does_not_get_modified(self):
        video_dir=self.target/"VideoUntertitel"
        video_dir.mkdir()
        keep=video_dir/"KEEP"
        keep.write_text("precious",encoding="utf-8")
        with self.assertRaisesRegex(video.DeltaVideoError,"ohne eigenen"):
            video.initialize_or_resume(self.src.resolve(),self.target.resolve(),video.audit.REPO)
        self.assertEqual(keep.read_text("utf-8"),"precious")
        self.assertFalse(video.video_marker(self.target).exists())

    def test_different_initial_proof_rejected_before_video_files(self):
        (self.target/"Deutsch_Pruefnachweis.xml").write_bytes(b"<OtherProof />")
        with self.assertRaisesRegex(video.DeltaVideoError,"Basis-Pruefnachweis"):
            video.initialize_or_resume(self.src.resolve(),self.target.resolve(),video.audit.REPO)
        self.assertFalse((self.target/video.WORKDIR).exists())

    def test_original_create_launchers_reused_without_changing_saves(self):
        generated=video.rc3.create_launchers(self.target)
        self.assertEqual(len(generated),6)
        self.assertTrue(all(p.is_file() for p in generated))
        for name in video.STARTERS:
            self.assertIn(b"DOSBox.exe",(self.target/name).read_bytes())
        for name in video.CONFIGS:
            self.assertIn(b"cloud_saves",(self.target/name).read_bytes())
        self.assertEqual((self.target/"cloud_saves"/"USER.SAV").read_bytes(),
                         b"NEVER-TOUCH-SAVED-GAME")
        self.assertEqual({n:sha((self.target/n).read_bytes())
                          for n in video.EXPECTED_BASE},self.hashes)

    def test_reference_video_files_match_or_abort_if_different(self):
        for f in video.VIDEO_FILES:
            data=("SYNTHETIC-VIDEO:"+f).encode()
            new=self.target/f
            old=self.ref/f
            new.parent.mkdir(parents=True,exist_ok=True)
            old.parent.mkdir(parents=True,exist_ok=True)
            new.write_bytes(data)
            old.write_bytes(data)
        matches=video.compare_video_reference(self.target,self.ref)
        self.assertEqual(len(matches),12)
        self.assertTrue(all(matches.values()))
        (self.ref/video.STARTERS[0]).write_bytes(b"DIFFERENT")
        with self.assertRaisesRegex(video.DeltaVideoError,"unterscheiden"):
            video.compare_video_reference(self.target,self.ref)

    def test_entire_video_orchestration_reuses_rc3b_functions_with_mocked_rendering(self):
        # No real DOS/FST video, 6 ISO render or CD patch: control-plane only.
        names=[f"F{i:03d}" for i in range(66)]
        entries=[]
        for mode in video.MODES:
            for cd,n in (("HARVEST.DAT",45),("HARVEST3.DAT",44),("HARVEST4.DAT",9)):
                for j in range(n):
                    film=names[j % len(names)]
                    entries.append({"mode":mode,"cd":cd,
                        "path":f"GRAPHIC/FST/{film}.FST","film_id":film,
                        "source_sha256":"0"*64})
        fake_sources={name:self.src/(name+".FST") for name in names}
        fake_reports=[{"film":name,"mode":mode,
                       "rendered_sha256":"1"*64}
                      for name in names for mode in video.MODES]
        core_before={n:(self.target/n).read_bytes() for n in video.EXPECTED_BASE}
        def make_fake_iso(target,temp,mode,cd,items,reports):
            self.assertTrue(items)
            out=target/"VideoUntertitel"/mode/cd
            out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(f"SYNTHETIC-ISO-{mode}-{cd}".encode())
            return out,sha(out.read_bytes()),False
        with (
            mock.patch.object(video,"verify_original_source",
                              return_value={"synthetic":"same"}) as verify_source,
            mock.patch.object(video.rc3,"free_space_check"),
            mock.patch.object(video.rc3,"extract_film_sources",
                              return_value=fake_sources) as extract,
            mock.patch.object(video.rc3,"render_all",
                              return_value=fake_reports) as render,
            mock.patch.object(video.rc3,"patch_cd_or_reuse",
                              side_effect=make_fake_iso) as patch_iso,
            mock.patch.object(video.rc3,"update_proof") as proof_update
        ):
            result=video.run_video_addon(
                self.src,self.target,video.audit.REPO,entries,None,workers=1
            )
        self.assertEqual(result["video_original_sources"],66)
        self.assertEqual(result["subtitle_rendered_variants"],132)
        self.assertEqual(result["video_iso_image_count"],6)
        self.assertEqual(result["launcher_count"],3)
        self.assertEqual(result["manifest_fst_locations"],196)
        self.assertFalse(result["is_new_full_delta_installer_from_scratch"])
        self.assertFalse(result["in_game_test_completed"])
        self.assertFalse(result["legal_clearance"])
        self.assertEqual(len(result["files_sha256"]),12)
        self.assertTrue(video.video_marker(self.target).exists(),
            "Successful rendering alone must not finalize before JSON proof is saved.")
        self.assertEqual(patch_iso.call_count,6)
        self.assertEqual(render.call_count,1)
        self.assertEqual(proof_update.call_count,1)
        self.assertEqual(verify_source.call_count,2)
        self.assertEqual({n:(self.target/n).read_bytes()
                          for n in video.EXPECTED_BASE},core_before)
        self.assertEqual((self.target/"cloud_saves"/"USER.SAV").read_bytes(),
                         b"NEVER-TOUCH-SAVED-GAME")

    def test_fail_on_missing_rc3b_video_reference_before_install(self):
        with self.assertRaisesRegex(video.DeltaVideoError,"Referenzdatei fehlt"):
            video.validate_source_and_test_copy(
                self.src,self.target,video.audit.REPO,self.ref
            )

    def test_cannot_resolve_own_target_as_reference_or_modify_original(self):
        with self.assertRaises(video.DeltaVideoError):
            video.validate_source_and_test_copy(
                self.src,self.target,video.audit.REPO,self.target
            )
        self.assertFalse(video.video_marker(self.target).exists())
        self.assertEqual((self.src/"HARVEST.DAT").read_bytes(),
                         b"SYNTHETIC-EN:HARVEST.DAT")


if __name__ == "__main__":
    unittest.main()
