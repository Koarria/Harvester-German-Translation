"""Synthetic validation of the private sparse-bitmap-delta proof of concept."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bitmap_delta_poc as poc


class TestSparseDelta(unittest.TestCase):
    def sample(self):
        src = b"Q" * 51 + b"old!" + b"K" * 75 + b"keep" + b"Z" * 52
        dst = bytearray(src)
        dst[0] = 0
        dst[51:55] = b"NEW?"
        dst[-1] = 1
        return src, bytes(dst)

    def test_exact_round_trip_and_only_changed_new_bytes(self):
        src, dst = self.sample()
        encoded = poc.create_delta(src, dst)
        self.assertEqual(poc.apply_delta(src, encoded), dst)
        self.assertEqual(src[:10], b"Q" * 10)
        count, changed = poc.delta_statistics(encoded)
        self.assertEqual(count, 3)
        self.assertEqual(changed, 6)
        self.assertEqual(
            len(encoded), poc.HEADER.size + 3 * poc.RUN.size + changed
        )
        self.assertEqual(poc.create_delta(src, dst), encoded)

    def test_identical_file_generates_header_only(self):
        src = b"same" * 64
        encoded = poc.create_delta(src, src)
        self.assertEqual(len(encoded), poc.HEADER.size)
        self.assertEqual(poc.delta_statistics(encoded), (0, 0))
        self.assertEqual(poc.apply_delta(src, encoded), src)

    def test_single_byte_at_both_ends_and_empty_unsupported(self):
        src = b"A" * 128
        mod = b"Z" + src[1:-1] + b"B"
        encoded = poc.create_delta(src, mod)
        self.assertEqual(poc.apply_delta(src, encoded), mod)
        self.assertEqual(poc.delta_statistics(encoded), (2, 2))
        with self.assertRaises(poc.DeltaError):
            poc.create_delta(b"", b"")
        with self.assertRaises(poc.DeltaError):
            poc.create_delta(b"A", b"longer")

    def test_wrong_source_hash_is_rejected(self):
        a, b = self.sample()
        encoded = poc.create_delta(a, b)
        modified = bytearray(a)
        modified[80] ^= 1
        with self.assertRaisesRegex(poc.DeltaError, "Original-SHA-256"):
            poc.apply_delta(bytes(modified), encoded)

    def test_corrupt_header_and_wrong_target_digest_rejected(self):
        a, b = self.sample()
        encoded = poc.create_delta(a, b)
        bad = bytearray(encoded)
        bad[0] ^= 1
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(a, bytes(bad))
        bad = bytearray(encoded)
        bad[8:12] = struct.pack("<I", len(a) + 1)
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(a, bytes(bad))
        bad = bytearray(encoded)
        bad[44] ^= 1  # target SHA is at offsets 44..75
        with self.assertRaisesRegex(poc.DeltaError, "Ziel-SHA"):
            poc.apply_delta(a, bytes(bad))

    def test_tampered_patch_bytes_and_trailing_or_truncated_data(self):
        a, b = self.sample()
        encoded = poc.create_delta(a, b)
        wrong = bytearray(encoded)
        wrong[-1] ^= 1
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(a, bytes(wrong))
        for data in (encoded[:-1], encoded + b"extra", encoded[:poc.HEADER.size - 1]):
            with self.assertRaises(poc.DeltaError):
                poc.apply_delta(a, data)

    def test_reject_overlap_zero_length_and_out_of_bounds(self):
        a = b"A" * 100
        h = poc.HEADER.pack(poc.MAGIC, len(a), poc.digest(a), poc.digest(a), 2)
        cases = [
            h + poc.RUN.pack(10, 2) + b"XY" + poc.RUN.pack(11, 1) + b"Z",
            h + poc.RUN.pack(10, 0) + poc.RUN.pack(15, 1) + b"B",
            h + poc.RUN.pack(98, 4) + b"XXXX" + poc.RUN.pack(15, 1) + b"B",
        ]
        for data in cases:
            with self.subTest(data=data[:30]):
                with self.assertRaises(poc.DeltaError):
                    poc.apply_delta(a, data)

    def test_reject_zero_length_run_even_single_and_redundant_original_bytes(self):
        a = b"A" * 100
        h = poc.HEADER.pack(poc.MAGIC, len(a), poc.digest(a), poc.digest(a), 1)
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(a, h + poc.RUN.pack(10, 0))
        with self.assertRaisesRegex(poc.DeltaError, "unveränderte Originalbytes"):
            poc.apply_delta(a, h + poc.RUN.pack(10, 1) + b"A")

    def test_count_bomb_rejected_before_allocation(self):
        a = b"X" * 100
        h = poc.HEADER.pack(poc.MAGIC, len(a), poc.digest(a), poc.digest(a), 2**32 - 1)
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(a, h)

    def test_two_source_variants_one_target_need_distinct_delta(self):
        a = b"A" * 150
        c = b"Q" * 150
        dst = b"Z" * 150
        first = poc.create_delta(a, dst)
        second = poc.create_delta(c, dst)
        self.assertNotEqual(first, second)
        self.assertEqual(poc.apply_delta(a, first), dst)
        self.assertEqual(poc.apply_delta(c, second), dst)
        with self.assertRaises(poc.DeltaError):
            poc.apply_delta(c, first)

    def test_format_is_not_an_implicit_file_writer(self):
        src, dst = self.sample()
        self.assertEqual(poc.apply_delta(src, poc.create_delta(src, dst)), dst)
        self.assertIsInstance(poc.apply_delta(src, poc.create_delta(src, dst)), bytes)

    def test_three_synthetic_gog_cds_and_seven_xfile_variants_end_to_end(self):
        """Use actual ISO and XFILE readers, never proprietary game originals."""
        import hashlib
        from tempfile import TemporaryDirectory
        import xml.etree.ElementTree as ET

        def both32(n):
            return struct.pack("<I", n) + struct.pack(">I", n)

        def both16(n):
            return struct.pack("<H", n) + struct.pack(">H", n)

        def iso_record(name, sector, size, is_dir=False):
            if isinstance(name, str):
                name = name.encode("ascii")
            length = 33 + len(name) + (len(name) % 2 == 0)
            rec = bytearray(length)
            rec[0] = length
            rec[2:10] = both32(sector)
            rec[10:18] = both32(size)
            rec[25] = 2 if is_dir else 0
            rec[28:32] = both16(1)
            rec[32] = len(name)
            rec[33:33 + len(name)] = name
            return bytes(rec)

        names = ["KEYWORD", "LOADGAME", "SAVEGAME",
                 "MOUSHELP", "KEYSHELP", "TIPS"]
        cds = ["HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT"]
        rules = ET.Element("HarvesterPatch")
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            assets = {}
            originals = {}
            for disc_index, cd in enumerate(cds):
                index = bytearray()
                inner = bytearray()
                manifest = ET.SubElement(rules, "Image", name=cd, count="2")
                for idx, resource in enumerate(names):
                    value = 35 + idx + (25 if disc_index == 2 and idx == 1 else 0)
                    original = bytes([value]) * 100
                    replacement = bytearray(original)
                    replacement[2 + idx * 3] ^= 0x5A
                    replacement = bytes(replacement)
                    filename = hashlib.sha256(replacement).hexdigest() + ".bin"
                    if filename not in assets:
                        location = folder / filename
                        location.write_bytes(replacement)
                        assets[filename] = location
                    resource_name = "1:/GRAPHIC/OTHER/" + resource + ".BM"
                    ET.SubElement(
                        manifest, "Bitmap", path=resource_name, asset=filename
                    )
                    rec = bytearray(148)
                    rec[:4] = b"XFLE"
                    raw_name = resource_name.replace("/", "\\").encode("ascii")
                    rec[4:4 + len(raw_name)] = raw_name
                    struct.pack_into(
                        "<IIII", rec, 132, len(inner) + 148,
                        len(original), 0, len(original)
                    )
                    index.extend(rec)
                    inner.extend(rec)
                    inner.extend(original)

                iso = bytearray(32 * 2048)
                pvd = 16 * 2048
                iso[pvd:pvd + 7] = b"\x01CD001\x01"
                iso[pvd + 80:pvd + 88] = both32(32)
                iso[pvd + 156:pvd + 190] = iso_record(
                    b"\x00", 20, 2048, is_dir=True
                )
                records = b"".join([
                    iso_record(b"\x00", 20, 2048, is_dir=True),
                    iso_record(b"\x01", 20, 2048, is_dir=True),
                    iso_record("INDEX.001;1", 23, len(index)),
                    iso_record("HARVEST.DAT;1", 24, len(inner)),
                ])
                iso[20 * 2048:20 * 2048 + len(records)] = records
                iso[23 * 2048:23 * 2048 + len(index)] = index
                iso[24 * 2048:24 * 2048 + len(inner)] = inner
                manifest.set("sha", hashlib.sha256(iso).hexdigest())
                (folder / cd).write_bytes(iso)
                originals[cd] = bytes(iso)

            self.assertEqual(len(assets), 7)
            result = poc.audit_gog_bitmaps(folder, rules, assets)
            summary = result["summary"]
            self.assertEqual(summary["original_cd_sha256_verified"], 3)
            self.assertEqual(summary["xfile_bitmap_uses_checked"], 18)
            self.assertEqual(summary["distinct_source_target_pairs"], 7)
            self.assertEqual(len(result["pairs"]), 7)
            self.assertTrue(all(
                pair["changed_byte_positions"] == 1 for pair in result["pairs"]
            ))
            self.assertFalse(result["contains_original_or_patched_game_bytes"])
            self.assertFalse(result["deltas_or_game_bytes_written"])
            for cd in cds:
                self.assertEqual(
                    (folder / cd).read_bytes(), originals[cd],
                    "Even the synthetic source ISO must not be changed."
                )
            corrupt = bytearray(originals[cds[0]])
            corrupt[-1] ^= 1
            (folder / cds[0]).write_bytes(corrupt)
            with self.assertRaisesRegex(poc.DeltaError, "SHA-256 falsch"):
                poc.audit_gog_bitmaps(folder, rules, assets)

    def test_preflight_uses_existing_verified_fix2(self):
        rules, assets, manifest = poc.audit.load_verified_rules()
        self.assertEqual(len(assets), 18)
        self.assertEqual(manifest, poc.audit.EXPECTED_RULES_SHA256)
        self.assertEqual(len(rules.findall("./Image")), 3)


if __name__ == "__main__":
    unittest.main()
