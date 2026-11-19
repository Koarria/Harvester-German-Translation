#!/usr/bin/env python3
"""Read-only integrity audit for published Harvester translation resources.

Does not publish assets, mutate the Delta, or access original game files.
Checks provenance/layout, source-vs-embedded manifest integrity, subtitle files
and absence of obvious sensitive local paths; not a legal rights clearance.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[1]
ZIP=ROOT/"resources"/"delta"/"Harvester_GOG_Deutsch_Delta_v1.0.0.zip"
RULES=ROOT/"resources"/"payload"/"Regeln.xml"
VIDEO=ROOT/"resources"/"payload"/"VideoManifest.xml"
SUBS=ROOT/"resources"/"payload"/"subtitles"
NATIVE=ROOT/"resources"/"payload"/"Harvester_Deutsch_Patcher.exe"
EXPECTED_NATIVE_SHA="9b8fada91a55db9c069309deb69137277cc951b154781523f7571c704f7a62e0"
HEX64=r"[0-9a-f]{64}"
EXPECTED_BUNDLE_SHA="e690300e4d858992c140d00eceee1ef9e6a4911f32faf98ed7feba93f5794768"
EXPECTED_RULES_SHA="7c72b55366546080544d603fbe4f24aa128d80c043a56cad36db4db40327266b"
BAD_PATHS=re.compile(r"(?:[A-Za-z]:\\Users\\|/home/[^/\s]+/|/Users/[^/\s]+/|/mnt/data/|github_pat_[A-Za-z0-9_]{15}|ghp_[A-Za-z0-9]{15}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY)",re.I)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def check(condition,what):
    if not condition:
        raise ValueError("STOP: "+what)

def no_secrets(data,kind):
    txt=data.decode("utf-8-sig")
    check(not BAD_PATHS.search(txt),"possible local path or secret in "+kind)
    check("\x00" not in txt,"NUL in "+kind)
    return txt

def zip_audit():
    raw=ZIP.read_bytes()
    check(len(raw)==328000 and sha(raw)==EXPECTED_BUNDLE_SHA,"Delta differs from real user-tested GitHub build")
    check(not ZIP.is_symlink(),"delta is symlink")
    with zipfile.ZipFile(ZIP) as archive:
        infos=archive.infolist()
        names=[i.filename for i in infos]
        check(len(names)==22 and len(names)==len(set(names)),"Delta ZIP must have exactly 22 unique entries")
        check(all(not x.is_dir() and x.compress_type==zipfile.ZIP_STORED and not x.flag_bits&1
                  and x.file_size<2_000_000 and not x.filename.startswith("/")
                  and ".." not in Path(x.filename).parts and "\\" not in x.filename
                  and (x.external_attr>>16)&0o170000 in (0,0o100000)
                  for x in infos),"Delta has unsafe ZIP entry")
        check(set(names).issuperset({"Regeln.xml","bundle.json"}),"Missing delta manifests")
        xml=archive.read("Regeln.xml")
        check(xml==RULES.read_bytes(),"Embedded rules differ from pinned released XML")
        check(sha(xml)==EXPECTED_RULES_SHA,"Pinned rules SHA mismatch")
        rules=ET.fromstring(xml)
        check(rules.tag=="HarvesterPatch" and len(rules.findall("./Assets/Asset"))==18,"Invalid rules/target mapping")
        check(len(rules.findall("./Image"))==3,"Unexpected original ISO count")
        no_secrets(xml,"Regeln.xml")
        data=json.loads(no_secrets(archive.read("bundle.json"),"bundle.json"))
        check(data.get("schema")=="harvester-gog-private-delta-bundle-v1","Wrong bundle schema")
        check(data.get("private_only") is True and data.get("legal_clearance") is False,"Original builder metadata changed")
        check(len(data.get("variants",[]))==20 and len(data.get("image_uses",[]))==48,"Missing binary variants or original refs")
        expected={"bundle.json","Regeln.xml"}
        for variant in data["variants"]:
            src,dst=variant["source_sha256"],variant["target_sha256"]
            check(re.fullmatch(HEX64,src) and re.fullmatch(HEX64,dst),"Variant has invalid checksum")
            file=f"deltas/{src}_{dst}.z"
            check(file==variant["member"],"Variant filename does not match manifest")
            check(variant["codec"] in ("bitmap-v2","copyadd-v1"),"Unknown delta codec")
            expected.add(file)
            packed=archive.read(file)
            check(len(packed)==variant["packed_bytes"] and sha(packed)==variant["packed_sha256"],
                  "Delta byte checksum mismatch")
            d=zlib.decompressobj()
            target_len=variant["unpacked_bytes"]
            check(0<target_len<=2_000_000,"Unsafe expanded delta size")
            content=d.decompress(packed,target_len+1)
            check(d.eof and not d.unconsumed_tail and not d.unused_data and len(content)==target_len,
                  "Bad zlib delta")
            magic=b"HVBDP02\x00" if variant["codec"]=="bitmap-v2" else b"HVVDL01\x00"
            check(content.startswith(magic),"Unknown binary delta encoding")
        check(set(names)==expected,"Unexpected files embedded in Delta ZIP")
        check(len(data["loose_root_uses"])==2,"Unexpected loose files mapping")
        return {"bundle_sha256":sha(raw),"zip_members":len(infos),"variants":20,
                "mapped_resource_uses":48,"translated_targets":18,
                "legacy_flags":"private_only=true,legal_clearance=false (historical metadata unchanged)"}

def srt_audit():
    children=list(SUBS.rglob("*"))
    check(all(not p.is_symlink() and (p.is_dir() or p.is_file()) for p in children),"Subtitle link")
    fs=sorted(p for p in children if p.is_file())
    categories={k:sorted((SUBS/k).glob("*.srt")) for k in ("10px","11px","endings")}
    check(len(fs)==128 and all(p.suffix==".srt" for p in fs),"Subtitles not exactly 128 SRTs")
    check([len(categories[k]) for k in ("10px","11px","endings")]==[62,62,4],"Wrong Subtitle group sizes")
    fst10={p.name.replace("_de_10px.srt","") for p in categories["10px"]}
    fst11={p.name.replace("_de_11px.srt","") for p in categories["11px"]}
    check(fst10==fst11 and len(fst10)==62,"Subtitle modes don't correspond")
    for p in fs:
        s=no_secrets(p.read_bytes(),p.relative_to(ROOT).as_posix())
        check(re.search(r"\d\d:\d\d:\d\d,\d{3}\s*-->\s*\d\d:\d\d:\d\d,\d{3}",s),"Invalid SRT format "+p.name)
        check(len(s)<=100000,"Oversized subtitle "+p.name)
    data=VIDEO.read_bytes()
    no_secrets(data,"VideoManifest.xml")
    video=ET.fromstring(data)
    check(video.tag=="HarvesterVideoManifest","Invalid video manifest root")
    entries=video.findall(".//Fst")
    modes={name:sum(e.get("mode")==name for e in entries) for name in ("10px","11px")}
    check(len(entries)==196 and modes=={"10px":98,"11px":98},"Wrong video CD index coverage")
    check(len(set(e.get("film_id") for e in entries))==66,"Wrong video source count")
    return {"subtitle_files":len(fs),"normal_per_size":62,"ending_subtitles":4,
            "video_manifest_entries":len(entries),"unique_film_ids":66,
            "video_manifest_sha256":sha(data)}

def main():
    check(sha(NATIVE.read_bytes())==EXPECTED_NATIVE_SHA and NATIVE.stat().st_size==25600,"Native C# patcher no longer matches tested v1.0.0")
    report={"schema":"harvester-public-resource-readonly-audit-v1",
            "source":"Exact v1.0.0 original ZIP and payload files from user-confirmed CI installer",
            "delta":zip_audit(),"native_patcher_sha256":sha(NATIVE.read_bytes()),
            "subtitles_and_video_manifest":srt_audit(),
            "binary_original_games_present":False,"legal_clearance_given":False}
    print("AUDIT PASS: 22 ZIP members, 20 binary delta variants, 18 translation targets")
    print("AUDIT PASS: 128 subtitle SRTs, 196 video manifest entries; 66 film sources")
    print("AUDIT PASS: Original SHA-256-pinned C# native patcher, 25600 bytes")
    print("AUDIT NOTICE: embedded ZIP manifest marks historical private_only=true and legal_clearance=false.")
    print("This does not assess copyright ownership; original game files were not read.")
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return 0
if __name__=="__main__":
    try:
        raise SystemExit(main())
    except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,zlib.error,ET.ParseError) as error:
        print("PUBLIC RESOURCE AUDIT FAILED:",str(error),file=sys.stderr)
        raise SystemExit(2)
