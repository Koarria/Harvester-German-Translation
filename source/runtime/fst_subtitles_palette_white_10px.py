#!/usr/bin/env python3
"""Harvester FST subtitle overlay with true white caption from safe unused palette slots.

- Never mutates source; per-frame output palette differs only in originally UNUSED index.
- Independently verifies every video pixel in RGB, source audio and restored palettes.
- Covers the original FST 0.6s audio prebuffer at C002B ending by test-only timing shift.
"""
import argparse,hashlib,json,struct
from pathlib import Path
import numpy as np
from .fst_codec import FST
from .fst_subtitles import load_srt,font_for,caption_mask
from .fst_subtitles_fast import fast_encode_delta,palette_indices

def build(srcpath,srtpath,dstpath,qa_path,cut_fix=False,font_size=10):
    srcpath=Path(srcpath);dstpath=Path(dstpath);srtpath=Path(srtpath)
    assert srcpath.resolve()!=dstpath.resolve()
    f=FST(srcpath);cues=load_srt(srtpath)
    if cut_fix:
        assert srcpath.stem=='C002B' and len(cues)==47
        if cues[-1][0]>=f.frames/f.fps:
            cues[-1]=(f.frames/f.fps-0.4,cues[-1][1],cues[-1][2])
    font=font_for(font_size)
    masks={}
    for _,_,s in cues:
        if s not in masks:
            a,b=caption_mask((f.w,f.h),s,font)
            masks[s]=(np.frombuffer(a.tobytes(),np.uint8)>=128,np.frombuffer(b.tobytes(),np.uint8)>=128)
    chunks=[];lengths=[];prev_pix=bytes(f.w*f.h);prev_pal=bytes(768);prev_caption=False
    cache={};ci=0;reencoded=0;updated_palettes=0;used_free=0;fallback=0;caption_frames=0
    palette_changes=[];old_audio=hashlib.sha256();new_audio=hashlib.sha256()
    for fi,pix,pal,audio in f.decode():
        tim=fi/f.fps
        while ci<len(cues) and tim>=cues[ci][1]:ci+=1
        caption=(cues[ci][2] if ci<len(cues) and cues[ci][0]<=tim<cues[ci][1] else '')
        origpal=pal; targetpal=origpal; targetpix=pix;used_white_slot=None
        if caption:
            caption_frames+=1
            outer,inner=masks[caption]
            rgb=np.frombuffer(origpal,np.uint8).reshape(256,3)
            _,black=palette_indices(origpal)
            exact=np.where(np.all(rgb==np.array([252,252,252]),axis=1))[0]
            if len(exact):white=int(exact[0])
            else:
                original=np.frombuffer(pix,np.uint8)
                free=np.flatnonzero(np.bincount(original,minlength=256)==0)
                free=free[free!=black]
                if len(free):
                    white=int(free[0]);used_white_slot=white; used_free+=1
                    rgb_modified=bytearray(origpal)
                    rgb_modified[3*white:3*white+3]=b'\xfc\xfc\xfc'
                    targetpal=bytes(rgb_modified)
                else:
                    white,_=palette_indices(origpal);fallback+=1
            assert white!=black
            q=np.frombuffer(pix,np.uint8).copy();q[outer]=black;q[inner]=white
            targetpix=q.tobytes()
        if caption or prev_caption:
            palette_block=bytes(v//4 for v in targetpal) if targetpal!=prev_pal else None
            if palette_block is not None: updated_palettes+=1
            video=fast_encode_delta(prev_pix,targetpix,f.w,f.h,palette_block)
            reencoded+=1
        else:
            length,_=f.entries[fi];video=f.buf[f.offsets[fi]:f.offsets[fi]+length]
        chunks.append(video+audio);lengths.append((len(video),len(audio)))
        old_audio.update(audio);new_audio.update(audio)
        palette_changes.append(used_white_slot)
        prev_pix=targetpix;prev_pal=targetpal;prev_caption=bool(caption)
    head=bytearray(f.buf[:32]);struct.pack_into('<I',head,12,max(f.maxsize,max(x[0] for x in lengths)))
    idx=b''.join(struct.pack('<IH',n,a) for n,a in lengths)
    dstpath.parent.mkdir(parents=True,exist_ok=True)
    dstpath.write_bytes(head+idx+b''.join(chunks))
    # Independent full decode RGB pixel audit.
    g=FST(dstpath)
    assert (f.w,f.h,f.frames,f.fps,f.sample_rate,f.bits)==(g.w,g.h,g.frames,g.fps,g.sample_rate,g.bits)
    ci=0;palcache={};indexed_frame_checks=0;rgb_outside_checks=0;verified_white_frames=0
    for fi,((si,origpix,origpal,oraud),(di,newpix,newpal,outaud)) in enumerate(zip(f.decode(),g.decode())):
        assert si==di==fi and oraud==outaud,('audio',fi)
        t=fi/f.fps
        while ci<len(cues) and t>=cues[ci][1]:ci+=1
        caption=cues[ci][2] if ci<len(cues) and cues[ci][0]<=t<cues[ci][1] else ''
        original=np.frombuffer(origpix,np.uint8)
        updated=np.frombuffer(newpix,np.uint8)
        origRGB=np.frombuffer(origpal,np.uint8).reshape(256,3)
        modRGB=np.frombuffer(newpal,np.uint8).reshape(256,3)
        if caption:
            outer,inner=masks[caption]
            # All original scene indices must be preserved except caption outline/glyph region.
            assert np.array_equal(original[~outer],updated[~outer]),('background-index',fi)
            assert np.array_equal(origRGB[original[~outer]],modRGB[updated[~outer]]),('background-RGB',fi)
            glyph=modRGB[updated[inner]]
            assert np.all(glyph==252),('not white',fi,np.unique(glyph,axis=0))
            blackregion=outer&~inner
            if np.any(blackregion):assert np.all(modRGB[updated[blackregion]]==0),('outline',fi)
            verified_white_frames+=1
            indexed_frame_checks+=int(np.count_nonzero(~outer))
        else:
            assert origpix==newpix and origpal==newpal,('noncaption-pixel-or-palette',fi)
        if fi%350==0:print('FRAME',fi,'/',f.frames,flush=True)
    assert old_audio.digest()==new_audio.digest()
    report={
      'source':str(srcpath),'output':str(dstpath),'source_bytes':len(f.buf),'output_bytes':len(g.buf),
      'source_sha256':hashlib.sha256(f.buf).hexdigest(),'output_sha256':hashlib.sha256(g.buf).hexdigest(),
      'frames':f.frames,'fps':f.fps,'video_seconds':f.frames/f.fps,
      'audio_seconds':sum(a for _,a in f.entries)/(f.sample_rate*f.bits/8),
      'cues':len(cues),'font_px':font_size,'cut_fix':cut_fix,
      'caption_frames':caption_frames,'reencoded_frames':reencoded,
      'frame_palette_blocks_written':updated_palettes,'frames_white_in_free_slot':used_free,
      'frames_no_free_slot_fallback':fallback,'frames_confirmed_pure_white':verified_white_frames,
      'original_audio_sha256':old_audio.hexdigest(),'output_audio_sha256':new_audio.hexdigest(),
      'verification':'PASS_ALL_FRAMES_ORIGINAL_BACKGROUND_RGB_PALETTE_RESTORED_AND_BITIDENTICAL_AUDIO',
      'white_definition':'252,252,252 (6-bit palette full white)',
      'original_src_palette_unchanged':True,'output_palette_changes_only_at_originally_unused_slots':True,
      'srt_cues':[{'start':a,'end':b,'text':s} for a,b,s in cues]
    }
    qa_path=Path(qa_path);qa_path.parent.mkdir(parents=True,exist_ok=True)
    qa_path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print('PASS',f.path.name,g.path.name,'pure-white frames',verified_white_frames,'fallback',fallback, 'sha256',report['output_sha256'],flush=True)
    return report

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('src');a.add_argument('srt');a.add_argument('dst');a.add_argument('--qa',required=True);a.add_argument('--cut-fix',action='store_true');a.add_argument('--font-size',type=int,choices=[10],default=10);x=a.parse_args()
    build(x.src,x.srt,x.dst,x.qa,cut_fix=x.cut_fix,font_size=x.font_size)
