#!/usr/bin/env python3
"""Harvester FIX2: private, read-only variable-length resource delta experiment.

COPY from an exact SHA-256-verified original or ADD literal new bytes, in RAM.
No original ISO, installed game, save, patch resource, or delta data is written.
Only a statistics-only JSON report can be written outside game/repository.
This does NOT grant publication/distribution rights and does NOT modify RC3b.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import struct
import sys
import zlib

import bitmap_delta_compact as compact
import bitmap_delta_poc as bitmaps
import originalvergleich_gog as audit
from runtime.harvester_iso import hash_file, scan_iso

MAGIC = b"HVVDL01\x00"
HEADER = struct.Struct("<8sII32s32sI")
COPY, ADD = 0, 1
ANCHOR = 16
MIN_COPY = 16
MIN_INDEX_STRIDE = 8
MAX_INDEX_ANCHORS = 200_000
MAX_CANDIDATES = 8
MAX_RESOURCE = audit.MAX_RESOURCE_BYTES
MAX_OPERATIONS = 1_000_000
MAX_DELTA = 3 * MAX_RESOURCE + HEADER.size
EXPECTED_FIX2_NON_BITMAP_TARGETS = 11
EXPECTED_NON_BITMAP_ISO_USES = 24
SAFE_LOOSE_NAMES = ("MENU.INI", "DIALOG.RSP")


class VariableDeltaError(ValueError):
    pass


def _check_data_size(original: bytes, target: bytes | None = None) -> None:
    if not 0 < len(original) <= MAX_RESOURCE:
        raise VariableDeltaError("Quellressource außerhalb sicherer Grenzen")
    if target is not None and not 0 < len(target) <= MAX_RESOURCE:
        raise VariableDeltaError("Zielressource außerhalb sicherer Grenzen")


def _index_source(original: bytes) -> tuple[dict[bytes, list[int]], int]:
    """Bound memory and candidates; deterministic even for repeated binary data."""
    stride = max(MIN_INDEX_STRIDE, (max(0, len(original) - ANCHOR) // MAX_INDEX_ANCHORS) + 1)
    anchors: dict[bytes, list[int]] = {}
    for start in range(0, len(original) - ANCHOR + 1, stride):
        key = original[start:start + ANCHOR]
        offsets = anchors.setdefault(key, [])
        if len(offsets) < MAX_CANDIDATES:
            offsets.append(start)
        else:
            # Keep the first 4 and the 4 most recent occurrences.
            offsets[4:] = offsets[5:] + [start]
    return anchors, stride


def _longest_equal(original: bytes, off: int, target: bytes, pos: int) -> int:
    """Exponential + binary search, using native byte-slice comparisons."""
    maximum = min(len(original) - off, len(target) - pos)
    lower = min(ANCHOR, maximum)
    if maximum <= lower:
        return lower
    upper = min(maximum, lower * 2)
    while original[off:off + upper] == target[pos:pos + upper]:
        lower = upper
        if upper == maximum:
            return lower
        upper = min(maximum, upper * 2)
    while lower < upper:
        middle = (lower + upper + 1) // 2
        if original[off:off + middle] == target[pos:pos + middle]:
            lower = middle
        else:
            upper = middle - 1
    return lower


def make_delta(original: bytes, target: bytes) -> tuple[bytes, dict]:
    """Copy matching ORIGINAL spans; store only unmatched/new bytes as ADD.

    Supports shifted blocks, insertions and deletions. It is intentionally a
    bounded heuristic, not a claim of globally optimal minimum binary diff.
    """
    _check_data_size(original, target)
    index, stride = _index_source(original)
    ops: list[tuple[int, int, bytes | int]] = []
    literal = bytearray()
    at = 0
    copied = 0
    added = 0

    def flush_literal() -> None:
        nonlocal added
        if literal:
            data = bytes(literal)
            ops.append((ADD, len(data), data))
            added += len(data)
            literal.clear()

    while at < len(target):
        length = 0
        from_at = 0
        if at + ANCHOR <= len(target) and len(original) >= ANCHOR:
            snippet = target[at:at + ANCHOR]
            for origin_pos in index.get(snippet, ()):
                matched = _longest_equal(original, origin_pos, target, at)
                if matched > length:
                    length = matched
                    from_at = origin_pos
                    if matched == min(len(original) - origin_pos, len(target) - at):
                        break
        if length >= MIN_COPY:
            flush_literal()
            # A previous contiguous COPY can extend across index boundaries.
            if (ops and ops[-1][0] == COPY
                    and ops[-1][1] + ops[-1][2] == from_at):
                _, prev_offset, prev_len = ops[-1]
                ops[-1] = (COPY, prev_offset, prev_len + length)
            else:
                ops.append((COPY, from_at, length))
            copied += length
            at += length
        else:
            literal.append(target[at])
            at += 1
        if len(ops) > MAX_OPERATIONS:
            raise VariableDeltaError("Zu viele Änderungsoperationen")
    flush_literal()
    if copied + added != len(target) or not ops or len(ops) > MAX_OPERATIONS:
        raise VariableDeltaError("Unvollständiger Delta-Encoder")
    result = bytearray(HEADER.pack(
        MAGIC, len(original), len(target), bitmaps.digest(original),
        bitmaps.digest(target), len(ops)
    ))
    for tag, a, b in ops:
        result.append(tag)
        if tag == COPY:
            result.extend(compact.encode_u32(a))
            result.extend(compact.encode_u32(b))
        else:
            result.extend(compact.encode_u32(a))
            result.extend(b)
    if len(result) > MAX_DELTA:
        raise VariableDeltaError("Delta überschreitet sichere Maximalgröße")
    return bytes(result), {
        "index_stride": stride,
        "copy_operations": sum(x[0] == COPY for x in ops),
        "literal_operations": sum(x[0] == ADD for x in ops),
        "copied_target_bytes": copied,
        "new_literal_bytes": added,
    }


def apply_delta(original: bytes, delta: bytes) -> bytes:
    """Reject wrong base, malformed/noncanonical instructions and wrong target."""
    _check_data_size(original)
    if not HEADER.size <= len(delta) <= MAX_DELTA:
        raise VariableDeltaError("Ungültige Delta-Länge")
    magic, source_size, target_size, source_sha, target_sha, count = HEADER.unpack_from(delta)
    if magic != MAGIC or source_size != len(original):
        raise VariableDeltaError("Ungültige Formatkennung oder Quellgröße")
    if not 0 < target_size <= MAX_RESOURCE:
        raise VariableDeltaError("Ungültige Zielgröße")
    if bitmaps.digest(original) != source_sha:
        raise VariableDeltaError("Falscher Original-SHA-256")
    if count == 0 or count > min(MAX_OPERATIONS, target_size):
        raise VariableDeltaError("Unplausible Operationsanzahl")
    if len(delta) < HEADER.size + 3 * count:
        raise VariableDeltaError("Abgeschnittenes Delta")
    offset = HEADER.size
    out = bytearray()
    last_tag = None
    for _ in range(count):
        if offset >= len(delta):
            raise VariableDeltaError("Abgeschnittener Operationstyp")
        tag = delta[offset]
        offset += 1
        if tag == COPY:
            src_pos, offset = compact.read_u32(delta, offset)
            run, offset = compact.read_u32(delta, offset)
            if run == 0 or src_pos + run > len(original):
                raise VariableDeltaError("Ungültiger COPY-Bereich")
            if len(out) + run > target_size:
                raise VariableDeltaError("COPY überschreitet Zielgröße")
            out.extend(original[src_pos:src_pos + run])
        elif tag == ADD:
            run, offset = compact.read_u32(delta, offset)
            if run == 0 or offset + run > len(delta) or len(out) + run > target_size:
                raise VariableDeltaError("Ungültiger ADD-Bereich")
            if last_tag == ADD:
                raise VariableDeltaError("Nicht kanonische benachbarte ADD-Bereiche")
            out.extend(delta[offset:offset + run])
            offset += run
        else:
            raise VariableDeltaError("Unbekannter Delta-Operationstyp")
        last_tag = tag
    if offset != len(delta):
        raise VariableDeltaError("Nachlaufende Bytes im Delta")
    if len(out) != target_size or bitmaps.digest(out) != target_sha:
        raise VariableDeltaError("Rekonstruktionsgröße oder Ziel-SHA-256 falsch")
    return bytes(out)


def compare_one(original: bytes, target: bytes) -> dict:
    encoded, stats = make_delta(original, target)
    if apply_delta(original, encoded) != target:
        raise VariableDeltaError("Ergebnis ist nicht byteidentisch zum FIX2-Ziel")
    packed = zlib.compress(encoded, 9)
    # ZIP/zlib benchmark only: decompress back to delta, then verify again.
    if apply_delta(original, zlib.decompress(packed)) != target:
        raise VariableDeltaError("Komprimiertes Delta rekonstruiert Ziel nicht korrekt")
    return {
        "source_sha256": audit.sha256_bytes(original),
        "target_sha256": audit.sha256_bytes(target),
        "original_bytes": len(original),
        "target_bytes": len(target),
        "variable_delta_bytes": len(encoded),
        "variable_delta_zlib9_bytes": len(packed),
        "target_zlib9_bytes_benchmark_only": len(zlib.compress(target, 9)),
        "delta_sha256": audit.sha256_bytes(encoded),
        **stats,
    }


def compare_original_gog(source: Path, rules, assets: dict[str, Path]) -> dict:
    """Read verified ISO resource extents only; root loose files optional.

    Never access cloud_saves, saved games, or any resource unrelated to FIX2.
    """
    images = rules.findall("./Image")
    if len(images) != 3:
        raise VariableDeltaError("Genau drei CD-Originalabbilder erwartet")
    bitmap_assets = {
        n.get("asset") for image in images for n in image.findall("Bitmap")
    }
    rest = set(assets).difference(bitmap_assets)
    if len(bitmap_assets) != 7 or len(rest) != EXPECTED_FIX2_NON_BITMAP_TARGETS:
        raise VariableDeltaError("Unerwartete FIX2-Ressourcenanzahl")
    seen_targets = set()
    pairs: dict[tuple[str, str], dict] = {}
    iso_uses = 0
    loose_rows = []

    def insert_pair(original: bytes, target: bytes, resource: str,
                    asset: str, origin: str) -> None:
        # Every usage is checked by SHA-256. Do not re-run a costly diff for
        # a previously verified identical source/target pair on another CD.
        original_sha = audit.sha256_bytes(original)
        target_sha = audit.sha256_bytes(target)
        key = (original_sha, target_sha)
        if key not in pairs:
            evidence = compare_one(original, target)
            if (evidence["source_sha256"], evidence["target_sha256"]) != key:
                raise VariableDeltaError("SHA-256-Abgleich im Vergleich widersprüchlich")
            pairs[key] = {
                "resource": resource,
                "asset_sha256": asset.removesuffix(".bin"),
                "locations": [origin],
                **evidence,
            }
        else:
            row = pairs[key]
            if (row["asset_sha256"] != asset.removesuffix(".bin")
                    or row["original_bytes"] != len(original)
                    or row["target_bytes"] != len(target)):
                raise VariableDeltaError("Inkonsistente doppelte Original/Ziel-Kombination")
            row["locations"].append(origin)
        seen_targets.add(asset)

    for image in images:
        disc = image.get("name")
        if disc not in audit.DISC_NAMES:
            raise VariableDeltaError("Unbekannte Original-CD: " + str(disc))
        iso = source / disc
        if not iso.is_file() or iso.is_symlink():
            raise VariableDeltaError("Originales ISO/CD-Abbild fehlt oder ist ein Symlink")
        if hash_file(iso) != image.get("sha"):
            raise VariableDeltaError("GOG-Original-CD-SHA-256 falsch: " + disc)
        listing = scan_iso(iso)
        if sum(not e.is_dir for e in listing.values()) != int(image.get("count", "-1")):
            raise VariableDeltaError("GOG-ISO-Inventar weicht vom Manifest ab: " + disc)
        for item in image.findall("Replace"):
            path, asset = item.get("path"), item.get("asset")
            if not path or not asset:
                raise VariableDeltaError("Unvollständige Replace-Anweisung")
            if path.upper().endswith(".BM"):
                if asset not in bitmap_assets:
                    raise VariableDeltaError("Unbekannte Bitmap-Ressource im Replace")
                continue
            if asset not in rest:
                raise VariableDeltaError("Unerwartetes Nicht-Bitmap-Ziel")
            entry = listing.get(path)
            if entry is None or entry.is_dir:
                raise VariableDeltaError("Originalressource fehlt: " + disc + "/" + path)
            original = audit.read_span(iso, entry.offset, entry.size)
            target = audit.read_replacement(assets, asset)
            insert_pair(original, target, path, asset, disc + ":" + path)
            iso_uses += 1

    if iso_uses != EXPECTED_NON_BITMAP_ISO_USES or seen_targets != rest:
        raise VariableDeltaError("Nicht alle 24 ISO-Verwendungen/11 FIX2-Ziele erfasst")

    # Optional GOG root files: NO cloud_saves (save compatibility is protected).
    for item in rules.findall("./Loose"):
        path, asset = item.get("path"), item.get("asset")
        if path not in SAFE_LOOSE_NAMES:
            continue
        if asset not in rest:
            raise VariableDeltaError("Unerwartetes loses FIX2-Ziel")
        candidate = source / path
        if not candidate.is_file():
            loose_rows.append({"resource": path, "status": "OPTIONAL_NOT_PRESENT"})
            continue
        if candidate.is_symlink():
            raise VariableDeltaError("Verlinkte lose Originalressource nicht erlaubt")
        size = candidate.stat().st_size
        if not 0 < size <= MAX_RESOURCE:
            raise VariableDeltaError("Lose Originalressource außerhalb sicherer Grenzen")
        original = candidate.read_bytes()
        target = audit.read_replacement(assets, asset)
        insert_pair(original, target, path, asset, "GOG_ROOT:" + path)
        loose_rows.append({
            "resource": path, "status": "COMPARED",
            "source_sha256": audit.sha256_bytes(original),
            "note": "Loose-file SHA is recorded, not authenticated by a CD image SHA.",
        })

    rows = sorted(pairs.values(), key=lambda p:(p["resource"], p["source_sha256"]))
    columns = ("original_bytes", "target_bytes", "variable_delta_bytes",
               "variable_delta_zlib9_bytes", "target_zlib9_bytes_benchmark_only",
               "new_literal_bytes", "copied_target_bytes")
    sums = {field: sum(row[field] for row in rows) for field in columns}
    return {
        "schema": "harvester-variable-resource-delta-poc-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Heuristic indexed source COPY+ADD; supports inserted/deleted bytes.",
        "source_paths_recorded": False,
        "contains_original_or_translated_game_bytes": False,
        "game_or_delta_bytes_written": False,
        "original_sources_modified": False,
        "legal_clearance": False,
        "notes": [
            "Exact hashes/byte reconstruction checked in RAM for each resource.",
            "Delta bytes are never stored. zlib9 values are in-memory measurements.",
            "This is not a legal right to redistribute translated or modified assets.",
            "Compressed full target sizes are comparison-only, not distribution assets.",
            "Optional loose root files are not covered by original CD image hashes.",
        ],
        "summary": {
            "verified_gog_iso_sha256": len(images),
            "non_bitmap_iso_replacements_checked": iso_uses,
            "distinct_fix2_non_bitmap_assets": len(seen_targets),
            "distinct_source_target_pairs_including_optional_loose": len(rows),
            "optional_loose_file_comparisons": sum(x["status"] == "COMPARED" for x in loose_rows),
            "total": sums,
        },
        "pairs": rows,
        "loose_files": loose_rows,
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Private read-only GOG FIX2 variable-length delta experiment"
    )
    p.add_argument("--preflight", action="store_true",
                   help="Only check unchanged FIX2 hashes, no GOG required")
    p.add_argument("--source", type=Path,
                   help="English original GOG game root containing the three CD images")
    p.add_argument("--output-dir", type=Path,
                   default=Path.home() / "Documents" / "Harvester_Variable_Delta_Analyse")
    args = p.parse_args()
    try:
        rules, assets, _ = audit.load_verified_rules()
        print("Unverändertes FIX2-Manifest und 18 Ressourcen: SHA-256 PASS")
        if args.preflight:
            return 0
        if args.source is None:
            p.error("--source ist für den Originalvergleich erforderlich")
        if args.source.is_symlink():
            raise VariableDeltaError("GOG-Quellordner ist ein Symlink")
        root = args.source.expanduser().resolve()
        if not root.is_dir():
            raise VariableDeltaError("Englischer Original-GOG-Ordner fehlt")
        destination = audit.valid_report_directory(args.output_dir, root)
        report = compare_original_gog(root, rules, assets)
        destination.mkdir(parents=True, exist_ok=True)
        filename = ("Harvester_Variable_Delta_"
                    + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        output = destination / filename
        with output.open("x", encoding="utf-8") as fd:
            json.dump(report, fd, ensure_ascii=False, indent=2)
            fd.write("\n")
        summary = report["summary"]
        total = summary["total"]
        print("3 CD-Hashes, {}/24 ISO-Verwendungen und {}/11 FIX2-Ziele PASS.".format(
            summary["non_bitmap_iso_replacements_checked"],
            summary["distinct_fix2_non_bitmap_assets"]
        ))
        print("Original/Ziel-Paare insgesamt:", summary[
            "distinct_source_target_pairs_including_optional_loose"])
        print("Ziele {} B, COPY+ADD {} B, mit zlib9 {} B.".format(
            total["target_bytes"], total["variable_delta_bytes"],
            total["variable_delta_zlib9_bytes"]
        ))
        print("Nur technischer JSON-Bericht gespeichert:", output)
        print("Keine Original-Dateien, Spielstände oder Deltas geschrieben.")
        return 0
    except (VariableDeltaError, compact.CompactError, audit.AuditError,
            OSError, ValueError, KeyError) as exc:
        print("VARIABLE-DELTA-PROTOTYP ABGEBROCHEN:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
