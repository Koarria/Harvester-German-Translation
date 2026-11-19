"""Synthetic read-only audit tests. No game originals included or required."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import struct
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import originalvergleich_gog as audit


class TestOriginalvergleich(unittest.TestCase):
    def test_payload_preflight_against_tracked_rc3b_assets(self):
        _, assets, digest = audit.load_verified_rules()
        self.assertEqual(digest, audit.EXPECTED_RULES_SHA256)
        self.assertEqual(len(assets), 18)

    def test_equal_bytes_report_and_minimum_contiguous_run(self):
        a = b"ORIGINAL" * 20
        x = audit.compare_bytes(a, a)
        self.assertTrue(x["byte_identical"])
        self.assertEqual(x["same_offset_equal_bytes"], len(a))
        self.assertEqual(x["same_offset_runs_ge_32_count"], 1)
        self.assertEqual(x["same_offset_bytes_in_runs_ge_32"], len(a))

    def test_changed_bytes_with_exact_prefix_and_suffix(self):
        a = b"A" * 64 + b"something_old" + b"Z" * 64
        b = b"A" * 64 + b"NEW!" + b"Z" * 64
        x = audit.compare_bytes(a, b)
        self.assertFalse(x["byte_identical"])
        self.assertEqual(x["exact_common_prefix_bytes"], 64)
        self.assertEqual(x["exact_common_suffix_bytes_no_overlap"], 64)
        self.assertEqual(x["same_offset_equal_bytes"] >= 64, True)

    def test_text_structure_does_not_expose_text(self):
        a = b"1. Hello/2. Other\r\nName: %s\r\n"
        b = b"1. Hallo/2. Sonst\r\nName: %s\r\n"
        x = audit.text_structure(a, b)
        self.assertTrue(x["slash_count_per_line_preserved"])
        self.assertTrue(x["percent_s_d_placeholders_per_line_preserved"])
        self.assertNotIn("Hello", str(x))
        self.assertNotIn("Hallo", str(x))

    @staticmethod
    def xfile_fixture():
        name = b"1:\\GRAPHIC\\OTHER\\KEYWORD.BM"
        record = bytearray(148)
        record[:4] = b"XFLE"
        record[4:4 + len(name)] = name
        struct.pack_into("<III", record, 132, 148, 4, 0)
        struct.pack_into("<I", record, 144, 4)
        return bytes(record), bytes(record) + b"DATA"

    def test_xfile_validates_148_byte_structure_and_path(self):
        index, dat = self.xfile_fixture()
        items = audit.parse_xfile_index(index, len(dat))
        self.assertIn("1:/GRAPHIC/OTHER/KEYWORD.BM", items)
        hdr, payload_at, size, original_record = items["1:/GRAPHIC/OTHER/KEYWORD.BM"]
        self.assertEqual((hdr, payload_at, size), (0, 148, 4))
        self.assertEqual(dat[hdr:hdr + 148], original_record)
        self.assertEqual(dat[payload_at:payload_at + size], b"DATA")

    def test_xfile_rejects_bad_offsets_and_duplicate_ids(self):
        index, dat = self.xfile_fixture()
        bad = bytearray(index)
        struct.pack_into("<I", bad, 132, 999)
        with self.assertRaises(audit.AuditError):
            audit.parse_xfile_index(bytes(bad), len(dat))
        with self.assertRaises(audit.AuditError):
            audit.parse_xfile_index(index + index, len(dat) * 2)

    def test_xfile_allows_irrelevant_empty_and_duplicate_names(self):
        target = "1:/GRAPHIC/OTHER/KEYWORD.BM"
        first, _ = self.xfile_fixture()

        def extra(name, cursor):
            rec = bytearray(148)
            rec[:4] = b"XFLE"
            rec[4:4 + len(name)] = name
            struct.pack_into("<IIII", rec, 132, cursor + 148, 1, 0, 1)
            return bytes(rec), cursor + 149

        filler1, pos1 = extra(b"UNRELATED", 152)
        filler2, pos2 = extra(b"UNRELATED", pos1)
        unnamed, end = extra(b"", pos2)
        data = first + filler1 + filler2 + unnamed
        with self.assertRaises(audit.AuditError):
            audit.parse_xfile_index(data, end)
        found = audit.parse_xfile_index(data, end, {target})
        self.assertEqual(set(found), {target})
        self.assertEqual(found[target][1:3], (148, 4))

    def test_xfile_still_rejects_duplicate_target_and_bad_target_metadata(self):
        target = "1:/GRAPHIC/OTHER/KEYWORD.BM"
        first, _ = self.xfile_fixture()
        duplicate = bytearray(first)
        struct.pack_into("<IIII", duplicate, 132, 300, 4, 0, 4)
        with self.assertRaises(audit.AuditError):
            audit.parse_xfile_index(first + bytes(duplicate), 304, {target})
        bad = bytearray(first)
        struct.pack_into("<I", bad, 140, 1)
        with self.assertRaises(audit.AuditError):
            audit.parse_xfile_index(bytes(bad), 152, {target})

    def test_exe_edits_checked_in_memory_original_remains_unchanged(self):
        source = b"0123456789abcdefghijklmnop"
        target = bytearray(source)
        target[3:5] = b"XY"
        target[15:18] = b"DEF"
        rules = ET.Element("Executable", target=hashlib.sha256(target).hexdigest())
        ET.SubElement(rules, "Edit", offset="3", old=b"34".hex(), new=b"XY".hex())
        ET.SubElement(rules, "Edit", offset="15", old=b"fgh".hex(), new=b"DEF".hex())
        data = audit.apply_exe_edits_for_verification(source, rules)
        self.assertEqual(data["edits_checked"], 2)
        self.assertEqual(data["edited_bytes"], 5)
        self.assertTrue(data["target_hash_matches"])
        self.assertEqual(source[3:5], b"34")
        wrong = ET.Element("Executable", target=hashlib.sha256(target).hexdigest())
        ET.SubElement(wrong, "Edit", offset="3", old=b"bad".hex(), new=b"XYZ".hex())
        with self.assertRaises(audit.AuditError):
            audit.apply_exe_edits_for_verification(source, wrong)

    def test_reports_cannot_write_inside_gog_or_repo(self):
        with TemporaryDirectory() as temp:
            source = Path(temp) / "GOG"
            source.mkdir()
            with self.assertRaises(audit.AuditError):
                audit.valid_report_directory(source / "Reports", source)
            self.assertEqual(audit.valid_report_directory(Path(temp) / "Reports", source),
                             (Path(temp) / "Reports").resolve())
        with self.assertRaises(audit.AuditError):
            audit.valid_report_directory(audit.REPO / "AUDIT.json", Path.home())

    def test_read_span_truncation_rejected(self):
        with TemporaryDirectory() as temp:
            file = Path(temp) / "source.bin"
            file.write_bytes(b"hello world")
            self.assertEqual(audit.read_span(file, 1, 3), b"ell")
            with self.assertRaises(audit.AuditError):
                audit.read_span(file, 0, len(b"hello world") + 1)


    def test_synthetic_iso_and_nested_xfile_end_to_end(self):
        """Real ISO reader + nested XFILE lookup, on synthetic bytes only."""
        def both32(n):
            return struct.pack("<I", n) + struct.pack(">I", n)

        def both16(n):
            return struct.pack("<H", n) + struct.pack(">H", n)

        def record(name, sector, size, is_dir=False):
            if isinstance(name, str):
                name = name.encode("ascii")
            length = 33 + len(name) + (len(name) % 2 == 0)
            result = bytearray(length)
            result[0] = length
            result[2:10] = both32(sector)
            result[10:18] = both32(size)
            result[25] = 2 if is_dir else 0
            result[28:32] = both16(1)
            result[32] = len(name)
            result[33:33 + len(name)] = name
            return bytes(result)

        with TemporaryDirectory() as temp:
            root = Path(temp)
            en_script = b"EN-script-original"
            de_script = b"DE-script-patched!"
            bitmap = b"ENpixels"
            de_bitmap = b"DEpixels"
            index = bytearray(148)
            index[:4] = b"XFLE"
            name = b"1:\\GRAPHIC\\OTHER\\KEYWORD.BM"
            index[4:4 + len(name)] = name
            struct.pack_into("<IIII", index, 132, 148, len(bitmap), 0, len(bitmap))
            native = bytes(index) + bitmap

            cd = bytearray(32 * 2048)
            pvd = 16 * 2048
            cd[pvd:pvd + 7] = b"\x01CD001\x01"
            cd[pvd + 80:pvd + 88] = both32(32)
            cd[pvd + 156:pvd + 190] = record(b"\0", 20, 2048, is_dir=True)
            entries = [
                record(b"\0", 20, 2048, is_dir=True),
                record(b"\1", 20, 2048, is_dir=True),
                record("HARVEST.SCR;1", 22, len(en_script)),
                record("INDEX.001;1", 23, len(index)),
                record("HARVEST.DAT;1", 24, len(native)),
            ]
            directory = b"".join(entries)
            cd[20 * 2048:20 * 2048 + len(directory)] = directory
            cd[22 * 2048:22 * 2048 + len(en_script)] = en_script
            cd[23 * 2048:23 * 2048 + len(index)] = index
            cd[24 * 2048:24 * 2048 + len(native)] = native
            iso = root / "HARVEST.DAT"
            iso.write_bytes(cd)

            names = ["a" * 64 + ".bin", "b" * 64 + ".bin"]
            for filename, data in zip(names, (de_script, de_bitmap)):
                (root / filename).write_bytes(data)
            assets = {name: root / name for name in names}
            rules = ET.Element(
                "Image", name="HARVEST.DAT", sha=hashlib.sha256(cd).hexdigest(),
                count="3"
            )
            ET.SubElement(rules, "Replace", path="HARVEST.SCR", asset=names[0])
            ET.SubElement(rules, "Bitmap", path="1:/GRAPHIC/OTHER/KEYWORD.BM", asset=names[1])
            result = audit.audit_image(root, rules, assets)
            self.assertEqual(result["status"], "VERIFIED", result["issues"])
            self.assertEqual(result["issues"], [])
            self.assertEqual(len(result["replacements"]), 1)
            self.assertEqual(len(result["native_bitmaps"]), 1)
            self.assertEqual(
                result["native_bitmaps"][0]["comparison"]["replacement_bytes"], len(de_bitmap)
            )
            self.assertEqual(iso.read_bytes(), cd, "Audit must never modify input ISO")
            ET.SubElement(rules, "Bitmap", path="1:/GRAPHIC/OTHER/MISSING.BM", asset=names[1])
            partial = audit.audit_image(root, rules, assets)
            self.assertEqual(partial["status"], "PARTIAL")
            self.assertTrue(partial["source_sha256_matches"])
            self.assertTrue(any("MISSING.BM" in issue for issue in partial["issues"]))


if __name__ == "__main__":
    unittest.main()
