#!/usr/bin/env python3
"""Harvester: PRIVATE, ISOLATED FIX2 CORE-ONLY installer test from a delta ZIP.

This is NOT the RC3b installer and NOT a releasable patch. It performs a
read-only verification of the original GOG CDs, 191 executable edits, all 20
bundle variants / 48 usages and 18 target hashes; then materializes the
18 private FIX2 target files in a short-lived staging folder.

With --execute-core-test it runs the EXACT pinned existing FIX2 core patcher
against a NEW, clearly distinct destination. It never runs the video renderer,
never touches an existing RC3b installation, and is not a 3-launcher test.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

import originalvergleich_gog as audit
import unified_delta_bundle as bundle
from runtime.harvester_iso import hash_file

TEST_TARGET_NAME = "Harvester GOG Deutsch"  # Isolated private player candidate; legacy branches untouched.
CORE_EXE = "Harvester_Deutsch_Patcher.exe"
CORE_SHA256 = "9b8fada91a55db9c069309deb69137277cc951b154781523f7571c704f7a62e0"
TARGET_EXE_SHA256 = "c461e05414a38b11c7e7d27c1ad47df823e2bdb87f2087639281cbc39cdb32b2"
CORE_CHECK_FILES = ("HARVEST.EXE", *audit.DISC_NAMES)
MAX_PRIVATE_ZIP_BYTES = 20 * 1024 * 1024


class ShadowInstallerError(ValueError):
    pass


def nested(ancestor: Path, child: Path) -> bool:
    try:
        return os.path.commonpath((str(ancestor), str(child))) == str(ancestor)
    except ValueError:
        return False


def verify_paths(source: Path, bundle_path: Path, target_parent: Path | None,
                 reference: Path | None) -> tuple[Path, Path, Path | None, Path | None]:
    for item in (source, bundle_path, target_parent, reference):
        if item is not None and item.is_symlink():
            raise ShadowInstallerError("Symbolische Pfade für Spiel/Paket/Ziel nicht gestattet")
    src, pack = source.expanduser().resolve(), bundle_path.expanduser().resolve()
    if not src.is_dir() or not pack.is_file() or not 0 < pack.stat().st_size <= MAX_PRIVATE_ZIP_BYTES:
        raise ShadowInstallerError("Englischer GOG-Originalordner oder privates Delta-ZIP fehlt")
    if nested(src, audit.REPO.resolve()) or nested(audit.REPO.resolve(), src):
        raise ShadowInstallerError("Original-GOG-Verzeichnis darf kein Repository-Pfad sein")
    target = None
    if target_parent is not None:
        parent = target_parent.expanduser().resolve()
        if not parent.is_dir():
            raise ShadowInstallerError("Der Elternordner der neuen Spielkopie muss bereits existieren")
        target = parent / TEST_TARGET_NAME
        if target.exists() or target.is_symlink():
            raise ShadowInstallerError("Zielordner existiert bereits und wird nicht überschrieben: " + target.name)
        if (nested(src, target) or nested(target, src)
                or nested(audit.REPO.resolve(), target)
                or nested(target, audit.REPO.resolve())):
            raise ShadowInstallerError("Originalspiel, Installationsziel und Programmdaten müssen getrennt sein")
        if nested(target, pack):
            raise ShadowInstallerError("Installationsdaten dürfen nicht im Zielordner liegen")
    rc3b = None
    if reference is not None:
        rc3b = reference.expanduser().resolve()
        if (not rc3b.is_dir() or rc3b == src
                or (target and (nested(rc3b, target) or nested(target, rc3b)))):
            raise ShadowInstallerError(
                "Vergleichsordner und neues Installationsziel müssen völlig getrennt bleiben"
            )
        for name in CORE_CHECK_FILES:
            f = rc3b / name
            if f.is_symlink() or not f.is_file():
                raise ShadowInstallerError("RC3b-Referenzdatei fehlt: " + name)
    return src, pack, target, rc3b


def restore_assets_from_private_zip(source: Path, zip_bytes: bytes, stage_payload: Path,
                                    expected_rules_sha: str = bundle.PINNED_RULES_SHA,
                                    check_exe: bool = True) -> tuple[dict, dict[str, str]]:
    """Verify full bundle BEFORE staging and write only 18 verified targets to stage.

    Does not read payload/Daten source bytes from the developer repository.
    Only the ZIP and exact original GOG resource spans supply the data.
    """
    if stage_payload.exists() or stage_payload.is_symlink():
        raise ShadowInstallerError("Staging-Payload existiert bereits")
    if nested(source.resolve(), stage_payload.resolve()) or nested(
            audit.REPO.resolve(), stage_payload.resolve()):
        raise ShadowInstallerError("Staging darf nicht in Quelle oder GitHub-Projekt liegen")

    proof = bundle.verify_bundle_bytes(source, zip_bytes,
                                       expected_rules_sha=expected_rules_sha,
                                       check_exe=check_exe)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as archive:
        xml = archive.read(bundle.RULES_NAME)
        document = json.loads(archive.read(bundle.MANIFEST_NAME))
        rules, sizes = bundle._trusted_rules(xml, expected_rules_sha)
        rows = document["image_uses"]
        variants = {v["id"]: v for v in document["variants"]}
        mapping = {(m["disc"], m["role"], m["path"]): m for m in rows}
        original_uses, _ = bundle.collect_original_uses(source, rules, sizes,
                                                        check_exe=False)
        staged = {}
        for usage in original_uses:
            asset = usage["asset"]
            if asset in staged:
                continue
            key = (usage["disc"], usage["role"], usage["path"])
            node = mapping[key]
            v = variants[node["variant"]]
            packed = archive.read(v["member"])
            if bundle.sha(packed) != v["packed_sha256"] or len(packed) != v["packed_bytes"]:
                raise ShadowInstallerError("Delta-ZIP hat sich während des Stagings geändert")
            delta = bundle._unpack(packed, v["unpacked_bytes"])
            rebuilt = bundle._restore(usage["source"], delta, v["codec"])
            if len(rebuilt) != sizes[asset] or bundle.sha(rebuilt) != asset[:-4]:
                raise ShadowInstallerError("Deutsche FIX2-Zielressource hat falsche Größe/SHA-256")
            staged[asset] = rebuilt
        if len(staged) != bundle.EXPECTED_ASSETS or set(staged) != set(sizes):
            raise ShadowInstallerError("Nicht alle 18 deutschen Ressourcen rekonstruiert")

    stage_payload.mkdir(parents=True, exist_ok=False)
    (stage_payload / "Daten").mkdir()
    (stage_payload / "Regeln.xml").write_bytes(xml)
    produced = {}
    for filename, data in sorted(staged.items()):
        dst = stage_payload / "Daten" / filename
        with dst.open("xb") as fd:
            fd.write(data)
        if hash_file(dst) != filename[:-4] or dst.stat().st_size != sizes[filename]:
            raise ShadowInstallerError("Staged FIX2-Datei nicht mehr byteidentisch")
        produced[filename] = filename[:-4]
    if hash_file(stage_payload / "Regeln.xml") != expected_rules_sha:
        raise ShadowInstallerError("Staged FIX2-Regeln stimmen nicht")
    return proof, produced


def check_verified_core(core_path: Path) -> None:
    if (core_path.is_symlink() or not core_path.is_file()
            or hash_file(core_path) != CORE_SHA256):
        raise ShadowInstallerError("Unveränderter FIX2-Basispachter nicht SHA-256-verifiziert")


def check_disk_reserve(source: Path, target: Path) -> None:
    # Conservative core-only estimate: the three original ISO images may be
    # copied and patched into a new target. Keep a separate 2 GiB reserve.
    discs = sum((source / name).stat().st_size for name in audit.DISC_NAMES)
    required = 2 * discs + 2 * 1024**3
    if shutil.disk_usage(target.parent).free < required:
        raise ShadowInstallerError(
            "Zu wenig freier Speicherplatz für getrennten Core-Test "
            "(mindestens 2x originale CD-Größe + 2 GiB Reserve benötigt)"
        )


def core_only_install(source: Path, private_zip: bytes, target: Path,
                      core_path: Path, reference: Path | None = None) -> dict:
    if os.name != "nt":
        raise ShadowInstallerError("Die echte FIX2-Testinstallation erfordert Windows")
    check_verified_core(core_path)
    if target.exists() or target.is_symlink():
        raise ShadowInstallerError("Vorhandene deutsche Spielkopien werden nie überschrieben")
    if target.name != TEST_TARGET_NAME:
        raise ShadowInstallerError("Der Name des Installationszielordners stimmt nicht")
    originals = {name: hash_file(source / name) for name in CORE_CHECK_FILES}
    # The exact original source hashes and EXE edit targets are verified
    # before any proprietary core executable can be started.
    with tempfile.TemporaryDirectory(prefix="HarvesterDeltaCore_PRIVATE_") as tmp:
        stage = Path(tmp)
        payload = stage / "payload"
        if (nested(source.resolve(), stage.resolve())
                or nested(audit.REPO.resolve(), stage.resolve())
                or nested(stage.resolve(), target.resolve())
                or nested(target.resolve(), stage.resolve())):
            raise ShadowInstallerError("Temporäre Ressourcenablage nicht sicher getrennt")
        proof, produced = restore_assets_from_private_zip(source, private_zip, payload)
        staged_core = payload / CORE_EXE
        shutil.copy2(core_path, staged_core)
        check_verified_core(staged_core)
        if not target.parent.is_dir() or target.exists():
            raise ShadowInstallerError("Neues Installationsziel nicht mehr verfügbar")
        # This is the SAME command as the tested RC3b base installer, but its
        # payload has just been materialized from the private delta ZIP.
        try:
            subprocess.run([str(staged_core), "--source", str(source),
                            "--target", str(target)], cwd=str(payload), check=True)
        finally:
            # Check the known original CD/EXE hashes even if the subprocess
            # fails. The staging temp folder is removed by the context manager.
            after = {name: hash_file(source / name) for name in CORE_CHECK_FILES}
            if originals != after:
                raise ShadowInstallerError("WARNUNG: Original-GOG-CDs/EXE wurden verändert!")
    if not (target / "Deutsch_Pruefnachweis.xml").is_file():
        raise ShadowInstallerError("FIX2-Installationsnachweis fehlt im neuen Zielordner")
    if hash_file(target / "HARVEST.EXE") != TARGET_EXE_SHA256:
        raise ShadowInstallerError("Neue HARVEST.EXE stimmt nicht mit FIX2-Zielhash")
    if not all((target / name).is_file() for name in audit.DISC_NAMES):
        raise ShadowInstallerError("Nicht alle drei neuen CD-Dateien wurden hergestellt")
    proof_hash = hash_file(target / "Deutsch_Pruefnachweis.xml")
    dest_hashes = {n: hash_file(target / n) for n in CORE_CHECK_FILES}
    comparison = {}
    if reference is not None:
        for name in CORE_CHECK_FILES:
            file = reference / name
            if file.is_symlink() or not file.is_file():
                raise ShadowInstallerError("RC3b-Vergleichsdatei fehlt oder ist verlinkt: " + name)
            comparison[name] = hash_file(file) == dest_hashes[name]
        if not all(comparison.values()):
            raise ShadowInstallerError(
                "Der neue FIX2-Basistest unterscheidet sich von der getesteten RC3b-Referenz"
            )
    return {
        "schema": "harvester-private-delta-shadow-core-test-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "real_core_test": True,
        "is_full_rc3b_test": False,
        "video_modes_created_by_this_test": 0,
        "bundle_variants_verified": proof["reconstructed_unique_pairs"],
        "bundle_iso_xfile_uses_verified": proof["verified_iso_and_xfile_uses"],
        "reconstructed_assets": len(produced),
        "original_source_sha256_unchanged": True,
        "patched_exe_sha256": dest_hashes["HARVEST.EXE"],
        "patched_cd_sha256": {k: dest_hashes[k] for k in audit.DISC_NAMES},
        "fix2_proof_sha256": proof_hash,
        "optional_reference_comparison": comparison,
        "contains_game_bytes_or_user_paths": False,
        "existing_rc3b_modified": False,
        "legal_clearance": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PRIVATER Harvester-Delta-Testinstaller: nur FIX2-Core, NICHT RC3b"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True,
                        help="NUR lokales privates Harvester_DeltaBundle_PRIVAT_*.zip")
    parser.add_argument("--target-parent", type=Path)
    parser.add_argument("--reference-rc3b", type=Path,
                        help="Optionaler bisher getesteter RC3b-Spielordner (nur lesend)")
    parser.add_argument("--execute-core-test", action="store_true",
                        help="Nur mit ausdrücklicher Angabe eine NEUE Testspielkopie erstellen")
    parser.add_argument("--output-dir", type=Path,
                        default=Path.home() / "Documents" / "Harvester_DeltaCore_Testberichte")
    args = parser.parse_args()
    try:
        if args.execute_core_test and args.target_parent is None:
            parser.error("Für die getrennte Testinstallation --target-parent angeben")
        src, path, target, reference = verify_paths(
            args.source, args.bundle, args.target_parent, args.reference_rc3b
        )
        private_zip = path.read_bytes()
        print("Prüfe ausschließlich den privaten Delta-Bundle-Inhalt im RAM ...", flush=True)
        evidence = bundle.verify_bundle_bytes(src, private_zip)
        print("PASS: 20/20 Quellpaare, 48/48 Originalverwendungen, 18/18 Ziele.")
        if not args.execute_core_test:
            print("NUR LESEN. Kein Testziel angelegt. Für Core-Test --execute-core-test angeben.")
            return 0
        check_verified_core(audit.REPO / "payload" / CORE_EXE)
        check_disk_reserve(src, target)
        # Validate the report output path before starting any native patcher.
        folder = audit.valid_report_directory(args.output_dir, src)
        if nested(target.resolve(), folder.resolve()):
            raise ShadowInstallerError("Technischer Bericht darf nicht im Testspielziel liegen")
        if reference is not None and nested(reference.resolve(), folder.resolve()):
            raise ShadowInstallerError("Technischer Bericht darf nicht in RC3b liegen")
        if reference is not None:
            print("Vergleiche die neue FIX2-Basiskopie nach dem Test nur lesend mit RC3b.")
        print("Erstelle nur die neue getrennte Spielkopie: " + str(target), flush=True)
        report = core_only_install(src, private_zip, target,
                                   audit.REPO / "payload" / CORE_EXE, reference)
        folder.mkdir(parents=True, exist_ok=True)
        name = ("Harvester_DeltaCore_TEST_"
                + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json")
        with (folder / name).open("x", encoding="utf-8") as fd:
            json.dump(report, fd, ensure_ascii=False, indent=2)
            fd.write("\n")
        print("FIX2 CORE-TEST PASS. Nur neues Testspiel erstellt; keine VideoUT-Varianten.")
        print("Nur diese JSON-Datei im Chat teilen:", folder / name)
        print("Deine funktionierende RC3b-Version bitte unverändert behalten.")
        return 0
    except (ShadowInstallerError, bundle.BundleError, audit.AuditError,
            OSError, ValueError, KeyError, zipfile.BadZipFile,
            subprocess.CalledProcessError) as exc:
        print("PRIVATER DELTA CORE-TEST ABGEBROCHEN:", exc, file=sys.stderr)
        print("Kein bestehendes RC3b-Spiel, keine Original-GOG-CDs ändern.")
        print("Eventuell neu entstandene Delta-Testkopie nicht starten, bis sie geprüft ist.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
