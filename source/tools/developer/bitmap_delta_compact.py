#!/usr/bin/env python3
"""Private in-memory compact bitmap delta benchmark (v2 varint vs v1).

No proprietary images, resource bytes, ISO images, or delta bytes are
written. Only a summary JSON without local game paths is produced.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys
import zlib

import bitmap_delta_poc as v1
import originalvergleich_gog as audit
from runtime.harvester_iso import hash_file, scan_iso

MAGIC = b"HVBDP02\x00"
HEADER = struct.Struct("<8sI32s32sI")
MAX_BYTES = v1.MAX_BITMAP * 2 + HEADER.size
MAX_U32 = 0xffffffff


class CompactError(ValueError):
    pass


def encode_u32(n: int) -> bytes:
    if not isinstance(n, int) or not 0 <= n <= MAX_U32:
        raise CompactError("Varint außerhalb uint32")
    result = bytearray()
    while n >= 0x80:
        result.append((n & 0x7f) | 0x80)
        n >>= 7
    result.append(n)
    return bytes(result)


def read_u32(data: bytes, at: int) -> tuple[int, int]:
    start, value, shift = at, 0, 0
    for i in range(5):
        if at >= len(data):
            raise CompactError("Abgeschnittener Varint")
        b = data[at]
        at += 1
        if i == 4 and (b & 0xf0):
            raise CompactError("Varint-Überlauf")
        value |= (b & 0x7f) << shift
        if not (b & 0x80):
            if data[start:at] != encode_u32(value):
                raise CompactError("Nicht kanonischer Varint")
            return value, at
        shift += 7
    raise CompactError("Zu langer Varint")


def make_delta(source: bytes, target: bytes) -> bytes:
    v1._check_source_size(source)
    if len(target) != len(source):
        raise CompactError("Nur gleich große Bitmap-Dateien erlaubt")
    runs = []
    pos = 0
    previous_end = 0
    while pos < len(source):
        if source[pos] == target[pos]:
            pos += 1
            continue
        start = pos
        while pos < len(source) and source[pos] != target[pos]:
            pos += 1
        runs.append((start - previous_end, target[start:pos]))
        previous_end = pos
    if len(runs) > (len(source) + 1)//2:
        raise CompactError("Unmögliche Änderungsbereichanzahl")
    result = bytearray(HEADER.pack(
        MAGIC, len(source), v1.digest(source), v1.digest(target), len(runs)
    ))
    for skip, changed in runs:
        result += encode_u32(skip)
        result += encode_u32(len(changed))
        result += changed
    if len(result) > MAX_BYTES:
        raise CompactError("Kompakt-Delta überschreitet Obergrenze")
    return bytes(result)


def restore_delta(source: bytes, delta: bytes) -> bytes:
    v1._check_source_size(source)
    if not HEADER.size <= len(delta) <= MAX_BYTES:
        raise CompactError("Ungültige Delta-Dateigröße")
    magic, length, original_hash, patched_hash, count = HEADER.unpack_from(delta)
    if magic != MAGIC or length != len(source):
        raise CompactError("Ungültiges Format oder falsche Quelllänge")
    if v1.digest(source) != original_hash:
        raise CompactError("Quell-SHA-256 ist falsch")
    if count > (length + 1)//2 or len(delta) < HEADER.size + 3*count:
        raise CompactError("Unplausible Anzahl Änderungsbereiche")
    result = bytearray(source)
    at, previous_end = HEADER.size, 0
    for n in range(count):
        skip, at = read_u32(delta, at)
        amount, at = read_u32(delta, at)
        if (n > 0 and skip == 0) or amount == 0:
            raise CompactError("Leerer oder nicht zusammengefasster Änderungsbereich")
        start = previous_end + skip
        end = start + amount
        if end > length or at + amount > len(delta):
            raise CompactError("Ungültiger Bytebereich oder abgeschnittene Nutzdaten")
        changed = delta[at:at + amount]
        if any(a == b for a, b in zip(source[start:end], changed)):
            raise CompactError("Delta enthält unveränderte Bytes")
        result[start:end] = changed
        previous_end = end
        at += amount
    if at != len(delta):
        raise CompactError("Unerwartete Daten nach Delta")
    rebuilt = bytes(result)
    if v1.digest(rebuilt) != patched_hash:
        raise CompactError("Ziel-SHA-256 ist falsch")
    return rebuilt


def compare_versions(original: bytes, target: bytes) -> dict:
    """Reconstruct with BOTH decoders and report only sizes/hashes."""
    delta1 = v1.create_delta(original, target)
    delta2 = make_delta(original, target)
    if v1.apply_delta(original, delta1) != target:
        raise CompactError("V1-Rekonstruktion fehlgeschlagen")
    if restore_delta(original, delta2) != target:
        raise CompactError("V2-Rekonstruktion fehlgeschlagen")
    count, changed = v1.delta_statistics(delta1)
    return {
        "source_sha256": audit.sha256_bytes(original),
        "target_sha256": audit.sha256_bytes(target),
        "source_bytes": len(original),
        "target_bytes": len(target),
        "changed_positions": changed,
        "run_count": count,
        "v1_bytes": len(delta1),
        "v2_varint_bytes": len(delta2),
        "v1_zlib9_bytes": len(zlib.compress(delta1, 9)),
        "v2_zlib9_bytes": len(zlib.compress(delta2, 9)),
        "v2_sha256": audit.sha256_bytes(delta2),
    }


def benchmark_local_gog(source: Path, rules, assets: dict[str, Path]) -> dict:
    """Repeat all trusted source checks; no game-content output."""
    cases: dict[tuple[str, str], dict] = {}
    uses = 0
    imgs = rules.findall("./Image")
    if len(imgs) != 3:
        raise CompactError("Es werden genau drei originale GOG-Abbilder erwartet")
    for node in imgs:
        name = node.get("name")
        if name not in audit.DISC_NAMES:
            raise CompactError("Unbekanntes CD-Abbild")
        source_iso = source / name
        if not source_iso.is_file() or source_iso.is_symlink():
            raise CompactError("Fehlendes oder verlinktes CD-Abbild: " + str(name))
        if hash_file(source_iso) != node.get("sha"):
            raise CompactError("Original-CD-SHA-256 falsch: " + name)
        entries = scan_iso(source_iso)
        if sum(not entry.is_dir for entry in entries.values()) != int(node.get("count","-1")):
            raise CompactError("ISO-Verzeichnisanzahl falsch: " + name)
        bitmap_nodes = node.findall("Bitmap")
        target_names = [item.get("path") for item in bitmap_nodes]
        if len(target_names) != 6 or any(not x for x in target_names):
            raise CompactError("Nicht genau sechs interne Zielgrafiken")
        wanted = {x.replace("\\", "/").upper() for x in target_names}
        if len(wanted) != len(target_names):
            raise CompactError("Doppelte Bitmap-Zielnamen")
        found = audit.locate_xfile(source_iso, entries, wanted)
        if set(found) != wanted:
            raise CompactError("Originalgrafiken fehlen in XFILE")
        for item in bitmap_nodes:
            resource, asset = item.get("path"), item.get("asset")
            pos, size = found[resource.replace("\\", "/").upper()]
            original = audit.read_span(source_iso, pos, size)
            target = audit.read_replacement(assets, asset)
            data = compare_versions(original, target)
            key = (data["source_sha256"], data["target_sha256"])
            if key in cases:
                prev = cases[key]
                if prev["v2_sha256"] != data["v2_sha256"] or prev["resource"] != resource:
                    raise CompactError("Inkonsistentes originales/übersetztes Ressourcenpaar")
                prev["discs"].append(name)
            else:
                cases[key] = {"resource": resource, "discs": [name], **data}
            uses += 1
    if uses != 18 or len(cases) != 7:
        raise CompactError("Nicht alle 18 Verwendungen / sieben eindeutigen Paare geprüft")
    cases_sorted = sorted(cases.values(), key=lambda x:(x["resource"], x["source_sha256"]))
    fields = ["source_bytes","changed_positions","run_count","v1_bytes",
              "v2_varint_bytes","v1_zlib9_bytes","v2_zlib9_bytes"]
    totals = {k:sum(row[k] for row in cases_sorted) for k in fields}
    return {
        "schema": "harvester-bitmap-delta-compact-v2-benchmark-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_paths_recorded": False,
        "game_or_delta_bytes_written": False,
        "original_sources_modified": False,
        "legal_clearance": False,
        "note": "All data reconstructed in RAM. Four size totals are actual measurements; zlib9 compresses only generated in-memory delta bytes. No game bytes included or written.",
        "summary": {"iso_sha256_verified":3,"xfile_bitmap_uses_checked":uses,
                    "distinct_source_target_pairs":len(cases_sorted),
                    "total":totals},
        "pairs":cases_sorted
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Private GOG bitmap delta v1/v2 benchmark (in RAM)")
    ap.add_argument("--preflight", action="store_true", help="Only check known FIX2 hashes")
    ap.add_argument("--source", type=Path, help="English original GOG game directory")
    ap.add_argument("--output-dir", type=Path,
                    default=Path.home() / "Documents" / "Harvester_Bitmap_Delta_V2_Analyse")
    args = ap.parse_args()
    try:
        rules, assets, _ = audit.load_verified_rules()
        print("FIX2-Manifests und 18/18 SHA-256: PASS")
        if args.preflight:
            return 0
        if args.source is None:
            ap.error("--source wird für einen echten Benchmark benötigt")
        if args.source.is_symlink():
            raise CompactError("Der GOG-Quellordner darf kein symbolischer Link sein")
        source = args.source.expanduser().resolve()
        if not source.is_dir():
            raise CompactError("GOG-Quellordner fehlt")
        output_dir = audit.valid_report_directory(args.output_dir, source)
        result = benchmark_local_gog(source, rules, assets)
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = output_dir / ("Harvester_Bitmap_Delta_V2_" + stamp + ".json")
        with path.open("x", encoding="utf-8") as fd:
            json.dump(result, fd, indent=2, ensure_ascii=False)
            fd.write("\n")
        t = result["summary"]["total"]
        print("3 GOG-CDs, 18 XFILE-Grafiken und 7 Quell/Ziel-Paare PASS.")
        print("V1 ungepackt: {} Bytes | V2 Varint ungepackt: {} Bytes".format(
            t["v1_bytes"],t["v2_varint_bytes"]))
        print("V1 mit zlib9: {} Bytes | V2 mit zlib9: {} Bytes".format(
            t["v1_zlib9_bytes"],t["v2_zlib9_bytes"]))
        print("Nur ein JSON-Messbericht wurde geschrieben:",path)
        return 0
    except (CompactError,v1.DeltaError,audit.AuditError,OSError,ValueError,KeyError) as exc:
        print("V2-BENCHMARK ABGEBROCHEN:",exc,file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
