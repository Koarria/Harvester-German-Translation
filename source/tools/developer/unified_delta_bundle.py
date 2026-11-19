#!/usr/bin/env python3
"""Private unified FIX2 delta bundle proof-of-concept.

Builds 20 source-specific zlib9 deltas for 18 target assets using only locally
SHA-256-verified GOG originals and private FIX2 targets. It immediately verifies
ALL 48 ISO/XFILE usages by decoding the bundle WITHOUT full target files.

DO NOT publish the resulting bundle: deltas contain translated game content.
Not a production installer. Does not modify original games, RC3b or saves.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime

import bitmap_delta_compact as bitmap
import originalvergleich_gog as audit
import variable_delta_poc as variable
from runtime.harvester_iso import hash_file, scan_iso

BUNDLE_SCHEMA = "harvester-gog-private-delta-bundle-v1"
MANIFEST_NAME = "bundle.json"
RULES_NAME = "Regeln.xml"
CODECS = {"bitmap-v2", "copyadd-v1"}
EXPECTED_USES = 48
EXPECTED_VARIANTS = 20
EXPECTED_ASSETS = 18
EXPECTED_LOOSE = ("MENU.INI", "DIALOG.RSP")
MAX_MANIFEST = 128 * 1024
MAX_PACKED = 3 * audit.MAX_RESOURCE_BYTES
MAX_RULES = 64 * 1024
MAX_MEMBERS = EXPECTED_VARIANTS + 2
PINNED_RULES_SHA = audit.EXPECTED_RULES_SHA256
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class BundleError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _trusted_rules(xml_bytes: bytes, expected_rules_sha: str):
    if (not 0 < len(xml_bytes) <= MAX_RULES
            or sha(xml_bytes) != expected_rules_sha):
        raise BundleError("Unbekanntes oder verändertes FIX2-Regelmanifest")
    root = ET.fromstring(xml_bytes)
    if root.tag != "HarvesterPatch":
        raise BundleError("Falscher XML-Regeltyp")
    images = root.findall("./Image")
    if (len(images) != 3
            or [i.get("name") for i in images] != list(audit.DISC_NAMES)):
        raise BundleError("CD-Zuordnung im Regelmanifest unvollständig")
    asset_nodes = root.findall("./Assets/Asset")
    assets = {}
    for node in asset_nodes:
        name, declared_sha = node.get("name"), node.get("sha")
        if (not name or not re.fullmatch(r"[0-9a-f]{64}\.bin", name)
                or declared_sha != name[:-4] or name in assets):
            raise BundleError("Unbekannte/mehrfache Zieldatei im Manifest")
        size = int(node.get("size", "-1"))
        if not 0 < size <= audit.MAX_RESOURCE_BYTES:
            raise BundleError("Ungültige Zielressourcengröße")
        assets[name] = size
    if len(assets) != EXPECTED_ASSETS:
        raise BundleError("Keine 18 eindeutigen FIX2-Zielressourcen")
    return root, assets


def _variant_id(source_sha: str, target_sha: str) -> str:
    if not HEX64.fullmatch(source_sha) or not HEX64.fullmatch(target_sha):
        raise BundleError("Ungültige Original-/Zielhashs")
    return source_sha + "_" + target_sha


def _member(variant_id: str) -> str:
    return "deltas/" + variant_id + ".z"


def collect_original_uses(source: Path, rules, target_sizes: dict,
                          check_exe: bool = True) -> tuple[list[dict], list[dict]]:
    """Returns only known ISO resource extents and optional GOG-root loose files.

    No cloud_saves traversal, no writing. Rechecks each entire original CD hash.
    """
    if source.is_symlink() or not source.is_dir():
        raise BundleError("Original-GOG-Verzeichnis fehlt oder ist verlinkt")
    if check_exe:
        exe_node = rules.find("./Executable")
        if exe_node is None:
            raise BundleError("HARVEST.EXE-Regeln fehlen")
        proof = audit.audit_executable(source, exe_node)
        if proof["status"] != "VERIFIED":
            raise BundleError("Original-HARVEST.EXE/191 Edits nicht verifiziert")
    uses = []
    used = set()
    for image in rules.findall("./Image"):
        disc = image.get("name")
        if disc not in audit.DISC_NAMES:
            raise BundleError("Unbekanntes CD-Abbild")
        iso = source / disc
        if iso.is_symlink() or not iso.is_file():
            raise BundleError("Original-GOG-CD fehlt oder ist ein Symlink: " + disc)
        if hash_file(iso) != image.get("sha"):
            raise BundleError("GOG-CD-SHA-256 falsch: " + disc)
        entries = scan_iso(iso)
        if sum(not e.is_dir for e in entries.values()) != int(image.get("count", "-1")):
            raise BundleError("ISO-Dateizahl ist nicht manifestkonform: " + disc)
        bitmaps = image.findall("Bitmap")
        names = [n.get("path") for n in bitmaps]
        wanted = {n.replace("\\", "/").upper() for n in names if n}
        if len(bitmaps) != 6 or len(wanted) != 6:
            raise BundleError("Genau sechs eindeutige XFILE-Zielnamen erforderlich")
        positions = audit.locate_xfile(iso, entries, wanted)
        if set(positions) != wanted:
            raise BundleError("XFILE-Abdeckung weicht vom Manifest ab")
        for role, nodes in (("Replace", image.findall("Replace")),
                            ("Bitmap", bitmaps)):
            for node in nodes:
                path, asset = node.get("path"), node.get("asset")
                if not path or asset not in target_sizes:
                    raise BundleError("Unbekanntes Original-/Zielressourcenmapping")
                identity = (disc, role, path)
                if identity in used:
                    raise BundleError("Doppelte Originalressource im Regelmanifest")
                used.add(identity)
                if role == "Bitmap":
                    loc = positions.get(path.replace("\\", "/").upper())
                    if loc is None:
                        raise BundleError("XFILE-Bitmap fehlt: " + path)
                    offset, size = loc
                else:
                    entry = entries.get(path)
                    if entry is None or entry.is_dir:
                        raise BundleError("Äußere ISO-Ressource fehlt: " + path)
                    offset, size = entry.offset, entry.size
                original = audit.read_span(iso, offset, size)
                uses.append({"disc": disc, "role": role, "path": path,
                             "asset": asset, "source": original,
                             "source_sha256": sha(original)})
    if len(uses) != EXPECTED_USES:
        raise BundleError("Nicht genau 30 Replace + 18 XFILE-Bitmap-Verwendungen")

    loose = []
    for node in rules.findall("./Loose"):
        path, asset = node.get("path"), node.get("asset")
        if path not in EXPECTED_LOOSE:
            continue  # Never open cloud_saves or any save-related path.
        if asset not in target_sizes:
            raise BundleError("Unbekanntes loses FIX2-Ziel")
        p = source / path
        if p.is_symlink():
            raise BundleError("Lose GOG-Ressource ist ein Symlink")
        if not p.is_file():
            loose.append({"path": path, "asset": asset, "status": "NOT_PRESENT"})
            continue
        if not 0 < p.stat().st_size <= audit.MAX_RESOURCE_BYTES:
            raise BundleError("Lose GOG-Ressource außerhalb sicherer Größe")
        raw = p.read_bytes()
        loose.append({"path": path, "asset": asset, "status": "COMPARED",
                      "source": raw, "source_sha256": sha(raw)})
    if sorted(x["path"] for x in loose) != sorted(EXPECTED_LOOSE):
        raise BundleError("Lose Original-Stammdateien falsch zugeordnet")
    return uses, loose


def _encode(source: bytes, target: bytes, codec: str) -> bytes:
    if codec == "bitmap-v2":
        if len(source) != len(target):
            raise BundleError("Bitmap-Original und Ziel müssen gleich groß sein")
        return bitmap.make_delta(source, target)
    if codec == "copyadd-v1":
        return variable.make_delta(source, target)[0]
    raise BundleError("Unbekannter Delta-Codec")


def _restore(source: bytes, payload: bytes, codec: str) -> bytes:
    if codec == "bitmap-v2":
        return bitmap.restore_delta(source, payload)
    if codec == "copyadd-v1":
        return variable.apply_delta(source, payload)
    raise BundleError("Unbekannter Delta-Codec")


def _unpack(packed: bytes, expected_size: int) -> bytes:
    if not 0 < expected_size <= MAX_PACKED:
        raise BundleError("Entpackgröße außerhalb sicherer Grenzen")
    try:
        dec = zlib.decompressobj()
        raw = dec.decompress(packed, expected_size + 1)
        if (len(raw) != expected_size or dec.unconsumed_tail or dec.unused_data
                or not dec.eof or dec.flush()):
            raise BundleError("zlib-Datensatz beschädigt oder übergroß")
        return raw
    except zlib.error as exc:
        raise BundleError("zlib-Datensatz beschädigt") from exc


def _zipinfo(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = 0o600 << 16
    return info


def build_bundle_bytes(source: Path, xml_bytes: bytes, targets: dict[str, Path],
                       expected_rules_sha: str = PINNED_RULES_SHA,
                       check_exe: bool = True) -> tuple[bytes, dict]:
    """Private local builder. No writes; it sees full verified FIX2 targets."""
    rules, sizes = _trusted_rules(xml_bytes, expected_rules_sha)
    if set(targets) != set(sizes):
        raise BundleError("Nicht genau die 18 gepinnten Zielasset-Namen")
    target_data = {}
    for name, expected_size in sizes.items():
        p = targets[name]
        if p.is_symlink() or not p.is_file() or p.stat().st_size != expected_size:
            raise BundleError("FIX2-Zielgröße/Dateipfad falsch: " + name)
        content = audit.read_replacement(targets, name)
        if len(content) != expected_size or sha(content) != name[:-4]:
            raise BundleError("FIX2-Ziel-SHA-256 falsch: " + name)
        target_data[name] = content
    source_uses, source_loose = collect_original_uses(source, rules, sizes,
                                                      check_exe=check_exe)
    variants, packed_members, mappings = {}, {}, []
    for use in source_uses:
        target = target_data[use["asset"]]
        codec = "bitmap-v2" if use["path"].upper().endswith(".BM") else "copyadd-v1"
        vid = _variant_id(use["source_sha256"], sha(target))
        if vid not in variants:
            delta = _encode(use["source"], target, codec)
            if _restore(use["source"], delta, codec) != target:
                raise BundleError("Rekonstruktion ist nicht bytegleich")
            packed = zlib.compress(delta, 9)
            if _restore(use["source"], _unpack(packed, len(delta)), codec) != target:
                raise BundleError("Ziel-SHA nach zlib-Dekompression falsch")
            variants[vid] = {
                "id": vid, "codec": codec, "source_sha256": use["source_sha256"],
                "target_sha256": sha(target), "source_bytes": len(use["source"]),
                "target_bytes": len(target), "unpacked_bytes": len(delta),
                "packed_sha256": sha(packed), "packed_bytes": len(packed),
                "member": _member(vid)
            }
            packed_members[_member(vid)] = packed
        elif (variants[vid]["codec"] != codec
              or variants[vid]["source_bytes"] != len(use["source"])
              or variants[vid]["target_bytes"] != len(target)):
            raise BundleError("Widersprüchliche Original-/Zielvariante")
        mappings.append({
            "disc": use["disc"], "role": use["role"], "path": use["path"],
            "asset": use["asset"], "variant": vid
        })
    if len(variants) != EXPECTED_VARIANTS or len(mappings) != EXPECTED_USES:
        raise BundleError("Nicht alle 20 Originalvarianten für 48 Verwendungen gefunden")
    if set(row["asset"] for row in mappings) != set(sizes):
        raise BundleError("Nicht alle 18 FIX2-Ziele abgedeckt")
    available = {}
    for use in mappings:
        available.setdefault(use["asset"], set()).add(use["variant"])
    loose_mapping = []
    for item in source_loose:
        entry = {"path": item["path"], "asset": item["asset"],
                 "status": item["status"]}
        if item["status"] == "COMPARED":
            vid = _variant_id(item["source_sha256"],
                              sha(target_data[item["asset"]]))
            if vid not in available.get(item["asset"], set()):
                raise BundleError("Lose GOG-Originalvariante ist nicht durch CD-Bundle abgesichert")
            entry["variant"] = vid
        loose_mapping.append(entry)
    manifest = {
        "schema": BUNDLE_SCHEMA, "rules_sha256": expected_rules_sha,
        "private_only": True, "legal_clearance": False,
        "image_uses": sorted(mappings, key=lambda x: (x["disc"], x["role"], x["path"])),
        "loose_root_uses": sorted(loose_mapping, key=lambda x: x["path"]),
        "variants": [variants[k] for k in sorted(variants)],
        "summary": {
            "iso_uses": EXPECTED_USES, "distinct_variants": len(variants),
            "distinct_target_assets": len(sizes),
            "packed_delta_bytes": sum(x["packed_bytes"] for x in variants.values()),
        },
    }
    if len(canonical_json(manifest)) > MAX_MANIFEST:
        raise BundleError("Bundle-Manifest zu groß")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(_zipinfo(RULES_NAME), xml_bytes)
        archive.writestr(_zipinfo(MANIFEST_NAME), canonical_json(manifest))
        for name in sorted(packed_members):
            archive.writestr(_zipinfo(name), packed_members[name])
    return stream.getvalue(), manifest


def verify_bundle_bytes(source: Path, bundle: bytes, expected_rules_sha: str =
                        PINNED_RULES_SHA, check_exe: bool = True,
                        target_refs: dict[str, bytes] | None = None) -> dict:
    """Decode all 48 resource occurrences WITHOUT requiring original FIX2 assets."""
    if not 0 < len(bundle) <= 20 * 1024 * 1024:
        raise BundleError("Bundle außerhalb sicherer Größenbegrenzung")
    with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(infos) != MAX_MEMBERS or len(set(names)) != len(names):
            raise BundleError("Doppelte/fehlende ZIP-Dateien")
        if (MANIFEST_NAME not in names or RULES_NAME not in names
                or any(info.compress_type != zipfile.ZIP_STORED
                       or info.flag_bits & 1
                       or info.file_size > MAX_PACKED for info in infos)):
            raise BundleError("Unbekannte ZIP-Einträge oder Kompression")
        by_name = {info.filename: info for info in infos}
        if by_name[MANIFEST_NAME].file_size > MAX_MANIFEST or by_name[RULES_NAME].file_size > MAX_RULES:
            raise BundleError("Manifest-/Regelgröße zu groß")
        xml_bytes = archive.read(RULES_NAME)
        rules, assets = _trusted_rules(xml_bytes, expected_rules_sha)
        manifest_bytes = archive.read(MANIFEST_NAME)
        data = json.loads(manifest_bytes)
        if (data.get("schema") != BUNDLE_SCHEMA
                or data.get("rules_sha256") != expected_rules_sha
                or data.get("legal_clearance") is not False
                or data.get("private_only") is not True
                or len(data.get("variants", [])) != EXPECTED_VARIANTS
                or len(data.get("image_uses", [])) != EXPECTED_USES):
            raise BundleError("Unbekannte oder unvollständige Bundle-Metadaten")
        variants = {}
        for v in data["variants"]:
            src, dst = v.get("source_sha256"), v.get("target_sha256")
            vid = _variant_id(src, dst)
            if (v.get("id") != vid or vid in variants
                    or v.get("member") != _member(vid)
                    or v.get("codec") not in CODECS
                    or not 0 < v.get("source_bytes", 0) <= audit.MAX_RESOURCE_BYTES
                    or not 0 < v.get("target_bytes", 0) <= audit.MAX_RESOURCE_BYTES
                    or not 0 < v.get("unpacked_bytes", 0) <= MAX_PACKED
                    or not 0 < v.get("packed_bytes", 0) <= MAX_PACKED
                    or not isinstance(v.get("packed_sha256"), str)
                    or not HEX64.fullmatch(v["packed_sha256"])):
                raise BundleError("Unzulässiger Delta-Metadatensatz")
            variants[vid] = v
        expected_names = {RULES_NAME, MANIFEST_NAME}
        expected_names.update(v["member"] for v in variants.values())
        if set(names) != expected_names:
            raise BundleError("ZIP enthält unbekannte oder fehlende Ressourcen")
        stored_packed = {}
        for vid, v in variants.items():
            packed = archive.read(v["member"])
            if len(packed) != v["packed_bytes"] or sha(packed) != v["packed_sha256"]:
                raise BundleError("Binär-Delta ist beschädigt: " + vid[:12])
            stored_packed[vid] = _unpack(packed, v["unpacked_bytes"])

    # Preserve all 48 expected resource paths/targets from the LOCKED rules XML.
    expected_usages = {
        (i.get("name"), role, n.get("path")): n.get("asset")
        for i in rules.findall("./Image")
        for role in ("Replace", "Bitmap")
        for n in i.findall(role)
    }
    uses = {}
    for m in data["image_uses"]:
        key = (m.get("disc"), m.get("role"), m.get("path"))
        if key not in expected_usages or key in uses or m.get("asset") != expected_usages[key]:
            raise BundleError("Ressourcenpfad im Bundle unterscheidet sich vom FIX2-Manifest")
        vid = m.get("variant")
        v = variants.get(vid)
        if v is None or v["target_sha256"] != m["asset"][:-4] or v["target_bytes"] != assets[m["asset"]]:
            raise BundleError("Falsche Delta-Zielressource")
        if v["codec"] != ("bitmap-v2" if m["path"].upper().endswith(".BM") else "copyadd-v1"):
            raise BundleError("Falsches Deltaformat für Ressourcenart")
        uses[key] = (v, stored_packed[vid])
    if set(uses) != set(expected_usages):
        raise BundleError("Unvollständige Ressourcenmatrix in Paket")

    originals, actual_loose = collect_original_uses(source, rules, assets, check_exe=check_exe)
    covered = set()
    for usage in originals:
        key = (usage["disc"], usage["role"], usage["path"])
        v, delta = uses[key]
        if sha(usage["source"]) != v["source_sha256"] or len(usage["source"]) != v["source_bytes"]:
            raise BundleError("Falsche Originalvariante für CD/Ressource: " + str(key))
        restored = _restore(usage["source"], delta, v["codec"])
        if sha(restored) != v["target_sha256"] or len(restored) != v["target_bytes"]:
            raise BundleError("Ziel-SHA-256/Größe nach Rekonstruktion falsch")
        if target_refs is not None and restored != target_refs[usage["asset"]]:
            raise BundleError("Bundle weicht vom bestehenden FIX2-Ziel ab")
        covered.add(v["id"])
    if covered != set(variants):
        raise BundleError("Nicht alle 20 Varianten tatsächlich rekonstruiert")

    loose_by_path = {i["path"]: i for i in data.get("loose_root_uses", [])}
    if set(loose_by_path) != set(EXPECTED_LOOSE):
        raise BundleError("Unerwartete GOG-Stammdateien")
    for path, entry in loose_by_path.items():
        expected_asset = next((n.get("asset") for n in rules.findall("./Loose")
                               if n.get("path") == path), None)
        if entry.get("asset") != expected_asset:
            raise BundleError("Lose Zielressource im Bundle falsch")
    # Validate optional loose originals as originally observed without opening saves.
    # Reuse previously hash-checked original entries; do not re-scan all CDs.
    for item in actual_loose:
        row = loose_by_path[item["path"]]
        if item["status"] != row.get("status"):
            raise BundleError("Lose GOG-Stammdatei geändert")
        if item["status"] == "COMPARED":
            vid = row.get("variant")
            if vid not in variants or (variants[vid]["source_sha256"] != sha(item["source"])
                                       or variants[vid]["target_sha256"] != item["asset"][:-4]):
                raise BundleError("GOG-Stammoriginal-/Zielvariante falsch")
    return {
        "verified_original_cd_sha256": 3, "verified_iso_and_xfile_uses": len(originals),
        "reconstructed_unique_pairs": len(covered), "target_asset_count": len(assets),
        "verified_loose_root_files": sum(x["status"] == "COMPARED" for x in actual_loose),
        "bundle_bytes": len(bundle),
        "sum_zlib9_delta_bytes": sum(v["packed_bytes"] for v in variants.values()),
        "source_or_game_written": False, "original_game_modified": False,
        "legal_clearance": False
    }


def main() -> int:
    p = argparse.ArgumentParser(
        description="Privater Harvester-GOG-Delta-Bundle-Prototyp (20 Quellen/18 Ziele)"
    )
    p.add_argument("--preflight", action="store_true",
                   help="Nur das unveränderte FIX2-Manifest und 18 Payload-Hashes prüfen")
    p.add_argument("--source", type=Path, help="Unveränderter englischer GOG-Originalordner")
    p.add_argument("--verify-bundle", type=Path,
                   help="Vorhandenes privates Delta-Bundle nur lesend verifizieren")
    p.add_argument("--output-dir", type=Path,
                   default=Path.home() / "Documents" / "Harvester_Privates_Delta_Bundle")
    args = p.parse_args()
    try:
        if args.preflight:
            audit.load_verified_rules()
            print("FIX2-Manifests und alle 18 Ersatzressourcen: PASS")
            return 0
        if args.source is None:
            p.error("--source ist erforderlich")
        if args.source.is_symlink():
            raise BundleError("Originalordner darf kein Symlink sein")
        source = args.source.expanduser().resolve()
        if not source.is_dir():
            raise BundleError("Englischer GOG-Ordner nicht gefunden")
        if args.verify_bundle:
            requested = args.verify_bundle.expanduser()
            if requested.is_symlink():
                raise BundleError("Privates Bundle darf kein symbolischer Link sein")
            file = requested.resolve()
            if not file.is_file() or not 0 < file.stat().st_size <= 20*1024*1024:
                raise BundleError("Privates Bundle fehlt/ist unzulässig groß")
            result = verify_bundle_bytes(source, file.read_bytes())
            print("Privates Delta-Bundle: PASS", result)
            return 0
        rules, assets, digest = audit.load_verified_rules()
        xml_bytes = (audit.REPO / "payload" / "Regeln.xml").read_bytes()
        output_dir = audit.valid_report_directory(args.output_dir, source)
        bundle, manifest = build_bundle_bytes(source, xml_bytes, assets, digest)
        references = {name: audit.read_replacement(assets, name) for name in assets}
        evidence = verify_bundle_bytes(source, bundle, target_refs=references)
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = ("Harvester_DeltaBundle_PRIVAT_"
                    + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".zip")
        dest = output_dir / filename
        with dest.open("xb") as f:
            f.write(bundle)
        summary_path = dest.with_suffix(".json")
        safe_summary = {
            "schema": BUNDLE_SCHEMA + "-report",
            "private_bundle_created": True,
            "private_bundle_path_excluded": True,
            "game_contents_in_json": False, "legal_clearance": False,
            **evidence,
        }
        with summary_path.open("x", encoding="utf-8") as f:
            json.dump(safe_summary, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("20/20 Quellvarianten, 48/48 Ressourcenvorkommen, 18/18 Zieldateien PASS.")
        print("Privates, NICHT zum Hochladen/Veröffentlichen freigegebenes Bundle:", dest)
        print("Nur diesen JSON-Bericht teilen:", summary_path)
        print("Weder RC3b noch Originaldateien oder Spielstände wurden verändert.")
        return 0
    except (BundleError, audit.AuditError, bitmap.CompactError,
            variable.VariableDeltaError, OSError, ValueError, KeyError,
            zipfile.BadZipFile, ET.ParseError, TypeError) as exc:
        print("BUNDLE-TEST ABGEBROCHEN:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
