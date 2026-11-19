"""Strict semantic verification of FIX2's *target-dependent* XML proof.

The native core patcher writes 'original' and 'ziel' paths into this XML; a
SHA-256 pinned for one installation is NOT portable to a different target.
This verifier checks the bound paths, pinned rules digest, every listed file's
SHA-256, filename safety, and the entire fresh core inventory instead.
No proprietary bytes or user paths are returned or logged.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import re
import xml.etree.ElementTree as ET

import originalvergleich_gog as audit
from runtime.harvester_iso import hash_file

RULES_SHA256 = audit.EXPECTED_RULES_SHA256
PROOF_FILE = "Deutsch_Pruefnachweis.xml"
CORE_FILES = frozenset({
    "HARVEST.EXE", "HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT",
    "goglog.ini", "Harvester_Deutsch_starten.cmd",
})
VIDEO_RELEASE = "HARVESTER_GOG_DEUTSCH_VIDEO_V1"
MAX_PROOF_BYTES = 8 * 1024 * 1024
HEX_SHA = re.compile(r"[0-9a-f]{64}\Z")


class ProofError(ValueError):
    pass


def _bad(message: str) -> None:
    raise ProofError("FIX2-Basis-Pruefnachweis ungueltig: " + message)


def _same_location(a: Path, b: Path) -> bool:
    left = os.path.normcase(os.path.normpath(str(a.expanduser().resolve())))
    right = os.path.normcase(os.path.normpath(str(b.expanduser().resolve())))
    return left == right


def _relative_path(raw: str) -> Path:
    if not raw:
        _bad("Ungueltiger relativer Dateipfad")
    parsed = PureWindowsPath(raw)
    if (parsed.drive or parsed.root or parsed.is_absolute() or
            any(x in ("", ".", "..") or ":" in x for x in parsed.parts)):
        _bad("Unzulaessiger Dateipfad im Nachweis")
    result = Path(*parsed.parts)
    if not result.parts or result.name.lower() == PROOF_FILE.lower():
        _bad("Unzulaessige Selbstreferenz im Nachweis")
    return result


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _progress_file(relative: str) -> bool:
    """Only files created by the existing RC3b video addon may be unregistered."""
    return (
        relative == "delta_video_installation_unvollstaendig.txt"
        or relative.startswith("_delta_video_arbeitsverzeichnis/")
        or relative.startswith("videountertitel/")
        or relative in {
            "harvester_deutsch_ohne_videountertitel.cmd",
            "harvester_deutsch_mit_10px_videountertiteln.cmd",
            "harvester_deutsch_mit_11px_videountertiteln.cmd",
            "dosbox_harvester_single_ohne_videout.conf",
            "dosbox_harvester_single_10px.conf",
            "dosbox_harvester_single_11px.conf",
            "lies_mich_spielstart.txt",
        }
    )


def verify_core_proof(source: Path, target: Path,
                      allow_video_progress: bool = False) -> str:
    """Verify proof without writing any game bytes, returning its *actual* SHA.

    Fresh unmarked cores require exact inventory equality: every file except
    the proof itself must appear in the signed-by-hash XML inventory. A marked
    partial video run may have only the RC3b-known extra video/checkpoint files.
    """
    source, target = source.resolve(), target.resolve()
    proof = target / PROOF_FILE
    if (_linked(target) or _linked(proof) or not proof.is_file() or
            not 0 < proof.stat().st_size <= MAX_PROOF_BYTES):
        _bad("Datei fehlt, verlinkt oder zu gross")
    try:
        root = ET.parse(proof).getroot()
    except ET.ParseError as exc:
        raise ProofError("FIX2-Basis-Pruefnachweis ist kein gueltiges XML") from exc
    if root.tag != "HarvesterDeutschInstallation":
        _bad("Unbekanntes XML-Root-Element")
    required = {"original", "ziel", "regeln_sha256"}
    attrs = root.attrib
    extra = set(attrs) - required
    if (not required.issubset(attrs) or
            extra not in (set(), {"video_untertitel_release"}) or
            (extra and not allow_video_progress) or
            (extra and attrs.get("video_untertitel_release") != VIDEO_RELEASE)):
        _bad("Unbekannte oder inkonsistente XML-Metadaten")
    if attrs["regeln_sha256"] != RULES_SHA256:
        _bad("Gepinnte FIX2-Regeln stimmen nicht")
    if not _same_location(Path(attrs["original"]), source):
        _bad("Nachweis gehoert zu einem anderen Originalordner")
    if not _same_location(Path(attrs["ziel"]), target):
        _bad("Nachweis gehoert zu einem anderen Zielordner")

    registered: dict[str, str] = {}
    for element in root:
        if element.tag != "Datei" or set(element.attrib) != {"pfad", "sha256"}:
            _bad("Unbekannter Dateieintrag im Nachweis")
        rel = _relative_path(element.attrib["pfad"])
        key = rel.as_posix().casefold()
        digest = element.attrib["sha256"]
        if key in registered or not HEX_SHA.fullmatch(digest):
            _bad("Doppelter Dateieintrag oder falsches SHA-256-Format")
        filename = target / rel
        if (not filename.is_file() or _linked(filename) or
                not filename.resolve().is_relative_to(target) or
                hash_file(filename) != digest):
            _bad("Registrierte Core-Datei fehlt oder SHA-256 ist falsch")
        registered[key] = digest

    needed = {x.casefold() for x in CORE_FILES}
    if extra:
        needed.discard("harvester_deutsch_starten.cmd")
        if "videountertitel/alter_fix2_starter.txt" not in registered:
            _bad("Archivierter FIX2-Starter fehlt im Video-Nachweis")
    if not needed.issubset(registered):
        _bad("Pflichtdatei im Installationsnachweis fehlt")

    seen: set[str] = set()
    for file in target.rglob("*"):
        if _linked(file):
            _bad("Verknuepfte Datei oder Junction im Testziel")
        if file.is_file():
            key = file.relative_to(target).as_posix().casefold()
            if key == PROOF_FILE.casefold():
                continue
            if key in seen:
                _bad("Dateiname unterscheidet sich nur durch Gross-/Kleinschreibung")
            seen.add(key)
            if key not in registered and not (
                    allow_video_progress and _progress_file(key)):
                _bad("Nicht registrierte Datei im Testziel")
    if not set(registered).issubset(seen):
        _bad("Im Nachweis registrierte Datei im Testziel nicht vorhanden")
    return hash_file(proof)
