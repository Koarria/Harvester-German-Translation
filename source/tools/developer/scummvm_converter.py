#!/usr/bin/env python3
"""Harvester GOG Deutsch -> ScummVM data-layout converter (release v1.0.0).

Does not patch ScummVM, modify GOG installations, or transfer DOSBox saves.
Uses the user's own GOG files and the separately installed German translation.
Supported target: ScummVM 2026.4.0 Harvester engine (English detection ID).
No original game resource files are embedded in this application.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT))
from runtime.harvester_iso import Extent, hash_file, scan_iso

ORIGINAL_EXE_SHA = "6a9f3844254c6b18900685f10a83ca146bc1eec1a396d68eb7dff16cd217e72c"
ORIGINAL_EXE_SIZE = 1173079
SCUMMVM_EXE_MD5_5000 = "787e43b868ebfaca614010af3ab66b6d"
DISC_IMAGES = ("HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT")
ISO_FILE_COUNTS = (330, 135, 112)  # Count ONLY files (Regeln.xml Image.count excludes directories)
SCUMMVM_ARCHIVE_PAIRS = (
    ("INDEX.001", "HARVEST.DAT"),
    ("INDEX.002", "SOUND.DAT"),
    ("INDEX.003", "HARVEST2.DAT"),
)
MODES = ("ohne", "10px", "11px")
TARGET_PREFIX = "Harvester ScummVM Deutsch"
CHUNK = 2 * 1024 * 1024
VIDEO_MANIFEST_SHA256 = "f56a5708018820bcbc6af0c6fb71f3f775a39b317bd1626eb898aa04aaf7162d"


class ConversionError(ValueError):
    pass


@dataclass(frozen=True)
class DiscPlan:
    number: int
    iso: Path
    entries: dict[str, Extent]
    archives: tuple[str, ...]


def require(condition: bool, why: str) -> None:
    if not condition:
        raise ConversionError(why)


def clean_dir(path: Path, label: str) -> Path:
    require(not path.is_symlink(), label + " ist ein symbolischer Link")
    p = path.resolve(strict=True)
    require(p.is_dir(), label + " ist kein Ordner")
    return p


def separate_from(path: Path, other: Path, a: str, b: str) -> None:
    require(not (path == other or path.is_relative_to(other) or other.is_relative_to(path)),
            a + " und " + b + " dürfen nicht ineinander liegen")


def verify_scummvm_exe(english: Path) -> Path:
    """Keep English EXE for engine detection; German DOS EXE patch is not executed."""
    exe = english / "HARVEST.EXE"
    require(exe.is_file() and not exe.is_symlink(), "Originale HARVEST.EXE fehlt")
    require(exe.stat().st_size == ORIGINAL_EXE_SIZE,
            "HARVEST.EXE-Größe stimmt nicht mit ScummVM 2026.4.0 (EN) überein")
    require(hash_file(exe) == ORIGINAL_EXE_SHA,
            "HARVEST.EXE ist keine verifizierte englische GOG-Originaldatei")
    with exe.open("rb") as stream:
        md5 = hashlib.md5(stream.read(5000)).hexdigest()
    require(md5 == SCUMMVM_EXE_MD5_5000,
            "HARVEST.EXE wird vom geprüften ScummVM-Detektor nicht erkannt")
    return exe


def read_rules() -> ET.Element:
    path = ROOT / "payload" / "Regeln.xml"
    require(path.is_file() and not path.is_symlink(), "Verbindliche Regeln.xml fehlt")
    require(hash_file(path) == "7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b",
            "Regeln.xml ist nicht die für den Release geprüfte Fassung")
    return ET.parse(path).getroot()


def game_iso_path(german: Path, mode: str, name: str) -> Path:
    require(mode in MODES, "Unbekannter Videountertitel-Modus")
    return (german / name if mode == "ohne" else
            german / "VideoUntertitel" / mode / name)


def verify_disc_images(german: Path, mode: str, rules: ET.Element) -> list[DiscPlan]:
    plans: list[DiscPlan] = []
    for num, (image, expected_file_count) in enumerate(zip(DISC_IMAGES, ISO_FILE_COUNTS), 1):
        iso = game_iso_path(german, mode, image)
        require(iso.is_file() and not iso.is_symlink(), "Deutsches CD-Abbild fehlt: " + str(iso))
        entries = scan_iso(iso)
        # The signed-off GOG patcher validates Image.count as number of FILES:
        #   entries.Values.Count(e => !e.Directory)
        # The ISO scanner returns both file and directory entries. On the
        # user's 11-px CD1: 330 files + 22 directories = 352 total entries.
        # Never reject a correct translated ISO because directories are counted.
        file_count = sum(not entry.is_dir for entry in entries.values())
        require(file_count == expected_file_count,
                f"Deutsches CD-Abbild {image}: {file_count} statt {expected_file_count} Dateien "
                f"({len(entries) - file_count} Verzeichnisse separat geprüft)")
        pairs = []
        for idx, data in SCUMMVM_ARCHIVE_PAIRS:
            available = idx in entries and data in entries
            if (idx in entries) != (data in entries):
                raise ConversionError(f"{image}: unvollständiges ScummVM-XFILE-Paar {idx}/{data}")
            if available:
                require(not entries[idx].is_dir and not entries[data].is_dir,
                        "ScummVM-XFILE-Index/Daten sind keine Dateien")
                pairs.append(idx + " + " + data)
        require(pairs, "In " + image + " fehlen alle ScummVM-XFILE-Archivpaare")
        if num == 1:
            require("INDEX.001 + HARVEST.DAT" in pairs,
                    "CD1 besitzt nicht das für ScummVM erforderliche Startarchiv")
        # Compare every known translated loose ISO replacement against the
        # original v1.0.0 rules; this catches an English-only/broken install.
        rule = next((n for n in rules.findall("Image") if n.get("name") == image), None)
        require(rule is not None, "Regelmanifest enthält das CD-Abbild nicht: " + image)
        require(rule.get("count") == str(expected_file_count),
                "CD-Dateianzahl weicht vom freigegebenen Regelmanifest ab: " + image)
        for node in rule.findall("Replace"):
            key, asset = node.get("path"), node.get("asset")
            require(key in entries and not entries[key].is_dir,
                    "Übersetzte Datei fehlt: " + image + "/" + str(key))
            digest = hash_file(iso, entries[key].offset, entries[key].size)
            require(digest == asset.removesuffix(".bin"),
                    "Übersetzte Datei falsch: " + image + "/" + key)
        plans.append(DiscPlan(num, iso, entries, tuple(pairs)))
    return plans


def verified_local_render_hashes(english: Path, german: Path, mode: str,
                                 discs: list[DiscPlan]) -> dict[tuple[str, str], dict]:
    """Validate the real locally rendered FST proofs; manifest target hashes
    describe historical pre-rendered patches, NOT RC3b local-renderer output.

    Neither the proof nor QA report is assumed globally hash-pinned: the proof
    must bind to exactly the two user-selected GOG folders, attest every
    selected VIDEO ISO and the QA JSON, and the QA must attest all 132 jobs.
    This verifies internal consistency with the installed, tested GOG release.
    """
    proof_path = german / "Deutsch_Pruefnachweis.xml"
    require(proof_path.is_file() and not proof_path.is_symlink()
            and 0 < proof_path.stat().st_size < 8 * 1024 * 1024,
            "Der deutsche Installationsnachweis fehlt oder ist ungültig")
    proof = ET.parse(proof_path).getroot()
    require(proof.tag == "HarvesterDeutschInstallation"
            and proof.get("regeln_sha256") ==
                "7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b"
            and proof.get("video_untertitel_release") == "HARVESTER_GOG_DEUTSCH_VIDEO_V1",
            "Deutsche Videoinstallation besitzt keinen gültigen v1.0.0-Prüfnachweis")
    require(proof.get("original") and proof.get("ziel")
            and os.path.normcase(str(Path(proof.get("original")).resolve())) ==
                os.path.normcase(str(english.resolve()))
            and os.path.normcase(str(Path(proof.get("ziel")).resolve())) ==
                os.path.normcase(str(german.resolve())),
            "Installationsnachweis gehört zu anderen GOG-Quell-/Zielordnern")

    registered: dict[str, str] = {}
    # Production installer.py:update_proof() deliberately moves the original
    # legacy launcher proof entry to VideoUntertitel/ALTER_FIX2_STARTER.txt,
    # then appends *the same launcher* to its generated-list a second time.
    # Thus a real signed-off GOG v1.0.0 XML has exactly two identical proof
    # rows for this ONE archived launcher. Reject ALL other duplicates and
    # any discrepancy in the two recorded hashes.
    archived_key = "videountertitel/alter_fix2_starter.txt"
    archived_count = 0
    for row in proof:
        require(row.tag == "Datei" and set(row.attrib) == {"pfad", "sha256"},
                "Unerwarteter Eintrag im deutschen Installationsnachweis")
        raw = row.get("pfad", "").replace("\\", "/")
        key = raw.casefold()
        digest = row.get("sha256", "")
        require(raw and not raw.startswith("/") and ":" not in raw
                and all(part not in ("", ".", "..") for part in raw.split("/"))
                and re.fullmatch(r"[0-9a-f]{64}", digest),
                "Unsicherer Pfad oder ungültiger SHA-256 im Installationsnachweis")
        if key in registered:
            require(key == archived_key and archived_count == 1
                    and registered[key] == digest,
                    "Unerwarteter oder widersprüchlicher Duplikat-Eintrag im Installationsnachweis")
            archived_count = 2
        else:
            registered[key] = digest
            if key == archived_key:
                archived_count = 1

    # The known duplicate is only accepted when the actual archived file has
    # the same content hash as BOTH entries. Never blindly ignore a duplicate.
    if archived_count:
        archived = german / "VideoUntertitel" / "ALTER_FIX2_STARTER.txt"
        require(archived.is_file() and not archived.is_symlink()
                and hash_file(archived) == registered[archived_key],
                "Archivierter deutscher Starter stimmt nicht mit dem Installationsnachweis überein")

    for disc in discs:
        iso_rel = f"VideoUntertitel/{mode}/{DISC_IMAGES[disc.number - 1]}"
        require(registered.get(iso_rel.casefold()) is not None,
                "Videountertitel-CD fehlt im deutschen Installationsnachweis: " + iso_rel)
        require(hash_file(disc.iso) == registered[iso_rel.casefold()],
                "Videountertitel-CD weicht vom deutschen SHA-256-Installationsnachweis ab: " + iso_rel)

    qa_rel = "VideoUntertitel/LOKALE_RENDER_QA.json"
    qa_path = german / qa_rel
    require(qa_path.is_file() and not qa_path.is_symlink()
            and 0 < qa_path.stat().st_size < 2 * 1024 * 1024
            and registered.get(qa_rel.casefold()) == hash_file(qa_path),
            "Lokale Render-QA stimmt nicht mit dem deutschen Installationsnachweis überein")
    report = json.loads(qa_path.read_text(encoding="utf-8-sig"))
    require(isinstance(report, dict)
            and report.get("release") == "HARVESTER_GOG_DEUTSCH_VIDEO_V1"
            and report.get("films") == 66
            and report.get("variant_render_jobs") == 132
            and report.get("iso_fst_positions") == 196,
            "Unbekannte oder unvollständige lokale Video-Render-QA")
    records = report.get("qa")
    require(isinstance(records, list) and len(records) == 132,
            "Lokale Video-Render-QA besitzt nicht 132 Datensätze")
    result: dict[tuple[str, str], dict] = {}
    for row in records:
        require(isinstance(row, dict), "Unerwarteter Render-QA-Datensatz")
        film, variant = row.get("film"), row.get("mode")
        require(isinstance(film, str) and re.fullmatch(r"[A-Z0-9_]{1,32}", film)
                and variant in ("10px", "11px")
                and re.fullmatch(r"[0-9a-f]{64}", str(row.get("source_sha256", "")))
                and re.fullmatch(r"[0-9a-f]{64}", str(row.get("rendered_sha256", ""))),
                "Ungültiger Film-/SHA-256-Datensatz der lokalen Render-QA")
        key = (film, variant)
        require(key not in result, "Doppeltes Film-/Modus-Ergebnis in der lokalen Render-QA")
        result[key] = row
    films = {key[0] for key in result}
    require(len(films) == 66 and all((film, variant) in result
            for film in films for variant in ("10px", "11px")),
            "Render-QA fehlt eine der beiden Untertitelvarianten für einen Film")
    return result


def verify_video_mode(english: Path, german: Path, mode: str,
                      discs: list[DiscPlan]) -> int:
    if mode == "ohne":
        return 0
    manifest = ROOT / "payload" / "VideoManifest.xml"
    require(manifest.is_file() and not manifest.is_symlink(), "VideoManifest.xml fehlt")
    require(hash_file(manifest) == VIDEO_MANIFEST_SHA256,
            "VideoManifest.xml wurde gegenüber dem Release verändert")
    entries = ET.parse(manifest).getroot().findall("Fst")
    relevant = [e for e in entries if e.get("mode") == mode]
    require(len(entries) == 196 and len(relevant) == 98,
            "Unvollständige Videountertitel-Matrix")

    # The original VideoManifest target_sha256 points to previously generated
    # HVP patch files. The actual v1.0.0 ships the RC3b *local renderer*, which
    # creates fresh FSTs and stores their exact hashes in LOKALE_RENDER_QA.json.
    # Trust ONLY the local QA after SHA-256 checks against the install proof
    # and also verify every FST extent actually present in the selected ISOs.
    rendered = verified_local_render_hashes(english, german, mode, discs)
    by_name = {DISC_IMAGES[i]: discs[i] for i in range(3)}
    seen: set[tuple[str, str]] = set()
    for item in relevant:
        disc = by_name.get(item.get("cd"))
        path, film = item.get("path"), item.get("film_id")
        require(disc is not None and isinstance(path, str)
                and path in disc.entries and not disc.entries[path].is_dir,
                "ScummVM-Untertitelvideo fehlt: " + str(path))
        key = (film, mode)
        qa = rendered.get(key)
        require(qa is not None
                and qa["source_sha256"] == item.get("source_sha256"),
                "Render-QA stammt nicht aus der freigegebenen deutschen Videopipeline: " + str(film))
        require((item.get("cd"), path) not in seen,
                "Doppelte Videoposition im freigegebenen Manifest")
        seen.add((item.get("cd"), path))
        found = hash_file(disc.iso, disc.entries[path].offset, disc.entries[path].size)
        require(found == qa["rendered_sha256"],
                "FST stimmt nicht mit der SHA-256-geprüften lokalen Render-QA überein: "
                + str(path) + " (" + mode + ")")
    require(len(seen) == 98, "Nicht alle 98 Videopositionen verifiziert")
    return len(relevant)


def preflight(english: Path, german: Path, target_parent: Path, mode: str) -> tuple[Path, list[DiscPlan], int, Path]:
    require(mode in MODES, "Modus muss ohne, 10px oder 11px sein")
    english = clean_dir(english, "Englisches GOG-Original")
    german = clean_dir(german, "Geprüfte deutsche GOG-Installation")
    target_parent = clean_dir(target_parent, "Ausgabe-Oberordner")
    separate_from(english, german, "Englische Installation", "deutsche Installation")
    separate_from(target_parent, english, "Ausgabeordner", "Original-GOG")
    separate_from(target_parent, german, "Ausgabeordner", "deutsche Installation")
    exe = verify_scummvm_exe(english)
    rules = read_rules()
    discs = verify_disc_images(german, mode, rules)
    videos = verify_video_mode(english, german, mode, discs)
    target = target_parent / (TARGET_PREFIX + " " + mode)
    require(not target.exists() and not target.is_symlink(), "Ziel existiert bereits: " + str(target))
    expected_bytes = sum(e.size for d in discs for e in d.entries.values() if not e.is_dir)
    reserve = expected_bytes + 512 * 1024 * 1024
    require(shutil.disk_usage(target_parent).free > reserve,
            "Zu wenig freier Speicherplatz für die ScummVM-Kopie (inkl. 512 MiB Reserve)")
    return exe, discs, videos, target


def copy_iso_member(src, entry: Extent, dst: Path) -> int:
    """Streaming copy of exactly one ISO extent, no games or archives altered."""
    require(not entry.is_dir, "ISO-Verzeichnis ist keine extrahierbare Datei")
    require(0 <= entry.offset and entry.size >= 0, "Ungültige ISO-Datei")
    remaining = entry.size
    src.seek(entry.offset)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("xb") as out:
        while remaining:
            chunk = src.read(min(CHUNK, remaining))
            if not chunk:
                raise ConversionError("Abgebrochene ISO-Kopie: " + entry.path)
            out.write(chunk)
            remaining -= len(chunk)
    require(dst.stat().st_size == entry.size, "Kopierte Datei hat unerwartete Größe")
    return entry.size


def convert(english: Path, german: Path, parent: Path, mode: str, execute: bool) -> dict:
    exe, plans, video_count, target = preflight(english, german, parent, mode)
    summary = {
        "schema": "harvester-gog-de-to-scummvm-conversion-v1",
        "scummvm_version": "2026.4.0",
        "mode": mode,
        "verified_original_harvest_exe": True,
        "verified_translated_iso_discs": 3,
        "verified_translated_fst_entries": video_count,
        "disc_file_counts": [sum(not e.is_dir for e in d.entries.values()) for d in plans],
        "archive_pairs": [list(d.archives) for d in plans],
        "dry_run": not execute,
        "original_game_modified": False,
        "source_game_saves_modified": False,
        "dos_saves_convertible": False,
    }
    if not execute:
        return summary
    parent = target.parent
    staged = Path(tempfile.mkdtemp(prefix=".HarvesterScummvmUnfertig_", dir=parent))
    try:
        shutil.copyfile(exe, staged / "HARVEST.EXE")
        require(hash_file(staged / "HARVEST.EXE") == ORIGINAL_EXE_SHA,
                "ScummVM-Erkennungs-EXE wurde beim Kopieren verändert")
        copied = 0
        for d in plans:
            disc_out = staged / ("CD" + str(d.number))
            disc_out.mkdir()
            with d.iso.open("rb") as stream:
                for key, entry in sorted(d.entries.items()):
                    dst = disc_out.joinpath(*key.split("/"))
                    if entry.is_dir:
                        dst.mkdir(parents=True, exist_ok=True)
                    else:
                        copied += copy_iso_member(stream, entry, dst)
            for index, data in SCUMMVM_ARCHIVE_PAIRS:
                if index + " + " + data in d.archives:
                    require((disc_out / index).is_file() and (disc_out / data).is_file(),
                            "XFILE-Archiv ist nach dem Extrahieren unvollständig")
        readme = (
            "HARVESTER GOG DEUTSCH - SCUMMVM\n\n"
            "Diese Datenkopie wurde aus der separaten deutschen GOG-Installation\n"
            "fuer ScummVM 2026.4.0 erzeugt.\n\n"
            "ScummVM starten, 'Spiel hinzufuegen' waehlen und diesen Ordner\n"
            "auswaehlen. Die englische Original-HARVEST.EXE ist ausschliesslich\n"
            "fuer die ScummVM-Spielerkennung vorhanden.\n"
            "CD1/CD2/CD3 enthalten die deutschen Spieldaten und die ausgewaehlte\n"
            "Videountertitel-Variante (ohne, 10px oder 11px).\n"
            "Eingebaute Untertitel sind bereits in die Videos gerendert.\n"
            "Der ScummVM-Untertitel-Schalter aendert diese Videotexte nicht.\n\n"
            "Empfohlene ScummVM-Grafik: pro Spiel OpenGL, 'An Fenster anpassen'\n"
            "mit erhaltenem 4:3-Bildverhaeltnis, Grafikfilter anfangs AUS fuer\n"
            "scharfe Schrift. Bei gewuenschter weicherer Grafik Filter EIN.\n"
            "Das Seitenverhaeltnis nicht auf 16:9 verzerren. 320x200-Modi\n"
            "koennen von Seitenverhaeltniskorrektur profitieren; bei 640x480\n"
            "ist das Bild bereits 4:3. Soundgeraet auf 'Standard' belassen.\n"
            "Die ScummVM-Spielstaende bleiben am gewohnten Speicherort und\n"
            "konnten mit dieser deutschen Fassung bereits geladen werden.\n"
            "DOSBox/GOG-Spielstaende werden NICHT automatisch uebernommen.\n"
            "Dieses Programm ist eine inoffizielle Fanuebersetzung, kein\n"
            "offizieller Bestandteil des ScummVM-Projekts.\n"
        )
        (staged / "SCUMMVM_DEUTSCH_HINWEISE.txt").write_text(readme, encoding="utf-8")
        summary["dry_run"] = False
        summary["bytes_copied"] = copied
        (staged / "ScummVM_Deutsch_Pruefbericht.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        require(not target.exists(), "Ziel entstand während der Kopie; niemals überschreiben")
        staged.replace(target)
        return summary
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Harvester GOG Deutsch -> ScummVM 2026.4.0")
    parser.add_argument("--english", type=Path, required=True, help="Unveränderter englischer GOG-Spielordner")
    parser.add_argument("--german", type=Path, required=True, help="Bestehender getesteter Harvester GOG Deutsch Ordner")
    parser.add_argument("--target-parent", type=Path, required=True, help="Neuer Ausgabe-Oberordner")
    parser.add_argument("--mode", choices=MODES, default="10px")
    parser.add_argument("--execute", action="store_true", help="Nach vollständigem Read-only-Preflight kopieren")
    args = parser.parse_args()
    try:
        report = convert(args.english, args.german, args.target_parent, args.mode, args.execute)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print("VORPRÜFUNG PASS" if not args.execute else "SCUMMVM-DATENKOPIE ERFOLGREICH ERSTELLT")
        return 0
    except (OSError, ValueError, ET.ParseError) as e:
        print("SCUMMVM-KONVERTIERUNG ABGEBROCHEN: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
