#!/usr/bin/env python3
"""Private proof of concept: sparse, same-length Harvester XFILE bitmap deltas.

READ-ONLY toward the original GOG installation and existing FIX2 payload.
All candidate deltas are constructed and re-applied IN MEMORY only.
The optional JSON output contains only hashes and measurements, no game bytes.
This is not a replacement for RC3b, a distributor, or legal clearance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import sys

import originalvergleich_gog as audit
from runtime.harvester_iso import hash_file, scan_iso

MAGIC = b"HVBDP01\x00"
HEADER = struct.Struct("<8sI32s32sI")
RUN = struct.Struct("<II")
MAX_BITMAP = audit.MAX_RESOURCE_BYTES
MAX_DELTA_BYTES = MAX_BITMAP * 2 + HEADER.size
EXPECTED_CD_COUNT = 3
EXPECTED_BITMAP_USES = 18
EXPECTED_DISTINCT_PAIRS = 7


class DeltaError(ValueError):
    """Invalid source, delta structure, or reconstruction hash."""


def digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _check_source_size(data: bytes) -> None:
    if not 0 < len(data) <= MAX_BITMAP:
        raise DeltaError("Unplausible Bitmap-Dateigröße")


def create_delta(original: bytes, replacement: bytes) -> bytes:
    """Store ONLY bytes differing from the original at the same offset.

    Format: 8-byte magic, source size, source+target SHA-256, run count;
    then sorted nonoverlapping (offset, length, NEW_BYTES) runs.
    No unchanged original bytes are included in the delta.
    """
    _check_source_size(original)
    if len(replacement) != len(original):
        raise DeltaError("Sparse-Format unterstützt nur gleich große Dateien")
    runs = []
    pos = 0
    while pos < len(original):
        if original[pos] == replacement[pos]:
            pos += 1
            continue
        start = pos
        while pos < len(original) and original[pos] != replacement[pos]:
            pos += 1
        runs.append((start, replacement[start:pos]))
    if len(runs) > len(original):
        raise DeltaError("Unplausibel viele Änderungsbereiche")
    output = bytearray(HEADER.pack(
        MAGIC, len(original), digest(original), digest(replacement), len(runs)
    ))
    for start, new_bytes in runs:
        output += RUN.pack(start, len(new_bytes))
        output += new_bytes
    if len(output) > MAX_DELTA_BYTES:
        raise DeltaError("Delta überschreitet sichere Obergrenze")
    return bytes(output)


def apply_delta(original: bytes, delta: bytes) -> bytes:
    """Only reconstruct IN MEMORY after exact source verification.

    Reject malformed, overlapping, redundant, truncated, trailing, or
    tampered data. Never write an ISO or resource to disk.
    """
    _check_source_size(original)
    if not HEADER.size <= len(delta) <= MAX_DELTA_BYTES:
        raise DeltaError("Delta-Länge ungültig")
    magic, size, source_hash, target_hash, count = HEADER.unpack_from(delta)
    if magic != MAGIC or size != len(original):
        raise DeltaError("Unbekanntes Deltaformat oder falsche Bitmap-Größe")
    if digest(original) != source_hash:
        raise DeltaError("Original-SHA-256 stimmt nicht mit dem Delta überein")
    if count > (size + 1) // 2 or len(delta) < HEADER.size + count * (RUN.size + 1):
        raise DeltaError("Ungültige Anzahl der Änderungsbereiche")
    target = bytearray(original)
    at = HEADER.size
    last_end = 0
    for run_index in range(count):
        if at + RUN.size > len(delta):
            raise DeltaError("Abgeschnittener Änderungsheader")
        off, length = RUN.unpack_from(delta, at)
        at += RUN.size
        end = off + length
        if (length == 0 or off < last_end
                or (run_index and off == last_end)
                or end > size or at + length > len(delta)):
            raise DeltaError("Überlappender, leerer oder ungültiger Änderungsbereich")
        new_bytes = delta[at:at + length]
        if any(a == b for a, b in zip(original[off:end], new_bytes)):
            raise DeltaError("Delta enthält unveränderte Originalbytes")
        target[off:end] = new_bytes
        at += length
        last_end = end
    if at != len(delta):
        raise DeltaError("Unerwartete Daten nach dem letzten Änderungsbereich")
    final = bytes(target)
    if digest(final) != target_hash:
        raise DeltaError("Rekonstruktion weicht vom erwarteten Ziel-SHA-256 ab")
    return final


def delta_statistics(delta: bytes) -> tuple[int, int]:
    _, _, _, _, count = HEADER.unpack_from(delta)
    cursor, changed = HEADER.size, 0
    for _ in range(count):
        _, length = RUN.unpack_from(delta, cursor)
        cursor += RUN.size + length
        changed += length
    if cursor != len(delta):
        raise DeltaError("Inkonsistente Deltastatistik")
    return count, changed


def audit_gog_bitmaps(source: Path, rules, assets: dict[str, Path]) -> dict:
    """Measure original GOG XFILE bitmap pairs without exporting image data."""
    cases: dict[tuple[str, str], dict] = {}
    uses = 0
    images = rules.findall("./Image")
    if len(images) != EXPECTED_CD_COUNT:
        raise DeltaError("Unerwartete Anzahl Original-CDs im FIX2-Manifest")
    for img in images:
        cd = img.get("name")
        if cd not in audit.DISC_NAMES:
            raise DeltaError("Unbekannte CD im Manifest: " + str(cd))
        iso = source / cd
        if not iso.is_file() or iso.is_symlink():
            raise DeltaError("GOG-CD-Abbild fehlt oder ist ein Link: " + str(cd))
        if hash_file(iso) != img.get("sha"):
            raise DeltaError("GOG-Original-CD-SHA-256 falsch: " + str(cd))
        entries = scan_iso(iso)
        count = sum(not entry.is_dir for entry in entries.values())
        if count != int(img.get("count", "-1")):
            raise DeltaError("GOG-CD-Inventar weicht vom FIX2-Manifest ab: " + str(cd))
        nodes = img.findall("Bitmap")
        names = [node.get("path") for node in nodes]
        if len(nodes) != 6 or any(not name for name in names):
            raise DeltaError("Unerwartete Bitmap-Zuordnungen im FIX2-Manifest")
        wanted = {name.replace("\\", "/").upper() for name in names}
        if len(wanted) != len(names):
            raise DeltaError("Doppelte XFILE-Zielnamen im Manifest")
        locations = audit.locate_xfile(iso, entries, wanted)
        if set(locations) != wanted:
            raise DeltaError("Nicht alle Bitmap-Originale im XFILE gefunden")
        for node in nodes:
            name, asset = node.get("path"), node.get("asset")
            offset, size = locations[name.replace("\\", "/").upper()]
            original = audit.read_span(iso, offset, size)
            replacement = audit.read_replacement(assets, asset)
            candidate = create_delta(original, replacement)
            reconstructed = apply_delta(original, candidate)
            if reconstructed != replacement:
                raise DeltaError("Bytevergleich gegen geprüfte deutsche Zieldatei fehlgeschlagen")
            n_runs, n_changed = delta_statistics(candidate)
            source_sha = audit.sha256_bytes(original)
            target_sha = audit.sha256_bytes(replacement)
            key = (source_sha, target_sha)
            if key not in cases:
                cases[key] = {
                    "resource": name,
                    "source_sha256": source_sha,
                    "target_sha256": target_sha,
                    "source_bytes": size,
                    "target_bytes": len(replacement),
                    "changed_byte_positions": n_changed,
                    "run_count": n_runs,
                    "delta_bytes_uncompressed": len(candidate),
                    "delta_sha256": audit.sha256_bytes(candidate),
                    "delta_smaller_than_target": len(candidate) < len(replacement),
                    "discs": [cd],
                }
            else:
                prior = cases[key]
                if (prior["delta_sha256"] != audit.sha256_bytes(candidate)
                        or prior["resource"] != name):
                    raise DeltaError("Inkonsistente gleiche Quellen/Ziel-Paare")
                prior["discs"].append(cd)
            uses += 1
    if uses != EXPECTED_BITMAP_USES or len(cases) != EXPECTED_DISTINCT_PAIRS:
        raise DeltaError("Unvollständige Bitmap-Matrix; keine Schätzung ausgeben")
    rows = sorted(cases.values(), key=lambda x: (x["resource"], x["source_sha256"]))
    original_sum = sum(x["source_bytes"] for x in rows)
    patch_sum = sum(x["delta_bytes_uncompressed"] for x in rows)
    report = {
        "schema": "harvester-bitmap-delta-poc-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "private_internal_prototype": True,
        "gog_sources_modified": False,
        "deltas_or_game_bytes_written": False,
        "contains_original_or_patched_game_bytes": False,
        "local_paths_recorded": False,
        "legal_distribution_clearance": False,
        "method_note": (
            "Byte-position-based uncompressed sparse deltas, in RAM only. "
            "Sizes are technical measurements, not a legal determination "
            "and not a tested public-release download size."
        ),
        "summary": {
            "original_cd_sha256_verified": len(images),
            "xfile_bitmap_uses_checked": uses,
            "distinct_source_target_pairs": len(rows),
            "source_bytes_all_distinct_pairs": original_sum,
            "delta_bytes_all_distinct_pairs": patch_sum,
            "changed_byte_positions_all_distinct_pairs":
                sum(x["changed_byte_positions"] for x in rows),
            "delta_percent_smaller_than_full_targets":
                round(100 * (1 - patch_sum / original_sum), 3),
        },
        "pairs": rows,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only prototype: sparse deltas for internal GOG XFILE .BM graphics"
    )
    parser.add_argument("--preflight", action="store_true",
                        help="Nur geprüfte FIX2-Manifest-/Payload-SHA-256 prüfen")
    parser.add_argument("--source", type=Path,
                        help="Ordner der originalen englischen GOG-Installation")
    parser.add_argument("--output-dir", type=Path,
                        default=Path.home() / "Documents" / "Harvester_Bitmap_Delta_Analyse",
                        help="Separater Berichtspfad (nicht im GOG-Ordner oder Repository)")
    args = parser.parse_args()
    try:
        rules, assets, _ = audit.load_verified_rules()
        print("FIX2-Vorprüfung: alle 18 Ressourcen + Manifest PASS")
        if args.preflight:
            return 0
        if args.source is None:
            parser.error("--source ist für die lokale Auswertung erforderlich")
        if args.source.is_symlink():
            raise DeltaError("GOG-Quellordner darf kein symbolischer Link sein")
        source = args.source.expanduser().resolve()
        if not source.is_dir():
            raise DeltaError("Englischer Original-GOG-Ordner fehlt")
        output = audit.valid_report_directory(args.output_dir, source)
        report = audit_gog_bitmaps(source, rules, assets)
        output.mkdir(parents=True, exist_ok=True)
        dest = output / ("Harvester_Bitmap_Delta_POC_"
                         + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        with dest.open("x", encoding="utf-8") as fd:
            json.dump(report, fd, indent=2, ensure_ascii=False)
            fd.write("\n")
        sums = report["summary"]
        print("Ergebnis:", dest)
        print(
            "3/3 CD-Hashes, {}/18 Grafikzuordnungen, {} eindeutige"
            " Quell/Ziel-Paare bytegenau in RAM rekonstruiert.".format(
                sums["xfile_bitmap_uses_checked"], sums["distinct_source_target_pairs"]
            )
        )
        print("Delta-Daten (ungepackt, inklusive Header/Offsets): {} Bytes"
              " vs. {} Bytes Vollressourcen.".format(
                  sums["delta_bytes_all_distinct_pairs"],
                  sums["source_bytes_all_distinct_pairs"]
              ))
        print("Es wurden keine Bild-/Spieldaten und keine Deltas gespeichert.")
        return 0
    except (DeltaError, audit.AuditError, OSError, ValueError, KeyError) as exc:
        print("PROTOTYP ABGEBROCHEN:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
