#!/usr/bin/env python3
"""Private one-pass Harvester delta developer installer (NOT a public installer).

Combines the REAL-GOG-tested FIX2 delta core + 66-film video addon by calling
their unchanged implementations. A single explicit start uses a NEW folder;
a second explicit --resume-video ONLY resumes a validated video checkpoint.

It does not modify the English original, existing RC3b, or save files. No
published game assets or private binary delta ZIP are uploaded to GitHub.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import sys

# The developer helpers are kept under tools/developer, while the unchanged
# RC3b film renderer lives in the repository root/runtime.
# The no-Python player prototype resolves its bundled payload from PyInstaller's
# private extraction directory; the normal developer source uses the repo root.
REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2])).resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import delta_core_shadow_installer as core
import delta_video_addon as video
import originalvergleich_gog as audit
import unified_delta_bundle as delta
import delta_embedded_bundle as embedded
import installer as rc3

if getattr(sys, "frozen", False):
    # audit is also imported by core, video and delta; one module instance.
    # Its default REPO derived from __file__ must be corrected for one-file
    # PyInstaller extraction, without altering the stable repository modules.
    audit.REPO = REPO_ROOT

REPORT_SCHEMA = "harvester-gog-deutsch-installationsbericht-v1"


def choose_bundle_argument(requested: Path | None, root: Path = REPO_ROOT) -> Path:
    """Resolve a locally bundled Delta inside this process's own _MEIPASS.

    Refuse overrides in a bundled frozen installer: the legacy developer
    CLI may still use an explicitly selected private ZIP.
    """
    packed = embedded.embedded_bundle_path(root)
    if packed is not None:
        if requested is not None:
            raise OnePassError("Ein-Datei-EXE benutzt nur das eingebaute Delta, kein externes --bundle")
        return packed
    if requested is None:
        raise OnePassError("Kein eingebautes Delta vorhanden: lokales privates Delta-ZIP erforderlich")
    return requested



class OnePassError(ValueError):
    pass


def inspect_paths(source: Path, bundle_path: Path, parent: Path,
                  reference: Path | None, resume_video: bool,
                  continue_verified_core: bool=False) -> tuple[Path,Path,Path,Path|None]:
    """Decide target without writing, reject any existing copy by default."""
    if any(x.is_symlink() for x in (source, bundle_path, parent) if x is not None):
        raise OnePassError("GOG-Original, Delta-ZIP und Ziel-Elternordner dürfen keine Links sein")
    if reference is not None and reference.is_symlink():
        raise OnePassError("RC3b-Referenz darf kein Link sein")
    src = source.expanduser().resolve()
    pack = bundle_path.expanduser().resolve()
    dst_parent = parent.expanduser().resolve()
    dest = dst_parent / core.TEST_TARGET_NAME
    if not dst_parent.is_dir():
        raise OnePassError("Ziel-Elternordner muss bereits existieren")
    if resume_video and continue_verified_core:
        raise OnePassError("Zwei verschiedene Fortsetzungsarten dürfen nicht kombiniert werden")
    if resume_video:
        if not dest.is_dir() or dest.is_symlink():
            raise OnePassError("Wiederaufnahme erfordert eine zuvor geprüfte deutsche Spielkopie")
        if not video.video_marker(dest).is_file() or not video.state_file(dest).is_file():
            raise OnePassError("Kein gültiger eigener Video-Unvollständig-Checkpoint vorhanden")
        if not pack.is_file() or not 0 < pack.stat().st_size <= core.MAX_PRIVATE_ZIP_BYTES:
            raise OnePassError("Private Delta-ZIP-Datei fehlt/ist unzulässig")
        # Video validates pinned source/CD/core hashes & checks RC3b reference.
        src,dest,ref = video.validate_source_and_test_copy(src,dest,audit.REPO,reference)
        return src,pack,dest,ref
    if continue_verified_core:
        if not dest.is_dir() or dest.is_symlink():
            raise OnePassError("Nur eine vorhandene, geprüfte Basisinstallation darf fortgesetzt werden")
        if (video.video_marker(dest).exists() or video.state_file(dest).exists() or
                (dest / video.WORKDIR).exists() or
                (dest / "VideoUntertitel").exists() or
                any((dest / n).exists() for n in (*video.STARTERS, *video.CONFIGS))):
            raise OnePassError("Core-Fortsetzung nur ohne jeden Video-Checkpoint oder Video-Ausgaben")
        if not pack.is_file() or not 0 < pack.stat().st_size <= core.MAX_PRIVATE_ZIP_BYTES:
            raise OnePassError("Privates Delta-Bundle fehlt/ist unzulässig")
        src,dest,ref = video.validate_source_and_test_copy(
            src,dest,audit.REPO,reference)
        # A native proof may contain target-specific paths. Verify *every*
        # registered core file and the target/root/rules bindings, read-only.
        video.core_proof.verify_core_proof(src,dest)
        return src,pack,dest,ref
    src,pack,dest,ref = core.verify_paths(src,pack,dst_parent,reference)
    if dest is None or dest.exists():
        raise OnePassError("Zielordner existiert bereits und wird nicht überschrieben")
    return src,pack,dest,ref


def validate_report_location(source: Path, dest: Path, reference: Path | None,
                             output_dir: Path) -> Path:
    """Never store even the path-free JSON report in a game/repo directory."""
    report_dir = audit.valid_report_directory(output_dir,source)
    target = dest.resolve()
    repo = audit.REPO.resolve()
    check = [target,repo]
    if reference is not None:
        check.append(reference.resolve())
    if any(core.nested(x,report_dir.resolve()) or
           core.nested(report_dir.resolve(),x) for x in check):
        raise OnePassError("Installationsbericht muss außerhalb der Spiel- und Programmdaten liegen")
    return report_dir


def preflight(source: Path,bundle_path: Path,parent: Path,
              reference: Path | None, resume_video: bool=False,
              report_dir: Path | None=None, continue_verified_core: bool=False
              ) -> tuple[Path,Path,Path,Path|None,list[dict],dict]:
    """All expensive verification BEFORE creating any game copy/marker."""
    src,pack,dest,ref = inspect_paths(
        source,bundle_path,parent,reference,resume_video,continue_verified_core)
    if report_dir is not None:
        validate_report_location(src,dest,ref,report_dir)
    if not rc3.is_original_gog(src):
        raise OnePassError("Unbekanntes/nicht originales GOG-Installationsverzeichnis")
    # This does not require the 18 complete German FIX2 .bin assets, because
    # the private verified delta ZIP is the sole FIX2 target content source.
    videos = video.validate_video_inputs(audit.REPO)
    video.verify_original_source(src,audit.REPO)
    core.check_verified_core(audit.REPO/"payload"/core.CORE_EXE)
    with pack.open("rb") as f:
        zip_bytes=f.read()
    result=delta.verify_bundle_bytes(src,zip_bytes)
    if (result["verified_original_cd_sha256"]!=3 or
        result["verified_iso_and_xfile_uses"]!=48 or
        result["reconstructed_unique_pairs"]!=20 or
        result["target_asset_count"]!=18):
        raise OnePassError("Delta-Bundle nicht vollständig gehasht/reproduzierbar")
    if not resume_video:
        # Additional original-CD copies are only needed for a fresh core.
        if not continue_verified_core:
            core.check_disk_reserve(src,dest)
        rc3.free_space_check(src,dest)
    return src,pack,dest,ref,videos,result


def make_report(core_result: dict|None,video_result: dict,
                bundle_proof: dict,resumed: bool,
                continued_verified_core: bool=False) -> dict:
    """Strict allowlisted statistics/hashes only. Never emit user paths or data."""
    keys=("real_video_addon_test","source_gog_original_sha256_unchanged",
          "delta_core_base_sha256_unchanged","video_original_sources",
          "subtitle_rendered_variants","video_iso_image_count",
          "launcher_count","launcher_config_count","manifest_fst_locations",
          "files_sha256","sha256_equal_to_existing_rc3b",
          "patched_exe_sha256","patched_cd_sha256",
          "final_fix2_proof_sha256","existing_rc3b_modified",
          "game_saves_modified_by_addon")
    video_safe={k:video_result[k] for k in keys}
    if (not video_safe["real_video_addon_test"] or
        video_safe["video_original_sources"]!=66 or
        video_safe["subtitle_rendered_variants"]!=132 or
        video_safe["video_iso_image_count"]!=6 or
        video_safe["launcher_count"]!=3 or
        video_safe["launcher_config_count"]!=3 or
        video_safe["manifest_fst_locations"]!=196 or
        set(video_safe["files_sha256"])!=set(video.VIDEO_FILES) or
        not video_safe["source_gog_original_sha256_unchanged"] or
        not video_safe["delta_core_base_sha256_unchanged"] or
        video_safe["existing_rc3b_modified"] or
        video_safe["game_saves_modified_by_addon"]):
        raise OnePassError("Video-Add-on-Ergebnis unvollständig")
    matches=video_safe["sha256_equal_to_existing_rc3b"]
    if matches and (set(matches)!=set(video.VIDEO_FILES) or
                    not all(matches.values())):
        raise OnePassError("Optionaler RC3b-Vergleich ist nicht vollständig PASS")
    if (bundle_proof["verified_iso_and_xfile_uses"]!=48 or
        bundle_proof["reconstructed_unique_pairs"]!=20 or
        bundle_proof["target_asset_count"]!=18):
        raise OnePassError("Delta-Bundle im Ergebnis unvollständig")
    if core_result is not None and (
        not core_result["real_core_test"] or
        not core_result["original_source_sha256_unchanged"] or
        core_result["existing_rc3b_modified"] or
        core_result["reconstructed_assets"]!=18):
        raise OnePassError("FIX2-Core-Abnahme fehlt")
    report = {
        "schema": REPORT_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "is_python_free_player_installer": bool(
            getattr(sys, "frozen", False)
            and embedded.embedded_bundle_path(REPO_ROOT) is not None
        ),
        "is_new_full_delta_installation_from_one_start": not resumed and not continued_verified_core,
        "resumed_video_only": resumed,
        "continued_preverified_core_only": continued_verified_core,
        "game_or_original_saves_modified_by_installer": False,
        "contains_game_or_translated_bytes_or_paths": False,
        "bundle_variants_verified":20,
        "iso_xfile_uses_verified":48,
        "target_asset_count":18,
        "core_result": {
            "created_now": core_result is not None,
            "matched_reference_core_files": (
                sum(core_result["optional_reference_comparison"].values())
                if core_result is not None else None
            ),
            "source_unchanged": (
                core_result["original_source_sha256_unchanged"]
                if core_result is not None else video_safe["source_gog_original_sha256_unchanged"]
            ),
            "core_sha256":video_safe["patched_exe_sha256"],
            "core_cds_sha256":video_safe["patched_cd_sha256"],
        },
        "video_result": {
            k:v for k,v in video_safe.items() if k not in (
                "real_video_addon_test",
                "sha256_equal_to_existing_rc3b",
                "existing_rc3b_modified",
            )
        },
    }
    # Only report optional developer reference comparisons when actually run.
    # The usual player's report must not show misleading "0 matches" or old RC names.
    if matches:
        report["reference_video_sha256_matches"] = len(matches)
    if core_result is None or not core_result["optional_reference_comparison"]:
        report["core_result"].pop("matched_reference_core_files")
    return report


def perform(source:Path,bundle_path:Path,parent:Path,
            reference:Path|None=None,workers:int|None=None,
            report_dir:Path|None=None,resume_video:bool=False,
            execute:bool=False,continue_verified_core:bool=False) -> dict|None:
    if workers is not None and not 1<=workers<=4:
        raise OnePassError("Nur 1 bis 4 parallele Film-Prozesse erlaubt")
    if resume_video and continue_verified_core:
        raise OnePassError("Wiederaufnahme von Video und Core nicht kombinierbar")
    if report_dir is None:
        report_dir=Path.home()/"Documents"/"Harvester_Deutsch_Installationsberichte"
    src,pack,dest,ref,records,proof=preflight(
        source,bundle_path,parent,reference,resume_video,report_dir,
        continue_verified_core)
    if not execute:
        print("Nur SHA-256-/Manifest-/Ressourcen-/Speicher-VORPRÜFUNG PASS; nichts geschrieben.")
        return None
    if os.name!="nt":
        raise OnePassError("Die Harvester-Installation erfordert Windows")
    core_result=None
    if continue_verified_core:
        print("Bereits geprüfte Basisinstallation wird fortgesetzt; die Basisdateien werden nicht erneut geändert.",flush=True)
    elif not resume_video:
        print("Erstelle eine neue deutsche Spielkopie mit 18 verifizierten Ressourcen ...",flush=True)
        core_result=core.core_only_install(
            src,pack.read_bytes(),dest,audit.REPO/"payload"/core.CORE_EXE,ref)
    else:
        print("Unterbrochene Videobearbeitung wird sicher fortgesetzt ...",flush=True)
    print("Erstelle deutsche Videountertitel für 66 Filme in zwei Schriftgrößen ...",flush=True)
    video_result=video.run_video_addon(src,dest,audit.REPO,records,ref,workers)
    result=make_report(core_result,video_result,proof,resume_video,continue_verified_core)
    folder=validate_report_location(src,dest,ref,report_dir)
    folder.mkdir(parents=True,exist_ok=True)
    filename=("Harvester_Deutsch_Installation_"+
              datetime.now().strftime("%Y%m%d_%H%M%S_%f")+".json")
    out=folder/filename
    # If writing the report fails, the video checkpoint marker remains,
    # and the user can explicitly resume without touching original/RC3b.
    with out.open("x",encoding="utf-8") as fd:
        json.dump(result,fd,indent=2,ensure_ascii=False)
        fd.write("\n")
    video.video_marker(dest).unlink()
    shutil.rmtree(dest/video.WORKDIR,ignore_errors=True)
    print("INSTALLATION ERFOLGREICH: Harvester GOG Deutsch wurde in einem eigenen Ordner erstellt.")
    print("Das englische Original und vorhandene Spielstände wurden nicht verändert.")
    print("Technischer Installationsbericht:",out)
    return result


def packaged_preflight() -> dict:
    """Read-only self-test, even on GitHub CI without any proprietary GOG ISO.

    Deliberately verifies ONLY the four narrowly required payload components:
    original FIX2 rules, video manifest, native FIX2 patcher, and 132 SRT uses.
    The 18 complete FIX2 .bin targets must never be packed into a frozen EXE.
    """
    payload=REPO_ROOT/"payload"
    rules=payload/"Regeln.xml"
    video_manifest=payload/"VideoManifest.xml"
    native=payload/core.CORE_EXE
    for path in (rules,video_manifest,native):
        if path.is_symlink() or not path.is_file():
            raise OnePassError("Fehlende private Payload-Komponente: "+path.name)
    if core.hash_file(rules)!=audit.EXPECTED_RULES_SHA256:
        raise OnePassError("Bundled FIX2-Regeln-SHA-256 stimmt nicht")
    if core.hash_file(video_manifest)!=rc3.MANIFEST_HASH:
        raise OnePassError("Bundled VideoManifest-SHA-256 stimmt nicht")
    core.check_verified_core(native)
    rows=video.validate_video_inputs(REPO_ROOT)
    if len(rows)!=196 or len({r["film_id"] for r in rows})!=66:
        raise OnePassError("Nicht 66 Filme/196 Positionen im Bundle vorhanden")
    embedded_pack = embedded.embedded_bundle_path(REPO_ROOT)
    if embedded_pack is not None:
        print("EIN-DATEI-BUNDLE-PREFLIGHT PASS: lokal eingebautes Delta mit SHA-256 und ZIP-Struktur geprüft.")
    if getattr(sys,"frozen",False) and (payload/"Daten").exists():
        raise OnePassError("UNZULÄSSIGE vollständige FIX2-Binärpayload in EXE")
    print("EXE-/PAKET-PREFLIGHT: Originalregeln, VideoManifest, native EXE und 132 SRT PASS.")
    if getattr(sys, "frozen", False):
        print("EXE-Paketprüfung PASS: Keine vollständigen FIX2-Zieldateien in der EXE.")
    else:
        print("Quellcode-Vorprüfung PASS (enthält keine Aussage über einen EXE-Paketbau).")
    print("Paketprüfung abgeschlossen. Vor jeder Installation wird die GOG-Version geprüft.")
    return {
        "rules_sha256":audit.EXPECTED_RULES_SHA256,
        "video_manifest_sha256":rc3.MANIFEST_HASH,
        "native_core_sha256":core.CORE_SHA256,
        "manifest_locations":196,
        "film_count":66,
        "full_FIX2_asset_files_bundled":False,
        "embedded_private_delta_verified":embedded_pack is not None,
        "legal_clearance":False,
    }


def main() -> int:
    parser=argparse.ArgumentParser(
        description="Harvester GOG Deutsch – Windows-Installationsassistent"
    )
    parser.add_argument("--gui",action="store_true",
                        help="Grafischen Windows-Installationsassistenten öffnen")
    parser.add_argument("--wizard-module-preflight",action="store_true",
                        help="Wizard-Modul nur importieren und prüfen, ohne GUI/GOG-Zugriffe")
    parser.add_argument("--source",type=Path)
    parser.add_argument("--bundle",type=Path,
                        help="Nur alte Entwickler-Builds: lokales privates Delta-ZIP")
    parser.add_argument("--embedded-bundle-preflight",action="store_true",
                        help="Nur lokal eingebautes Delta verifizieren (ohne GOG)")
    parser.add_argument("--target-parent",type=Path)
    parser.add_argument("--packaged-preflight",action="store_true",
                        help="Nur die EXE-Payload ohne Original-GOG und ohne Spielkopie prüfen")
    parser.add_argument("--reference-rc3b",type=Path)
    parser.add_argument("--workers",type=int,choices=range(1,5))
    parser.add_argument("--execute-onepass",action="store_true")
    parser.add_argument("--resume-video",action="store_true",
                        help="Nur explizite Wiederaufnahme eines gültigen Video-Checkpoints")
    parser.add_argument("--continue-verified-core",action="store_true",
                        help="Vorhandenen unmarkierten Core nach strikter XML-/SHA-Prüfung nur um Video erweitern")
    parser.add_argument("--output-dir",type=Path,default=(
        Path.home()/"Documents"/"Harvester_Deutsch_Installationsberichte"
    ))
    args=parser.parse_args()
    try:
        if args.wizard_module_preflight:
            if len(sys.argv) != 2:
                parser.error("--wizard-module-preflight nur ohne weitere Parameter verwenden")
            import delta_onepass_wizard as wizard
            if len(wizard.STARTER_HELP.strip().splitlines()) != 3:
                raise OnePassError("Wizard hat keine drei vollständigen Starterhinweise")
            print("WIZARD-MODUL-PREFLIGHT PASS: Modul und drei Starterhinweise importiert; keine GUI oder GOG-Daten geöffnet.")
            return 0
        # Frozen EXE should open a user-friendly window on double click.
        # The source developer CLI keeps its mandatory explicit arguments.
        launch_wizard = args.gui or (getattr(sys, "frozen", False) and len(sys.argv) == 1)
        if launch_wizard:
            if args.gui and len(sys.argv) != 2:
                parser.error("--gui nur ohne weitere Parameter verwenden")
            import delta_onepass_wizard
            return delta_onepass_wizard.launch_gui()
        if args.packaged_preflight:
            packaged_preflight()
            return 0
        if args.embedded_bundle_preflight:
            if len(sys.argv) != 2:
                parser.error("--embedded-bundle-preflight nur ohne weitere Parameter verwenden")
            if embedded.embedded_bundle_path(REPO_ROOT) is None:
                raise OnePassError("EXE hat kein lokal eingebautes Delta-Bundle")
            print("EINGEBAUTES PRIVATES DELTA SHA-/ZIP-PREFLIGHT PASS. Kein GOG-Zugriff.")
            return 0
        if args.source is None or args.target_parent is None:
            parser.error("--source und --target-parent gemeinsam erforderlich")
        pack = choose_bundle_argument(args.bundle)
        perform(args.source,pack,args.target_parent,args.reference_rc3b,
                args.workers,args.output_dir,args.resume_video,args.execute_onepass,
                args.continue_verified_core)
        return 0
    except (OnePassError,embedded.EmbeddedDeltaError,
            core.ShadowInstallerError,video.DeltaVideoError,
            audit.AuditError,delta.BundleError,OSError,ValueError,KeyError,
            json.JSONDecodeError) as exc:
        print("HARVESTER-INSTALLATION ABGEBROCHEN:",exc,file=sys.stderr)
        print("Kein bestehendes RC3b, GOG-Original oder Spielstand verändern. "
              "Eine unvollständige Installation nicht starten.")
        return 2


if __name__=="__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
