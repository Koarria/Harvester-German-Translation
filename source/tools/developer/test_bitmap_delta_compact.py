"""Synthetic, no-game-data tests for compact bitmap delta v2."""
from __future__ import annotations

import struct
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bitmap_delta_compact as compact
import bitmap_delta_poc as v1


class TestCompactDelta(unittest.TestCase):
    def test_roundtrip_and_size_vs_v1(self):
        original=b"A"*51+b"B"*25+b"C"*51+b"D"*25+b"E"*51
        target=bytearray(original)
        target[0]=0
        target[50:53]=b"XYZ"
        target[130:133]=b"123"
        target[-1]=9
        target=bytes(target)
        one=v1.create_delta(original,target)
        two=compact.make_delta(original,target)
        self.assertEqual(compact.restore_delta(original,two),target)
        self.assertEqual(v1.apply_delta(original,one),target)
        self.assertLess(len(two),len(one))
        self.assertEqual(compact.compare_versions(original,target)["v2_varint_bytes"],len(two))

    def test_varint_encoding_canonical_boundaries(self):
        for value in (0,1,2,127,128,129,255,300,16383,16384,65536,2**21,2**28,0xffffffff):
            blob=compact.encode_u32(value)
            self.assertEqual(compact.read_u32(blob,0),(value,len(blob)))
            self.assertLessEqual(len(blob),5)

    def test_varint_invalid_data(self):
        for bad in (b"",b"\x80",b"\x80\x00",b"\xff\xff\xff\xff\x10",
                    b"\x80\x80\x80\x80\x80",b"\xff\xff\xff\xff\xff"):
            with self.subTest(bad=bad),self.assertRaises(compact.CompactError):
                compact.read_u32(bad,0)
        for bad in (-1,0x100000000,1.3):
            with self.subTest(bad=bad),self.assertRaises(compact.CompactError):
                compact.encode_u32(bad)

    def test_identical_source_target_header_only(self):
        original=b"same"*100
        delta=compact.make_delta(original,original)
        self.assertEqual(len(delta),compact.HEADER.size)
        self.assertEqual(compact.restore_delta(original,delta),original)

    def test_wrong_size_and_bad_source(self):
        original=b"A"*100
        target=b"B"*100
        delta=compact.make_delta(original,target)
        with self.assertRaises(compact.CompactError):
            compact.make_delta(original,target+b"!")
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(b"B"+original[1:],delta)

    def test_detect_bad_target_data_and_hash(self):
        original=b"A"*100
        dst=b"B"*100
        delta=compact.make_delta(original,dst)
        changed=bytearray(delta)
        changed[-1]^=1
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(original,bytes(changed))
        changed=bytearray(delta)
        changed[44]^=1
        with self.assertRaisesRegex(compact.CompactError,"Ziel-SHA"):
            compact.restore_delta(original,bytes(changed))

    def test_trailing_bytes_and_truncation_fail(self):
        original=b"A"*100
        target=b"Z"+original[1:]
        delta=compact.make_delta(original,target)
        for bad in (delta+b"\x00",delta[:-1],delta[:compact.HEADER.size-1]):
            with self.subTest(length=len(bad)),self.assertRaises(compact.CompactError):
                compact.restore_delta(original,bad)

    def test_noncanonical_zero_and_adjacent_runs(self):
        original=b"A"*100
        sha=v1.digest(original)
        header=lambda count:compact.HEADER.pack(compact.MAGIC,len(original),sha,sha,count)
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(original,header(1)+b"\x80\x00\x01Z")
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(original,header(1)+b"\x00\x00")
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(original,header(2)+b"\x00\x01Z\x00\x01Y")

    def test_count_bomb_and_overflowed_runs(self):
        original=b"A"*30
        sha=v1.digest(original)
        for bad in (
            compact.HEADER.pack(compact.MAGIC,30,sha,sha,2**32-1),
            compact.HEADER.pack(compact.MAGIC,30,sha,sha,1)+b"\x1e\x01Z",
        ):
            with self.assertRaises(compact.CompactError):
                compact.restore_delta(original,bad)

    def test_one_target_two_sources_are_not_interchangeable(self):
        original=b"A"*300
        variant=b"B"*300
        target=b"Z"*300
        d1=compact.make_delta(original,target)
        d2=compact.make_delta(variant,target)
        self.assertNotEqual(d1,d2)
        self.assertEqual(compact.restore_delta(original,d1),target)
        self.assertEqual(compact.restore_delta(variant,d2),target)
        with self.assertRaises(compact.CompactError):
            compact.restore_delta(variant,d1)

    def test_many_short_runs_and_roundtrip(self):
        original=b"A"*8192
        modified=bytes((ord("Z") if i%2 else ord("A")) for i in range(len(original)))
        d1=v1.create_delta(original,modified)
        d2=compact.make_delta(original,modified)
        self.assertEqual(compact.restore_delta(original,d2),modified)
        self.assertLess(len(d2),len(d1))

    def test_diff_vs_v1_stat_fields(self):
        a=b"x"*1000
        b=bytes(ord("z") if i%31==1 else ord("x") for i in range(1000))
        d=compact.compare_versions(a,b)
        self.assertEqual(d["changed_positions"],sum(x!=y for x,y in zip(a,b)))
        self.assertLess(d["v2_varint_bytes"],d["v1_bytes"])
        self.assertLess(d["v2_zlib9_bytes"],d["v2_varint_bytes"])
        self.assertEqual(d["source_sha256"],v1.audit.sha256_bytes(a))
        self.assertEqual(d["target_sha256"],v1.audit.sha256_bytes(b))


if __name__=="__main__":
    unittest.main()
