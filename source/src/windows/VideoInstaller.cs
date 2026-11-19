// Harvester GOG DE V7 - additional, mode-specific video CD images.
// Compiled with DeutschPatcher.cs into the same Windows .NET Framework 4.x EXE.
// Installer source compiles during setup using the built-in Windows .NET Framework C# compiler.
// VideoManifest and all 196 verified HVP payloads exist and native tests pass.
using System;
using System.IO;
using System.IO.Compression;
using System.Xml;
using System.Text;
using System.Linq;
using System.Collections.Generic;

public partial class DeutschPatcher {
  // SHA256 of the V7 development manifest. The final build pins the
  // verified manifest as an immutable SHA-256 integrity checkpoint.
  const string VideoManifestHash = "f56a5708018820bcbc6af0c6fb71f3f775a39b317bd1626eb898aa04aaf7162d";
  static readonly string[] VideoModes = {"10px", "11px"};
  static readonly string[] VideoDiscs = {"HARVEST.DAT", "HARVEST3.DAT", "HARVEST4.DAT"};
  class VideoDelta {
    public string Mode, Cd, IsoPath, SourceHash, TargetHash, PatchFile, PatchHash;
  }
  static List<VideoDelta> ReadVideoManifest() {
    string f=Path.Combine(Package,"VideoUntertitel","VideoManifest.xml");
    Require(File.Exists(f),"VideoManifest.xml fehlt; keine vollstaendige 10/11px-Installation moeglich");
    Require(VideoManifestHash.Length==64 && Hash(f)==VideoManifestHash,"Video-Manifest nicht fuer diese Installer-Version freigegeben");
    var x=new XmlDocument();x.XmlResolver=null;x.Load(f);
    XmlNode root=x.SelectSingleNode("/HarvesterVideoManifest");
    Require(root!=null && A(root,"version")=="1" && A(root,"ready")=="release", "FST-Untertitelpaket nicht freigegeben oder Manifest-Version falsch");
    var list=new List<VideoDelta>();var unique=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
    foreach(XmlNode n in root.SelectNodes("Fst")) {
      var d=new VideoDelta{Mode=A(n,"mode"),Cd=A(n,"cd"),IsoPath=A(n,"path"),
        SourceHash=A(n,"source_sha256"),TargetHash=A(n,"target_sha256"),
        PatchFile=A(n,"patch"),PatchHash=A(n,"patch_sha256")};
      Require(VideoModes.Contains(d.Mode) && VideoDiscs.Contains(d.Cd),"Unbekannter Video-Modus oder CD");
      Require(d.IsoPath.StartsWith("GRAPHIC/FST/",StringComparison.Ordinal) && d.IsoPath.EndsWith(".FST",StringComparison.Ordinal) &&
              d.IsoPath==d.IsoPath.ToUpperInvariant() && !d.IsoPath.Contains("..") && !d.IsoPath.Contains("\\"),"Unsicherer FST-Pfad");
      Require(d.PatchFile.EndsWith(".hvp",StringComparison.Ordinal) && Path.GetFileName(d.PatchFile)==d.PatchFile &&
              d.PatchFile.IndexOfAny(Path.GetInvalidFileNameChars())<0,"Unsicherer Delta-Paketpfad");
      foreach(string h in new[]{d.SourceHash,d.TargetHash,d.PatchHash})
        Require(h.Length==64 && h.All(ch=>"0123456789abcdef".IndexOf(ch)>=0),"FST-Hash fehlt oder ungueltig");
      Require(unique.Add(d.Mode+"/"+d.Cd+"/"+d.IsoPath),"Doppelte FST-Patchposition");
      list.Add(d);
    }
    Require(list.Count==196,"Es muessen genau 98 FST-Eintraege pro Schriftgroesse vorliegen");
    foreach(string mode in VideoModes) {
      Require(list.Count(d=>d.Mode==mode)==98, "Falsche FST-Anzahl: "+mode);
      Require(list.Count(d=>d.Mode==mode && d.Cd=="HARVEST.DAT")==45, "CD1 unvollstaendig: "+mode);
      Require(list.Count(d=>d.Mode==mode && d.Cd=="HARVEST3.DAT")==44, "CD3 unvollstaendig: "+mode);
      Require(list.Count(d=>d.Mode==mode && d.Cd=="HARVEST4.DAT")==9, "CD4 unvollstaendig: "+mode);
    }
    var a=list.Where(d=>d.Mode=="10px").ToDictionary(d=>d.Cd+"/"+d.IsoPath,d=>d.SourceHash,StringComparer.OrdinalIgnoreCase);
    foreach(var d in list.Where(d=>d.Mode=="11px"))
      Require(a.ContainsKey(d.Cd+"/"+d.IsoPath) && a[d.Cd+"/"+d.IsoPath]==d.SourceHash,"10/11px-Quellmapping widerspricht sich");
    foreach(var d in list) {
      string p=Path.Combine(Package,"VideoUntertitel","Patches",d.PatchFile);
      Require(File.Exists(p) && Hash(p)==d.PatchHash,"FST-Delta fehlt oder ist beschaedigt: "+d.PatchFile);
    }
    return list;
  }
  // .hvp = raw DEFLATE over HVP1 | int32 operation count | copy/insert commands.
  // Copy: byte 0, int64 source offset, int32 length. Insert: byte 1, int32
  // length, raw target bytes. No memory-unsafe external binaries are run.
  static void ApplyVideoDelta(string sourceFst,string compressedPatch,string resultFst,string expectedHash) {
    using(var src=File.OpenRead(sourceFst))
    using(var file=File.OpenRead(compressedPatch))
    using(var df=new DeflateStream(file,CompressionMode.Decompress))
    using(var rd=new BinaryReader(df,Encoding.ASCII))
    using(var output=new FileStream(resultFst,FileMode.CreateNew,FileAccess.Write)) {
      byte[] magic=rd.ReadBytes(4);Require(magic.SequenceEqual(new byte[]{72,86,80,49}),"FST-Delta-Magie ungueltig");
      int count=rd.ReadInt32();Require(count>0 && count<1000000,"FST-Delta-Operationszahl ungueltig");
      byte[] buffer=new byte[2*1024*1024];
      for(int i=0;i<count;i++) {
        byte op=rd.ReadByte();
        if(op==0) {
          long off=rd.ReadInt64();int len=rd.ReadInt32();
          Require(off>=0 && len>0 && off<=src.Length && len<=src.Length-off,"FST-Delta-COPY ausserhalb Quellvideo");
          CopySpan(src,output,off,len);
        }else if(op==1) {
          int len=rd.ReadInt32();Require(len>0 && len<512*1024*1024,"FST-Delta-INSERT ungueltig");
          while(len>0) {int n=rd.Read(buffer,0,Math.Min(len,buffer.Length));Require(n>0,"Unvollstaendiges FST-Delta");output.Write(buffer,0,n);len-=n;}
        }else throw new Exception("Unbekannte FST-Delta-Operation");
      }
      Require(df.ReadByte()==-1,"Ueberzaehlige FST-Delta-Daten");
      output.Flush(true);
    }
    Require(Hash(resultFst)==expectedHash,"FST-Ziel-Hash stimmt nicht; Video nicht freigegeben");
  }
  static void PatchVideoIso(string germanIso,string targetIso,List<VideoDelta> patches,string tmp) {
    var before=Scan(germanIso);
    foreach(var p in patches)Require(before.ContainsKey(p.IsoPath) && !before[p.IsoPath].Directory &&
      SpanHash(germanIso,before[p.IsoPath])==p.SourceHash,"FST-Quelle nicht die bestaetigte Originalfassung: "+p.Cd+"/"+p.IsoPath);
    string baselineHash=Hash(germanIso);
    File.Copy(germanIso,targetIso,false);File.SetAttributes(targetIso,FileAttributes.Normal);
    Require(Hash(targetIso)==baselineHash,"Deutsche CD-Moduskopie abweichend");
    Directory.CreateDirectory(tmp);
    using(var f=new FileStream(targetIso,FileMode.Open,FileAccess.ReadWrite)) {
      int n=0;
      foreach(var p in patches) {
        Entry entry=before[p.IsoPath];
        string orig=Path.Combine(tmp,"orig_"+n.ToString()+".fst");
        string modified=Path.Combine(tmp,"patched_"+n.ToString()+".fst");
        using(var old=File.OpenRead(germanIso))using(var o=new FileStream(orig,FileMode.CreateNew,FileAccess.Write))CopySpan(old,o,entry.Offset,entry.Size);
        Require(Hash(orig)==p.SourceHash,"Quell-FST-Bytes ungleich Manifest");
        ApplyVideoDelta(orig,Path.Combine(Package,"VideoUntertitel","Patches",p.PatchFile),modified,p.TargetHash);
        f.Position=f.Length;
        while(f.Position%Sector!=0)f.WriteByte(0);
        long off=f.Position;
        using(var data=File.OpenRead(modified))CopySpan(data,f,0,data.Length);
        long len=f.Position-off;
        while(f.Position%Sector!=0)f.WriteByte(0);
        PutBoth(f,entry.Record+2,checked((uint)(off/Sector)));
        PutBoth(f,entry.Record+10,checked((uint)len));
        File.Delete(orig);File.Delete(modified);n++;
      }
      PutBoth(f,16*Sector+80,checked((uint)(f.Length/Sector)));
      f.Flush(true);
    }
    var after=Scan(targetIso);
    Require(before.Keys.OrderBy(x=>x).SequenceEqual(after.Keys.OrderBy(x=>x)),"Video-CD-Dateiindex veraendert");
    var pmap=patches.ToDictionary(p=>p.IsoPath,p=>p.TargetHash,StringComparer.OrdinalIgnoreCase);
    foreach(var kv in before) {
      if(kv.Value.Directory)continue;
      string expected=pmap.ContainsKey(kv.Key)?pmap[kv.Key]:SpanHash(germanIso,kv.Value);
      Require(SpanHash(targetIso,after[kv.Key])==expected,"Video-CD-Hashfehler: "+kv.Key);
    }
    Require(Hash(germanIso)==baselineHash,"FIX2-CD wurde beim Untertitelbau veraendert");
    Directory.Delete(tmp,true);
  }
  static void BuildVideoModes(string stage,List<VideoDelta> manifest) {
    // Runs only AFTER FIX2 has built its German CD images. FIX2 never replaces
    // GRAPHIC/FST, therefore FST source hashes remain identical to the original.
    foreach(string mode in VideoModes)foreach(string cd in VideoDiscs) {
      string folder=Path.Combine(stage,"VideoUntertitel",mode);Directory.CreateDirectory(folder);
      string output=Path.Combine(folder,cd),basis=Path.Combine(stage,cd);
      var items=manifest.Where(d=>d.Mode==mode && d.Cd==cd).OrderBy(d=>d.IsoPath).ToList();
      Console.WriteLine("Bereite Video-CD " + cd + " / " + mode + " vor ("+items.Count+" Filme)");
      PatchVideoIso(basis,output,items,Path.Combine(stage,"_VIDEO_FST_TEMP"));
    }
  }
  static void CreateModeLaunchers(string stage) {
    string single=Path.Combine(stage,"dosbox_harvester_single.conf");
    byte[] raw=File.ReadAllBytes(single);
    string original=Encoding.GetEncoding(1252).GetString(raw);
    string tag="imgmount d -t iso -fs iso \"..\\HARVEST.DAT\" \"..\\HARVEST3.DAT\" \"..\\HARVEST4.DAT\"";
    Require(original.Contains(tag) && original.IndexOf(tag,StringComparison.Ordinal)==original.LastIndexOf(tag,StringComparison.Ordinal),"DOSBox-Quellkonfiguration unbekannt");
    Require(original.Contains("mount C \"..\\cloud_saves\" -t overlay") && original.Contains("harvest.exe"),"Gemeinsames Spielstand-Overlay fehlt");
    string[] names={"Harvester_Deutsch_ohne_Videountertitel.cmd","Harvester_Deutsch_mit_10px_Videountertiteln.cmd","Harvester_Deutsch_mit_11px_Videountertiteln.cmd"};
    string[] configs={"dosbox_harvester_single_ohne_VideoUT.conf","dosbox_harvester_single_10px.conf","dosbox_harvester_single_11px.conf"};
    string[] modes={"", "10px", "11px"};
    for(int i=0;i<3;i++) {
      string mount=i==0?tag:"imgmount d -t iso -fs iso \"..\\VideoUntertitel\\"+modes[i]+"\\HARVEST.DAT\" \"..\\VideoUntertitel\\"+modes[i]+"\\HARVEST3.DAT\" \"..\\VideoUntertitel\\"+modes[i]+"\\HARVEST4.DAT\"";
      string config=original.Replace(tag,mount);
      File.WriteAllBytes(Path.Combine(stage,configs[i]),Encoding.GetEncoding(1252).GetBytes(config));
      string cmd="@echo off\r\ncd /d \"%~dp0DOSBOX\" || exit /b 1\r\n\"DOSBox.exe\" -conf \"..\\dosbox_harvester.conf\" -conf \"..\\"+configs[i]+"\"\r\n";
      File.WriteAllText(Path.Combine(stage,names[i]),cmd,Encoding.ASCII);
    }
  }
}
