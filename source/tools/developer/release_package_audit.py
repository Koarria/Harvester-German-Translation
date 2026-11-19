"""Strict local release ZIP audit. This source is never shipped to players.

The release ZIP must contain precisely the setup EXE, German readme and its
SHA-256 checksum; never source code, tests, game CDs, developer reports or ZIPs.
Works with synthetic fake EXEs in GitHub CI and locally after real EXE build.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
import zipfile

EXE_NAME = "Harvester_GOG_Deutsch_Setup.exe"
README_NAME = "LIES_MICH.txt"
HASH_NAME = "SHA256SUMS.txt"
ZIP_NAME = "Harvester_GOG_Deutsch_v1.0.0.zip"
ALLOWED = frozenset((EXE_NAME, README_NAME, HASH_NAME))
DIGEST = re.compile(r"[0-9a-f]{64}")


class ReleaseAuditError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def expected_checksum_line(exe_sha: str) -> str:
    if not DIGEST.fullmatch(exe_sha):
        raise ReleaseAuditError("Ungueltiger EXE-SHA")
    return exe_sha + "  " + EXE_NAME + "\n"


def verify_release_package(folder: Path, archive_path: Path) -> dict[str, object]:
    if folder.is_symlink() or not folder.is_dir():
        raise ReleaseAuditError("Release-Verzeichnis fehlt oder ist verlinkt")
    existing = {x.name for x in folder.iterdir()}
    if existing != ALLOWED:
        raise ReleaseAuditError("Release-Ordner enthält unzulässige oder fehlende Dateien")
    for name in ALLOWED:
        file = folder / name
        if file.is_symlink() or not file.is_file():
            raise ReleaseAuditError("Unzulaessige Datei oder Link im Release")
    exe = folder / EXE_NAME
    readme = folder / README_NAME
    checksum = folder / HASH_NAME
    if exe.stat().st_size < 16:
        raise ReleaseAuditError("Setup-EXE fehlt oder ist leer")
    if not readme.stat().st_size or readme.stat().st_size > 128 * 1024:
        raise ReleaseAuditError("Deutsche Anleitung fehlt oder ist zu gross")
    readme_bytes = readme.read_bytes()
    if b"HARVESTER" not in readme_bytes or b"INSTALLATION" not in readme_bytes:
        raise ReleaseAuditError("Unbekannte Release-Anleitung")
    readme_bytes.decode("utf-8", "strict")
    sha = sha256_file(exe)
    expected = expected_checksum_line(sha).encode("ascii")
    if checksum.read_bytes() != expected:
        raise ReleaseAuditError("EXE-SHA-256-Pruefsumme im Paket ist falsch")
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ReleaseAuditError("Release-ZIP fehlt oder ist verlinkt")
    if archive_path.resolve().is_relative_to(folder.resolve()):
        raise ReleaseAuditError("Das Release-ZIP darf nicht im eigenen Inhalt liegen")
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = archive.infolist()
            names = [i.filename for i in members]
            if (len(names) != len(ALLOWED) or set(names) != ALLOWED or
                    any(i.is_dir() for i in members)):
                raise ReleaseAuditError("ZIP enthaelt Test-, Entwickler- oder andere Zusatzdateien")
            for name in (README_NAME, HASH_NAME):
                if archive.read(name) != (folder / name).read_bytes():
                    raise ReleaseAuditError("ZIP-Datei weicht von der Freigabevorlage ab")
            h = hashlib.sha256()
            with archive.open(EXE_NAME, "r") as handle:
                for part in iter(lambda: handle.read(1024 * 1024), b""):
                    h.update(part)
            if h.hexdigest() != sha:
                raise ReleaseAuditError("EXE im ZIP weicht vom SHA-256-Sollwert ab")
    except zipfile.BadZipFile as exc:
        raise ReleaseAuditError("Ungueltiges Release-ZIP") from exc
    return {"archive": ZIP_NAME, "setup_exe_sha256": sha, "member_count": 3,
            "only_allowlisted_files": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Pruefe nur das lokal vorbereitete Release-Paket")
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify_release_package(args.folder, args.zip)
    except (OSError, UnicodeError, ReleaseAuditError) as exc:
        print("STOPP – Release-Paket nicht sauber:", exc, file=sys.stderr)
        return 2
    print("RELEASE-PAKETINHALT PASS – 3 freigegebene Dateien, keine Testdateien.")
    print("SHA-256 der EXE:", result["setup_exe_sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
