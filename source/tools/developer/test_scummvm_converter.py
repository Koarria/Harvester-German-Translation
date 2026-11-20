#!/usr/bin/env python3
"""Synthetic-only safety tests for private ScummVM bridge; no copyrighted GOG ISO needed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scummvm_converter as converter
from runtime.harvester_iso import Extent


class ScummvmConverterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.english = self.root / "English GOG"
        self.german = self.root / "Harvester GOG Deutsch"
        self.parent = self.root / "Output"
        for path in (self.english, self.german, self.parent):
            path.mkdir()
        self.original = b"ScummVM detection test fixture 2026.4.0" * 8
        (self.english / "HARVEST.EXE").write_bytes(self.original)
        self.rules = ET.Element("HarvesterPatch")
        self.indexes = (
            ("INDEX.001", "HARVEST.DAT"),
            ("INDEX.002", "SOUND.DAT"),
            ("INDEX.003", "HARVEST2.DAT"),
        )
        self.items = {}
        self.entries = {}
        for number, filename in enumerate(converter.DISC_IMAGES, 1):
            idx, data = self.indexes[number-1]
            blobs = {
                idx: f"index-{number}".encode("ascii"),
                data: f"game-archive-{number}".encode("ascii"),
                "DIALOG.RSP": f"Deutscher Dialog {number}".encode("utf-8"),
            }
            raw = bytearray()
            mapping = {}
            for key, content in blobs.items():
                mapping[key] = Extent(key, len(raw), len(raw), len(content), False)
                raw.extend(content)
            (self.german / filename).write_bytes(raw)
            self.entries[filename] = mapping
            self.items[filename] = blobs
            node = ET.SubElement(self.rules, "Image", name=filename, count="3")
            target = hashlib.sha256(blobs["DIALOG.RSP"]).hexdigest() + ".bin"
            ET.SubElement(node, "Replace", path="DIALOG.RSP", asset=target)

    def patches(self):
        return (
            mock.patch.object(converter, "ISO_FILE_COUNTS", (3,3,3)),
            mock.patch.object(converter, "scan_iso", side_effect=lambda path:self.entries[Path(path).name]),
            mock.patch.object(converter, "read_rules", return_value=self.rules),
            mock.patch.object(converter, "ORIGINAL_EXE_SIZE", len(self.original)),
            mock.patch.object(converter, "ORIGINAL_EXE_SHA", hashlib.sha256(self.original).hexdigest()),
            mock.patch.object(converter, "SCUMMVM_EXE_MD5_5000", hashlib.md5(self.original[:5000]).hexdigest()),
        )

    def test_preflight_only_never_writes_anything(self):
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            result=converter.convert(self.english,self.german,self.parent,"ohne",False)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["verified_translated_iso_discs"],3)
        self.assertEqual(result["verified_translated_fst_entries"],0)
        self.assertEqual(list(self.parent.iterdir()),[])

    def test_cd1_330_files_plus_22_directories_not_rejected(self):
        # Regression for screenshot: German 11-px HARVEST.DAT has 352 ISO
        # entries, but signed-off Regeln.xml counts 330 *files* only.
        # This fixture is small, but reproduces 3 files + 22 directories.
        for n in range(22):
            name = f"FOLDER{n:02d}"
            self.entries["HARVEST.DAT"][name] = Extent(name, 0, 0, 0, True)
        self.assertEqual(len(self.entries["HARVEST.DAT"]), 25)
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            result=converter.convert(self.english,self.german,self.parent,"ohne",True)
        output=self.parent/"Harvester ScummVM Deutsch ohne"
        self.assertEqual(result["disc_file_counts"][0],3)
        self.assertTrue(output.is_dir())
        self.assertTrue((output/"CD1"/"FOLDER00").is_dir())
        self.assertTrue((output/"CD1"/"FOLDER21").is_dir())
        self.assertFalse((self.german/"FOLDER00").exists())
        self.assertEqual((self.english/"HARVEST.EXE").read_bytes(),self.original)

    def test_missing_game_file_rejected_even_when_directories_exist(self):
        self.entries["HARVEST.DAT"].pop("DIALOG.RSP")
        self.entries["HARVEST.DAT"]["GRAPHIC"]=Extent("GRAPHIC",0,0,0,True)
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            with self.assertRaisesRegex(converter.ConversionError,"Dateien"):
                converter.convert(self.english,self.german,self.parent,"ohne",True)
        self.assertEqual(list(self.parent.iterdir()),[])

    def test_real_copy_keeps_original_untouched_and_scummvm_cd_layout(self):
        oldEnglish=(self.english/"HARVEST.EXE").read_bytes()
        oldImages=[(self.german/x).read_bytes() for x in converter.DISC_IMAGES]
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            result=converter.convert(self.english,self.german,self.parent,"ohne",True)
        output=self.parent/"Harvester ScummVM Deutsch ohne"
        self.assertFalse(result["dry_run"])
        self.assertTrue(output.is_dir())
        self.assertEqual((output/"HARVEST.EXE").read_bytes(),oldEnglish)
        for n,(idx,data) in enumerate(self.indexes,1):
            self.assertEqual((output/f"CD{n}"/idx).read_bytes(),self.items[converter.DISC_IMAGES[n-1]][idx])
            self.assertEqual((output/f"CD{n}"/data).read_bytes(),self.items[converter.DISC_IMAGES[n-1]][data])
            self.assertEqual((output/f"CD{n}"/"DIALOG.RSP").read_bytes(),self.items[converter.DISC_IMAGES[n-1]]["DIALOG.RSP"])
        self.assertEqual([ (self.german/x).read_bytes() for x in converter.DISC_IMAGES ],oldImages)
        self.assertEqual((self.english/"HARVEST.EXE").read_bytes(),oldEnglish)
        self.assertFalse((output/"cloud_saves").exists())
        self.assertTrue((output/"ScummVM_Deutsch_Pruefbericht.json").exists())

    def test_bad_english_exe_rejected_before_target_creation(self):
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4]):
            with self.assertRaisesRegex(converter.ConversionError,"ScummVM-Detektor"):
                converter.convert(self.english,self.german,self.parent,"ohne",True)
        self.assertEqual(list(self.parent.iterdir()),[])

    def test_existing_target_is_never_overwritten(self):
        dest=self.parent/"Harvester ScummVM Deutsch ohne"
        dest.mkdir()
        (dest/"saved.dat").write_bytes(b"EXISTING DATA")
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            with self.assertRaisesRegex(converter.ConversionError,"Ziel existiert bereits"):
                converter.convert(self.english,self.german,self.parent,"ohne",True)
        self.assertEqual((dest/"saved.dat").read_bytes(),b"EXISTING DATA")

    def test_incomplete_scummvm_archive_pair_fails_without_copy(self):
        self.entries["HARVEST3.DAT"].pop("SOUND.DAT")
        # Keep the three-entry ISO inventory unchanged so the pair
        # completeness guard, rather than entry-count guard, is exercised.
        self.entries["HARVEST3.DAT"]["EXTRA.BIN"] = Extent("EXTRA.BIN", 0, 0, 4, False)
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            with self.assertRaisesRegex(converter.ConversionError,"unvollständiges ScummVM-XFILE-Paar"):
                converter.convert(self.english,self.german,self.parent,"ohne",True)
        self.assertEqual(list(self.parent.iterdir()),[])

    def test_bad_target_folder_inside_gog_rejected(self):
        inside=self.german/"My New Game"
        inside.mkdir()
        with (self.patches()[0],self.patches()[1],self.patches()[2],
              self.patches()[3],self.patches()[4],self.patches()[5]):
            with self.assertRaisesRegex(converter.ConversionError,"dürfen nicht ineinander liegen"):
                converter.convert(self.english,self.german,inside,"ohne",True)

    def test_correct_iso_choice_per_mode(self):
        name="HARVEST.DAT"
        self.assertEqual(converter.game_iso_path(self.german,"ohne",name),self.german/name)
        self.assertEqual(converter.game_iso_path(self.german,"10px",name),
                         self.german/"VideoUntertitel"/"10px"/name)
        self.assertEqual(converter.game_iso_path(self.german,"11px",name),
                         self.german/"VideoUntertitel"/"11px"/name)
        with self.assertRaisesRegex(converter.ConversionError,"Modus"):
            converter.game_iso_path(self.german,"12px",name)


    def make_locally_rendered_video_fixture(self):
        """Reproduce 66 films/132 local renders and 196 FST positions, without GOG files.

        Manifest target_sha256 intentionally differs from locally rendered output.
        Its historical SHA must NOT cause an otherwise correct GOG ISO to fail.
        """
        payload = self.root/"pinned"/"payload"
        payload.mkdir(parents=True)
        xml = ET.Element("HarvesterVideoManifest")
        movie_bytes = {}
        qa_records = []
        originals = {}
        for num in range(66):
            film = f"F{num:03d}"
            originals[film] = hashlib.sha256(("original-"+film).encode()).hexdigest()
            for mode in ("10px","11px"):
                data = (f"locally-rendered-{mode}-{film}").encode()
                movie_bytes[(film,mode)] = data
                qa_records.append({
                    "film":film,"mode":mode,
                    "source_sha256":originals[film],
                    "rendered_sha256":hashlib.sha256(data).hexdigest()
                })
        data_for_disc = [bytearray(),bytearray(),bytearray()]
        maps = [{},{},{}]
        for mode in ("10px","11px"):
            for n in range(98):
                film = f"F{n%66:03d}"
                disc_number = 1 if n < 66 else 2
                disc_name = converter.DISC_IMAGES[disc_number-1]
                path = f"GRAPHIC/FST/{film}.FST"
                ET.SubElement(xml,"Fst",{
                    "mode":mode,"cd":disc_name,"path":path,"film_id":film,
                    "source_sha256":originals[film],
                    "target_sha256":hashlib.sha256(("legacy-pre-rendered-"+film+mode).encode()).hexdigest()
                })
                if mode=="11px":
                    data=movie_bytes[(film,mode)]
                    holder=data_for_disc[disc_number-1]
                    maps[disc_number-1][path] = Extent(path, len(holder), len(holder), len(data), False)
                    holder.extend(data)
        manifest = payload/"VideoManifest.xml"
        manifest.write_bytes(ET.tostring(xml,encoding="utf-8",xml_declaration=True))
        movie_root=self.german/"VideoUntertitel"/"11px"
        movie_root.mkdir(parents=True)
        discs=[]
        for i,name in enumerate(converter.DISC_IMAGES):
            path=movie_root/name
            path.write_bytes(data_for_disc[i])
            discs.append(converter.DiscPlan(i+1,path,maps[i],()))
        qa_root = self.german/"VideoUntertitel"
        qa_file = qa_root/"LOKALE_RENDER_QA.json"
        qa_doc={
            "release":"HARVESTER_GOG_DEUTSCH_VIDEO_V1",
            "films":66,"variant_render_jobs":132,"iso_fst_positions":196,
            "qa":qa_records
        }
        qa_file.write_text(json.dumps(qa_doc),encoding="utf-8")
        proof=ET.Element("HarvesterDeutschInstallation",{
            "original":str(self.english.resolve()),
            "ziel":str(self.german.resolve()),
            "regeln_sha256":"7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b",
            "video_untertitel_release":"HARVESTER_GOG_DEUTSCH_VIDEO_V1"
        })
        for file in [qa_file, *[disc.iso for disc in discs]]:
            ET.SubElement(proof,"Datei",{
                "pfad":str(file.relative_to(self.german)).replace("/","\\"),
                "sha256":hashlib.sha256(file.read_bytes()).hexdigest()
            })
        proof_file=self.german/"Deutsch_Pruefnachweis.xml"
        proof_file.write_bytes(ET.tostring(proof,encoding="utf-8",xml_declaration=True))
        return payload.parent, manifest, discs, qa_file, proof_file


    def add_real_installer_archived_starter(self, german, proof_file):
        """Exact duplicate behavior of production installer.py:update_proof:
        modify the existing legacy launcher proof row to the archive path,
        then generated.append(archived) adds the same row again.
        """
        archived=german/"VideoUntertitel"/"ALTER_FIX2_STARTER.txt"
        archived.write_bytes(b"@echo off\r\nREM legacy FIX2 launcher\r\n")
        digest=hashlib.sha256(archived.read_bytes()).hexdigest()
        tree=ET.parse(proof_file)
        path="VideoUntertitel\\ALTER_FIX2_STARTER.txt"
        ET.SubElement(tree.getroot(),"Datei",{"pfad":path,"sha256":digest})
        ET.SubElement(tree.getroot(),"Datei",{"pfad":path,"sha256":digest})
        tree.write(proof_file,encoding="utf-8",xml_declaration=True)
        return archived

    def test_exact_real_v1_proof_with_double_archived_launcher_passes(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        archived=self.add_real_installer_archived_starter(self.german,proof)
        self.assertTrue(archived.is_file())
        self.assertEqual(len(ET.parse(proof).getroot().findall("Datei")),6)  # QA + 3 discs + 2 identical archived starter entries
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            self.assertEqual(
                converter.verify_video_mode(self.english,self.german,"11px",discs),98)

    def test_duplicate_other_than_archived_launcher_still_rejected(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        tree=ET.parse(proof)
        node=tree.getroot().findall("Datei")[0]
        ET.SubElement(tree.getroot(),"Datei",dict(node.attrib))
        tree.write(proof,encoding="utf-8",xml_declaration=True)
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Duplikat"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_wrong_sha_in_second_known_duplicate_rejected(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        self.add_real_installer_archived_starter(self.german,proof)
        tree=ET.parse(proof)
        tree.getroot().findall("Datei")[-1].set("sha256","a"*64)
        tree.write(proof,encoding="utf-8",xml_declaration=True)
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Duplikat"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_archived_launcher_data_modified_rejected_despite_identical_duplicate_hashes(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        archived=self.add_real_installer_archived_starter(self.german,proof)
        archived.write_bytes(archived.read_bytes()+b"MODIFIED")
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Archivierter deutscher Starter"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_third_archived_launcher_entry_rejected(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        self.add_real_installer_archived_starter(self.german,proof)
        tree=ET.parse(proof)
        node=tree.getroot().findall("Datei")[-1]
        ET.SubElement(tree.getroot(),"Datei",dict(node.attrib))
        tree.write(proof,encoding="utf-8",xml_declaration=True)
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Duplikat"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_production_installer_source_confirmed_legacy_duplicate_path(self):
        source=(Path(__file__).resolve().parents[2]/"installer.py").read_text("utf-8")
        self.assertIn("generated.append(archived)",source)
        self.assertIn("node.attrib['pfad']",source)
        self.assertIn("for item in generated:",source)
        self.assertIn("e = ET.SubElement(proof,'Datei')",source)

    def test_local_renderer_sha_not_legacy_manifest_target_sha(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        first=ET.parse(manifest).getroot().findall("Fst")[98]
        self.assertEqual(first.get("mode"),"11px")
        actual=hashlib.sha256(
            (b"locally-rendered-11px-F000")).hexdigest()
        self.assertNotEqual(actual,first.get("target_sha256"))
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            self.assertEqual(converter.verify_video_mode(self.english,self.german,"11px",discs),98)

    def test_local_render_qa_change_fails_sha_proof(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        qa.write_bytes(qa.read_bytes()+b" ")
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Render-QA stimmt nicht"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_video_disc_change_fails_sha_proof(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        disc=discs[0].iso
        original=disc.read_bytes()
        disc.write_bytes(b"X"+original[1:])
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"Videountertitel-CD weicht"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_wrong_original_folder_in_install_proof_rejected(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        tree=ET.parse(proof)
        tree.getroot().set("original",str(self.root/"Different Original GOG"))
        tree.write(proof,encoding="utf-8",xml_declaration=True)
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"anderen GOG-Quell"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)

    def test_missing_rendered_movie_rejected_even_with_modified_proof(self):
        root,manifest,discs,qa,proof=self.make_locally_rendered_video_fixture()
        # Simulate both ISO and proof modified together but QA still originally
        # attests the local renderer's 66x2 outputs.
        disc=discs[0].iso
        original=disc.read_bytes()
        disc.write_bytes(b"Q"+original[1:])
        tree=ET.parse(proof)
        for row in tree.getroot().findall("Datei"):
            if row.get("pfad","").replace("\\","/")=="VideoUntertitel/11px/HARVEST.DAT":
                row.set("sha256",hashlib.sha256(disc.read_bytes()).hexdigest())
        tree.write(proof,encoding="utf-8",xml_declaration=True)
        with (mock.patch.object(converter,"ROOT",root),
              mock.patch.object(converter,"VIDEO_MANIFEST_SHA256",
                                hashlib.sha256(manifest.read_bytes()).hexdigest())):
            with self.assertRaisesRegex(converter.ConversionError,"FST stimmt nicht"):
                converter.verify_video_mode(self.english,self.german,"11px",discs)


if __name__=="__main__":
    unittest.main()
