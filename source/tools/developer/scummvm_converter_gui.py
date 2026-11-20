#!/usr/bin/env python3
"""Windows GUI for Harvester GOG Deutsch ScummVM converter v1.0.0."""
from __future__ import annotations

from pathlib import Path
import queue
import sys
import threading

import scummvm_converter as core


def selftest() -> int:
    if core.MODES != ("ohne", "10px", "11px") or len(core.DISC_IMAGES) != 3:
        return 2
    if not (core.ROOT / "payload" / "Regeln.xml").is_file():
        return 3
    if not (core.ROOT / "payload" / "VideoManifest.xml").is_file():
        return 4
    return 0


def launch() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    class Wizard:
        def __init__(self):
            self.root = tk.Tk()
            self.root.title("Harvester GOG Deutsch -> ScummVM")
            self.root.resizable(False, False)
            self.root.geometry("790x485")
            self.running = False
            self.notifications = queue.Queue()
            self.english = tk.StringVar()
            self.german = tk.StringVar()
            self.target_parent = tk.StringVar()
            self.mode = tk.StringVar(value="10px")
            self.status = tk.StringVar(value="Bitte die drei Ordner auswählen.")
            base = ttk.Frame(self.root, padding=16)
            base.pack(fill="both", expand=True)
            ttk.Label(base, text="Deutsche Harvester-GOG-Version für ScummVM vorbereiten",
                      font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 9))
            ttk.Label(base, text="ScummVM 2026.4.0 · Deutsche Fanübersetzung für eine eigene GOG-Version",
                      wraplength=730).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))
            fields = (
                ("Unveränderte englische GOG-Installation:", self.english),
                ("Installierte deutsche GOG-Version (Harvester GOG Deutsch):", self.german),
                ("Ausgabe-Oberordner (neue ScummVM-Kopie):", self.target_parent),
            )
            self.controls = []
            for k,(title,variable) in enumerate(fields):
                row = 2 + k * 2
                ttk.Label(base,text=title).grid(row=row,column=0,columnspan=3,sticky="w",pady=(0,2))
                entry=ttk.Entry(base,textvariable=variable,width=79)
                entry.grid(row=row+1,column=0,columnspan=2,sticky="we",pady=(0,10))
                btn=ttk.Button(base,text="Durchsuchen",command=lambda v=variable:self.browse(v))
                btn.grid(row=row+1,column=2,sticky="e",padx=(12,0),pady=(0,10))
                self.controls.extend((entry,btn))
            ttk.Label(base,text="Videountertitel:").grid(row=8,column=0,sticky="w")
            modes=ttk.Combobox(base,textvariable=self.mode,values=core.MODES,state="readonly",width=15)
            modes.grid(row=8,column=1,sticky="w",pady=(0,8))
            self.controls.append(modes)
            self.start=ttk.Button(base,text="ScummVM-Kopie erstellen",command=self.begin)
            self.start.grid(row=9,column=0,sticky="w",pady=(5,8))
            self.spinner=ttk.Progressbar(base,mode="indeterminate",length=300)
            self.spinner.grid(row=9,column=1,columnspan=2,sticky="w",padx=(15,0))
            ttk.Label(base,textvariable=self.status,wraplength=730).grid(row=10,column=0,columnspan=3,sticky="w")
            self.log = tk.Text(base,width=91,height=7,wrap="word",state="disabled",font=("Consolas",9))
            self.log.grid(row=11,column=0,columnspan=3,sticky="we",pady=(8,0))
            self.append("Das englische Original, die deutsche DOSBox-Version und alle Spielstände bleiben unverändert.")
            self.append("ScummVM benutzt eigene Spielstände; vorhandene DOSBox-Spielstände werden nicht übernommen.")
            self.append("Die ursprüngliche HARVEST.EXE wird nur für ScummVM-Erkennung kopiert.")
            self.root.protocol("WM_DELETE_WINDOW",self.close)
            self.root.after(120,self.poll)

        def append(self,msg):
            self.log.configure(state="normal")
            self.log.insert("end",msg+"\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        def browse(self,var):
            path=filedialog.askdirectory(parent=self.root,title="Harvester-Verzeichnis auswählen")
            if path:
                var.set(path)

        def begin(self):
            if self.running:
                return
            a,b,c=self.english.get().strip(),self.german.get().strip(),self.target_parent.get().strip()
            if not a or not b or not c:
                messagebox.showerror("Angaben fehlen","Bitte alle drei Ordner angeben.",parent=self.root)
                return
            mode=self.mode.get()
            target=Path(c)/ (core.TARGET_PREFIX+" "+mode)
            if not messagebox.askyesno(
                    "Neue ScummVM-Datenkopie anlegen",
                    "Es wird ausschließlich ein NEUER Ordner erstellt:\n\n"+str(target)+
                    "\n\nVorher laufen automatische SHA-256- und ISO-Prüfungen.\n"
                    "Die bestehenden GOG-Ordner bleiben unverändert.\n\nFortfahren?",
                    parent=self.root):
                return
            self.running=True
            self.start.configure(state="disabled")
            for widget in self.controls:
                widget.configure(state="disabled")
            self.spinner.start(12)
            self.status.set("Prüfe Originaldateien und extrahiere danach 3 deutsche CDs. Fenster geöffnet lassen.")
            self.append("Starte automatische Prüfung/Kopie für Modus "+mode+".")
            def work():
                try:
                    report=core.convert(Path(a),Path(b),Path(c),mode,True)
                    self.notifications.put(("ok",(str(target),report)))
                except Exception as e:
                    self.notifications.put(("error",str(e)))
            threading.Thread(target=work,daemon=True).start()

        def poll(self):
            try:
                kind,result=self.notifications.get_nowait()
            except queue.Empty:
                pass
            else:
                self.running=False
                self.spinner.stop()
                self.start.configure(state="normal")
                for widget in self.controls:
                    widget.configure(state="normal" if widget.winfo_class()!="TCombobox" else "readonly")
                if kind=="ok":
                    folder,report=result
                    self.status.set("Erfolgreich! Die deutsche ScummVM-Kopie ist einsatzbereit.")
                    self.append("Datendateien erfolgreich erstellt: "+folder)
                    self.append("CD-Quelldateien: "+str(report["disc_file_counts"]))
                    messagebox.showinfo("Datenkopie erstellt",
                        "ScummVM öffnen und diesen Ordner über 'Spiel hinzufügen' auswählen:\n\n"+
                        folder+
                        "\n\nDie Original-EXE dient nur zur Erkennung. "
                        "Deine vorhandenen ScummVM-Spielstände kannst du weiter laden. "
                        "DOSBox-Spielstände werden nicht automatisch übernommen.",
                        parent=self.root)
                else:
                    self.status.set("Keine ScummVM-Kopie freigegeben; siehe Fehlermeldung.")
                    self.append("ABGEBROCHEN: "+result)
                    messagebox.showerror("ScummVM-Konverter abgebrochen",result,parent=self.root)
            self.root.after(120,self.poll)

        def close(self):
            if self.running:
                messagebox.showwarning("Prüfung läuft",
                                       "Bitte nicht während der Extraktion schließen.",parent=self.root)
                return
            self.root.destroy()

    wizard=Wizard()
    wizard.root.mainloop()


if __name__=="__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    launch()
