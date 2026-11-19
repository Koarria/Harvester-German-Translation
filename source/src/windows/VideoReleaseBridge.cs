// Final installer extension. Reuses FIX2 hash/ISO methods; original GOG files are read-only.
using System;
using System.IO;
using System.Collections.Generic;
using System.Linq;
using System.Xml;
public partial class DeutschPatcher {
    private static List<VideoDelta> VerifiedReleasePatches;
    public static int ReleasePreflight(string package) {
        Package=Path.GetFullPath(package);
        VerifiedReleasePatches=ReadVideoManifest();
        return VerifiedReleasePatches.Count;
    }
    public static void ReleaseCreateModes(string package,string germanGame) {
        Package=Path.GetFullPath(package);
        germanGame=Path.GetFullPath(germanGame);
        Require(Directory.Exists(germanGame),"Deutsche FIX2-Spielkopie fehlt");
        Require(File.Exists(Path.Combine(germanGame,"Deutsch_Pruefnachweis.xml")),"FIX2-Pruefnachweis fehlt");
        Require(File.Exists(Path.Combine(germanGame,"dosbox_harvester_single.conf")),"GOG DOSBox-Konfiguration fehlt");
        Require(File.Exists(Path.Combine(germanGame,"DOSBOX","DOSBox.exe")),"GOG DOSBox.exe fehlt");
        Require(Hash(Path.Combine(germanGame,"HARVEST.EXE"))=="c461e05414a38b11c7e7d27c1ad47df823e2bdb87f2087639281cbc39cdb32b2", "HARVEST.EXE entspricht nicht FIX2 - keine Aenderungen");
        foreach(string cd in VideoDiscs)Require(File.Exists(Path.Combine(germanGame,cd)),"Deutsche FIX2-CD fehlt: "+cd);
        var verified=VerifiedReleasePatches??ReadVideoManifest();
        Require(verified.Count==196,"Untertitelquellen unvollstaendig");
        BuildVideoModes(germanGame,verified);
        CreateModeLaunchers(germanGame);
        foreach(string mode in VideoModes)foreach(string cd in VideoDiscs)
            Require(File.Exists(Path.Combine(germanGame,"VideoUntertitel",mode,cd)),"Video-CD wurde nicht gebaut: "+mode+"/"+cd);
        foreach(string name in new[]{"Harvester_Deutsch_ohne_Videountertitel.cmd","Harvester_Deutsch_mit_10px_Videountertiteln.cmd","Harvester_Deutsch_mit_11px_Videountertiteln.cmd"})
            Require(File.Exists(Path.Combine(germanGame,name)),"Spielstarter fehlt: "+name);
        ArchiveLegacyStarterAndUpdateProof(germanGame);
    }
    static void ArchiveLegacyStarterAndUpdateProof(string game) {
        string oldName="Harvester_Deutsch_starten.cmd";
        string oldLauncher=Path.Combine(game,oldName);
        string archivedRelative=Path.Combine("VideoUntertitel","ALTER_FIX2_STARTER.txt");
        string archived=Path.Combine(game,archivedRelative);
        string proofPath=Path.Combine(game,"Deutsch_Pruefnachweis.xml");
        var doc=new XmlDocument();doc.XmlResolver=null;doc.Load(proofPath);
        Require(doc.DocumentElement!=null && doc.DocumentElement.Name=="HarvesterDeutschInstallation","FIX2-Pruefnachweis ungueltig");
        var root=doc.DocumentElement;
        if(File.Exists(oldLauncher)) {
            Require(!File.Exists(archived),"Archiv fuer alten FIX2-Starter existiert schon");
            string oldHash=Hash(oldLauncher);
            File.Move(oldLauncher,archived);
            Require(Hash(archived)==oldHash,"Alten FIX2-Starter nicht unveraendert archiviert");
            bool present=false;
            foreach(XmlElement e in doc.SelectNodes("/HarvesterDeutschInstallation/Datei")) {
                if(string.Equals(e.GetAttribute("pfad"),oldName,StringComparison.OrdinalIgnoreCase)) {
                    Require(e.GetAttribute("sha256")==oldHash,"Alten FIX2-Starter nicht im Pruefnachweis erkannt");
                    e.SetAttribute("pfad",archivedRelative);present=true;break;
                }
            }
            if(!present) {
                var e=doc.CreateElement("Datei"); e.SetAttribute("pfad",archivedRelative);e.SetAttribute("sha256",oldHash);root.AppendChild(e);
            }
        }
        var outputs=new List<string>{"Harvester_Deutsch_ohne_Videountertitel.cmd","Harvester_Deutsch_mit_10px_Videountertiteln.cmd","Harvester_Deutsch_mit_11px_Videountertiteln.cmd", "dosbox_harvester_single_ohne_VideoUT.conf","dosbox_harvester_single_10px.conf","dosbox_harvester_single_11px.conf"};
        foreach(string mode in VideoModes)foreach(string cd in VideoDiscs)outputs.Add(Path.Combine("VideoUntertitel",mode,cd));
        foreach(string relative in outputs) {
            string full=Path.Combine(game,relative);
            Require(File.Exists(full),"Nachweisdatei fehlt: "+relative);
            var node=doc.CreateElement("Datei");node.SetAttribute("pfad",relative);node.SetAttribute("sha256",Hash(full));root.AppendChild(node);
        }
        root.SetAttribute("video_untertitel_release","FINAL_V1_2026_11_09_66_FILME_10_11PX_LODGE");
        string temp=proofPath+".tmp_"+Guid.NewGuid().ToString("N");
        doc.Save(temp);
        File.Replace(temp,proofPath,null);
        Require(Directory.GetFiles(game,"Harvester_Deutsch_*.cmd",SearchOption.TopDirectoryOnly).Length==3,"Es muessen exakt drei deutsche Start-CMDs vorhanden sein");
    }
}
