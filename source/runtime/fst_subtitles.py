#!/usr/bin/env python3
# coding: utf-8
"""Harvester .FST subtitle burn-in experiment.
Read-only source; output is a separate FST with original PCM and timing preserved.
Requires Python 3.9+ / Pillow.  FST is 2TSF FutureVision format.
"""
import argparse, hashlib, re, struct, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .fst_codec import FST


def load_srt(p):
    data=Path(p).read_text(encoding='utf-8-sig').replace('\r\n','\n')
    cues=[]
    def sec(t):
        h,m,s,ms=(int(x) for x in re.split(r'[:,.]',t))
        return h*3600+m*60+s+ms/1000
    for part in re.split(r'\n\s*\n',data.strip()):
        lines=[x.strip() for x in part.splitlines() if x.strip()]
        if len(lines)<2:continue
        if re.fullmatch(r'\d+',lines[0]): lines=lines[1:]
        if not lines or '-->' not in lines[0]:raise ValueError(f'Bad SRT cue: {part[:100]}')
        a,b=(x.strip() for x in lines[0].split('-->',1))
        start,end=sec(a),sec(b)
        if start<0 or end<=start: raise ValueError('Invalid subtitle duration')
        cues.append((start,end,'\n'.join(lines[1:])))
    return cues


def font_for(size, explicit=None):
    candidates=[explicit, '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
       '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf',
       'C:/Windows/Fonts/arialbd.ttf', 'C:/Windows/Fonts/segoeuib.ttf']
    for font in candidates:
        if font and Path(font).is_file():return ImageFont.truetype(str(font),size)
    raise FileNotFoundError('No readable bold TrueType font. Use --font PATH')


def caption_mask(size,caption,font,y=None):
    w,h=size
    outline=Image.new('L',size,0); center=Image.new('L',size,0)
    od=ImageDraw.Draw(outline);cd=ImageDraw.Draw(center)
    text=caption.replace('\\n','\n')
    # Wrap at pixel width; preserve explicit line breaks
    lines=[]
    for src_line in text.splitlines():
        current=''
        for word in src_line.split():
            proposal=(current+' '+word).strip()
            if current and cd.textbbox((0,0),proposal,font=font)[2] > w-20:
                lines.append(current);current=word
            else:current=proposal
        lines.append(current)
    if not lines: return outline,center
    step=font.size+3
    for i,line in enumerate(lines):
        bw=cd.textbbox((0,0),line,font=font)[2]
        if bw>w-10:raise ValueError('Subtitle too wide for 320-pixel movie: '+line)
    start_y=(h-16)-len(lines)*step if y is None else y
    for i,line in enumerate(lines):
        bbox=cd.textbbox((0,0),line,font=font)
        # bbox top normally includes font ascent gap, text baseline adjusted
        x=(w-(bbox[2]-bbox[0]))//2-bbox[0];yy=start_y+i*step-bbox[1]
        od.text((x,yy),line,font=font,fill=255,stroke_width=1,stroke_fill=255)
        cd.text((x,yy),line,font=font,fill=255)
    return outline,center


def palette_color_indexes(pal):
    cols=[pal[i*3:i*3+3] for i in range(256)]
    white=min(range(256),key=lambda i:sum((int(c)-252)**2 for c in cols[i]))
    black=min(range(256),key=lambda i:sum(int(c)**2 for c in cols[i]))
    return white,black


def overlay(srcpix,pal,caption,font,w,h):
    if not caption:return bytes(srcpix)
    outline,center=caption_mask((w,h),caption,font)
    ww,bb=palette_color_indexes(pal)
    oo=outline.tobytes();cc=center.tobytes()
    out=bytearray(srcpix)
    for idx,(o,c) in enumerate(zip(oo,cc)):
        if o>=128:out[idx]=ww if c>=128 else bb
    return bytes(out)


def bitpack(bits):
    # Legacy FST uses integer bit_count // 8 + 1, even when count % 8 == 0
    result=bytearray(len(bits)//8+1)
    for i,b in enumerate(bits):
        if b: result[i//8] |= 0x80>>(i%8)
    return result


def encode_delta(prevpix,newpix,w,h,palette_bytes=None):
    """Lossless 4x4 block-delta encoder with literal/BTC modes."""
    ncols=w//4
    bits=[int(palette_bytes is not None)];data=bytearray()
    for ty in range(h//4):
        for tx in range(ncols):
            x=tx*4;y=ty*4
            old=b''.join(prevpix[(y+dy)*w+x:(y+dy)*w+x+4] for dy in range(4))
            new=b''.join(newpix[(y+dy)*w+x:(y+dy)*w+x+4] for dy in range(4))
            if old==new:bits.append(0);continue
            bits.append(1)
            cols=list(dict.fromkeys(new))
            if len(cols)<=2:
                bits.append(1)
                c0=cols[0];c1=cols[-1]
                mask=0
                for k,c in enumerate(new):
                    if c==c1 and c1!=c0:mask|=0x8000>>k
                data.extend(bytes((c0,c1))+struct.pack('<H',mask))
            else:
                bits.append(0);data.extend(new)
    if len(bits)>65535:raise ValueError('Control bitmap too large')
    return (struct.pack('<H',len(bits))+bitpack(bits)
        +(palette_bytes or b'')+bytes(data))


def source_palette_block(f,fi):
    vs,_=f.entries[fi];p=f.buf[f.offsets[fi]:f.offsets[fi]+vs]
    bitcount=struct.unpack_from('<H',p)[0];bitmap_end=2+(bitcount//8+1)
    if p[2]&128:return p[bitmap_end:bitmap_end+768]
    return None


def build(src_path,dst_path,srt_path,font_size=13,font_path=None):
    src_path=Path(src_path).resolve();dst_path=Path(dst_path).resolve()
    if src_path==dst_path:raise ValueError('Never replace the original source FST')
    f=FST(src_path)
    cues=load_srt(srt_path)
    font=font_for(font_size,font_path)
    frame_data=[];prior_target=bytes(f.w*f.h)
    changed=[];audit=[];previous_caption=False
    original_audio_hash=hashlib.sha256();new_audio_hash=hashlib.sha256()
    originals=[]
    for fi,orig_pix,palette,audio in f.decode():
        originals.append((orig_pix,palette))
        time=fi/f.fps
        caption=next((txt for a,b,txt in cues if a<=time<b),'')
        target=overlay(orig_pix,palette,caption,font,f.w,f.h)
        if caption or previous_caption:
            # re-encode only caption frames and first restoration frame afterwards
            pal_block=source_palette_block(f,fi)
            raw=encode_delta(prior_target,target,f.w,f.h,pal_block)
            changed.append(fi)
        else:
            vlen,alen=f.entries[fi];offset=f.offsets[fi]
            raw=f.buf[offset:offset+vlen]
        original_audio_hash.update(audio)
        new_audio_hash.update(audio)
        frame_data.append((raw,audio))
        prior_target=target
        previous_caption=bool(caption)
        audit.append((fi,caption,hashlib.sha256(audio).hexdigest()[:12]))
    header=bytearray(f.buf[:32]);struct.pack_into('<I',header,12,max(f.maxsize,max(len(v) for v,_ in frame_data)))
    idx=bytearray();chunks=bytearray()
    for v,a in frame_data:
        if len(v)>2**32-1 or len(a)>65535:raise ValueError('Too-large movie chunk')
        idx+=struct.pack('<IH',len(v),len(a))
        chunks+=v+a
    dst_path.parent.mkdir(parents=True,exist_ok=True)
    dst_path.write_bytes(header+idx+chunks)
    # Independent-read verification from newly written bytes, including audio exactness and image losslessness.
    g=FST(dst_path)
    assert (g.w,g.h,g.frames,g.fps,g.sample_rate,g.bits)==(f.w,f.h,f.frames,f.fps,f.sample_rate,f.bits)
    giter=g.decode()
    changed_pixels=0;outside_changes=0
    for fi,(outfi,pix,pal,audio) in enumerate(giter):
        original,pal_orig=originals[fi]
        txt=audit[fi][1]
        expected=overlay(original,pal_orig,txt,font,f.w,f.h)
        if pix!=expected:raise AssertionError(f'Video mismatch at frame {fi}, pixels: '+str(sum(a!=b for a,b in zip(pix,expected))))
        _,audlen=f.entries[fi]
        o=f.offsets[fi]+f.entries[fi][0]
        if audio!=f.buf[o:o+audlen]:raise AssertionError(f'Audio differs at frame {fi}')
        changed_pixels+=sum(a!=b for a,b in zip(pix,original))
        if pal!=pal_orig:raise AssertionError(f'Palette mismatch at frame {fi}')
    report={
      'source':str(src_path),'output':str(dst_path),'source_sha256':hashlib.sha256(f.buf).hexdigest(),
      'output_sha256':hashlib.sha256(g.buf).hexdigest(),
      'source_bytes':len(f.buf),'output_bytes':len(g.buf),
      'resolution':[f.w,f.h],'frames':f.frames,'fps':f.fps,
      'duration_seconds':f.frames/f.fps,
      'sample_rate':f.sample_rate,'sample_bits':f.bits,
      'source_audio_sha256':original_audio_hash.hexdigest(),
      'output_audio_sha256':new_audio_hash.hexdigest(),
      'reencoded_frames':changed,
      'different_video_pixels_within_cues':changed_pixels,
      'decode_and_exact_video_audio_verify':'PASS',
      'cues': [{'start':a,'end':b,'text':t} for a,b,t in cues],
    }
    return report


def main():
    ap=argparse.ArgumentParser(description='Test German transparent captions in Harvester FST')
    ap.add_argument('source_fst');ap.add_argument('srt');ap.add_argument('output_fst')
    ap.add_argument('--font-size',type=int,default=13);ap.add_argument('--font',default=None)
    args=ap.parse_args()
    import json
    print(json.dumps(build(args.source_fst,args.output_fst,args.srt,args.font_size,args.font),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
