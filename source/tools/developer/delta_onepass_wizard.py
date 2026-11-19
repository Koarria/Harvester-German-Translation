#!/usr/bin/env python3
"""Private Windows wizard for the frozen Harvester Delta OnePass prototype.

No game data is embedded or uploaded by this GUI. The existing OnePass CLI
always performs the full hash/preflight gate before creating a fresh target.
The GUI drives it as a child process, never with shell=True.
"""
from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

import installer as rc3
import delta_core_shadow_installer as core
import delta_video_addon as video
import delta_embedded_bundle as embedded
import originalvergleich_gog as audit

def decode_log_output(raw: bytes, fallback: str = "cp850") -> str:
    """Decode UTF-8 Python logs and legacy OEM output from the native patcher.

    The native Windows C# process can emit the local OEM code page while the
    Python OnePass wrapper emits UTF-8. Decoding all child output as UTF-8 with
    'replace' destroyed German umlauts (e.g. VORPRUEFUNG in the GUI).
    """
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        try:
            return raw.decode(fallback, "replace")
        except LookupError:
            return raw.decode("cp850", "replace")


def advanced_options_active(reference: str, workers: str,
                            resume_video: bool, continue_core: bool) -> bool:
    """Never hide a non-default recovery, reference or worker configuration."""
    return bool(reference.strip() or workers != "auto"
                or resume_video or continue_core)


def planned_target_label(parent: str) -> str:
    """Show the exact separate target without altering its name or path."""
    if not parent.strip():
        return "Zielordner: Bitte zuerst einen bestehenden übergeordneten Ordner auswählen."
    return "Zielordner: " + str(Path(parent.strip()) / core.TEST_TARGET_NAME)


STARTER_HELP = (
    "Harvester_Deutsch_ohne_Videountertitel.cmd  – deutsche Texte, ohne Video-UT\n"
    "Harvester_Deutsch_mit_10px_Videountertiteln.cmd  – Video-UT mit 10 px\n"
    "Harvester_Deutsch_mit_11px_Videountertiteln.cmd  – Video-UT mit 11 px"
)


def child_command(
    executable: Path, entry_script: Path, frozen: bool,
    source: Path, bundle: Path | None, parent: Path,
    reference: Path | None = None, workers: int | None = None,
    resume: bool = False, execute: bool = False,
    continue_verified_core: bool = False,
) -> list[str]:
    """Argument list, not a shell command; paths may contain spaces/metacharacters."""
    if resume and continue_verified_core:
        raise ValueError("Wiederaufnahmearten können nicht kombiniert werden")
    if workers is not None and (not isinstance(workers, int) or not 1 <= workers <= 4):
        raise ValueError("Ungültige Zahl paralleler Filmprozesse")
    if not str(source).strip() or not str(parent).strip() or (bundle is None and not frozen):
        raise ValueError("Original, Delta-Bundle und Ziel-Elternordner fehlen")
    cmd = [str(executable)] if frozen else [str(executable), str(entry_script)]
    cmd += [
        "--source", str(source),
        "--target-parent", str(parent),
    ]
    if bundle is not None:
        cmd += ["--bundle", str(bundle)]
    # In frozen one-file mode, never pass the GUI's private _MEIPASS path:
    # the child process resolves its own unpacked delta ZIP.
    if reference is not None:
        cmd += ["--reference-rc3b", str(reference)]
    if workers is not None:
        cmd += ["--workers", str(workers)]
    if resume:
        cmd.append("--resume-video")
    if continue_verified_core:
        cmd.append("--continue-verified-core")
    if execute:
        cmd.append("--execute-onepass")
    return cmd


def finished_installation(parent: Path) -> bool:
    """GUI-level completion indicator; full integrity checks remain in OnePass."""
    target = parent / core.TEST_TARGET_NAME
    if not target.is_dir() or target.is_symlink():
        return False
    if (video.video_marker(target).exists() or
            (target / video.WORKDIR).exists() or
            (target / "INSTALLATION_UNVOLLSTAENDIG.txt").exists()):
        return False
    needed = (
        "HARVEST.EXE", *rc3.DISCS, "Deutsch_Pruefnachweis.xml",
        "LIES_MICH_SPIELSTART.txt",
        *video.STARTERS, *video.CONFIGS, *video.OUTPUT_CDS,
    )
    return all((target / name).is_file() and not (target / name).is_symlink()
               for name in needed)


class DeltaWizard:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Harvester GOG Deutsch – Installation")
        root.minsize(790, 540)
        self.events: queue.Queue[tuple] = queue.Queue()
        self.running = False
        self.preflight_signature: tuple | None = None
        self.finished_target: Path | None = None

        detected = rc3.detect_gog()
        self.source = tk.StringVar(value=str(detected) if detected else "")
        self.embedded_delta = embedded.embedded_bundle_path(audit.REPO) is not None
        self.bundle = tk.StringVar()
        self.parent = tk.StringVar()
        self.reference = tk.StringVar()
        self.workers = tk.StringVar(value="auto")
        self.resume = tk.BooleanVar(value=False)
        self.continue_core = tk.BooleanVar(value=False)
        self.advanced_open = tk.BooleanVar(value=False)
        self.target_preview = tk.StringVar()

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame, text="Harvester GOG Deutsch",
            font=("Segoe UI", 16, "bold")
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text=("Deutsche Fanübersetzung für die GOG-Version. "
                  "Das englische Original und vorhandene Spielstände bleiben erhalten."),
            wraplength=750
        ).pack(anchor="w", pady=(6, 14))

        paths = ttk.LabelFrame(frame, text="Schritt 1: Lokale Dateien und Ordner", padding=10)
        paths.pack(fill="x")
        self.path_controls: list[tk.Widget] = []
        self._path_row(paths, 0, "Englisches GOG-Original", self.source, directory=True)
        if self.embedded_delta:
            ttk.Label(
                paths, text="Übersetzungsdaten sind in dieser EXE enthalten (SHA-256-geschützt)",
                wraplength=680
            ).grid(row=1, column=0, columnspan=3, sticky="w", pady=5)
        else:
            self._path_row(paths, 1, "Privates Delta-Bundle (.zip)", self.bundle, directory=False)
        self._path_row(paths, 2, "Übergeordneter Zielordner", self.parent, directory=True)
        detect = ttk.Button(paths, text="GOG automatisch suchen", command=self.detect_source)
        detect.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self.path_controls.append(detect)
        paths.columnconfigure(1, weight=1)

        ttk.Label(
            frame, textvariable=self.target_preview, wraplength=750
        ).pack(anchor="w", pady=(9, 3))
        ttk.Label(
            frame, text=("Das Spiel wird in einem neuen Unterordner „Harvester GOG Deutsch“ installiert. "
                         "Das Original bleibt unverändert; ein bereits vorhandener "
                         "Zielordner wird niemals überschrieben."),
            wraplength=750
        ).pack(anchor="w", pady=(0, 8))

        self.advanced_toggle = ttk.Checkbutton(
            frame, variable=self.advanced_open, command=self.toggle_advanced,
            text="Erweiterte Optionen anzeigen"
        )
        self.advanced_toggle.pack(anchor="w", pady=(2, 2))
        self.path_controls.append(self.advanced_toggle)

        self.advanced_frame = ttk.LabelFrame(
            frame, text="Wiederaufnahme und Leistung", padding=10
        )
        self.advanced_frame.columnconfigure(1, weight=1)

        settings = ttk.Frame(self.advanced_frame)
        settings.grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 4))
        ttk.Label(settings, text="Filmprozesse:").pack(side="left", padx=(0, 6))
        worker_select = ttk.Combobox(
            settings, textvariable=self.workers,
            values=("auto", "1", "2", "3", "4"),
            width=6, state="readonly"
        )
        worker_select.pack(side="left")
        self.path_controls.append(worker_select)

        resume_box = ttk.Checkbutton(
            self.advanced_frame,
            text="Unterbrochene Videobearbeitung fortsetzen",
            variable=self.resume, command=self.change_resume
        )
        resume_box.grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 2))
        self.path_controls.append(resume_box)

        core_continue_check = ttk.Checkbutton(
            self.advanced_frame, variable=self.continue_core, command=self.change_core,
            text="Abgeschlossene Basisinstallation fortsetzen (nur nach Abbruch)"
        )
        core_continue_check.grid(row=3, column=0, columnspan=3, sticky="w", pady=(2, 4))
        self.path_controls.append(core_continue_check)

        # Optional expert action only. The normal install always performs the
        # complete read-only SHA-/resource-/storage preflight itself, *before*
        # the native core can create the new target folder.
        self.preflight_button = ttk.Button(
            self.advanced_frame, text="Nur prüfen (SHA-256) – ohne Installation",
            command=lambda: self.start(False)
        )
        self.preflight_button.grid(row=4, column=0, columnspan=3,
                                   sticky="w", pady=(8, 4))

        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        self.install_button = ttk.Button(
            actions, text="Deutsch installieren", command=lambda: self.start(True)
        )
        self.install_button.pack(side="left")
        self.open_button = ttk.Button(
            actions, text="Spielordner öffnen", command=self.open_target,
            state="disabled"
        )
        self.open_button.pack(side="right")

        ttk.Label(frame, text="Prüf- und Installationsprotokoll (nur auf diesem PC):").pack(
            anchor="w", pady=(13, 4)
        )
        self.log = scrolledtext.ScrolledText(
            frame, height=13, wrap="word", state="disabled", font=("Consolas", 9)
        )
        self.log.pack(fill="both", expand=True)

        self.status = tk.StringVar(value=(
            "GOG- und Zielordner auswählen, dann Deutsch installieren. SHA-256 wird automatisch geprüft."
        ))
        ttk.Label(frame, textvariable=self.status, wraplength=750).pack(
            anchor="w", pady=(8, 0)
        )

        for value in (self.source, self.bundle, self.reference, self.workers):
            value.trace_add("write", lambda *_: self.invalidate())
        self.parent.trace_add("write", lambda *_: self.changed_parent())
        self.refresh_target_preview()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.pump)

    def changed_parent(self):
        self.refresh_target_preview()
        self.invalidate()

    def refresh_target_preview(self):
        self.target_preview.set(planned_target_label(self.parent.get()))

    def toggle_advanced(self):
        if self.advanced_open.get():
            self.advanced_frame.pack(
                fill="x", after=self.advanced_toggle, pady=(5, 9)
            )
            return
        if advanced_options_active(
            self.reference.get(), self.workers.get(),
            self.resume.get(), self.continue_core.get()
        ):
            self.advanced_open.set(True)
            messagebox.showwarning(
                "Erweiterte Optionen noch aktiv",
                "Eine konfigurierte SHA-Referenz, Filmprozesszahl oder "
                "Wiederaufnahme darf nicht versteckt werden. "
                "Bitte zuerst die Werte auf Standard zurücksetzen.",
                parent=self.root
            )
            return
        self.advanced_frame.pack_forget()

    def _path_row(self, parent, row, title, value, directory):
        ttk.Label(parent, text=title + ":").grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=value, width=66)
        entry.grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        choose = ttk.Button(
            parent, text="Durchsuchen",
            command=lambda: self.browse(value, directory)
        )
        choose.grid(row=row, column=2, pady=4)
        self.path_controls.extend((entry, choose))

    def browse(self, value: tk.StringVar, directory: bool):
        candidate = Path(value.get()).expanduser()
        initial = candidate if candidate.is_dir() else candidate.parent
        if not initial.is_dir():
            initial = Path.home()
        if directory:
            result = filedialog.askdirectory(
                parent=self.root, initialdir=str(initial), mustexist=True,
                title="Ordner wählen"
            )
        else:
            result = filedialog.askopenfilename(
                parent=self.root, initialdir=str(initial),
                title="Privates Delta-Bundle-ZIP wählen",
                filetypes=(("ZIP-Dateien", "*.zip"), ("Alle Dateien", "*.*"))
            )
        if result:
            value.set(result)

    def detect_source(self):
        detected = rc3.detect_gog()
        if detected is None:
            messagebox.showinfo(
                "GOG nicht automatisch gefunden",
                "Bitte das englische Originalverzeichnis selbst auswählen. "
                "Die vollständige SHA-256-Prüfung folgt vor jeder Installation.",
                parent=self.root
            )
        else:
            self.source.set(str(detected))
            messagebox.showinfo(
                "GOG gefunden",
                "Kandidat gefunden. Die Integrität wird erst im Preflight bestätigt:\n"
                + str(detected), parent=self.root
            )

    def change_resume(self):
        if self.resume.get():
            self.continue_core.set(False)
        self._update_mode_text()
        self.invalidate()

    def change_core(self):
        if self.continue_core.get():
            self.resume.set(False)
        self._update_mode_text()
        self.invalidate()

    def _update_mode_text(self):
        self.install_button.configure(
            text=("Basisinstallation fortsetzen" if self.continue_core.get()
                  else "Deutsch installieren")
        )

    def invalidate(self):
        self.preflight_signature = None
        if not self.running:
            # Installation requires NO separately approved preflight; the child
            # runs the full immutable-content verification before any writes.
            self.install_button.configure(state="normal")
            # Previously completed copies must not be opened through a button
            # that now visually belongs to a different selected target parent.
            self.finished_target = None
            self.open_button.configure(state="disabled")

    def snapshot(self) -> tuple:
        values = tuple(v.get().strip() for v in (
            self.source, self.bundle, self.parent, self.reference
        ))
        if not values[0] or not values[2] or (not self.embedded_delta and not values[1]):
            raise ValueError("Bitte GOG-Ordner, Ziel-Elternordner und ggf. privates Delta-ZIP auswählen")
        if self.workers.get() not in ("auto", "1", "2", "3", "4"):
            raise ValueError("Filmprozesse: auto oder 1 bis 4")
        worker_count = None if self.workers.get() == "auto" else int(self.workers.get())
        if self.resume.get() and self.continue_core.get():
            raise ValueError("Core-/Video-Fortsetzung nicht gleichzeitig möglich")
        return values + (worker_count, bool(self.resume.get()), bool(self.continue_core.get()))

    def _args(self, config: tuple, execute: bool) -> list[str]:
        source, bundle, parent, reference, workers, resume, continue_core = config
        script = Path(__file__).with_name("delta_onepass_installer.py")
        return child_command(
            Path(sys.executable), script, bool(getattr(sys, "frozen", False)),
            Path(source), None if self.embedded_delta else Path(bundle), Path(parent),
            Path(reference) if reference else None, workers, resume, execute,
            continue_verified_core=continue_core
        )

    def log_line(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip("\r\n") + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_busy(self, busy: bool):
        self.running = busy
        for widget in self.path_controls:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="disabled" if busy else "readonly")
            else:
                widget.configure(state="disabled" if busy else "normal")
        self.preflight_button.configure(state="disabled" if busy else "normal")
        self.install_button.configure(state="disabled" if busy else "normal")
        self.open_button.configure(state=(
            "normal" if not busy and self.finished_target is not None else "disabled"
        ))

    def start(self, execute: bool):
        if self.running:
            return
        try:
            config = self.snapshot()
            command = self._args(config, execute)
        except ValueError as exc:
            messagebox.showerror("Eingabe unvollständig", str(exc), parent=self.root)
            return

        if execute:
            dest = Path(config[2]) / core.TEST_TARGET_NAME
            label = ("Die bereits geprüfte Basisinstallation um die Untertitelvideos ergänzen?"
                     if config[6] else "Harvester als neue deutsche Spielkopie installieren?")
            answer = simpledialog.askstring(
                "Ausdrückliche Zustimmung erforderlich",
                label + "\n\n"
                + "Englisches Original (nur lesend):\n" + config[0] + "\n\n"
                + "Neuer Zielordner:\n" + str(dest) + "\n\n"
                + "Der vollständige SHA-256-Sicherheitscheck läuft automatisch VOR der Installation.\n"
                + "Zum Starten exakt JA eingeben:",
                parent=self.root
            )
            if answer != "JA":
                self.status.set("Installation nicht bestätigt. Keine Installation gestartet.")
                return

        self.status.set(
            "Prüfe SHA-256 und Speicher automatisch; danach wird Deutsch installiert. Fenster nicht schließen." if execute else
            "Prüfung aktiv – Spielordner werden nicht verändert."
        )
        self.log_line(("\n=== AUTOMATISCHE VORPRÜFUNG UND INSTALLATION ===" if execute else "\n=== OPTIONALE SCHREIBGESCHÜTZTE PRÜFUNG ==="))
        self.set_busy(True)
        threading.Thread(
            target=self.run_child, args=(command, config, execute), daemon=True
        ).start()

    def run_child(self, command: list[str], config: tuple, execute: bool):
        try:
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            options = {}
            if os.name == "nt":
                options["creationflags"] = subprocess.CREATE_NO_WINDOW
            with subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                # Raw bytes: UTF-8 Python and OEM-encoded native C# may mix.
                # Decode per line instead of corrupting native German umlauts.
                bufsize=0, env=env, **options
            ) as process:
                if process.stdout is not None:
                    for raw_line in process.stdout:
                        self.events.put(("log", decode_log_output(raw_line)))
                returncode = process.wait()
            self.events.put(("finished", config, execute, returncode))
        except OSError as exc:
            self.events.put(("failed", str(exc)))

    def pump(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log":
                    self.log_line(event[1])
                elif event[0] == "finished":
                    self.process_finished(*event[1:])
                elif event[0] == "failed":
                    self.preflight_signature = None
                    self.set_busy(False)
                    self.status.set("Prozessstart fehlgeschlagen")
                    messagebox.showerror(
                        "EXE konnte nicht gestartet werden", event[1], parent=self.root
                    )
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def process_finished(self, config: tuple, execute: bool, returncode: int):
        self.preflight_signature = None
        if returncode != 0:
            self.status.set(
                "Abbruch: technischen Fehler im Protokoll prüfen. "
                "Unvollständige Installationen nicht starten."
            )
            self.log_line("FEHLER: Installations-/Prüfprozess, Rückgabecode " + str(returncode))
            self.set_busy(False)
            messagebox.showerror(
                "Nicht abgeschlossen",
                "Die Prüfung oder Installation wurde abgebrochen. "
                "Eine unvollständige Installation darf nicht gestartet "
                "oder ohne erneute Prüfung fortgesetzt werden.",
                parent=self.root
            )
            return
        if not execute:
            self.preflight_signature = config
            self.status.set(
                "SHA-256-Vorprüfung PASS. Die Installation ist auch ohne vorherige separate Prüfung möglich."
            )
            self.log_line("PASS: Die Prüfung hat keine neue Spielkopie erstellt.")
            self.set_busy(False)
            return

        target = Path(config[2]) / core.TEST_TARGET_NAME
        if not finished_installation(Path(config[2])):
            self.status.set("Unvollständig: die fertigen Starter-/CD-Dateien fehlen")
            self.log_line("STOPP: Kein vollständiger Installationsnachweis im Zielordner.")
            self.set_busy(False)
            messagebox.showerror(
                "Installation nicht als fertig bestätigt",
                "Die neue Spielkopie darf noch nicht gestartet werden.", parent=self.root
            )
            return
        self.finished_target = target
        self.status.set("Installation abgeschlossen. Drei Spielstarter verfügbar.")
        self.set_busy(False)
        messagebox.showinfo(
            "Harvester GOG Deutsch – Installation abgeschlossen",
            "Die neue Spielkopie liegt unter:\n" + str(target)
            + "\n\nDrei Startmöglichkeiten:\n" + STARTER_HELP
            + "\n\nVor dem Wechsel das Spiel beenden. "
              "Die Originalinstallation bleibt unverändert.",
            parent=self.root
        )

    def open_target(self):
        if self.finished_target is not None and finished_installation(
            self.finished_target.parent
        ):
            try:
                os.startfile(str(self.finished_target))
            except OSError as exc:
                messagebox.showerror("Explorer konnte nicht öffnen", str(exc), parent=self.root)

    def on_close(self):
        if self.running:
            messagebox.showwarning(
                "Installation/Prüfung noch aktiv",
                "Bitte den laufenden Schritt abschließen lassen. "
                "Ein harter Abbruch kann eine unvollständige Installation hinterlassen.",
                parent=self.root
            )
            return
        self.root.destroy()


def launch_gui() -> int:
    if os.name != "nt":
        print("Der grafische Harvester-Installer ist nur unter Windows verfügbar.",
              file=sys.stderr)
        return 2
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print("Windows-Oberfläche konnte nicht gestartet werden: " + str(exc),
              file=sys.stderr)
        return 2
    DeltaWizard(root)
    root.mainloop()
    return 0
