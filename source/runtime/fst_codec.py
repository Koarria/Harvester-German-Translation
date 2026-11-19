#!/usr/bin/env python3
"""Read/modify Harvester FutureVision FST2/2TSF movie frames. No proprietary code.
     Decoder reference: https://wiki.multimedia.cx/index.php/FutureVision_FST
"""
import struct, io
from pathlib import Path
from PIL import Image

class FST:
    def __init__(self,path):
        self.path=Path(path)
        self.buf=self.path.read_bytes()
        if self.buf[:4]!=b'2TSF': raise ValueError('Not Harvester FST')
        self.w,self.h,self.maxsize,self.frames,self.fps,self.sample_rate,self.bits=struct.unpack_from('<7I',self.buf,4)
        if self.w%4 or self.h%4 or self.w*self.h>4_000_000 or self.frames>20000 or not 0<self.fps<=60:raise ValueError('Invalid FST params')
        self.entries=[struct.unpack_from('<IH',self.buf,32+6*i) for i in range(self.frames)]
        self.start=32+6*self.frames
        self.offsets=[]
        pos=self.start
        for v,a in self.entries:
            if v<3 or pos+v+a>len(self.buf): raise ValueError('Bad frame at '+str(len(self.offsets)))
            self.offsets.append(pos)
            pos+=v+a
        if pos!=len(self.buf):raise ValueError(f'Trailing data {len(self.buf)-pos}')
    def decode(self, sample=None, progress=False):
        # generator yields frame_index, indexed pixel bytes, rgb palette bytes, audio bytes
        curpix=bytearray(self.w*self.h)
        curpal=bytes([0]*768)
        nblocks=(self.w//4)*(self.h//4)
        for fi,((vs,aus),st) in enumerate(zip(self.entries,self.offsets)):
            p=self.buf[st:st+vs]
            bitcount=struct.unpack_from('<H',p,0)[0]
            bitbytes=bitcount//8+1
            if 2+bitbytes>len(p):raise ValueError(f'Frame {fi}: short bitstream')
            bits=p[2:2+bitbytes]
            q=2+bitbytes
            bi=0
            def bit():
                nonlocal bi
                if bi>=bitcount:raise ValueError(f'Frame {fi} block {block}/{nblocks}: ran out of control bits: {bi}/{bitcount}')
                v=(bits[bi//8]>>(7-bi%8))&1
                bi+=1
                return v
            if bit():
                if q+768>len(p):raise ValueError(f'Frame {fi}: short palette')
                curpal=bytes(min(255,x*4) for x in p[q:q+768]);q+=768
            for block in range(nblocks):
                if bi>=bitcount and nblocks-block<=32: break
                if not bit():continue
                if bi>=bitcount and nblocks-block<=32: break
                by=(block//(self.w//4))*4
                bx=(block%(self.w//4))*4
                if bit():
                    if q+4>len(p):
                        if nblocks-block<=32:break
                        raise ValueError(f'Frame {fi}: short BTC {block}/{nblocks}')
                    c0,c1,masklo,maskhi=p[q:q+4];q+=4
                    mask=(maskhi<<8)|masklo
                    for yy in range(4):
                        for xx in range(4):
                            curpix[(by+yy)*self.w+bx+xx]=c1 if (mask & (0x8000>>(yy*4+xx))) else c0
                else:
                    if q+16>len(p):
                        if nblocks-block<=32:break
                        raise ValueError(f'Frame {fi}: short raw {block}/{nblocks}')
                    for yy in range(4):
                        start=(by+yy)*self.w+bx
                        curpix[start:start+4]=p[q+4*yy:q+4*yy+4]
                    q+=16
            if q!=len(p):
                if len(p)-q>32: raise ValueError(f'Frame {fi}: leftover {len(p)-q} bytes, bits {bi}/{bitcount}')
            yield fi,bytes(curpix),curpal,self.buf[st+vs:st+vs+aus]

def to_image(pix,pal,w,h):
    img=Image.frombytes('P',(w,h),pix)
    img.putpalette(pal)
    return img.convert('RGB')

if __name__=='__main__':
 import sys
 f=FST(sys.argv[1]);print(f.path.name,'frames',f.frames,'fps',f.fps,'dims',f.w,f.h,'duration',f.frames/f.fps,'aud',f.sample_rate,f.bits)
 samples=set((0,1,10,30,60,90,119,150,180,240,300,450,600,750,900,1200))
 im=[]
 for i,pix,pal,pcm in f.decode():
  if i in samples:
   img=to_image(pix,pal,f.w,f.h);im.append((i,img))
 if im:
  sheet=Image.new('RGB',(f.w*4,(f.h+18)*((len(im)+3)//4)),(20,20,20))
  from PIL import ImageDraw
  d=ImageDraw.Draw(sheet)
  for k,(i,img) in enumerate(im):
   x=(k%4)*f.w;y=(k//4)*(f.h+18)
   sheet.paste(img,(x,y+18));d.text((x+4,y+2),f'{f.path.name} frame {i} sec {i/f.fps:.1f}',fill='white')
  op=f.path.with_suffix('.contact.png');sheet.save(op);print('contact',op)
