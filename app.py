import os, sys, re, shutil, subprocess, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
EXT={'.mp4','.mov','.mkv','.avi','.webm','.m4v'}
PRESETS={
'Affiliate Auto':dict(c=1.05,b=0.02,s=1.08,g=1.0,sharp=.55,denoise=.25,crf=18),
'Low Light':dict(c=1.03,b=.05,s=1.04,g=1.06,sharp=.45,denoise=.45,crf=19),
'Daylight':dict(c=1.04,b=0,s=1.10,g=.99,sharp=.60,denoise=.18,crf=18),
'Soft Product':dict(c=1.02,b=.015,s=1.06,g=1.01,sharp=.38,denoise=.30,crf=19)}

def bin(name):
 p=ROOT/name
 return str(p) if p.exists() else shutil.which(name)
FF=bin('ffmpeg.exe') or bin('ffmpeg'); FP=bin('ffprobe.exe') or bin('ffprobe')

def probe(src):
 if not FP: raise RuntimeError('ffprobe tidak ditemukan')
 x=subprocess.run([FP,'-v','error','-select_streams','v:0','-show_entries','stream=width,height','-show_entries','format=duration','-of','default=nw=1:nk=1',str(src)],capture_output=True,text=True)
 if x.returncode: raise RuntimeError(x.stderr[-500:])
 a=x.stdout.strip().splitlines(); return int(a[0]),int(a[1]),float(a[2]) if len(a)>2 else 0

def stats(src):
 if not FF:return .5,.2
 try:
  x=subprocess.run([FF,'-v','error','-i',str(src),'-vf','fps=1,scale=96:-2,format=gray','-frames:v','6','-f','rawvideo','-pix_fmt','gray','pipe:1'],capture_output=True,timeout=60)
  if not x.stdout:return .5,.2
  import numpy as np
  a=np.frombuffer(x.stdout,dtype=np.uint8)/255
  return float(a.mean()),float(a.std())
 except:return .5,.2

def filter_for(src,preset,auto):
 p=PRESETS[preset]; m,sd=stats(src) if auto else (.5,.2)
 b=max(-.06,min(.08,p['b']+(0.5-m)*.22)); c=max(.94,min(1.12,p['c']*(1+(0.20-sd)*.25)))
 if m<.25:b+=.015
 if m>.82:b-=.01
 return ','.join([f"scale=ceil(iw*1.5/2)*2:ceil(ih*1.5/2)*2:flags=lanczos",f"eq=contrast={c:.4f}:brightness={b:.4f}:saturation={p['s']}:gamma={p['g']}",f"hqdn3d={p['denoise']}:{p['denoise']}:3:3",f"unsharp=5:5:{p['sharp']}:5:5:0",'scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos','crop=1080:1920','format=yuv420p'])

def process(src,dst,preset,auto,cb):
 if not FF:raise RuntimeError('FFmpeg tidak ditemukan')
 _,_,dur=probe(src); vf=filter_for(src,preset,auto)
 cmd=[FF,'-y','-hide_banner','-i',str(src),'-vf',vf,'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','medium','-crf',str(PRESETS[preset]['crf']),'-c:a','aac','-b:a','160k','-ar','48000','-movflags','+faststart',str(dst)]
 p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
 for line in p.stdout:
  m=re.search(r'time=(\d+):(\d+):(\d+(?:\.\d+)?)',line)
  if m and dur:cb(min(100,(int(m[1])*3600+int(m[2])*60+float(m[3]))/dur*100))
 if p.wait():raise RuntimeError('FFmpeg gagal memproses video')

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title('Upscaller');self.geometry('760x560');self.files=[];self.out=Path.home()/'Videos'/'Upscaller';self.out.mkdir(parents=True,exist_ok=True);self.ui()
 def ui(self):
  ttk.Label(self,text='UPSCALLER',font=('Segoe UI',22,'bold')).pack(pady=(18,0));ttk.Label(self,text='FFmpeg Video Enhancer • TikTok Affiliate').pack(pady=(0,14))
  bar=ttk.Frame(self);bar.pack(fill='x',padx=12);ttk.Button(bar,text='Tambah Video',command=self.add).pack(side='left');ttk.Button(bar,text='Hapus Semua',command=self.clear).pack(side='left',padx=8);ttk.Button(bar,text='Folder Output',command=self.folder).pack(side='right')
  self.lb=tk.Listbox(self,height=12);self.lb.pack(fill='both',expand=True,padx=12,pady=8)
  opt=ttk.Frame(self);opt.pack(fill='x',padx=12);ttk.Label(opt,text='Preset').grid(row=0,column=0,sticky='w');self.pre=tk.StringVar(value='Affiliate Auto');ttk.Combobox(opt,textvariable=self.pre,values=list(PRESETS),state='readonly',width=28).grid(row=0,column=1,sticky='w',padx=8);self.auto=tk.BooleanVar(value=True);ttk.Checkbutton(opt,text='Auto exposure / contrast / saturation',variable=self.auto).grid(row=1,column=1,sticky='w',padx=8,pady=7);ttk.Label(opt,text='Output: 1080×1920 • H.264 • AAC • MP4').grid(row=2,column=1,sticky='w',padx=8)
  self.pg=ttk.Progressbar(self,maximum=100);self.pg.pack(fill='x',padx=12,pady=8);self.st=ttk.Label(self,text='Siap.');self.st.pack(anchor='w',padx=12);self.btn=ttk.Button(self,text='PROSES VIDEO',command=self.start);self.btn.pack(fill='x',padx=12,pady=15,ipady=8)
 def add(self):
  for p in filedialog.askopenfilenames(filetypes=[('Video','*.mp4 *.mov *.mkv *.avi *.webm *.m4v')]):
   if Path(p).suffix.lower() in EXT and p not in self.files:self.files.append(p);self.lb.insert('end',p)
 def clear(self):self.files=[];self.lb.delete(0,'end')
 def folder(self):
  p=filedialog.askdirectory(initialdir=self.out)
  if p:self.out=Path(p)
 def start(self):
  if not self.files:return messagebox.showwarning('Upscaller','Tambahkan video terlebih dahulu.')
  self.btn.config(state='disabled');threading.Thread(target=self.work,daemon=True).start()
 def work(self):
  try:
   for i,s in enumerate(self.files):
    src=Path(s);dst=self.out/f'{src.stem}_upscalled.mp4';self.after(0,self.st.config,{'text':f'Memproses {i+1}/{len(self.files)} • {src.name}'})
    process(src,dst,self.pre.get(),self.auto.get(),lambda v:self.after(0,self.pg.config,{'value':(i*100+v)/len(self.files)}))
   self.after(0,lambda:messagebox.showinfo('Upscaller',f'Selesai.\n{self.out}'));self.after(0,self.st.config,{'text':'Selesai.'})
  except Exception as e:self.after(0,lambda:messagebox.showerror('Upscaller',str(e)));self.after(0,self.st.config,{'text':'Gagal.'})
  finally:self.after(0,self.btn.config,{'state':'normal'})

if __name__=='__main__':App().mainloop()
