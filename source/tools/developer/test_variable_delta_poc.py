"""Synthetic regression tests: variable-length FIX2 COPY/ADD delta PoC.

No proprietary Harvester resources, original game images or saves used here.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import variable_delta_poc as poc


class TestVariableDelta(unittest.TestCase):
    def fixture(self):
        original = (
            b"HEADER|" + bytes(range(128)) * 8 + b"|MIDDLE|"
            + b"a_string_with_repeated_structure-" * 24 + b"|TAIL"
        )
        target = (
            original[:104] + b"<INSERTED-DEUTSCH>"
            + original[104:610] + original[636:]
            + b"<NEW-END>"
        )
        self.assertNotEqual(len(original), len(target))
        return original, target

    def test_insert_delete_roundtrip_variable_length(self):
        original, target = self.fixture()
        encoded, stats = poc.make_delta(original, target)
        self.assertEqual(poc.apply_delta(original, encoded), target)
        self.assertGreater(stats["copied_target_bytes"], 0)
        self.assertGreater(stats["new_literal_bytes"], 0)
        self.assertEqual(
            stats["copied_target_bytes"] + stats["new_literal_bytes"], len(target)
        )
        self.assertEqual(poc.make_delta(original, target), (encoded, stats))

    def test_identical_content_uses_copy(self):
        original = bytes(range(256)) * 9
        delta, stats = poc.make_delta(original, original)
        self.assertEqual(poc.apply_delta(original, delta), original)
        self.assertEqual(stats["new_literal_bytes"], 0)
        self.assertEqual(stats["copied_target_bytes"], len(original))

    def test_entirely_different_content_literal_fallback(self):
        src, target = b"A" * 200, b"Z" * 240
        encoded, stats = poc.make_delta(src, target)
        self.assertEqual(stats["copied_target_bytes"], 0)
        self.assertEqual(stats["new_literal_bytes"], len(target))
        self.assertEqual(poc.apply_delta(src, encoded), target)

    def test_short_files_smaller_than_match_anchor(self):
        original, target = b"xy", b"NEW-WORD"
        delta, stats = poc.make_delta(original, target)
        self.assertEqual(poc.apply_delta(original, delta), target)
        self.assertEqual(stats["new_literal_bytes"], len(target))

    def test_repeated_binary_runs_and_offset_shift(self):
        src = b"\x00" * 5000 + b"abcdefghijklmnopqrstuvwxyz" * 40
        target = b"\x00" * 4000 + b"prefix" + src[4000:] + b"tail!"
        delta, stats = poc.make_delta(src, target)
        self.assertEqual(poc.apply_delta(src, delta), target)
        self.assertGreater(stats["copied_target_bytes"], 3000)

    def test_wrong_original_hash_rejected(self):
        original, target = self.fixture()
        delta, _ = poc.make_delta(original, target)
        changed = original[:-1] + bytes([original[-1] ^ 0x7f])
        with self.assertRaisesRegex(poc.VariableDeltaError, "Original-SHA-256"):
            poc.apply_delta(changed, delta)

    def test_corrupt_header_and_wrong_target_digest_rejected(self):
        original, target = self.fixture()
        delta, _ = poc.make_delta(original, target)
        bad = bytearray(delta)
        bad[0] ^= 1
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, bytes(bad))
        bad = bytearray(delta)
        bad[48] ^= 1  # source SHA 16..47, target SHA 48..79
        with self.assertRaisesRegex(poc.VariableDeltaError, "Ziel-SHA-256"):
            poc.apply_delta(original, bytes(bad))

    def test_bad_ops_truncation_and_trailing_data_rejected(self):
        original, target = self.fixture()
        data, _ = poc.make_delta(original, target)
        invalid = [
            data[:-1], data + b"x",
            data[:poc.HEADER.size - 1],
            data[:poc.HEADER.size] + b"\xfe" + data[poc.HEADER.size + 1:],
        ]
        for bad in invalid:
            with self.subTest(n=len(bad)), self.assertRaises(
                (poc.VariableDeltaError, poc.compact.CompactError)
            ):
                poc.apply_delta(original, bad)

    def test_copy_outside_original_and_add_outside_target(self):
        original = b"A" * 128
        sha = poc.bitmaps.digest(original)
        header = poc.HEADER.pack(poc.MAGIC, len(original), 8, sha, sha, 1)
        bad_copy = (
            header + bytes([poc.COPY])
            + poc.compact.encode_u32(120) + poc.compact.encode_u32(30)
        )
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, bad_copy)
        bad_add = header + bytes([poc.ADD]) + poc.compact.encode_u32(9) + b"X"*9
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, bad_add)

    def test_reject_zero_length_count_bomb_and_consecutive_literal(self):
        original = b"A" * 128
        sha = poc.bitmaps.digest(original)
        header = lambda count: poc.HEADER.pack(poc.MAGIC, 128, 3, sha, sha, count)
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, header(0))
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, header(999_999))
        no_length = header(1) + bytes([poc.ADD]) + b"\x00"
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, no_length)
        adjacent = (
            header(2) + bytes([poc.ADD]) + b"\x01Z"
            + bytes([poc.ADD]) + b"\x02YY"
        )
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(original, adjacent)

    def test_different_original_versions_need_different_deltas(self):
        original = b"A" * 300 + b"same-tail" * 8
        variant = b"A" * 100 + b"other-longer" + b"A" * 195 + b"same-tail" * 8
        target = b"translated" + b"A" * 275 + b"same-tail" * 8
        self.assertNotEqual(len(original), len(variant))
        d1, _ = poc.make_delta(original, target)
        d2, _ = poc.make_delta(variant, target)
        self.assertNotEqual(d1, d2)
        self.assertEqual(poc.apply_delta(original, d1), target)
        self.assertEqual(poc.apply_delta(variant, d2), target)
        with self.assertRaises(poc.VariableDeltaError):
            poc.apply_delta(variant, d1)

    def test_statistics_and_zlib_roundtrip_no_exports(self):
        original, target = self.fixture()
        measurements = poc.compare_one(original, target)
        self.assertEqual(measurements["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(measurements["target_sha256"], hashlib.sha256(target).hexdigest())
        self.assertEqual(
            measurements["copied_target_bytes"] + measurements["new_literal_bytes"],
            len(target)
        )
        encoded, _ = poc.make_delta(original, target)
        # Compression may increase the size of already very short deltas.
        self.assertEqual(
            measurements["variable_delta_zlib9_bytes"],
            len(poc.zlib.compress(encoded, 9))
        )
        self.assertNotIn("original", str(measurements).lower().split("source_sha256")[0])

    def test_preflight_checks_existing_18_fix2_assets(self):
        rules, assets, manifest = poc.audit.load_verified_rules()
        self.assertEqual(manifest, poc.audit.EXPECTED_RULES_SHA256)
        self.assertEqual(len(assets), 18)
        self.assertEqual(
            len({n.get("asset") for img in rules.findall("./Image")
                 for n in img.findall("Bitmap")}), 7
        )

    def test_three_synthetic_images_cover_all_24_iso_uses_and_11_assets(self):
        """Full harness on fabricated resources; scan_iso is mocked, hashes real."""
        common = [
            ("HARVEST.SCR", "script_a"),
            ("DIALOG.RSP", "dialog_a"),
            ("DIALOGUE.IDX", "idx"),
            ("ADJHEAD.RCS", "tips"),
            ("GRAPHIC/FONT/TEXTFONT.CFT", "font1"),
            ("GRAPHIC/FONT/MEDFONT1.CFT", "font2"),
            ("GRAPHIC/FONT/TEXTFNT2.CFT", "font3"),
            ("GRAPHIC/FONT/MEDFONT2.CFT", "font4"),
            ("MENU.INI", "menu"),
        ]
        expected = [
            common,
            [x for x in common if x[0] not in ("DIALOG.RSP", "MENU.INI")],
            [(path, "script_b" if path == "HARVEST.SCR"
              else "dialog_b" if path == "DIALOG.RSP" else asset)
             for path, asset in common if path != "MENU.INI"],
        ]
        bitmap_assets = {f"b{n}.bin" for n in range(7)}
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            root = ET.Element("HarvesterPatch")
            original_per_asset, patched_per_asset, assets = {}, {}, {}
            for disc in expected:
                for _, name in disc:
                    if name in original_per_asset:
                        continue
                    base = (b"CODE-MARKER:" + name.encode() +
                            b"0123456789-abcdefghijklmnopqrstuvwxyz" * 12)
                    original_per_asset[name] = base
                    patched_per_asset[name] = base[:80] + b"NEUER-TEXT" + base[91:] + b"!"
                    file = folder / (name + ".bin")
                    file.write_bytes(patched_per_asset[name])
                    assets[name + ".bin"] = file
            for n in range(7):
                # Bitmap resource inventory is excluded from this harness.
                file = folder / f"b{n}.bin"
                file.write_bytes(b"safe synthetic bitmap")
                assets[f"b{n}.bin"] = file
            entries_by_disc = {}
            cd_names = ("HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT")
            for cd, manifest_rows in zip(cd_names, expected):
                img = ET.SubElement(root, "Image", name=cd)
                extents = {}
                combined = bytearray()
                for path, name in manifest_rows:
                    original = original_per_asset[name]
                    if cd == "HARVEST4.DAT" and name == "idx":
                        original = original[:80] + b"DIFFERENT-ORIGIN" + original[90:]
                    start = len(combined)
                    combined += original
                    extents[path] = SimpleNamespace(offset=start, size=len(original), is_dir=False)
                    ET.SubElement(img, "Replace", path=path, asset=name + ".bin")
                # Include two BMP Replace entries; the code must skip them.
                for n in (0, 1):
                    ET.SubElement(img, "Replace", path=f"GRAPHIC/OTHER/G{n}.BM",
                                  asset=f"b{n}.bin")
                for n in range(7):
                    ET.SubElement(img, "Bitmap", path=f"1:/GRAPHIC/OTHER/B{n}.BM",
                                  asset=f"b{n}.bin")
                img.set("count", str(len(extents)))
                raw = bytes(combined)
                img.set("sha", hashlib.sha256(raw).hexdigest())
                (folder / cd).write_bytes(raw)
                entries_by_disc[cd] = extents
            # Root loose files checked only at game root, not cloud_saves.
            for path, name in (("MENU.INI", "menu"), ("DIALOG.RSP", "dialog_a")):
                ET.SubElement(root, "Loose", path=path, asset=name + ".bin")
                (folder / path).write_bytes(original_per_asset[name])
            ET.SubElement(root, "Loose", path="cloud_saves/DIALOG.RSP",
                          asset="dialog_a.bin")
            saves = folder / "cloud_saves"
            saves.mkdir()
            (saves / "DIALOG.RSP").write_bytes(b"USER-SAVE-DO-NOT-TOUCH")
            cd_hashes = {cd: (folder / cd).read_bytes() for cd in cd_names}
            with mock.patch.object(
                poc, "scan_iso", side_effect=lambda path: entries_by_disc[path.name]
            ), mock.patch.object(poc, "compare_one", wraps=poc.compare_one) as measured:
                report = poc.compare_original_gog(folder, root, assets)
            self.assertEqual(
                measured.call_count,
                report["summary"]["distinct_source_target_pairs_including_optional_loose"],
                "Only reconstruct each unique SHA-256 source/target pair once."
            )
            s = report["summary"]
            self.assertEqual(s["verified_gog_iso_sha256"], 3)
            self.assertEqual(s["non_bitmap_iso_replacements_checked"], 24)
            self.assertEqual(s["distinct_fix2_non_bitmap_assets"], 11)
            self.assertEqual(s["optional_loose_file_comparisons"], 2)
            self.assertGreaterEqual(s["distinct_source_target_pairs_including_optional_loose"], 12)
            self.assertGreater(s["total"]["copied_target_bytes"], 0)
            self.assertFalse(report["game_or_delta_bytes_written"])
            self.assertFalse(report["contains_original_or_translated_game_bytes"])
            self.assertEqual((saves / "DIALOG.RSP").read_bytes(), b"USER-SAVE-DO-NOT-TOUCH")
            for cd in cd_names:
                self.assertEqual((folder / cd).read_bytes(), cd_hashes[cd])


if __name__ == "__main__":
    unittest.main()
