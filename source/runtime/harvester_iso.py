"""Strict, minimal ISO9660 extent reader/writer for known Harvester GOG images.

No CD filesystem restructuring. Replacements are appended at sector boundaries;
existing directory records and the primary volume space size are updated.
The original ISO images are never opened in write mode.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import os
import shutil
import struct

SECTOR = 2048


@dataclass(frozen=True)
class Extent:
    path: str
    record: int
    offset: int
    size: int
    is_dir: bool


def hash_file(path: Path, pos: int = 0, size: int | None = None) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fd:
        fd.seek(pos)
        while size is None or size:
            chunk = fd.read(2 * 1024 * 1024 if size is None else min(size, 2 * 1024 * 1024))
            if not chunk:
                if size is None:
                    break
                raise ValueError(f"Truncated span in {path}")
            h.update(chunk)
            if size is not None:
                size -= len(chunk)
    return h.hexdigest()


def both32(raw: bytes, offset: int) -> int:
    le = struct.unpack_from("<I", raw, offset)[0]
    be = struct.unpack_from(">I", raw, offset + 4)[0]
    if le != be:
        raise ValueError("Inconsistent ISO9660 byte order")
    return le


def write_both32(fd, pos: int, num: int) -> None:
    if not 0 <= num <= 0xffffffff:
        raise ValueError("ISO size/offset out of range")
    fd.seek(pos)
    fd.write(struct.pack("<I", num) + struct.pack(">I", num))


def scan_iso(path: Path) -> dict[str, Extent]:
    path = Path(path)
    length = path.stat().st_size
    seen: set[tuple[int, int]] = set()
    entries: dict[str, Extent] = {}
    with path.open("rb") as fd:
        fd.seek(16 * SECTOR)
        pvd = fd.read(SECTOR)
        if len(pvd) != SECTOR or pvd[:7] != b"\x01CD001\x01":
            raise ValueError(f"Not an ISO9660 primary descriptor: {path}")
        if both32(pvd, 80) * SECTOR != length:
            raise ValueError("ISO volume size does not match actual length")
        def recurse(at: int, extent_len: int, prefix: str, depth: int):
            if (depth >= 16 or at < 0 or extent_len <= 0 or
                    at + extent_len > length or (at, extent_len) in seen):
                raise ValueError("Bad/recursive ISO directory extent")
            seen.add((at, extent_len))
            cursor = 0
            while cursor < extent_len:
                fd.seek(at + cursor)
                one = fd.read(1)
                if not one:
                    raise ValueError("Truncated ISO directory")
                n = one[0]
                if not n:
                    cursor = (cursor // SECTOR + 1) * SECTOR
                    continue
                if n < 34 or cursor + n > extent_len or (cursor % SECTOR) + n > SECTOR:
                    raise ValueError("Bad ISO directory record size")
                rec_pos = at + cursor
                fd.seek(rec_pos)
                rec = fd.read(n)
                cursor += n
                if len(rec) != n or 33 + rec[32] > n or rec[25] & 128:
                    raise ValueError("Unsupported ISO directory record")
                if rec[32] == 1 and rec[33] in (0, 1):
                    continue
                raw_name = rec[33:33 + rec[32]].decode("ascii")
                name = raw_name.split(";", 1)[0].rstrip(".").upper()
                if not name or name in (".", "..") or "/" in name or "\\" in name:
                    raise ValueError("Unsafe ISO entry name")
                key = prefix + name
                pos = both32(rec, 2) * SECTOR
                size = both32(rec, 10)
                is_dir = (rec[25] & 2) != 0
                if pos < 0 or size < 0 or pos + size > length or key in entries:
                    raise ValueError(f"Invalid ISO entry extent: {key}")
                entries[key] = Extent(key, rec_pos, pos, size, is_dir)
                if is_dir:
                    recurse(pos, size, key + "/", depth + 1)
        recurse(both32(pvd, 158) * SECTOR, both32(pvd, 166), "", 0)
    return entries


def extract_fst(iso: Path, entry: Extent, destination: Path, expect_hash: str) -> None:
    if entry.is_dir or not entry.path.startswith("GRAPHIC/FST/") or not entry.path.endswith(".FST"):
        raise ValueError("Requested ISO resource is not a FST film")
    if hash_file(iso, entry.offset, entry.size) != expect_hash:
        raise ValueError(f"Original FST SHA-256 mismatch: {entry.path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if hash_file(destination) != expect_hash:
            raise ValueError(f"Conflicting source video: {destination.name}")
        return
    try:
        with Path(iso).open("rb") as src, destination.open("xb") as out:
            src.seek(entry.offset)
            remaining = entry.size
            while remaining:
                buf = src.read(min(remaining, 2 * 1024 * 1024))
                if not buf:
                    raise ValueError("Incomplete ISO video extent")
                out.write(buf)
                remaining -= len(buf)
        if hash_file(destination) != expect_hash:
            raise ValueError("Extracted FST not byte-identical to original")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def patch_iso(base: Path, dest: Path, items: list[dict], rendered_folder: Path) -> None:
    """Replace selected FST ISO resources while preserving all others.

    `items`: verified manifest entries containing path, film_id, source_sha256.
    Caller must have validated all rendered source/QA hashes.
    """
    base, dest = Path(base), Path(dest)
    if base.resolve() == dest.resolve() or dest.exists():
        raise ValueError("Refusing to overwrite source/existing target ISO")
    baseline = hash_file(base)
    before = scan_iso(base)
    expected_targets: dict[str, str] = {}
    for item in items:
        p = item["path"]
        if p not in before or before[p].is_dir:
            raise ValueError(f"Missing FST from ISO: {p}")
        if hash_file(base, before[p].offset, before[p].size) != item["source_sha256"]:
            raise ValueError(f"Changed German ISO FST: {p}")
        converted = rendered_folder / (item["film_id"] + ".FST")
        if not converted.is_file():
            raise ValueError(f"Rendered FST missing: {item['film_id']}")
        expected_targets[p] = hash_file(converted)

    dest.parent.mkdir(parents=True, exist_ok=True)
    pending = dest.with_suffix(dest.suffix + ".pending")
    if pending.exists():
        raise ValueError("Pending output ISO already exists; cannot silently overwrite")
    try:
        shutil.copyfile(base, pending)
        if hash_file(pending) != baseline:
            raise ValueError("Initial ISO copy differs from original German ISO")
        with pending.open("r+b") as fd:
            fd.seek(0, os.SEEK_END)
            for item in items:
                item_path = item["path"]
                converted = rendered_folder / (item["film_id"] + ".FST")
                e = before[item_path]
                pad = (-fd.tell()) % SECTOR
                if pad:
                    fd.write(bytes(pad))
                off = fd.tell()
                with converted.open("rb") as inp:
                    shutil.copyfileobj(inp, fd, 2 * 1024 * 1024)
                size = fd.tell() - off
                pad = (-fd.tell()) % SECTOR
                if pad:
                    fd.write(bytes(pad))
                write_both32(fd, e.record + 2, off // SECTOR)
                write_both32(fd, e.record + 10, size)
                fd.seek(0, os.SEEK_END)
            write_both32(fd, 16 * SECTOR + 80, fd.seek(0, os.SEEK_END) // SECTOR)
            fd.flush()
            os.fsync(fd.fileno())
        after = scan_iso(pending)
        if before.keys() != after.keys():
            raise ValueError("ISO directory inventory changed")
        for name, old in before.items():
            if old.is_dir:
                continue
            expected = expected_targets.get(name)
            if expected is None:
                expected = hash_file(base, old.offset, old.size)
            new = after[name]
            if hash_file(pending, new.offset, new.size) != expected:
                raise ValueError(f"Bad resource after patch: {name}")
        if hash_file(base) != baseline:
            raise ValueError("Original German ISO changed during patching")
        os.replace(pending, dest)
        return baseline  # RC3 checkpoint: already independently verified base SHA.
    except BaseException:
        pending.unlink(missing_ok=True)
        raise
