"""RC3 resource-conservative film worker scheduler, cache, and progress output."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing
from pathlib import Path
import ctypes
import json
import os
import struct
import time

from .dual_renderer import render_both, sha256_file, valid_cached, MODES


def available_memory() -> int | None:
    """Conservative available physical RAM (not installed total RAM)."""
    if os.name == 'nt':
        class Status(ctypes.Structure):
            _fields_ = [('dwLength', ctypes.c_ulong), ('dwMemoryLoad', ctypes.c_ulong),
                        ('ullTotalPhys', ctypes.c_ulonglong), ('ullAvailPhys', ctypes.c_ulonglong),
                        ('ullTotalPageFile', ctypes.c_ulonglong), ('ullAvailPageFile', ctypes.c_ulonglong),
                        ('ullTotalVirtual', ctypes.c_ulonglong), ('ullAvailVirtual', ctypes.c_ulonglong),
                        ('ullAvailExtendedVirtual', ctypes.c_ulonglong)]
        state = Status()
        state.dwLength = ctypes.sizeof(Status)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return int(state.ullAvailPhys)
        except (OSError, AttributeError):
            pass
        return None
    try:
        with open('/proc/meminfo', encoding='ascii') as f:
            for row in f:
                if row.startswith('MemAvailable:'):
                    return int(row.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def choose_workers(cpu: int | None, free_ram: int | None, largest_fst: int,
                   requested: int | None = None) -> int:
    """Bounded 1-4 worker policy: no machine needs a high-end CPU or much RAM.

    Source, both outputs and intermediate frames coexist in one worker, so a
    job reserve scales with movie size. Always keep at least 1.5 GiB free for Windows + the foreground app.
    """
    if requested is not None and not 1 <= requested <= 4:
        raise ValueError('--workers muss zwischen 1 und 4 liegen')
    threads = max(1, cpu or 1)
    cpu_limit = 1 if threads <= 3 else (2 if threads <= 7 else (3 if threads <= 11 else 4))
    if free_ram is None:
        memory_limit = 1  # Unknown RAM -> safe sequential mode
    else:
        mib = 1024 * 1024
        memory_per_worker = max(512 * mib, 384 * mib + 4 * max(0, largest_fst))
        memory_limit = max(1, (max(0, free_ram - 1536 * mib)) // memory_per_worker)
    return int(max(1, min(cpu_limit if requested is None else requested, memory_limit, 4)))


def fst_frame_count(path: Path) -> int:
    with Path(path).open('rb') as stream:
        hdr = stream.read(32)
    if len(hdr) != 32 or hdr[:4] != b'2TSF':
        raise ValueError('Ungültiger FST-Header: ' + str(path))
    _, _, _, nframes, _, _, _ = struct.unpack_from('<7I', hdr, 4)
    if not 0 < nframes <= 20000:
        raise ValueError('Ungültige Bildanzahl: ' + str(path))
    return nframes


def render_one_task(task: dict) -> dict:
    film = task['film']
    source = Path(task['source'])
    payload = Path(task['payload'])
    temp = Path(task['temp'])
    paths = {m: temp / 'output_fst' / m / (film + '.FST') for m in MODES}
    qa = {m: temp / 'render_qa' / m / (film + '.json') for m in MODES}
    # Imported inside the worker to avoid a circular dependency from installer.py
    def subtitle(m):
        if film in {'C002A', 'C002B', 'C003', 'C004'}:
            return payload / 'subtitles' / 'endings' / (film + '_DE.srt')
        return payload / 'subtitles' / m / (film + '_de_' + m + '.srt')
    captions = {m: subtitle(m) for m in MODES}
    start = time.monotonic()
    cached = valid_cached(source, captions, paths, qa, task['source_sha256'])
    if cached is None:
        # These are installer-owned scratch paths inside the validated RC3 temp.
        for m in MODES:
            for p in (paths[m], qa[m], Path(str(paths[m]) + '.pending'),
                      Path(str(qa[m]) + '.pending')):
                p.unlink(missing_ok=True)
        cached = render_both(source, captions, paths, qa, cut_fix=(film == 'C002B'))
        if any(cached[m]['source_sha256'] != task['source_sha256'] for m in MODES):
            raise ValueError('Source SHA-256 änderte sich während des Renderings: ' + film)
        reused = False
    else:
        reused = True
    return {'film': film, 'reports': cached, 'reused': reused,
            'seconds': time.monotonic()-start, 'frames': task['frames']}


def render_all(sources: dict[str, Path], payload: Path, temp: Path,
               source_hashes: dict[str, str], requested_workers: int | None = None,
               log=print) -> list[dict]:
    max_size = max(p.stat().st_size for p in sources.values())
    memory = available_memory()
    workers = choose_workers(os.cpu_count(), memory, max_size, requested_workers)
    log(f'RC3: {workers} parallele(r) Videoprozess(e), CPU={os.cpu_count() or 1}, '
        f'freier RAM={memory//(1024**2) if memory is not None else "unbekannt"} MiB.')
    tasks = [{'film': film, 'source': str(path), 'payload': str(payload),
              'temp': str(temp), 'source_sha256': source_hashes[film],
              'frames': fst_frame_count(path)} for film, path in sources.items()]
    tasks.sort(key=lambda t: t['frames'], reverse=True)
    completed = []
    begin = time.monotonic()
    total_frames = sum(t['frames'] for t in tasks)
    processed = 0
    def report(result):
        nonlocal processed
        completed.append(result)
        processed += result['frames']
        elapsed = max(0.001, time.monotonic() - begin)
        remain = max(0, int(elapsed * (total_frames - processed) / max(1, processed)))
        eta = f'ca. {remain//60}m {remain%60}s Restzeit' if processed else 'Restzeit unbekannt'
        status = 'aus Cache' if result['reused'] else 'neu gerendert und geprüft'
        log(f'Video {len(completed)}/{len(tasks)}: {result["film"]} '
            f'(10/11 px, {status}; {result["seconds"]:.0f}s); {eta}')
    if workers == 1:
        for item in tasks:
            report(render_one_task(item))
    else:
        # A process per movie instead of threads: Python decoding is CPU-bound.
        # Windows uses the native safe spawn model, PyInstaller freeze_support.
        with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context('spawn')) as pool:
            futures = {pool.submit(render_one_task, item): item['film'] for item in tasks}
            try:
                for future in as_completed(futures):
                    report(future.result())
            except BaseException:
                for future in futures:
                    future.cancel()
                raise
    if len(completed) != len(sources):
        raise ValueError('Nicht alle Filme fertig')
    reports = []
    for item in sorted(completed, key=lambda x: x['film']):
        for mode in MODES:
            reports.append({'film': item['film'], 'mode': mode,
                            'source_sha256': item['reports'][mode]['source_sha256'],
                            'rendered_sha256': item['reports'][mode]['output_sha256'],
                            'frames': item['reports'][mode]['frames'],
                            'subtitle_cues': item['reports'][mode]['cues'],
                            'qa_verification': item['reports'][mode]['verification']})
    log(f'RC3: 132 Varianten geprüft in {round(time.monotonic()-begin)} Sekunden '
        f'({sum(x["reused"] for x in completed)} Film-Paare aus Cache).')
    return reports
