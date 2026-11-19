"""PRIVATE one-file player candidate: locate a delta ZIP embedded at LOCAL build time.

No proprietary ZIP is committed, retrieved from GitHub, generated or uploaded
here. PyInstaller extracts this read-only resource to its own _MEIPASS for
each process. Never hand a parent GUI process's _MEIPASS path to a child EXE.
This digest authenticates local packaging consistency; the existing GOG-bound
delta.verify_bundle_bytes() remains the authoritative asset verification.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import zipfile

EMBEDDED_DIR = "private_embedded"
BUNDLE_NAME = "delta.bundle.zip"
SHA_NAME = "delta.bundle.sha256"
MAX_BYTES = 20 * 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class EmbeddedDeltaError(ValueError):
    pass


def embedded_bundle_path(root: Path) -> Path | None:
    """Find and verify a local embedded bundle without depending on game paths.

    Returns None if neither private packaging resource exists; legacy developer
    builds can still use their explicit local --bundle path. If *one* exists,
    refuse the broken build rather than silently falling back to another ZIP.
    """
    directory = root / EMBEDDED_DIR
    path = directory / BUNDLE_NAME
    sha_path = directory / SHA_NAME
    present_bundle = path.exists() or path.is_symlink()
    present_sha = sha_path.exists() or sha_path.is_symlink()
    if not present_bundle and not present_sha:
        return None
    if (not present_bundle or not present_sha or directory.is_symlink() or
            path.is_symlink() or sha_path.is_symlink() or
            not path.is_file() or not sha_path.is_file()):
        raise EmbeddedDeltaError("Eingebautes Delta ist unvollständig oder verlinkt")
    if not 0 < path.stat().st_size <= MAX_BYTES:
        raise EmbeddedDeltaError("Eingebautes Delta hat ungültige Größe")
    if not 0 < sha_path.stat().st_size <= 128:
        raise EmbeddedDeltaError("Eingebauter Delta-SHA-Nachweis hat ungültige Größe")
    try:
        expected = sha_path.read_text(encoding="ascii").strip()
    except UnicodeError as exc:
        raise EmbeddedDeltaError("Eingebauter SHA-Nachweis ist nicht ASCII") from exc
    if not HEX64.fullmatch(expected):
        raise EmbeddedDeltaError("Eingebauter SHA-Nachweis hat ungültiges Format")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise EmbeddedDeltaError("Eingebautes Delta passt nicht zum SHA-256-Baunachweis")
    # Only verify the packaging shape here. The authoritative verification
    # reconstructs all 18 FIX2 targets from the user's own original GOG files.
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (len(names) != 22 or len(set(names)) != 22 or
                    not {"bundle.json", "Regeln.xml"}.issubset(names) or
                    any(member.is_dir() or member.file_size > MAX_BYTES
                        or name.startswith("/") or "\\" in name or
                        ".." in Path(name).parts
                        for name, member in zip(names, members))):
                raise EmbeddedDeltaError("Eingebautes Delta hat kein gültiges Privatpaket-Layout")
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise EmbeddedDeltaError("Eingebautes Delta-ZIP ist beschädigt") from exc
    return path

