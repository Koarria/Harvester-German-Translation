#!/usr/bin/env python3
"""Harvester: PRIVATE, isolated 66-video subtitle add-on for VERIFIED delta core.

Uses the existing, unchanged installer.py renderer, ISO writing and launchers.
Only upgrades a precisely SHA-pinned, distinct "Harvester GOG Deutsch Delta Test"
core installation, NEVER the working RC3b installation or original English GOG.

The new full-video test is deliberately separated from the already PASSED
Delta Core test. No proprietary data uploaded to GitHub/CI; no public release.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET

import delta_core_shadow_installer as shadow
import delta_core_proof as core_proof
import installer as rc3
import originalvergleich_gog as audit
from runtime.harvester_iso import hash_file
from runtime.fst_subtitles import load_srt

SCHEMA = "harvester-private-delta-video-addon-test-v1"
NAME = shadow.TEST_TARGET_NAME
STATE_TAG = "HARVESTER_PRIVATE_DELTA_VIDEO_ADDON_V1"
MARKER = "DELTA_VIDEO_INSTALLATION_UNVOLLSTAENDIG.txt"
WORKDIR = "_DELTA_VIDEO_ARBEITSVERZEICHNIS"
EXPECTED_BASE = {
    "HARVEST.EXE": shadow.TARGET_EXE_SHA256,
    "HARVEST.DAT": "456526160cc43f014503c4062b8875457f6176b0aebdc00623f73e9c2ab8c533",
    "HARVEST3.DAT": "1d4060fba0131d6af1bb35c2f54c221b840e85fa4e02030ad06f2e69bca53859",
    "HARVEST4.DAT": "53ca6234f41c962536206bf45fadcde403633e2b35b06a80b02be63513075c62",
}
MODES = rc3.MODES
DISC_NAMES = rc3.DISCS
STARTERS = (
    "Harvester_Deutsch_ohne_Videountertitel.cmd",
    "Harvester_Deutsch_mit_10px_Videountertiteln.cmd",
    "Harvester_Deutsch_mit_11px_Videountertiteln.cmd",
)
CONFIGS = (
    "dosbox_harvester_single_ohne_VideoUT.conf",
    "dosbox_harvester_single_10px.conf",
    "dosbox_harvester_single_11px.conf",
)
OUTPUT_CDS = tuple(f"VideoUntertitel/{mode}/{cd}" for mode in MODES for cd in DISC_NAMES)
VIDEO_FILES = STARTERS + CONFIGS + OUTPUT_CDS
VIDEO_MANIFEST = "VideoManifest.xml"


class DeltaVideoError(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_video_inputs(repo: Path) -> list[dict]:
    """RC3b video-only preflight: 196 mapping rows/66 films/132 subtitle uses.

    In contrast to rc3.payload_preflight(), deliberately never reads/needs the
    18 full payload/Daten/*.bin targets; those came from our private delta ZIP.
    The renderer/patcher/launcher implementations themselves remain unchanged.
    """
    manifest = repo / "payload" / VIDEO_MANIFEST
    if not manifest.is_file() or manifest.is_symlink() or hash_file(manifest) != rc3.MANIFEST_HASH:
        raise DeltaVideoError("VideoManifest.xml fehlt oder SHA-256 ist falsch")
    xml = ET.parse(manifest).getroot()
    if xml.tag != "HarvesterVideoManifest" or xml.get("version") != "1" or xml.get("ready") != "release":
        raise DeltaVideoError("Unbekanntes/nicht freigegebenes Video-Manifest")
    entries = [dict(n.attrib) for n in xml.findall("Fst")]
    if len(entries) != 196:
        raise DeltaVideoError("Es sind genau 196 Video-Zuordnungen erforderlich")
    by_key = set()
    films: dict[str, set[str]] = {}
    by_mode = {m: set() for m in MODES}
    source_by_location = {}
    for row in entries:
        try:
            mode, disc, path, film = (row[n] for n in ("mode", "cd", "path", "film_id"))
            if (mode not in MODES or disc not in DISC_NAMES
                    or not re.fullmatch(r"GRAPHIC/FST/[A-Z0-9]+\.FST", path)
                    or not re.fullmatch(r"[A-Z0-9_]+", film)):
                raise DeltaVideoError("Ungültiger Video-/Modus-/CD-Eintrag")
            for key in ("source_sha256", "target_sha256", "patch_sha256"):
                if not re.fullmatch(r"[0-9a-f]{64}", row[key]):
                    raise DeltaVideoError("Ungültiger FST-SHA-256-Wert")
        except KeyError as exc:
            raise DeltaVideoError("Videomanifest-Zuordnung ohne Pflichtfeld") from exc
        name = (mode, disc, path)
        if name in by_key:
            raise DeltaVideoError("Doppelte Video-CD-Position")
        by_key.add(name)
        films.setdefault(film, set()).add(row["source_sha256"])
        by_mode[mode].add(film)
        source_key = (disc, path)
        if source_key in source_by_location and source_by_location[source_key] != row["source_sha256"]:
            raise DeltaVideoError("Quellvideo-SHA zwischen Video-Modi unterschiedlich")
        source_by_location[source_key] = row["source_sha256"]
    if len(films) != 66 or any(len(s) != 1 for s in films.values()):
        raise DeltaVideoError("Nicht genau 66 eindeutige Originalfilme")
    if by_mode["10px"] != by_mode["11px"] or len(by_mode["10px"]) != 66:
        raise DeltaVideoError("10-px und 11-px-Filmlisten unterschiedlich")
    for mode in MODES:
        if Counter(r["cd"] for r in entries if r["mode"] == mode) != Counter({
            "HARVEST.DAT":45, "HARVEST3.DAT":44, "HARVEST4.DAT":9
        }):
            raise DeltaVideoError("Video-CD-Vorkommen fehlen für " + mode)
        for film in films:
            srt = rc3.subtitle_file(repo / "payload", film, mode)
            if srt.is_symlink() or not srt.is_file() or not load_srt(srt):
                raise DeltaVideoError("Unvollständige SRT-Untertitel: " + film + "/" + mode)
    return entries


def validate_source_and_test_copy(source: Path, target: Path, repo: Path,
                                  reference: Path | None = None) -> tuple[Path, Path, Path | None]:
    """Read-only prerequisites and collision protection, including old RC3b."""
    if any(p.is_symlink() for p in (source, target, repo)
           if p is not None) or (reference is not None and reference.is_symlink()):
        raise DeltaVideoError("Symbolische Links für Original, Ziel oder Vergleichsordner sind nicht zulässig")
    src, dst, package = source.expanduser().resolve(), target.expanduser().resolve(), repo.resolve()
    if dst.name != NAME or not dst.is_dir():
        raise DeltaVideoError("Nur eine zuvor geprüfte deutsche Basisinstallation kann fortgesetzt werden")
    rc3.safe_separate(src, dst, package, allow_resume=True)
    if shadow.nested(dst, package) or shadow.nested(package, dst):
        raise DeltaVideoError("Installationsziel und Programmdateien müssen getrennt sein")
    ref = None
    if reference is not None:
        ref = reference.expanduser().resolve()
        if (not ref.is_dir() or ref == dst or
                shadow.nested(ref, dst) or shadow.nested(dst, ref) or
                shadow.nested(src, ref) or shadow.nested(ref, src)):
            raise DeltaVideoError("Vergleichsordner darf sich nicht mit Original oder Ziel überschneiden")
        for file in (*EXPECTED_BASE, *VIDEO_FILES):
            p = ref / file
            if p.is_symlink() or not p.is_file():
                raise DeltaVideoError("RC3b-Referenzdatei fehlt: " + file)
    for name, expected in EXPECTED_BASE.items():
        p = dst / name
        if p.is_symlink() or not p.is_file() or hash_file(p) != expected:
            raise DeltaVideoError("SHA-256 der deutschen Basisinstallation stimmt nicht: " + name)
        if ref is not None and hash_file(ref / name) != expected:
            raise DeltaVideoError("RC3b-Referenzbasis ist nicht identisch: " + name)
    proof = dst / "Deutsch_Pruefnachweis.xml"
    if proof.is_symlink() or not proof.is_file():
        raise DeltaVideoError("FIX2-Pruefnachweis fehlt im Delta-Core")
    if ET.parse(proof).getroot().tag != "HarvesterDeutschInstallation":
        raise DeltaVideoError("Unbekanntes FIX2-Nachweisformat")
    return src, dst, ref


def verify_original_source(source: Path, repo: Path) -> dict:
    """Strict manifest/CD and EXE checks, without full German FIX2 payload."""
    xml = repo / "payload" / "Regeln.xml"
    if xml.is_symlink() or not xml.is_file() or hash_file(xml) != audit.EXPECTED_RULES_SHA256:
        raise DeltaVideoError("Unveränderte FIX2-Regeln fehlen")
    rules = ET.parse(xml).getroot()
    if rules.tag != "HarvesterPatch" or len(rules.findall("./Image")) != 3:
        raise DeltaVideoError("Ungültige CD-Hashregeln")
    hashes = {}
    for disc in rules.findall("./Image"):
        name = disc.get("name")
        if name not in DISC_NAMES or name in hashes:
            raise DeltaVideoError("Doppelte/unbekannte Quell-CD")
        file = source / name
        if file.is_symlink() or hash_file(file) != disc.get("sha"):
            raise DeltaVideoError("Englische GOG-Original-CD wurde verändert: " + str(name))
        hashes[name] = disc.get("sha")
    if set(hashes) != set(DISC_NAMES):
        raise DeltaVideoError("Nicht alle drei Original-CDs gefunden")
    exe = rules.find("./Executable")
    if exe is None or audit.audit_executable(source, exe)["status"] != "VERIFIED":
        raise DeltaVideoError("Englische Original-EXE/191 Edits nicht verifiziert")
    hashes["HARVEST.EXE"] = hash_file(source / "HARVEST.EXE")
    return hashes


def state_file(target: Path) -> Path:
    return target / WORKDIR / "state.json"


def video_marker(target: Path) -> Path:
    return target / MARKER


def initialize_or_resume(source: Path, target: Path, repo: Path,
                         reference: Path | None = None) -> tuple[Path, bool]:
    """Refuse unknown previously modified core; safe checkpointed reruns."""
    marker = video_marker(target)
    work = target / WORKDIR
    if work.is_symlink() or marker.is_symlink() or state_file(target).is_symlink():
        raise DeltaVideoError("Verlinktes Video-Arbeitsverzeichnis nicht erlaubt")
    if marker.exists():
        if not work.is_dir() or not state_file(target).is_file():
            raise DeltaVideoError("Unbekannte unvollständige Video-Testinstallation")
        data = json.loads(state_file(target).read_text("utf-8"))
        expected = {"tag": STATE_TAG, "source": str(source),
                    "target": str(target), "manifest_sha256": rc3.MANIFEST_HASH}
        if any(data.get(k) != v for k, v in expected.items()):
            raise DeltaVideoError("Unbekannter/inkonsistenter Video-Fortsetzungsstand")
        initial_sha = data.get("initial_proof_sha256")
        if not isinstance(initial_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", initial_sha):
            raise DeltaVideoError("Ungültiger initialer Proof-SHA im eigenen Video-Checkpoint")
        # A normal partial render leaves the core XML unchanged. Near the end,
        # update_proof() legitimately rewrites XML before the JSON report is
        # committed; that later XML must independently pass semantic verification.
        try:
            current_sha = core_proof.verify_core_proof(
                source, target, allow_video_progress=True)
        except core_proof.ProofError as exc:
            raise DeltaVideoError(str(exc)) from exc
        if current_sha != initial_sha:
            top = ET.parse(target / "Deutsch_Pruefnachweis.xml").getroot()
            if top.attrib.get("video_untertitel_release") != core_proof.VIDEO_RELEASE:
                raise DeltaVideoError("Delta-Pruefnachweis unerwartet verändert")
        return work, True
    if work.exists() or work.is_symlink() or (target / "VideoUntertitel").exists():
        raise DeltaVideoError("Video-Ausgaben existieren ohne eigenen Fortsetzungsnachweis")
    if any((target / name).exists() for name in STARTERS+CONFIGS):
        raise DeltaVideoError("Startdateien liegen bereits ohne gültigen Wiederaufnahmenachweis vor")
    # The native patcher embeds original/target paths in this XML.
    # Its whole-file SHA cannot be fixed across different target directories.
    # Strictly verify the actual per-file hashes, source/target/rules binding
    # and complete core inventory instead.
    try:
        actual_proof_sha = core_proof.verify_core_proof(source, target)
    except core_proof.ProofError as exc:
        raise DeltaVideoError(str(exc)) from exc
    work.mkdir(exist_ok=False)
    rc3.write_json_atomic(
        state_file(target), {
            "tag": STATE_TAG, "source": str(source),
            "target": str(target), "manifest_sha256": rc3.MANIFEST_HASH,
            "initial_proof_sha256": actual_proof_sha,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    marker.write_text(
        "HARVESTER-INSTALLATION UNVOLLSTÄNDIG: Nicht spielen und keine Startdateien ausführen.\n",
        encoding="utf-8"
    )
    return work, False


def compare_video_reference(target: Path, reference: Path | None) -> dict[str, bool]:
    """Optional comparison with the previous proven full RC3b, strictly read-only."""
    if reference is None:
        return {}
    result = {}
    for file in VIDEO_FILES:
        fresh, known = target / file, reference / file
        if fresh.is_symlink() or not fresh.is_file() or known.is_symlink() or not known.is_file():
            raise DeltaVideoError("Fehlende Video-Datei im RC3b-Direktvergleich: " + file)
        result[file] = hash_file(fresh) == hash_file(known)
    if not all(result.values()):
        raise DeltaVideoError("Neue Videountertitel-/Starter-Dateien unterscheiden sich von RC3b")
    return result


def run_video_addon(source: Path, target: Path, repo: Path, entries: list[dict],
                    reference: Path | None = None, workers: int | None = None) -> dict:
    """Perform 132 renders + 6 video ISOs + 3 launchers on a known delta test."""
    if os.name != "nt":
        raise DeltaVideoError("Die Videountertitel-Installation erfordert Windows")
    if workers is not None and not 1 <= workers <= 4:
        raise DeltaVideoError("Maximal 1–4 Videoprozesse zulässig")
    source, target, reference = validate_source_and_test_copy(source, target, repo, reference)
    original_before = verify_original_source(source, repo)
    if (shadow.nested(target, source) or shadow.nested(source, target)
            or shadow.nested(repo.resolve(), target) or shadow.nested(target, repo.resolve())):
        raise DeltaVideoError("Quell-/Zieltrennung für neue Videos nicht gewährleistet")
    rc3.free_space_check(source, target)
    base_before = {name: hash_file(target / name) for name in EXPECTED_BASE}
    temp, resumed = initialize_or_resume(source, target, repo, reference)
    marker = video_marker(target)
    rc3.log("Basisprüfung PASS: Spiel-EXE und drei CD-Dateien stimmen mit den geprüften SHA-256-Werten überein.")
    completed = False
    try:
        films = rc3.extract_film_sources(target, entries, temp)
        reference_hashes = {row["film_id"]: row["source_sha256"] for row in entries}
        reports = rc3.render_all(films, repo / "payload", temp, reference_hashes,
                                 requested_workers=workers, log=rc3.log)
        if len(films) != 66 or len(reports) != 132:
            raise DeltaVideoError("Video-Rendering nicht vollständig (66/132)")
        built = []
        cd_hashes = {}
        for mode in MODES:
            for cd in DISC_NAMES:
                items = sorted(
                    (row for row in entries if row["mode"] == mode and row["cd"] == cd),
                    key=lambda row: row["path"]
                )
                out, h, _ = rc3.patch_cd_or_reuse(
                    target, temp, mode, cd, items, reports
                )
                built.append(out)
                cd_hashes[out] = h
        if len(built) != 6 or any(not x.is_file() for x in built):
            raise DeltaVideoError("Nicht alle sechs Untertitel-CDs erstellt")
        generated = rc3.create_launchers(target)
        if len(generated) != 6:
            raise DeltaVideoError("Nicht genau drei Starter und drei DOSBox-Konfigurationen")
        reference_checks = compare_video_reference(target, reference)
        rc3.update_proof(target, generated + built, reports,
                         precalculated_hashes=cd_hashes)
        guide = rc3.write_start_guide(target)
        if not guide.is_file() or any(not (target / n).is_file() for n in VIDEO_FILES):
            raise DeltaVideoError("Spielstart-Anleitung oder Startdateien fehlen")
        base_after = {name: hash_file(target / name) for name in EXPECTED_BASE}
        if base_after != base_before or base_after != EXPECTED_BASE:
            raise DeltaVideoError("FIX2-Basis-CDs oder EXE wurden während der Videoarbeit verändert")
        original_after = verify_original_source(source, repo)
        if original_after != original_before:
            raise DeltaVideoError("Original-GOG-Dateien wurden bei Videopatch geändert")
        generated_hashes = {file: hash_file(target / file) for file in VIDEO_FILES}
        proof_hash = hash_file(target / "Deutsch_Pruefnachweis.xml")
        output = {
            "schema": SCHEMA,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "real_video_addon_test": True,
            "is_new_full_delta_installer_from_scratch": False,
            "start_from_verified_delta_core": True,
            "source_gog_original_sha256_unchanged": True,
            "delta_core_base_sha256_unchanged": True,
            "video_original_sources": len(films),
            "subtitle_rendered_variants": len(reports),
            "video_iso_image_count": len(built),
            "launcher_count": 3,
            "launcher_config_count": 3,
            "manifest_fst_locations": len(entries),
            "files_sha256": generated_hashes,
            "sha256_equal_to_existing_rc3b": reference_checks,
            "patched_exe_sha256": base_after["HARVEST.EXE"],
            "patched_cd_sha256": {cd: base_after[cd] for cd in DISC_NAMES},
            "final_fix2_proof_sha256": proof_hash,
            "existing_rc3b_modified": False,
            "contains_original_or_translated_game_bytes": False,
            "contains_local_user_paths": False,
            "game_saves_modified_by_addon": False,
            "in_game_test_completed": False,
            "legal_clearance": False,
        }
        completed = True
        return output
    finally:
        if not completed:
            rc3.log("INSTALLATION UNVOLLSTÄNDIG. Nicht starten. Der geprüfte Arbeitsstand bleibt erhalten.")


def main() -> int:
    parser = argparse.ArgumentParser(description=(
        "Privater Harvester-Delta-Video-Test: nur separat geprüfte Delta-Core-Kopie."
    ))
    parser.add_argument("--source", type=Path, required=True,
                        help="Unverändertes englisches GOG-Original")
    parser.add_argument("--target", type=Path, required=True,
                        help="Bereits getesteter Delta-Core-Spielordner")
    parser.add_argument("--reference-rc3b", type=Path,
                        help="Bestehender funktionierender RC3b-Spielordner (nur lesend)")
    parser.add_argument("--workers", type=int, choices=range(1, 5),
                        help="Optional höchstens 1 bis 4 parallele Filmprozesse")
    parser.add_argument("--execute-video-test", action="store_true",
                        help="Nur mit explizitem Flag bestehende isolierte Delta-Testkopie erweitern")
    parser.add_argument("--output-dir", type=Path, default=(
        Path.home() / "Documents" / "Harvester_DeltaVideo_Testberichte"
    ))
    args = parser.parse_args()
    try:
        repo = audit.REPO
        inputs = validate_video_inputs(repo)
        if args.target.is_symlink() or args.source.is_symlink():
            raise DeltaVideoError("Verlinkter Original-/Testordner verweigert")
        source, target, reference = validate_source_and_test_copy(
            args.source, args.target, repo, args.reference_rc3b
        )
        verify_original_source(source, repo)
        if not args.execute_video_test:
            print("VIDEO-PREFLIGHT PASS: 66 Filme/132 SRT-Varianten/196 ISO-Ziele; Delta-Core-Basis 4/4 PASS.")
            print("Kein Spielordner wurde verändert. Für Video-Test explizit --execute-video-test.")
            return 0
        folder = audit.valid_report_directory(args.output_dir, source)
        if any(shadow.nested(x, folder.resolve()) for x in (target, repo.resolve())):
            raise DeltaVideoError("JSON-Bericht darf weder im Spieltest noch Repository stehen")
        if reference is not None and shadow.nested(reference, folder.resolve()):
            raise DeltaVideoError("Bericht darf nicht in RC3b gespeichert werden")
        report = run_video_addon(source, target, repo, inputs, reference, args.workers)
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / ("Harvester_DeltaVideo_TEST_" +
                        datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        with out.open("x", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            f.write("\n")
        # Only declare the video installation complete after the JSON report
        # has been safely written; failed report output leaves a resumable marker.
        video_marker(target).unlink()
        shutil.rmtree(target / WORKDIR, ignore_errors=True)
        print("DELTA-VIDEO-FULL-TEST PASS: 66 Filme, 132 Varianten, 6 CDs, 3 Startmodi.")
        if report["sha256_equal_to_existing_rc3b"]:
            print("Video-/Starter-Dateien mit der bisherigen RC3b per SHA-256 verglichen: PASS.")
        print("Nur diesen technischen JSON-Bericht hochladen:", out)
        print("Ingame-Tests und Rechtefreigabe noch offen.")
        return 0
    except (DeltaVideoError, audit.AuditError, OSError, ValueError,
            ET.ParseError, KeyError, json.JSONDecodeError) as exc:
        print("PRIVATER DELTA-VIDEO-TEST ABGEBROCHEN:", exc, file=sys.stderr)
        print("Vorhandene RC3b-Spielkopie/englisches Original nicht verändern. "
              "Eine Delta-Testkopie mit Video-Unvollständig-Marker nicht starten.")
        return 2


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
