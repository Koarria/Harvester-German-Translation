"""RC3: render 10px+11px from one original FST decode; verify both outputs.

This keeps RC2a's exact overlay, palette-slot and encoder rules. A completed
movie and its QA report are published only after every frame has passed.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

import numpy as np

from .fst_codec import FST
from .fst_subtitles import caption_mask, font_for, load_srt
from .fst_subtitles_fast import fast_encode_delta, palette_indices

CACHE_VERSION = 'RC3_DUAL_RENDER_V1'
MODES = ('10px', '11px')
PASS = 'PASS_ALL_FRAMES_ORIGINAL_BACKGROUND_RGB_PALETTE_RESTORED_AND_BITIDENTICAL_AUDIO'


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as fd:
        for data in iter(lambda: fd.read(4 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def font_hash(font) -> str:
    """Cache invalidation: never trust renders after a font substitution."""
    location = getattr(font, 'path', None)
    if not location or not Path(location).is_file():
        raise ValueError('Die verwendete Schriftdatei ist für die Cache-Prüfung nicht lesbar')
    return sha256_file(Path(location))


def prepare_cues(f: FST, path: Path, film: str, mode: str, cut_fix: bool):
    cues = load_srt(path)
    if cut_fix:
        if film != 'C002B' or len(cues) != 47:
            raise ValueError('Unerwarteter C002B-Timing-Fix')
        if cues[-1][0] >= f.frames / f.fps:
            cues[-1] = (f.frames / f.fps - 0.4, cues[-1][1], cues[-1][2])
    font = font_for(int(mode[:-2]))
    masks = {}
    for start, end, text in cues:
        if not text or start < 0 or end <= start:
            raise ValueError('Ungültige SRT-Untertitelzeiten')
        if text not in masks:
            a, b = caption_mask((f.w, f.h), text, font)
            masks[text] = (np.frombuffer(a.tobytes(), np.uint8) >= 128,
                           np.frombuffer(b.tobytes(), np.uint8) >= 128)
    return {'cues': cues, 'masks': masks, 'srt_sha256': sha256_file(path),
            'font_sha256': font_hash(font), 'font_size': int(mode[:-2]),
            'ci': 0, 'prev_pix': bytes(f.w * f.h), 'prev_pal': bytes(768),
            'prev_caption': False, 'lengths': [], 'max_video': f.maxsize,
            'reencoded': 0, 'updated_palettes': 0, 'used_free': 0,
            'fallback': 0, 'caption_frames': 0, 'palette_changes': [],
            'old_audio': hashlib.sha256(), 'new_audio': hashlib.sha256()}


def render_both(src: Path, subtitles: dict[str, Path], outputs: dict[str, Path],
                reports: dict[str, Path], cut_fix: bool = False) -> dict[str, dict]:
    """No change to the original file; produces 2 verified output files.

    Output is streamed to disk instead of storing 2 entire encoded videos in
    growing Python lists. The original FST is decoded ONCE for encoding and
    ONCE for the independent dual-output verification.
    """
    src = Path(src)
    f = FST(src)
    film = src.stem
    if set(subtitles) != set(MODES) or set(outputs) != set(MODES) or set(reports) != set(MODES):
        raise ValueError('Beide Schriftvarianten sind erforderlich')
    if any(src.resolve() == Path(outputs[m]).resolve() for m in MODES):
        raise ValueError('Original-FST darf nicht überschrieben werden')
    states = {m: prepare_cues(f, Path(subtitles[m]), film, m, cut_fix) for m in MODES}
    pending_files = {m: Path(str(outputs[m]) + '.pending') for m in MODES}
    pending_qa = {m: Path(str(reports[m]) + '.pending') for m in MODES}
    for m in MODES:
        Path(outputs[m]).parent.mkdir(parents=True, exist_ok=True)
        Path(reports[m]).parent.mkdir(parents=True, exist_ok=True)
        if pending_files[m].exists() or pending_qa[m].exists():
            raise ValueError('Vorherige nicht abgeschlossene Renderdatei vorhanden: ' + film)
    file_handles = {}
    try:
        for mode in MODES:
            file_handles[mode] = pending_files[mode].open('xb', buffering=1024 * 1024)
            file_handles[mode].write(bytes(32 + 6 * f.frames))
        for fi, pix, pal, audio in f.decode():
            t = fi / f.fps
            for mode in MODES:
                st = states[mode]
                cues = st['cues']
                ci = st['ci']
                while ci < len(cues) and t >= cues[ci][1]:
                    ci += 1
                st['ci'] = ci
                caption = cues[ci][2] if ci < len(cues) and cues[ci][0] <= t < cues[ci][1] else ''
                targetpal, targetpix = pal, pix
                if caption:
                    st['caption_frames'] += 1
                    outer, inner = st['masks'][caption]
                    rgb = np.frombuffer(pal, np.uint8).reshape(256, 3)
                    _, black = palette_indices(pal)
                    exact = np.where(np.all(rgb == np.array([252, 252, 252]), axis=1))[0]
                    if len(exact):
                        white = int(exact[0])
                    else:
                        original = np.frombuffer(pix, np.uint8)
                        free = np.flatnonzero(np.bincount(original, minlength=256) == 0)
                        free = free[free != black]
                        if len(free):
                            white = int(free[0])
                            st['used_free'] += 1
                            modified = bytearray(pal)
                            modified[3 * white:3 * white + 3] = b'\xfc\xfc\xfc'
                            targetpal = bytes(modified)
                        else:
                            white, _ = palette_indices(pal)
                            st['fallback'] += 1
                    if white == black:
                        raise ValueError('No distinct black/white palette indices')
                    q = np.frombuffer(pix, np.uint8).copy()
                    q[outer] = black
                    q[inner] = white
                    targetpix = q.tobytes()
                if caption or st['prev_caption']:
                    palette_block = (bytes(v // 4 for v in targetpal)
                                     if targetpal != st['prev_pal'] else None)
                    if palette_block is not None:
                        st['updated_palettes'] += 1
                    video = fast_encode_delta(st['prev_pix'], targetpix, f.w, f.h, palette_block)
                    st['reencoded'] += 1
                else:
                    length, _ = f.entries[fi]
                    video = f.buf[f.offsets[fi]:f.offsets[fi] + length]
                file_handles[mode].write(video)
                file_handles[mode].write(audio)
                st['lengths'].append((len(video), len(audio)))
                st['max_video'] = max(st['max_video'], len(video))
                st['old_audio'].update(audio)
                st['new_audio'].update(audio)
                st['prev_pix'] = targetpix
                st['prev_pal'] = targetpal
                st['prev_caption'] = bool(caption)
        for mode in MODES:
            st = states[mode]
            out = file_handles[mode]
            header = bytearray(f.buf[:32])
            struct.pack_into('<I', header, 12, st['max_video'])
            idx = b''.join(struct.pack('<IH', n, a) for n, a in st['lengths'])
            out.seek(0)
            out.write(header)
            out.write(idx)
            out.flush()
            os.fsync(out.fileno())
            out.close()
        file_handles.clear()
        # Verify both independent output decoders against ONE source decode.
        gs = {m: FST(pending_files[m]) for m in MODES}
        for mode in MODES:
            g = gs[mode]
            if (f.w, f.h, f.frames, f.fps, f.sample_rate, f.bits) != (
                    g.w, g.h, g.frames, g.fps, g.sample_rate, g.bits):
                raise ValueError(f'FST-Videodaten fehlerhaft: {mode}')
            states[mode]['verify_ci'] = 0
            states[mode]['confirmed_white'] = 0
        for (fi, origpix, origpal, oraud), a, b in zip(f.decode(), gs['10px'].decode(), gs['11px'].decode()):
            for mode, (di, newpix, newpal, outaud) in zip(MODES, (a, b)):
                st = states[mode]
                if di != fi or oraud != outaud:
                    raise AssertionError(f'Audio/Frame stimmt nicht: {film} {mode} Frame {fi}')
                cues = st['cues']
                ci = st['verify_ci']
                t = fi / f.fps
                while ci < len(cues) and t >= cues[ci][1]:
                    ci += 1
                st['verify_ci'] = ci
                caption = cues[ci][2] if ci < len(cues) and cues[ci][0] <= t < cues[ci][1] else ''
                if caption:
                    outer, inner = st['masks'][caption]
                    original = np.frombuffer(origpix, np.uint8)
                    updated = np.frombuffer(newpix, np.uint8)
                    orig_rgb = np.frombuffer(origpal, np.uint8).reshape(256, 3)
                    new_rgb = np.frombuffer(newpal, np.uint8).reshape(256, 3)
                    if not np.array_equal(original[~outer], updated[~outer]):
                        raise AssertionError('Non-caption video index differs')
                    if not np.array_equal(orig_rgb[original[~outer]], new_rgb[updated[~outer]]):
                        raise AssertionError('Non-caption RGB differs')
                    if not np.all(new_rgb[updated[inner]] == 252):
                        raise AssertionError('Caption is not white')
                    outline = outer & ~inner
                    if np.any(outline) and not np.all(new_rgb[updated[outline]] == 0):
                        raise AssertionError('Caption outline is not black')
                    st['confirmed_white'] += 1
                elif origpix != newpix or origpal != newpal:
                    raise AssertionError('Uncaptioned frame/palette differs')
        results = {}
        original_sha = hashlib.sha256(f.buf).hexdigest()
        for mode in MODES:
            st = states[mode]
            g = gs[mode]
            if st['old_audio'].digest() != st['new_audio'].digest():
                raise AssertionError('Audio SHA mismatch')
            if st['fallback'] or st['confirmed_white'] != st['caption_frames']:
                raise AssertionError(f'Caption QA failed: {film} {mode}')
            results[mode] = {
                'source': str(src), 'output': str(outputs[mode]),
                'source_bytes': len(f.buf), 'output_bytes': len(g.buf),
                'source_sha256': original_sha, 'output_sha256': hashlib.sha256(g.buf).hexdigest(),
                'frames': f.frames, 'fps': f.fps, 'video_seconds': f.frames/f.fps,
                'audio_seconds': sum(a for _, a in f.entries)/(f.sample_rate*f.bits/8),
                'cues': len(st['cues']), 'font_px': st['font_size'], 'cut_fix': cut_fix,
                'caption_frames': st['caption_frames'], 'reencoded_frames': st['reencoded'],
                'frame_palette_blocks_written': st['updated_palettes'],
                'frames_white_in_free_slot': st['used_free'],
                'frames_no_free_slot_fallback': st['fallback'],
                'frames_confirmed_pure_white': st['confirmed_white'],
                'original_audio_sha256': st['old_audio'].hexdigest(),
                'output_audio_sha256': st['new_audio'].hexdigest(),
                'verification': PASS,
                'white_definition': '252,252,252 (6-bit palette full white)',
                'original_src_palette_unchanged': True,
                'output_palette_changes_only_at_originally_unused_slots': True,
                'srt_cues': [{'start': a, 'end': b, 'text': s} for a,b,s in st['cues']],
                'pipeline_revision': CACHE_VERSION, 'subtitle_sha256': st['srt_sha256'],
                'font_sha256': st['font_sha256']
            }
        # All reports and both movies verified; publish outputs and QA atomically per file.
        for mode in MODES:
            pending_qa[mode].write_text(json.dumps(results[mode], ensure_ascii=False, indent=2), encoding='utf-8')
        for mode in MODES:
            os.replace(pending_files[mode], outputs[mode])
        for mode in MODES:
            os.replace(pending_qa[mode], reports[mode])
        return results
    finally:
        for fd in file_handles.values():
            fd.close()
        for p in list(pending_files.values()) + list(pending_qa.values()):
            p.unlink(missing_ok=True)


def valid_cached(src: Path, subtitles: dict[str, Path], outputs: dict[str, Path],
                 reports: dict[str, Path], expected_src_sha: str):
    """Use only fully verified, unmodified prior output; fail closed otherwise."""
    try:
        fonts = {m: font_hash(font_for(int(m[:-2]))) for m in MODES}
        items = {}
        for mode in MODES:
            if not outputs[mode].is_file() or not reports[mode].is_file():
                return None
            record = json.loads(reports[mode].read_text(encoding='utf-8'))
            if any([record.get('pipeline_revision') != CACHE_VERSION,
                    record.get('source_sha256') != expected_src_sha,
                    record.get('subtitle_sha256') != sha256_file(subtitles[mode]),
                    record.get('font_sha256') != fonts[mode],
                    record.get('verification') != PASS,
                    record.get('frames_no_free_slot_fallback') != 0,
                    record.get('frames_confirmed_pure_white') != record.get('caption_frames'),
                    sha256_file(outputs[mode]) != record.get('output_sha256')]):
                return None
            items[mode] = record
        return items
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
