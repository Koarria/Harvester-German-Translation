"""Synthetic cross-format/20-pair unified Harvester bundle tests. NO game data."""
from __future__ import annotations

from collections import Counter
import hashlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
import unittest
import xml.etree.ElementTree as ET
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import unified_delta_bundle as bundle


DISC_NAMES = ("HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT")
# Mirrors the 11 / 9 / 10 outer resource counts in the real, pinned FIX2 rules.
COMMON = [
    "HARVEST.SCR", "DIALOG.RSP", "GRAPHIC/OTHER/KEYSHELP.BM",
    "GRAPHIC/OTHER/MOUSHELP.BM", "DIALOGUE.IDX", "ADJHEAD.RCS",
    "GRAPHIC/FONT/TEXTFONT.CFT", "GRAPHIC/FONT/MEDFONT1.CFT",
    "GRAPHIC/FONT/TEXTFNT2.CFT", "GRAPHIC/FONT/MEDFONT2.CFT", "MENU.INI",
]
INNER = [
    "KEYWORD.BM", "LOADGAME.BM", "SAVEGAME.BM",
    "MOUSHELP.BM", "KEYSHELP.BM", "TIPS.BM",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Fixture:
    def __init__(self, folder: Path):
        self.folder = folder
        self.rules = ET.Element("HarvesterPatch")
        self.assets = {}
        self.targets = {}
        self.listings = {}
        self.inner_locations = {}
        self.original_images = {}
        self.usage_count = 0
        self.asset_names = {}

        # Create 18 distinct synthetic TARGET payloads: 11 nonbitmap + 7 bitmap.
        for i, category in enumerate([
            "SCRIPT_A", "DIALOG_A", "KEYS", "MOUS", "IDX", "ADJ",
            "FONT1", "FONT2", "FONT3", "FONT4", "MENU",
            "KEYWORD", "LOAD_A", "SAVE", "TIPS", "SCRIPT_B",
            "DIALOG_B", "LOAD_B"
        ]):
            binary = (f"{i:02d}_TARGET_{category}_".encode("ascii")
                      + bytes([(31 + i) % 255]) * (120 + i * 3))
            if category in ("KEYS","MOUS","KEYWORD","LOAD_A","SAVE","TIPS","LOAD_B"):
                binary = binary[:160].ljust(160, b"0")
            digest = _sha(binary)
            name = digest + ".bin"
            self.asset_names[category] = name
            self.targets[name] = binary
            path = folder / name
            path.write_bytes(binary)
            self.assets[name] = path
            ET.SubElement(self.rules, "Assets") if self.rules.find("Assets") is None else None
            ET.SubElement(self.rules.find("Assets"), "Asset",
                          name=name, sha=digest, size=str(len(binary)))

        for disc_index, disc in enumerate(DISC_NAMES):
            items = COMMON[:]
            if disc_index == 1:
                items = [item for item in COMMON if item not in ("DIALOG.RSP","MENU.INI")]
            if disc_index == 2:
                items = [item for item in COMMON if item != "MENU.INI"]
            img = ET.SubElement(self.rules, "Image", name=disc)
            raw = bytearray()
            listing, locations = {}, {}
            for resource in items:
                category = self._category(resource, disc_index)
                asset = self.asset_names[category]
                original = self._original(category, outer=True)
                offset = len(raw)
                raw.extend(original)
                listing[resource] = SimpleNamespace(
                    offset=offset, size=len(original), is_dir=False
                )
                ET.SubElement(img, "Replace", path=resource, asset=asset)
                self.usage_count += 1
            for name in INNER:
                category = self._category_inner(name, disc_index)
                asset = self.asset_names[category]
                original = self._original(category, outer=False)
                offset = len(raw)
                raw.extend(original)
                full = "1:/GRAPHIC/OTHER/" + name
                locations[full] = (offset, len(original))
                ET.SubElement(img, "Bitmap", path=full, asset=asset)
                self.usage_count += 1
            self.original_images[disc] = bytes(raw)
            (folder / disc).write_bytes(raw)
            img.set("count", str(len(listing)))
            img.set("sha", _sha(raw))
            self.listings[disc] = listing
            self.inner_locations[disc] = locations

        # The loose-root GOG originals are also present in the ISO resource data.
        for path, resource in (("MENU.INI", "MENU"), ("DIALOG.RSP", "DIALOG_A")):
            ET.SubElement(self.rules, "Loose", path=path,
                          asset=self.asset_names[resource])
            (folder / path).write_bytes(self._original(resource, outer=True))
        ET.SubElement(self.rules, "Loose", path="cloud_saves/DIALOG.RSP",
                      asset=self.asset_names["DIALOG_A"])
        saves = folder / "cloud_saves"
        saves.mkdir()
        (saves / "DIALOG.RSP").write_bytes(b"PROTECTED-USER-SAVE-DO-NOT-TOUCH")
        self.xml = ET.tostring(self.rules, encoding="utf-8", xml_declaration=True)
        self.rules_sha = _sha(self.xml)
        assert self.usage_count == 48
        assert len(self.assets) == 18

    @staticmethod
    def _category(path, disc_index):
        if path.endswith("KEYSHELP.BM"): return "KEYS"
        if path.endswith("MOUSHELP.BM"): return "MOUS"
        if path == "HARVEST.SCR": return "SCRIPT_B" if disc_index == 2 else "SCRIPT_A"
        if path == "DIALOG.RSP": return "DIALOG_B" if disc_index == 2 else "DIALOG_A"
        return {
            "DIALOGUE.IDX":"IDX", "ADJHEAD.RCS":"ADJ",
            "GRAPHIC/FONT/TEXTFONT.CFT":"FONT1",
            "GRAPHIC/FONT/MEDFONT1.CFT":"FONT2",
            "GRAPHIC/FONT/TEXTFNT2.CFT":"FONT3",
            "GRAPHIC/FONT/MEDFONT2.CFT":"FONT4", "MENU.INI":"MENU"
        }[path]

    @staticmethod
    def _category_inner(name, disc_index):
        return {
            "KEYWORD.BM":"KEYWORD",
            "LOADGAME.BM":"LOAD_B" if disc_index == 2 else "LOAD_A",
            "SAVEGAME.BM":"SAVE",
            "MOUSHELP.BM":"MOUS", "KEYSHELP.BM":"KEYS", "TIPS.BM":"TIPS"
        }[name]

    def _original(self, category, outer):
        target = self.targets[self.asset_names[category]]
        if category in ("KEYS", "MOUS", "KEYWORD", "LOAD_A", "SAVE",
                        "TIPS", "LOAD_B"):
            start = bytearray(target)
            start[7] ^= 0x57
            start[23] ^= (0x33 if outer else 0x11)
            return bytes(start)
        # Variable-length resources; preserve a COPY substring and insertion.
        return target[:26] + b"ENGLISH-OLD" + target[32:-1]

    def context(self):
        return (
            mock.patch.object(bundle, "scan_iso",
                              side_effect=lambda path: self.listings[path.name]),
            mock.patch.object(bundle.audit, "locate_xfile",
                              side_effect=lambda path, entries, wanted:
                              self.inner_locations[path.name])
        )


class TestUnifiedBundle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.fix = Fixture(self.folder)

    def tearDown(self):
        self.tmp.cleanup()

    def build(self):
        a, b = self.fix.context()
        with a, b:
            return bundle.build_bundle_bytes(
                self.folder, self.fix.xml, self.fix.assets,
                expected_rules_sha=self.fix.rules_sha, check_exe=False
            )

    def verify(self, data, refs=True):
        a, b = self.fix.context()
        with a, b:
            return bundle.verify_bundle_bytes(
                self.folder, data, expected_rules_sha=self.fix.rules_sha,
                check_exe=False,
                target_refs=self.fix.targets if refs else None
            )

    def repack(self, data, edit):
        with zipfile.ZipFile(io.BytesIO(data), "r") as src:
            members = {name: src.read(name) for name in src.namelist()}
        edit(members)
        mem = io.BytesIO()
        with zipfile.ZipFile(mem, "w") as dst:
            for name in sorted(members):
                dst.writestr(bundle._zipinfo(name), members[name])
        return mem.getvalue()

    def test_48_uses_20_variants_18_assets_real_zip_roundtrip(self):
        data, manifest = self.build()
        self.assertEqual(len(manifest["image_uses"]), 48)
        self.assertEqual(len(manifest["variants"]), 20)
        self.assertEqual(manifest["summary"]["distinct_target_assets"], 18)
        self.assertEqual(
            Counter(m["role"] for m in manifest["image_uses"]),
            Counter({"Replace":30,"Bitmap":18})
        )
        self.assertEqual(
            Counter(v["codec"] for v in manifest["variants"]),
            Counter({"bitmap-v2":9,"copyadd-v1":11})
        )
        self.assertGreater(len(data), 200)  # A real, in-memory ZIP byte sequence.
        proof = self.verify(data)
        self.assertEqual(proof["verified_iso_and_xfile_uses"], 48)
        self.assertEqual(proof["reconstructed_unique_pairs"], 20)
        self.assertEqual(proof["target_asset_count"], 18)
        self.assertEqual(proof["verified_loose_root_files"], 2)
        self.assertEqual(proof["sum_zlib9_delta_bytes"],
                         manifest["summary"]["packed_delta_bytes"])
        self.assertFalse(proof["source_or_game_written"])
        with zipfile.ZipFile(io.BytesIO(data), "r") as z:
            self.assertEqual(len(z.namelist()), 22)
            self.assertEqual(z.read("Regeln.xml"), self.fix.xml)
            self.assertFalse(any(name.endswith(".bin") for name in z.namelist()))
        for cd, original in self.fix.original_images.items():
            self.assertEqual((self.folder / cd).read_bytes(), original)
        self.assertEqual((self.folder / "cloud_saves/DIALOG.RSP").read_bytes(),
                         b"PROTECTED-USER-SAVE-DO-NOT-TOUCH")

    def test_zip_deterministic_independent_of_time(self):
        first, _ = self.build()
        second, _ = self.build()
        self.assertEqual(first, second)

    def test_wrong_original_iso_sha_rejected(self):
        data, _ = self.build()
        path = self.folder / DISC_NAMES[2]
        path.write_bytes(path.read_bytes() + b"wrong")
        with self.assertRaisesRegex(bundle.BundleError, "CD-SHA-256"):
            self.verify(data)

    def test_unknown_loose_root_source_variant_rejected(self):
        (self.folder / "MENU.INI").write_bytes(b"UNSUPPORTED-ENGLISH-VERSION")
        with self.assertRaisesRegex(bundle.BundleError, "nicht durch CD-Bundle"):
            self.build()

    def test_deleted_zip_variant_rejected(self):
        data, manifest = self.build()
        member = manifest["variants"][0]["member"]
        bad = self.repack(data, lambda members: members.pop(member))
        with self.assertRaises(bundle.BundleError):
            self.verify(bad)

    def test_corrupt_packed_delta_rejected(self):
        data, manifest = self.build()
        member = manifest["variants"][0]["member"]
        def corrupt(members):
            payload = bytearray(members[member])
            payload[-2] ^= 1
            members[member] = bytes(payload)
        with self.assertRaisesRegex(bundle.BundleError, "beschädigt"):
            self.verify(self.repack(data, corrupt))

    def test_corrupt_usage_mapping_rejected(self):
        data, _ = self.build()
        def change(members):
            import json
            manifest = json.loads(members["bundle.json"])
            manifest["image_uses"][0]["path"] = "GRAPHIC/OTHER/HACKED.BM"
            members["bundle.json"] = bundle.canonical_json(manifest)
        with self.assertRaisesRegex(bundle.BundleError, "Ressourcenpfad"):
            self.verify(self.repack(data, change))

    def test_modified_rule_xml_cannot_override_trusted_pin(self):
        data, _ = self.build()
        bad = self.repack(data, lambda members: members.__setitem__(
            "Regeln.xml", members["Regeln.xml"] + b"changed"
        ))
        with self.assertRaisesRegex(bundle.BundleError, "Regelmanifest"):
            self.verify(bad)

    def test_trailing_zlib_bytes_rejected_even_with_correct_packed_hash(self):
        data, manifest = self.build()
        member = manifest["variants"][0]["member"]
        def inject(members):
            import json
            doc = json.loads(members["bundle.json"])
            for v in doc["variants"]:
                if v["member"] == member:
                    p = members[member] + b"EXTRA"
                    v["packed_sha256"] = _sha(p)
                    v["packed_bytes"] = len(p)
                    members[member] = p
                    break
            members["bundle.json"] = bundle.canonical_json(doc)
        with self.assertRaisesRegex(bundle.BundleError, "zlib-Datensatz"):
            self.verify(self.repack(data, inject))

    def test_reject_duplicate_zip_member(self):
        data, _ = self.build()
        mem = io.BytesIO(data)
        with zipfile.ZipFile(mem, "a") as z:
            z.writestr(bundle._zipinfo("Regeln.xml"), b"duplicate")
        with self.assertRaisesRegex(bundle.BundleError, "ZIP-Dateien"):
            self.verify(mem.getvalue())

    def test_reject_unknown_or_wrong_target_asset(self):
        data, _ = self.build()
        def change(members):
            import json
            doc = json.loads(members["bundle.json"])
            doc["image_uses"][0]["asset"] = "0"*64+".bin"
            members["bundle.json"] = bundle.canonical_json(doc)
        with self.assertRaisesRegex(bundle.BundleError, "Ressourcenpfad"):
            self.verify(self.repack(data, change))

    def test_builder_rejects_modified_target_asset(self):
        name = next(iter(self.fix.assets))
        self.fix.assets[name].write_bytes(b"CORRUPT")
        with self.assertRaises(bundle.BundleError):
            self.build()

    def test_executable_must_be_verified_in_production_mode(self):
        a, b = self.fix.context()
        with a, b, self.assertRaisesRegex(bundle.BundleError, "HARVEST.EXE"):
            bundle.build_bundle_bytes(
                self.folder, self.fix.xml, self.fix.assets,
                expected_rules_sha=self.fix.rules_sha, check_exe=True
            )

    def test_existing_fix2_preflight_still_passes(self):
        rules, assets, digest = bundle.audit.load_verified_rules()
        self.assertEqual(digest, bundle.PINNED_RULES_SHA)
        self.assertEqual(len(assets),18)
        self.assertEqual(len(rules.findall("./Image")), 3)


if __name__ == "__main__":
    unittest.main()
