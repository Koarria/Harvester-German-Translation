#!/usr/bin/env python3
"""Harvester GOG German installer RC3 with adaptive, resumable FST rendering.

Retains RC2a's tested FIX2 core patcher and original files; renders both
subtitle sizes from one decode, parallel only if CPU and free RAM permit.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime
import multiprocessing
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import xml.etree.ElementTree as ET

# First-party render and ISO modules: tracked together with this program.
from runtime.harvester_iso import scan_iso, extract_fst, hash_file, patch_iso
from runtime.fst_subtitles import load_srt
from runtime.render_jobs import render_all

TARGET_NAME = 'Harvester GOG Deutsch'
MODES = ('10px', '11px')
STATE_TAG = 'HARVESTER_GOG_DEUTSCH_PYTHON_LOCAL_RENDER_RC3'
DISCS = ('HARVEST.DAT', 'HARVEST3.DAT', 'HARVEST4.DAT')
RULES_HASH = '7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b'
MANIFEST_HASH = 'f56a5708018820bcbc6af0c6fb71f3f775a39b317bd1626eb898aa04aaf7162d'
CORE_EXE_HASH = '9b8fada91a55db9c069309deb69137277cc951b154781523f7571c704f7a62e0'
CORE_EXE_TARGET_HASH = 'c461e05414a38b11c7e7d27c1ad47df823e2bdb87f2087639281cbc39cdb32b2'


def root_dir() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)).resolve()


def log(msg: str):
    print(msg, flush=True)


def assert_hash(path: Path, expected: str):
    actual = hash_file(path)
    if actual != expected:
        raise ValueError(f'SHA-256 stimmt nicht: {path.name} ({actual})')


def payload_preflight(root: Path) -> list[dict[str, str]]:
    payload = root / 'payload'
    for name, sha in [('Regeln.xml', RULES_HASH), ('VideoManifest.xml', MANIFEST_HASH),
                      ('Harvester_Deutsch_Patcher.exe', CORE_EXE_HASH)]:
        path = payload / name
        if not path.is_file():
            raise FileNotFoundError(f'Patch-Komponente fehlt: {name}')
        assert_hash(path, sha)
    rules = ET.parse(payload / 'Regeln.xml').getroot()
    for e in rules.findall('./Assets/Asset'):
        filename = e.attrib['name']
        if Path(filename).name != filename or not filename.endswith('.bin'):
            raise ValueError('Ungültiger Assets-Pfad')
        item = payload / 'Daten' / filename
        if not item.is_file() or item.stat().st_size != int(e.attrib['size']):
            raise ValueError(f'FIX2-Patchdaten fehlen: {filename}')
        assert_hash(item, e.attrib['sha'])

    xml = ET.parse(payload / 'VideoManifest.xml').getroot()
    if (xml.tag != 'HarvesterVideoManifest' or xml.attrib.get('version') != '1'
            or xml.attrib.get('ready') != 'release'):
        raise ValueError('Videomanifest nicht freigegeben')
    records = [dict(e.attrib) for e in xml.findall('Fst')]
    if len(records) != 196:
        raise ValueError('Erwartet 196 CD-/Schriftgrößen-Zuordnungen')
    unique = set()
    for row in records:
        if row['mode'] not in MODES or row['cd'] not in DISCS:
            raise ValueError('Unbekannte Video-Variante oder CD')
        f = row['film_id']
        if not re.fullmatch(r'[A-Z0-9_]+', f) or not re.fullmatch(r'GRAPHIC/FST/[A-Z0-9]+\.FST',row['path']):
            raise ValueError(f'Ungültiger Filmname/Pfad: {f}')
        for attr in ('source_sha256', 'target_sha256', 'patch_sha256'):
            if not re.fullmatch(r'[0-9a-f]{64}', row[attr]):
                raise ValueError('Ungültiger SHA-256 im Videomanifest')
        key = (row['mode'], row['cd'], row['path'])
        if key in unique:
            raise ValueError('Video-CD-Pfad doppelt')
        unique.add(key)
    for mode in MODES:
        by_cd = Counter(row['cd'] for row in records if row['mode'] == mode)
        if by_cd != {'HARVEST.DAT': 45, 'HARVEST3.DAT': 44, 'HARVEST4.DAT': 9}:
            raise ValueError(f'CD-Zuordnung unvollständig: {mode}')
    per_film: dict[str, set[str]] = {}
    per_mode: dict[str, set[str]] = {s:set() for s in MODES}
    source_pairs: dict[str, str] = {}
    for row in records:
        per_film.setdefault(row['film_id'], set()).add(row['source_sha256'])
        per_mode[row['mode']].add(row['film_id'])
        x = row['cd'] + '/' + row['path']
        if x in source_pairs and source_pairs[x] != row['source_sha256']:
            raise ValueError('Source SHA zwischen 10/11 px verschieden')
        source_pairs[x] = row['source_sha256']
    if (len(per_film) != 66 or any(len(hashes) != 1 for hashes in per_film.values())
            or per_mode['10px'] != per_mode['11px']):
        raise ValueError('66 Videoquellen nicht eindeutig')
    for film in per_film:
        for mode in MODES:
            srt = subtitle_file(payload, film, mode)
            if not srt.is_file() or not load_srt(srt):
                raise ValueError(f'Leere oder fehlende SRT: {film} {mode}')
    log('Paketprüfung OK: 66 Filme, 196 CD-Positionen, 132 SRT-Varianten.')
    return records


def subtitle_file(payload: Path, film: str, mode: str) -> Path:
    if film in {'C002A', 'C002B', 'C003', 'C004'}:
        return payload / 'subtitles' / 'endings' / f'{film}_DE.srt'
    return payload / 'subtitles' / mode / f'{film}_de_{mode}.srt'


def is_original_gog(path: Path) -> bool:
    return path.is_dir() and all((path / x).is_file() for x in (
        'HARVEST.EXE', *DISCS, 'DOSBOX/DOSBox.exe', 'dosbox_harvester_single.conf'))


def detect_gog() -> Path | None:
    if os.name != 'nt':
        return None
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for access in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                try:
                    with winreg.OpenKey(hive, r'Software\GOG.com\Games\1207661373', 0,
                                        winreg.KEY_READ | access) as key:
                        for value in ('DOSBOXFOLDER', 'path', 'gamepath'):
                            try:
                                candidate = Path(winreg.QueryValueEx(key, value)[0]).expanduser()
                            except (FileNotFoundError, OSError):
                                continue
                            for p in (candidate, candidate.parent, candidate.parent.parent):
                                if is_original_gog(p):
                                    return p.resolve()
                except OSError:
                    continue
    except ImportError:
        pass
    return None


def pick_paths() -> tuple[Path, Path]:
    import tkinter as tk
    from tkinter import filedialog, messagebox
    win = tk.Tk()
    win.withdraw()
    win.wm_attributes('-topmost', True)
    try:
        found = detect_gog()
        source = found if found and messagebox.askyesno(
            'Harvester GOG gefunden', f'Originalinstallation gefunden:\n\n{found}\n\nVerwenden?',
            parent=win) else None
        if source is None:
            selected = filedialog.askdirectory(title='Englischen GOG-Spielordner auswählen', parent=win)
            if not selected:
                raise KeyboardInterrupt('Ordnerauswahl abgebrochen')
            source = Path(selected)
        parent = filedialog.askdirectory(
            title='Zielordner für separate deutsche Installation auswählen',
            initialdir=str(source.parent),parent=win)
        if not parent:
            raise KeyboardInterrupt('Zielauswahl abgebrochen')
        target = Path(parent) / TARGET_NAME
        if target.exists() and not ((target / 'INSTALLATION_UNVOLLSTAENDIG.txt').is_file()
                                     and (target / '_PYTHON_RENDER_ARBEITSVERZEICHNIS' / 'state.json').is_file()):
            raise ValueError('Der Zielordner ist bereits vorhanden und wird nicht überschrieben: ' + str(target) + '\n'
                             'Zum Spielen bitte die Start-CMDs direkt in diesem Ordner verwenden. '
                             'Für eine neue Installation einen anderen Ziel-Elternordner wählen.')
        question = ('Unvollständige RC3-Installation fortsetzen?' if target.exists()
                    else 'Harvester Deutsch installieren')
        if not messagebox.askokcancel(question,
                                     'Englisches GOG-Original:\n' + str(source) +
                                     '\n\nInstallationsordner:\n' + str(target) +
                                     '\n\nRC3 passt die Videobearbeitung an CPU und Arbeitsspeicher an. '
                                     'Abgeschlossene Schritte können bei einem Abbruch wiederverwendet werden.\n\nStarten?', parent=win):
            raise KeyboardInterrupt('Installation abgebrochen')
        return source, target
    finally:
        win.destroy()


def safe_separate(source: Path, target: Path, package: Path, allow_resume: bool = False) -> None:
    if target.is_symlink() or source.is_symlink():
        raise ValueError('Quell-/Zielordner darf kein Symlink sein')
    source, target, package = (x.resolve() for x in (source, target, package))
    if not is_original_gog(source):
        raise ValueError('Die GOG-Quelldateien fehlen oder der Ordner ist falsch')
    if target.exists() and not allow_resume:
        raise ValueError('Zielordner existiert bereits, wird nicht überschrieben: ' + str(target))
    if target.is_symlink():
        raise ValueError('Zielordner darf kein Symlink/Junction sein')
    if not target.parent.is_dir():
        raise ValueError('Ziel-Elternordner existiert nicht')
    def nested(a, b):
        try:
            return os.path.commonpath((str(a), str(b))).casefold() == str(a).casefold()
        except ValueError:
            return False
    if (nested(source, target) or nested(target, source) or nested(source, package)
            or nested(package, target) or nested(target, package)):
        raise ValueError('Quell-, Paket- und Zielverzeichnis müssen getrennt sein')
    if source == target:
        raise ValueError('Quellordner darf niemals Ziel sein')
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('GOG-Quelle enthält Symlink/Junction: ' + str(path))


def free_space_check(source: Path, target: Path) -> None:
    original_size = sum(p.stat().st_size for p in source.rglob('*') if p.is_file())
    discs_size = sum((source / c).stat().st_size for c in DISCS)
    required = original_size + 7 * discs_size + 2 * 1024**3
    available = shutil.disk_usage(target.parent).free
    if available < required:
        raise ValueError(f'Zu wenig freier Speicher: benötigt ca. {required//(1024**3)+1} GiB, '
                         f'verfügbar {available//(1024**3)} GiB')
    log(f'Speicher-Vorprüfung: frei {available//(1024**3)} GiB; Reserve OK.')


def extract_film_sources(target: Path, records: list[dict], temp: Path) -> dict[str,Path]:
    log('Extrahiere und prüfe 66 Original-FSTs aus deutscher Spielkopie ...')
    maps = {cd: scan_iso(target / cd) for cd in DISCS}
    sources = {}
    for row in sorted(records, key=lambda r: (r['film_id'], r['mode'], r['cd'])):
        film = row['film_id']
        if film in sources:
            continue
        cd, path = row['cd'], row['path']
        if path not in maps[cd]:
            raise ValueError('FST nicht in GOG-Image: ' + cd + '/' + path)
        dst = temp / 'original_fst' / (film + '.FST')
        extract_fst(target / cd, maps[cd][path], dst, row['source_sha256'])
        sources[film] = dst
        if len(sources) % 10 == 0:
            log(f'  Originalfilme verifiziert: {len(sources)}/66')
    if len(sources) != 66:
        raise ValueError('Nicht alle 66 Filme gefunden')
    return sources




def create_launchers(target: Path) -> list[Path]:
    config = target / 'dosbox_harvester_single.conf'
    raw = config.read_bytes()
    text = raw.decode('cp1252')
    tag = 'imgmount d -t iso -fs iso "..\\HARVEST.DAT" "..\\HARVEST3.DAT" "..\\HARVEST4.DAT"'
    if text.count(tag) != 1 or 'mount C "..\\cloud_saves" -t overlay' not in text or 'harvest.exe' not in text:
        raise ValueError('Unbekannte GOG DOSBox-Konfiguration; kein sicherer Drei-Modus-Start')
    generated = []
    for mode, name, conf in (
        ('', 'Harvester_Deutsch_ohne_Videountertitel.cmd', 'dosbox_harvester_single_ohne_VideoUT.conf'),
        ('10px', 'Harvester_Deutsch_mit_10px_Videountertiteln.cmd','dosbox_harvester_single_10px.conf'),
        ('11px', 'Harvester_Deutsch_mit_11px_Videountertiteln.cmd','dosbox_harvester_single_11px.conf')
    ):
        mount = tag if not mode else ('imgmount d -t iso -fs iso '
            f'"..\\VideoUntertitel\\{mode}\\HARVEST.DAT" '
            f'"..\\VideoUntertitel\\{mode}\\HARVEST3.DAT" '
            f'"..\\VideoUntertitel\\{mode}\\HARVEST4.DAT"')
        config_path = target / conf
        expected_conf = text.replace(tag, mount).encode('cp1252')
        if config_path.exists():
            if config_path.read_bytes() != expected_conf:
                raise ValueError('Startkonfiguration existiert und ist verändert: ' + conf)
        else:
            config_path.write_bytes(expected_conf)
        generated.append(config_path)
        cmd = target / name
        expected_cmd = (f'@echo off\r\ncd /d "%~dp0DOSBOX" || exit /b 1\r\n'
                        f'"DOSBox.exe" -conf "..\\dosbox_harvester.conf" -conf "..\\{conf}"\r\n').encode('ascii')
        if cmd.exists():
            if cmd.read_bytes() != expected_cmd:
                raise ValueError('Startdatei existiert und ist verändert: ' + name)
        else:
            cmd.write_bytes(expected_cmd)
        generated.append(cmd)
    return generated


def update_proof(target: Path, generated: list[Path], reports: list[dict],
                 precalculated_hashes: dict[Path, str] | None = None) -> None:
    proof_path = target / 'Deutsch_Pruefnachweis.xml'
    if not proof_path.is_file():
        raise FileNotFoundError('FIX2-Installationsnachweis fehlt')
    tree = ET.parse(proof_path)
    proof = tree.getroot()
    if proof.tag != 'HarvesterDeutschInstallation':
        raise ValueError('Unbekanntes FIX2-Prüfnachweisformat')
    if proof.attrib.get('video_untertitel_release') == 'HARVESTER_GOG_DEUTSCH_VIDEO_V1':
        registered = {node.attrib.get('pfad','').replace('\\', '/').casefold(): node.attrib.get('sha256')
                      for node in proof.findall('Datei')}
        for item in generated:
            key = str(item.relative_to(target)).replace('\\', '/').casefold()
            h = (precalculated_hashes[item] if precalculated_hashes and item in precalculated_hashes
                 else hash_file(item))
            if registered.get(key) != h:
                raise ValueError('RC3-Nachweis nachträglich verändert: ' + str(item))
        qa_path = target / 'VideoUntertitel' / 'LOKALE_RENDER_QA.json'
        if not qa_path.is_file() or registered.get(str(qa_path.relative_to(target)).replace('\\', '/').casefold()) != hash_file(qa_path):
            raise ValueError('RC3-QA fehlt oder stimmt nicht')
        return
    video_root = target / 'VideoUntertitel'
    video_root.mkdir(parents=True, exist_ok=True)
    legacy = target / 'Harvester_Deutsch_starten.cmd'
    archived = video_root / 'ALTER_FIX2_STARTER.txt'
    if legacy.exists():
        if archived.exists():
            raise ValueError('Legacy-Starter und Archiv existieren gleichzeitig')
        old_hash = hash_file(legacy)
        legacy.rename(archived)
    elif archived.exists():
        old_hash = hash_file(archived)
    else:
        raise ValueError('Der FIX2-Starter oder sein Archiv fehlt')
    adjusted = False
    for node in proof.findall('Datei'):
        if node.attrib.get('pfad','').casefold() == legacy.name.casefold():
            if node.attrib.get('sha256','') != old_hash:
                raise ValueError('Legacy-Starter-Nachweis stimmt nicht')
            node.attrib['pfad'] = str(archived.relative_to(target)).replace('/', os.sep)
            adjusted = True
            break
    if not adjusted:
        raise ValueError('Legacy-Starter nicht im FIX2-Prüfnachweis')
    generated.append(archived)
    qa_path = video_root / 'LOKALE_RENDER_QA.json'
    qa_path.write_text(json.dumps({'release':'HARVESTER_GOG_DEUTSCH_VIDEO_V1',
                                   'date': datetime.now().isoformat(timespec='seconds'),
                                   'films':66, 'variant_render_jobs':132,
                                   'iso_fst_positions':196,
                                   'qa':reports}, ensure_ascii=False, indent=2), 'utf-8')
    generated.append(qa_path)
    for item in generated:
        e = ET.SubElement(proof,'Datei')
        e.set('pfad', str(item.relative_to(target)).replace('/', os.sep))
        e.set('sha256', precalculated_hashes[item] if precalculated_hashes and item in precalculated_hashes else hash_file(item))
    proof.set('video_untertitel_release','HARVESTER_GOG_DEUTSCH_VIDEO_V1')
    temp = proof_path.with_suffix('.xml.new')
    tree.write(temp, encoding='utf-8', xml_declaration=True)
    os.replace(temp, proof_path)


# Player-facing start guide; generated only after the CD images and launchers exist.
def launch_guide(target: Path) -> str:
    return ("HARVESTER GOG DEUTSCH - SPIEL STARTEN\n"
            "==================================\n\n"
            "Installation abgeschlossen.\n\n"
            "Installierter Spielordner:\n" + str(target) + "\n\n"
            "Zum Starten im Spielordner eine dieser drei CMD-Dateien doppelklicken:\n\n"
            "  1. Harvester_Deutsch_ohne_Videountertitel.cmd\n"
            "     Deutsche Spieltexte, keine Videountertitel.\n\n"
            "  2. Harvester_Deutsch_mit_10px_Videountertiteln.cmd\n"
            "     Deutsche Spieltexte und Videountertitel (10 Pixel).\n\n"
            "  3. Harvester_Deutsch_mit_11px_Videountertiteln.cmd\n"
            "     Deutsche Spieltexte und Videountertitel (11 Pixel).\n\n"
            "Alle drei Varianten nutzen denselben cloud_saves-Spielstandordner.\n"
            "Vor dem Wechsel der Startvariante das Spiel ganz beenden.\n"
            "Die englische GOG-Originalinstallation bleibt unveraendert.\n")


def write_start_guide(target: Path) -> Path:
    p = target / 'LIES_MICH_SPIELSTART.txt'
    p.write_text(launch_guide(target), encoding='utf-8')
    return p


def notify_success(target: Path) -> None:
    # GUI is optional: a missing desktop or Explorer must never turn a valid
    # installation into a reported failure after the completion marker is gone.
    info = ("Installation erfolgreich abgeschlossen!\n\n"
            + "Spielordner:\n" + str(target) + "\n\n"
            + "Zum Spielen im Spielordner eine dieser CMD-Dateien starten:\n\n"
            + "Harvester_Deutsch_ohne_Videountertitel.cmd\n"
            + "Harvester_Deutsch_mit_10px_Videountertiteln.cmd\n"
            + "Harvester_Deutsch_mit_11px_Videountertiteln.cmd\n\n"
            + "Die drei Varianten verwenden gemeinsame Spielstaende.\n\n"
            + "Spielordner jetzt im Explorer oeffnen?")
    try:
        import tkinter as tk
        from tkinter import messagebox
        win = tk.Tk()
        try:
            win.withdraw()
            win.wm_attributes('-topmost', True)
            opened = messagebox.askyesno('Harvester Deutsch - Installation fertig', info, parent=win)
        finally:
            win.destroy()
        if opened:
            os.startfile(str(target))
    except Exception as exc:
        log('Hinweis: Das optionale Dialogfenster / Explorer konnte nicht geoeffnet werden: ' + str(exc))


def state_file(target: Path) -> Path:
    return target / '_PYTHON_RENDER_ARBEITSVERZEICHNIS' / 'state.json'


def write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + '.new')
    if pending.exists():
        pending.unlink()  # Only installer-owned scratch checkpoint, not a game file.
    pending.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(pending, path)


def validate_resume(source: Path, target: Path) -> Path:
    marker = target / 'INSTALLATION_UNVOLLSTAENDIG.txt'
    temp = target / '_PYTHON_RENDER_ARBEITSVERZEICHNIS'
    state = state_file(target)
    if not marker.is_file() or not state.is_file() or temp.is_symlink():
        raise ValueError('Ziel existiert, ist aber keine unvollständige RC3-Installation; nichts verändert')
    try:
        obj = json.loads(state.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise ValueError('RC3-Zustand beschädigt; kein unsicheres Fortsetzen') from exc
    if not isinstance(obj, dict) or (obj.get('tag') != STATE_TAG or
        obj.get('source') != str(source.resolve()) or
        obj.get('target') != str(target.resolve()) or
        obj.get('manifest_sha256') != MANIFEST_HASH or
        obj.get('core_target_sha256') != CORE_EXE_TARGET_HASH):
        raise ValueError('RC3-Zustand gehört zu einer anderen Installation; nichts verändert')
    if not (target / 'Deutsch_Pruefnachweis.xml').is_file():
        raise ValueError('FIX2-Nachweis fehlt; Fortsetzung verweigert')
    assert_hash(target / 'HARVEST.EXE', CORE_EXE_TARGET_HASH)
    for cd in DISCS:
        if not (target / cd).is_file():
            raise ValueError('Basis-CD-Abbild fehlt; Fortsetzung verweigert: ' + cd)
    return temp


def patch_cd_or_reuse(target: Path, temp: Path, mode: str, cd: str,
                      items: list[dict], all_reports: list[dict]) -> tuple[Path, str, bool]:
    """Skip an existing CD only if its SHA and all selected movie hashes match."""
    base = target / cd
    dest = target / 'VideoUntertitel' / mode / cd
    checkpoint = temp / 'iso_qa' / mode / (cd + '.json')
    movie_hashes = {r['film']: r['rendered_sha256'] for r in all_reports if r['mode'] == mode}
    wanted = {item['path']: movie_hashes[item['film_id']] for item in items}
    if dest.exists():
        if not checkpoint.is_file():
            raise ValueError('Untertitel-CD existiert ohne vollständigen RC3-Prüfnachweis: '
                             + str(dest) + '; Sicherheitsstopp')
        proof = json.loads(checkpoint.read_text(encoding='utf-8'))
        if not isinstance(proof, dict) or proof.get('mode') != mode or proof.get('disc') != cd or proof.get('movies') != wanted:
            raise ValueError('Untertitel-CD passt nicht mehr zu den Quellvideos: ' + cd + ' ' + mode)
        if hash_file(base) != proof.get('base_sha256') or hash_file(dest) != proof.get('output_sha256'):
            raise ValueError('CD wurde nach dem Rendern verändert; keine unsichere Wiederaufnahme')
        log(f'Untertitel-CD {cd} {mode} aus geprüftem Zwischenstand übernommen.')
        return dest, proof['output_sha256'], True
    if checkpoint.exists():
        checkpoint.unlink()  # Stale checkpoint, no output file exists.
    pending = dest.with_suffix(dest.suffix + '.pending')
    if pending.exists():
        pending.unlink()  # Incomplete RC3 temp file; never a user GOG original.
    log(f'Erstelle CD {cd} mit {len(items)} ersetzten Videos ({mode}) ...')
    from runtime.harvester_iso import patch_iso
    baseline = patch_iso(base, dest, items, temp / 'output_fst' / mode)
    output_sha = hash_file(dest)
    write_json_atomic(checkpoint, {'mode':mode, 'disc':cd, 'base_sha256': baseline,
                                   'output_sha256': output_sha, 'movies': wanted})
    return dest, output_sha, False


def install(source: Path, target: Path, root: Path, records: list[dict],
            requested_workers: int | None = None) -> None:
    if os.name != 'nt':
        raise OSError('Der echte FIX2-GOG-Installer benötigt Windows. Linux ist nur für QA/Dry-Run vorgesehen.')
    resuming = target.exists()
    safe_separate(source, target, root, allow_resume=resuming)
    marker = target / 'INSTALLATION_UNVOLLSTAENDIG.txt'
    if resuming:
        temp = validate_resume(source, target)
        log('RC3: Unvollständige Installation erkannt; geprüfte Filmdaten werden wiederverwendet.')
    else:
        free_space_check(source, target)
        log('Starte unveränderten deutschen FIX2-Basispacher ...')
        subprocess.run([str(root / 'payload' / 'Harvester_Deutsch_Patcher.exe'),
                        '--source', str(source), '--target', str(target)],
                       cwd=str(root / 'payload'), check=True)
        proof_path = target / 'Deutsch_Pruefnachweis.xml'
        if not proof_path.is_file():
            raise ValueError('FIX2 hat keinen Installationsnachweis erzeugt')
        assert_hash(target / 'HARVEST.EXE', CORE_EXE_TARGET_HASH)
        temp = target / '_PYTHON_RENDER_ARBEITSVERZEICHNIS'
        temp.mkdir(exist_ok=False)
        write_json_atomic(state_file(target), {'tag':STATE_TAG, 'source':str(source.resolve()),
                         'target':str(target.resolve()), 'manifest_sha256':MANIFEST_HASH,
                         'core_target_sha256':CORE_EXE_TARGET_HASH})
        marker.write_text('RC3-Videorender noch nicht abgeschlossen; Spiel bitte noch nicht starten.\n', encoding='utf-8')
    try:
        sources = extract_film_sources(target, records, temp)
        reference_hashes = {r['film_id']:r['source_sha256'] for r in records}
        all_reports = render_all(sources, root / 'payload', temp, reference_hashes,
                                 requested_workers=requested_workers, log=log)
        produced = []
        checked_hashes: dict[Path, str] = {}
        for mode in MODES:
            for cd in DISCS:
                items = sorted((r for r in records if r['mode'] == mode and r['cd'] == cd),
                               key=lambda r:r['path'])
                dest, iso_hash, _ = patch_cd_or_reuse(target, temp, mode, cd, items, all_reports)
                checked_hashes[dest] = iso_hash
                produced.append(dest)
        for mode in MODES:
            for cd in DISCS:
                if not (target / 'VideoUntertitel' / mode / cd).is_file():
                    raise ValueError('Fehlende neue Untertitel-CD: ' + mode + '/' + cd)
        created = create_launchers(target)
        created.extend(produced)
        update_proof(target, created, all_reports, precalculated_hashes=checked_hashes)
        write_start_guide(target)
        marker.unlink()
        log('PASS: Spielkopie, 132 eigene FST-Renderings, 6 ISO-Abbilder, 3 Spielstarter.')
        log('Installiert: ' + str(target))
        log('\n' + '=' * 66)
        log('SPIELSTART: Die folgenden CMD-Dateien liegen direkt im Spielordner:')
        for starter in ('Harvester_Deutsch_ohne_Videountertitel.cmd',
                        'Harvester_Deutsch_mit_10px_Videountertiteln.cmd',
                        'Harvester_Deutsch_mit_11px_Videountertiteln.cmd'):
            log('  ' + starter)
        log('Spielordner: ' + str(target))
        log('Weitere Hinweise: LIES_MICH_SPIELSTART.txt')
        log('=' * 66 + '\n')
    finally:
        if not marker.exists():
            shutil.rmtree(temp, ignore_errors=True)
        else:
            log('INSTALLATION UNVOLLSTÄNDIG. Nicht starten. Fortschritt gespeichert unter: ' + str(temp))


def main() -> int:
    if not __debug__:
        raise RuntimeError('Python-Optimierung (-O) deaktiviert alle Renderer-Assertions; wird verweigert')
    parser=argparse.ArgumentParser(description='Harvester Deutsch GitHub Python Local-Render RC3')
    parser.add_argument('--source',type=Path,help='GOG-Originalordner (optional, sonst GUI)')
    parser.add_argument('--target-parent',type=Path,help='Elternordner für neue deutsche Installation')
    parser.add_argument('--preflight',action='store_true',help='Nur Paket und Untertitel prüfen')
    parser.add_argument('--workers',type=int,choices=range(1,5),default=None,
                        help='Optionale Obergrenze 1 bis 4; automatische RAM-Grenze bleibt aktiv')
    args=parser.parse_args()
    if sys.version_info < (3,10):
        raise RuntimeError('Python 3.10 oder neuer benötigt')
    if not args.preflight and os.name != 'nt':
        raise OSError('Windows erforderlich; --preflight ist plattformübergreifend')
    package=root_dir()
    records=payload_preflight(package)
    if args.preflight:
        return 0
    if args.source and args.target_parent:
        src,target=args.source,(args.target_parent / TARGET_NAME)
    elif args.source or args.target_parent:
        parser.error('--source und --target-parent müssen zusammen angegeben werden')
    else:
        src,target=pick_paths()
    log('GOG Quelle: '+str(src))
    log('Neue deutsche Kopie: '+str(target))
    install(src,target,package,records, requested_workers=args.workers)
    if not (args.source and args.target_parent):
        notify_success(target)
    return 0


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except KeyboardInterrupt as exc:
        log('Abgebrochen: '+str(exc))
        sys.exit(2)
    except Exception as exc:
        log('STOP: '+str(exc))
        traceback.print_exc()
        log('Das englische GOG-Original bleibt unangetastet. Falls ein Zielordner angelegt wurde, ist er möglicherweise unvollständig.')
        if getattr(sys, 'frozen', False) and sys.stdin and sys.stdin.isatty():
            try: input('Eingabetaste drücken, um dieses Fenster zu schließen ...')
            except EOFError: pass
        sys.exit(1)
