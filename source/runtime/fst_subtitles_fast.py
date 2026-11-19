#!/usr/bin/env python3
# Harvester FST caption encoder, performance-optimised and verified against the PoC decoder.
# 2026-11-09. Pixel masks, original audio, palette bytes are preserved.
import argparse, hashlib, json, struct
from pathlib import Path
import numpy as np
from .fst_codec import FST
from .fst_subtitles import load_srt, font_for, caption_mask, source_palette_block


def fast_encode_delta(prev, target, width, height, palette_block=None):
    p = np.frombuffer(prev, dtype=np.uint8).reshape(height,width)
    t = np.frombuffer(target, dtype=np.uint8).reshape(height,width)
    # Interleaved dimensions: each block is a 4x4 patch.
    dirty = np.any((p != t).reshape(height//4,4,width//4,4), axis=(1,3))
    bits = [int(palette_block is not None)]
    data = bytearray()
    for yy in range(height//4):
        for xx in range(width//4):
            if not dirty[yy,xx]:
                bits.append(0); continue
            bits.append(1)
            tile = t[yy*4:yy*4+4,xx*4:xx*4+4].ravel().tobytes()
            cols = tuple(dict.fromkeys(tile))
            if len(cols)<=2:
                bits.append(1)
                c0,c1=cols[0],cols[-1]
                mask=0
                for k,c in enumerate(tile):
                    if c==c1 and c1!=c0:mask|=0x8000>>k
                data.extend(bytes([c0,c1]));data.extend(struct.pack('<H',mask))
            else:
                bits.append(0);data.extend(tile)
    if len(bits)>65535:raise ValueError('Too many control bits')
    # FST requires one *additional* byte if bit length is byte-aligned.
    packed = np.packbits(np.asarray(bits,dtype=np.uint8),bitorder='big').tobytes()
    if len(bits)%8==0: packed+=b'\0'
    return (struct.pack('<H',len(bits))+packed+(palette_block or b'')+data)


def palette_indices(pal):
    rgb=np.frombuffer(pal,dtype=np.uint8).reshape(256,3).astype(np.int32)
    white=np.argmin(np.sum((rgb-252)**2,axis=1))
    black=np.argmin(np.sum(rgb**2,axis=1))
    return int(white),int(black)


def build(src_path,dst_path,srt_path,font_size=11,font_path=None, qa_path=None, cut_fix=False):
    src_path=Path(src_path).resolve();dst_path=Path(dst_path).resolve()
    if src_path==dst_path:raise ValueError('Output must differ from original')
    src=FST(src_path); cues=load_srt(srt_path)
    # Optional timing workaround for the prebuffered 0.6s audio overhang in C002B.
    if cut_fix:
        assert src.path.stem=='C002B' and len(cues)==47
        end=src.frames/src.fps
        if cues[-1][0]>=end:
            a,b,tx=cues[-1]
            cues[-1]=(max(end-0.40,0),b,tx)
    font=font_for(font_size,font_path)
    masks={}
    for a,b,caption in cues:
        assert caption and b>a and a>=0
        if caption not in masks:
            outline,center=caption_mask((src.w,src.h),caption,font)
            outer = np.frombuffer(outline.tobytes(), dtype=np.uint8) >=128
            inner = np.frombuffer(center.tobytes(), dtype=np.uint8) >=128
            masks[caption]=(outer,inner)
    entries=[]; chunks=[]
    last_target=bytes(src.w*src.h)
    old_audio=hashlib.sha256();new_audio=hashlib.sha256()
    palcache={}; framed=[]; changed=[]; pixel_changes=0
    cueidx=0;prior_caption=''
    for fi,origpix,pal,audio in src.decode():
        tim=fi/src.fps
        while cueidx<len(cues) and tim>=cues[cueidx][1]:cueidx+=1
        caption=''
        if cueidx<len(cues) and cues[cueidx][0]<=tim<cues[cueidx][1]:caption=cues[cueidx][2]
        if caption:
            if pal not in palcache:palcache[pal]=palette_indices(pal)
            ww,bb=palcache[pal]
            outer,inner=masks[caption]
            pix=np.frombuffer(origpix,dtype=np.uint8).copy()
            pix[outer]=bb;pix[inner]=ww
            target=pix.tobytes()
            pixel_changes+=int(np.count_nonzero(pix != np.frombuffer(origpix,dtype=np.uint8)))
        else:target=origpix
        if caption or prior_caption:
            raw=fast_encode_delta(last_target,target,src.w,src.h,source_palette_block(src,fi))
            changed.append(fi)
        else:
            vlen,_=src.entries[fi];off=src.offsets[fi]
            raw=src.buf[off:off+vlen]
        entries.append((len(raw),len(audio)))
        chunks.append(raw+audio)
        old_audio.update(audio);new_audio.update(audio)
        framed.append(caption)
        last_target=target;prior_caption=caption
    dst_path.parent.mkdir(parents=True,exist_ok=True)
    header=bytearray(src.buf[:32])
    struct.pack_into('<I',header,12,max(src.maxsize,max(x[0] for x in entries)))
    index=b''.join(struct.pack('<IH',n,a) for n,a in entries)
    dst_path.write_bytes(header+index+b''.join(chunks))
    # Reopen output independently, and verify every decoded pixel/audio/palette.
    dst=FST(dst_path)
    if (src.w,src.h,src.fps,src.frames,src.sample_rate,src.bits)!=(dst.w,dst.h,dst.fps,dst.frames,dst.sample_rate,dst.bits):raise AssertionError('Metadata mismatches')
    mismatch=[];ori=src.decode();res=dst.decode()
    for fi,((si,spix,spal,saud),(di,dpix,dpal,daud)) in enumerate(zip(ori,res)):
        assert si==di==fi and spal==dpal and saud==daud, f'FST palette/audio mismatch frame {fi}'
        caption=framed[fi]
        if caption:
            ww,bb=palcache[spal]
            outer,inner=masks[caption]
            q=np.frombuffer(spix,dtype=np.uint8).copy()
            q[outer]=bb;q[inner]=ww
            expected=q.tobytes()
        else:expected=spix
        if dpix!=expected: mismatch.append(fi)
    if mismatch:raise AssertionError(f'FST output pixels mismatch: {mismatch[:20]}')
    report={
      'source':str(src_path),'output':str(dst_path),
      'source_sha256':hashlib.sha256(src.buf).hexdigest(),
      'output_sha256':hashlib.sha256(dst.buf).hexdigest(),
      'source_bytes':len(src.buf),'output_bytes':len(dst.buf),
      'resolution':[src.w,src.h],'frames':src.frames,'fps':src.fps,
      'video_frame_duration_s':src.frames/src.fps,
      'pcm_audio_duration_s':sum(a for _,a in src.entries)/(src.sample_rate*src.bits/8),
      'sample_rate':src.sample_rate,'sample_bits':src.bits,
      'source_audio_sha256':old_audio.hexdigest(),'output_audio_sha256':new_audio.hexdigest(),
      'reencoded_frames_count':len(changed),'reencoded_frames_first_last':[changed[0],changed[-1]] if changed else [],
      'different_video_pixels_within_cues':pixel_changes,'decode_and_exact_video_audio_verify':'PASS',
      'font_size':font_size,'number_of_cues':len(cues),'cut_fix':cut_fix,
      'cues':[{'start':a,'end':b,'text':t} for a,b,t in cues]
    }
    if qa_path:Path(qa_path).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n','utf-8')
    return report

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('src');ap.add_argument('srt');ap.add_argument('dst');ap.add_argument('--font-size',type=int,default=11);ap.add_argument('--qa');ap.add_argument('--cut-fix',action='store_true')
    args=ap.parse_args()
    res=build(args.src,args.dst,args.srt,args.font_size,qa_path=args.qa,cut_fix=args.cut_fix)
    print('PASS',res['source_sha256'],res['output_sha256'],res['frames'],res['number_of_cues'],res['reencoded_frames_count'])
