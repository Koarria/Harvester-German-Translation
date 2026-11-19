#!/usr/bin/env python3
"""Harvester GOG FIX2: read-only source/payload comparison for a *local* GOG copy.

No third-party dependencies, no game patching, no extracted proprietary data,
and no original text/pixel contents in the JSON report. Not a legal clearance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from runtime.harvester_iso import hash_file, scan_iso  # noqa: E402

EXPECTED_RULES_SHA256 = "7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b"
MAX_RESOURCE_BYTES = 16 * 1024 * 1024
MAX_EXE_BYTES = 16 * 1024 * 1024
XFILE_RECORD_SIZE = 148
RUN_MIN = 32
DISC_NAMES = ("HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT")


class AuditError(Exception):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_verified_rules(root: Path = REPO, expected_sha: str | None = EXPECTED_RULES_SHA256):
    """Reject edited/unrecognised rules and any altered payload file before auditing."""
    rules_path = root / "payload" / "Regeln.xml"
    if not rules_path.is_file():
        raise AuditError("Regeln.xml fehlt")
    digest = hash_file(rules_path)
    if expected_sha is not None and digest != expected_sha:
        raise AuditError("Regeln.xml stimmt nicht mit dem geprüften RC3b-Stand überein")
    rules = ET.parse(rules_path).getroot()
    if rules.tag != "HarvesterPatch":
        raise AuditError("Unbekanntes Regeln.xml-Format")
    assets: dict[str, Path] = {}
    for node in rules.findall("./Assets/Asset"):
        name, expected, size = node.get("name"), node.get("sha"), node.get("size")
        if not name or not re.fullmatch(r"[0-9a-f]{64}\.bin", name):
            raise AuditError("Ungültiger FIX2-Datenname")
        if not expected or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise AuditError("Ungültiger FIX2-Datenhash")
        if name in assets:
            raise AuditError("Doppelte FIX2-Datendatei")
        target = root / "payload" / "Daten" / name
        if not target.is_file() or target.is_symlink():
            raise AuditError("FIX2-Datei fehlt oder ist ein Link: " + name)
        if target.stat().st_size != int(size):
            raise AuditError("FIX2-Dateigröße falsch: " + name)
        if hash_file(target) != expected:
            raise AuditError("FIX2-SHA-256 falsch: " + name)
        assets[name] = target
    if len(assets) != 18:
        raise AuditError("Erwartet 18 eindeutig geprüfte FIX2-Datendateien")
    return rules, assets, digest


def read_span(path: Path, offset: int, size: int) -> bytes:
    if offset < 0 or size < 0 or size > MAX_RESOURCE_BYTES:
        raise AuditError("Unplausible Ressourcengrenze")
    with path.open("rb") as fd:
        fd.seek(offset)
        result = fd.read(size)
    if len(result) != size:
        raise AuditError("Ressource ist abgeschnitten")
    return result


def compare_bytes(original: bytes, modified: bytes) -> dict:
    """Byte evidence at identical offsets; NOT an estimate of copyright ownership.

    Insertions can shift unchanged ranges: aligned counts deliberately do not
    attempt to infer the globally optimal or legally relevant byte ancestry.
    """
    bound = min(len(original), len(modified))
    prefix = 0
    while prefix < bound and original[prefix] == modified[prefix]:
        prefix += 1
    suffix = 0
    while suffix < bound - prefix and original[-1 - suffix] == modified[-1 - suffix]:
        suffix += 1

    same_offsets = 0
    long_runs_bytes = 0
    long_runs_count = 0
    longest_run = 0
    run = 0
    for i in range(bound):
        if original[i] == modified[i]:
            same_offsets += 1
            run += 1
        else:
            if run >= RUN_MIN:
                long_runs_count += 1
                long_runs_bytes += run
            longest_run = max(longest_run, run)
            run = 0
    if run >= RUN_MIN:
        long_runs_count += 1
        long_runs_bytes += run
    longest_run = max(longest_run, run)
    return {
        "original_bytes": len(original),
        "replacement_bytes": len(modified),
        "same_size": len(original) == len(modified),
        "byte_identical": original == modified,
        "same_offset_equal_bytes": same_offsets,
        "same_offset_equal_percent_of_overlap": round(100 * same_offsets / bound, 3) if bound else None,
        "longest_same_offset_run_bytes": longest_run,
        "same_offset_runs_ge_32_count": long_runs_count,
        "same_offset_bytes_in_runs_ge_32": long_runs_bytes,
        "exact_common_prefix_bytes": prefix,
        "exact_common_suffix_bytes_no_overlap": suffix,
    }


def text_structure(original: bytes, modified: bytes) -> dict:
    """Compare structure without publishing any lines of text."""
    left = original.decode("cp1252").splitlines()
    right = modified.decode("cp1252").splitlines()
    overlap = min(len(left), len(right))
    return {
        "original_lines": len(left),
        "replacement_lines": len(right),
        "equal_lines_same_index": sum(left[i] == right[i] for i in range(overlap)),
        "slash_count_per_line_preserved": (
            len(left) == len(right)
            and all(left[i].count("/") == right[i].count("/") for i in range(overlap))
        ),
        "percent_s_d_placeholders_per_line_preserved": (
            len(left) == len(right)
            and all(
                re.findall(r"%(?:\d+\$)?[sd]", left[i])
                == re.findall(r"%(?:\d+\$)?[sd]", right[i])
                for i in range(overlap)
            )
        ),
    }


def read_replacement(assets: dict[str, Path], name: str) -> bytes:
    if name not in assets:
        raise AuditError("Unbekanntes Ersatzasset: " + str(name))
    path = assets[name]
    if path.stat().st_size > MAX_RESOURCE_BYTES:
        raise AuditError("FIX2-Ressource für Vergleich zu groß")
    return path.read_bytes()


def comparison_row(
    disc_name: str,
    role: str,
    resource_name: str,
    original: bytes,
    replacement: bytes,
    source: str,
) -> dict:
    row = {
        "disc": disc_name,
        "role": role,
        "resource": resource_name,
        "origin": source,
        "original_sha256": sha256_bytes(original),
        "replacement_sha256": sha256_bytes(replacement),
        "comparison": compare_bytes(original, replacement),
    }
    if resource_name.upper().endswith((".RSP", ".RCS", ".INI")):
        row["text_structure"] = text_structure(original, replacement)
    return row


def parse_xfile_index(
    data: bytes, native_length: int, wanted_names: set[str] | None = None
) -> dict[str, tuple[int, int, int, bytes]]:
    """Validate all XFILE offsets; require name uniqueness only for patch targets.

    FIX2 CheckNative permits empty/duplicate names for unrelated game resources.
    Selected replacement graphics remain uniquely named and size/flag verified.
    """
    if len(data) % XFILE_RECORD_SIZE:
        raise AuditError("INDEX.001 hat keine 148-Byte-Einträge")
    wanted = None if wanted_names is None else {
        name.replace("\\", "/").upper() for name in wanted_names
    }
    found = {}
    cursor = 0
    for at in range(0, len(data), XFILE_RECORD_SIZE):
        rec = data[at:at + XFILE_RECORD_SIZE]
        if rec[:4] != b"XFLE":
            raise AuditError("Unbekannter XFILE-Indexmarker")
        offset, size = struct.unpack_from("<II", rec, 132)
        if offset != cursor + XFILE_RECORD_SIZE or offset + size > native_length:
            raise AuditError("Unsichere XFILE-Indexgrenze")
        name = rec[4:132].split(b"\0", 1)[0].decode(
            "cp1252", errors="replace"
        ).replace("\\", "/").upper()
        if wanted is None:
            if not name or name in found:
                raise AuditError("Leerer/doppelter XFILE-Ressourcenname")
            found[name] = (cursor, offset, size, rec)
        elif name in wanted:
            if name in found:
                raise AuditError("Doppelter XFILE-ZIEL-Ressourcenname: " + name)
            flags, declared_size = struct.unpack_from("<II", rec, 140)
            if flags != 0 or declared_size != size:
                raise AuditError("Ungültige XFILE-ZIEL-Metadaten: " + name)
            found[name] = (cursor, offset, size, rec)
        # Other entries need not have names or unique identifiers.
        cursor = offset + size
    if cursor != native_length:
        raise AuditError("XFILE-Index deckt Native-Container nicht ab")
    return found


def locate_xfile(
    iso: Path, entries, wanted_names: set[str]
) -> dict[str, tuple[int, int]]:
    idx = entries.get("INDEX.001")
    inner = entries.get("HARVEST.DAT")
    if idx is None or inner is None or idx.is_dir or inner.is_dir:
        raise AuditError("INDEX.001 oder inneres HARVEST.DAT fehlt im Originalabbild")
    index = read_span(iso, idx.offset, idx.size)
    locations = parse_xfile_index(index, inner.size, wanted_names=wanted_names)
    # Compare every index record against the native resource header, as FIX2 does.
    with iso.open("rb") as fd:
        cursor = 0
        for at in range(0, len(index), XFILE_RECORD_SIZE):
            rec = index[at:at + XFILE_RECORD_SIZE]
            fd.seek(inner.offset + cursor)
            if fd.read(XFILE_RECORD_SIZE) != rec:
                raise AuditError("XFILE-Index und Native-Ressourcenkopf widersprechen sich")
            off, size = struct.unpack_from("<II", rec, 132)
            cursor = off + size
    return {
        name: (inner.offset + off, size)
        for name, (_, off, size, _) in locations.items()
    }

def audit_image(source: Path, image_node, assets: dict[str, Path]) -> dict:
    name = image_node.get("name")
    result = {
        "name": name,
        "status": "NOT_CHECKED",
        "expected_source_sha256": image_node.get("sha"),
        "source_sha256": None,
        "source_sha256_matches": False,
        "replacements": [],
        "native_bitmaps": [],
        "issues": [],
    }
    if name not in DISC_NAMES:
        result["issues"].append("Unbekannter CD-Abbildname im Manifest")
        return result
    iso = source / name
    if not iso.is_file() or iso.is_symlink():
        result["status"] = "SOURCE_MISSING"
        result["issues"].append("Originales CD-Abbild fehlt")
        return result
    try:
        digest = hash_file(iso)
        result["source_sha256"] = digest
        if digest != result["expected_source_sha256"]:
            result["status"] = "SOURCE_HASH_MISMATCH"
            result["issues"].append("Nicht unterstütztes oder geändertes GOG-CD-Abbild; Vergleich ausgelassen")
            return result
        result["source_sha256_matches"] = True
        entries = scan_iso(iso)
        count = sum(not entry.is_dir for entry in entries.values())
        result["original_iso_files"] = count
        if count != int(image_node.get("count", "-1")):
            result["status"] = "ISO_FILE_COUNT_MISMATCH"
            result["issues"].append("ISO-Inventar entspricht nicht dem FIX2-Regelmanifest")
            return result
        result["status"] = "VERIFIED"
        for node in image_node.findall("Replace"):
            path, asset = node.get("path"), node.get("asset")
            entry = entries.get(path)
            if entry is None or entry.is_dir:
                result["issues"].append("Fehlende Originalressource: " + str(path))
                continue
            try:
                origin = read_span(iso, entry.offset, entry.size)
                patch = read_replacement(assets, asset)
                result["replacements"].append(comparison_row(
                    name, "ISO_REPLACE", path, origin, patch, "outer ISO extent"
                ))
            except (AuditError, OSError, ValueError) as exc:
                result["issues"].append("Replace " + str(path) + ": " + str(exc))
        bitmap_nodes = image_node.findall("Bitmap")
        try:
            targets = [node.get("path") for node in bitmap_nodes]
            if any(not path for path in targets):
                raise AuditError("Leerer XFILE-Zielpfad im Regelmanifest")
            normalized = {path.replace("\\", "/").upper() for path in targets}
            if len(normalized) != len(targets):
                raise AuditError("Doppelter XFILE-Zielpfad im Regelmanifest")
            native = locate_xfile(iso, entries, normalized)
            for node in bitmap_nodes:
                path, asset = node.get("path"), node.get("asset")
                located = native.get(path.upper()) if path else None
                if located is None:
                    result["issues"].append("XFILE-Bitmap fehlt: " + str(path))
                    continue
                try:
                    pos, size = located
                    origin = read_span(iso, pos, size)
                    patch = read_replacement(assets, asset)
                    result["native_bitmaps"].append(comparison_row(
                        name, "XFILE_BITMAP", path, origin, patch, "inner XFILE"
                    ))
                except (AuditError, OSError, ValueError) as exc:
                    result["issues"].append("XFILE " + str(path) + ": " + str(exc))
        except (AuditError, OSError, ValueError) as exc:
            result["issues"].append("XFILE-Untersuchung nicht möglich: " + str(exc))
        if result["issues"]:
            result["status"] = "PARTIAL"
    except (OSError, ValueError, AuditError, KeyError, ET.ParseError) as exc:
        result["status"] = "INSPECTION_FAILED"
        result["issues"].append(str(exc))
    return result


def apply_exe_edits_for_verification(original: bytes, executable_node) -> dict:
    """Simulate edits only in memory; reject all inconsistent patch offsets/bytes."""
    modified = bytearray(original)
    edits = executable_node.findall("Edit")
    cursor = 0
    total_bytes = 0
    for e in edits:
        offset = int(e.get("offset"))
        old = bytes.fromhex(e.get("old"))
        new = bytes.fromhex(e.get("new"))
        if (offset < cursor or len(old) != len(new)
                or offset < 0 or offset + len(old) > len(original)):
            raise AuditError("Ungültiger/überlappender HARVEST.EXE-Edit")
        if original[offset:offset + len(old)] != old:
            raise AuditError("HARVEST.EXE-Originalbytes an Offset " + str(offset) + " abweichend")
        modified[offset:offset + len(old)] = new
        cursor = offset + len(old)
        total_bytes += len(old)
    target_hash = sha256_bytes(modified)
    return {
        "edits_checked": len(edits),
        "edited_bytes": total_bytes,
        "derived_target_sha256": target_hash,
        "expected_target_sha256": executable_node.get("target"),
        "target_hash_matches": target_hash == executable_node.get("target"),
    }


def audit_executable(source: Path, executable_node) -> dict:
    path = source / "HARVEST.EXE"
    result = {
        "file": "HARVEST.EXE",
        "status": "NOT_CHECKED",
        "expected_source_sha256": executable_node.get("source"),
        "source_sha256": None,
    }
    if not path.is_file() or path.is_symlink():
        result["status"] = "SOURCE_MISSING"
        return result
    try:
        size = path.stat().st_size
        if size > MAX_EXE_BYTES:
            raise AuditError("EXE für sicheren In-Memory-Vergleich zu groß")
        original = path.read_bytes()
        digest = sha256_bytes(original)
        result["source_sha256"] = digest
        if digest != executable_node.get("source"):
            result["status"] = "SOURCE_HASH_MISMATCH"
            return result
        result["verification"] = apply_exe_edits_for_verification(original, executable_node)
        result["status"] = (
            "VERIFIED"
            if result["verification"]["target_hash_matches"]
            else "TARGET_HASH_MISMATCH"
        )
    except (OSError, ValueError, AuditError) as exc:
        result["status"] = "INSPECTION_FAILED"
        result["issue"] = str(exc)
    return result


def audit_loose(source: Path, rules, assets: dict[str, Path]) -> list[dict]:
    """Read only loose *root* files; never inspect cloud_saves/user save files."""
    rows = []
    seen: set[str] = set()
    for node in rules.findall("./Loose"):
        resource, asset = node.get("path"), node.get("asset")
        if resource not in {"MENU.INI", "DIALOG.RSP"} or resource in seen:
            continue
        seen.add(resource)
        path = source / resource
        if not path.is_file():
            rows.append({"resource": resource, "status": "OPTIONAL_NOT_FOUND"})
            continue
        try:
            rows.append({
                "status": "COMPARED",
                **comparison_row("GOG_ROOT", "LOOSE", resource,
                                 read_span(path, 0, path.stat().st_size),
                                 read_replacement(assets, asset), "game root"),
            })
        except (OSError, ValueError, AuditError) as exc:
            rows.append({"resource": resource, "status": "INSPECTION_FAILED", "issue": str(exc)})
    return rows


def valid_report_directory(folder: Path, source: Path) -> Path:
    folder = folder.expanduser().resolve()
    source = source.resolve()
    repository = REPO.resolve()
    if folder == source or source in folder.parents:
        raise AuditError("Der Bericht darf nicht im originalen GOG-Spielordner liegen")
    if folder == repository or repository in folder.parents:
        raise AuditError("Der Bericht darf nicht in das GitHub-Repository geschrieben werden")
    return folder


def build_report(source: Path, rules, assets: dict[str, Path], manifest_digest: str) -> dict:
    discs = [audit_image(source, node, assets) for node in rules.findall("./Image")]
    executable_node = rules.find("./Executable")
    if executable_node is None:
        raise AuditError("EXE-Regeln fehlen")
    executable = audit_executable(source, executable_node)
    loose = audit_loose(source, rules, assets)
    issues = sum(len(x["issues"]) for x in discs)
    ok_discs = sum(x["source_sha256_matches"] for x in discs)
    fully_audited = sum(x["status"] == "VERIFIED" for x in discs)
    expected_native = sum(len(node.findall("Bitmap")) for node in rules.findall("./Image"))
    result = {
        "schema": "harvester-gog-originalvergleich-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_paths_recorded": False,
        "contains_original_game_bytes_or_text": False,
        "legal_clearance": False,
        "method_notice": (
            "Hashes and aligned byte evidence are technical observations only. "
            "Equal bytes at the same offsets do not prove copyright origin; "
            "insertions may shift otherwise identical bytes. This is NOT legal clearance."
        ),
        "manifest_sha256": manifest_digest,
        "fix2_payload_assets_verified_before_comparison": len(assets),
        "discs": discs,
        "executable": executable,
        "loose_files": loose,
        "summary": {
            "iso_source_hashes_matched": ok_discs,
            "iso_sources_expected": len(discs),
            "iso_fully_audited": fully_audited,
            "native_xfile_bitmaps_expected": expected_native,
            "iso_replacement_resources_compared": sum(len(x["replacements"]) for x in discs),
            "native_xfile_bitmaps_compared": sum(len(x["native_bitmaps"]) for x in discs),
            "source_or_resource_issues": issues,
            "exe_status": executable["status"],
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvester GOG: schreibgeschützter Original-/FIX2-Vergleich")
    parser.add_argument("--source", type=Path, help="Originaler installierter englischer GOG-Spielordner")
    parser.add_argument("--output-dir", type=Path,
                        default=Path.home() / "Documents" / "Harvester_Originalvergleich",
                        help="Separater Berichtsordner, niemals im Spielordner/Repository")
    parser.add_argument("--preflight", action="store_true",
                        help="Nur geprüfte Regeln.xml und FIX2-Payload-Hashes kontrollieren")
    args = parser.parse_args()
    try:
        rules, assets, manifest_hash = load_verified_rules()
        print("FIX2-Payload PASS: 18 SHA-256-geprüfte Ersatzressourcen; Regeln.xml geprüft.")
        if args.preflight:
            return 0
        if args.source is None:
            parser.error("--source ist für den Originalvergleich erforderlich")
        source = args.source.expanduser().resolve()
        if not source.is_dir():
            raise AuditError("GOG-Quellordner existiert nicht")
        output_dir = valid_report_directory(args.output_dir, source)
        report = build_report(source, rules, assets, manifest_hash)
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output = output_dir / ("Harvester_Originalvergleich_" + stamp + ".json")
        with output.open("x", encoding="utf-8") as fd:
            json.dump(report, fd, ensure_ascii=False, indent=2)
            fd.write("\n")
        summary = report["summary"]
        print("Bericht erstellt:", output)
        print("GOG-CD-Hashes: {}/{}; direkte Vergleiche: {}; XFILE-Bitmaps: {}; EXE: {}.".format(
            summary["iso_source_hashes_matched"], summary["iso_sources_expected"],
            summary["iso_replacement_resources_compared"],
            summary["native_xfile_bitmaps_compared"], summary["exe_status"]))
        print("Der Bericht enthält keine Originaldialoge, Grafikdaten oder persönlichen Pfade.")
        if summary["iso_source_hashes_matched"] != 3 or summary["exe_status"] != "VERIFIED":
            print("WARNUNG: Nicht alle Originalhashes/EXE-Prüfungen bestanden; Bericht beachten.")
            return 2
        if (summary["source_or_resource_issues"]
                or summary["iso_fully_audited"] != 3
                or summary["native_xfile_bitmaps_compared"]
                   != summary["native_xfile_bitmaps_expected"]):
            print("WARNUNG: Teilprüfungen offen; Bericht beachten (Exitcode 2).")
            return 2
        return 0
    except (AuditError, OSError, ValueError, ET.ParseError) as exc:
        print("AUDIT STOP:", exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
