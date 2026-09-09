import sys, re, shutil, subprocess, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

ROOT=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent))
EXT={".mp4",".mov",".mkv",".avi",".webm",".m4v"}

def bin(name):
    p=ROOT/name
    return str(p) if p.exists() else shutil.which(name)

FF=bin("ffmpeg.exe") or bin("ffmpeg")
FP=bin("ffprobe.exe") or bin("ffprobe")

def probe(src):
    if not FP: raise RuntimeError("ffprobe tidak ditemukan")
    x=subprocess.run([FP,"-v","error","-select_streams","v:0",
                      "-show_entries","stream=width,height,r_frame_rate",
                      "-show_entries","format=duration",
                      "-of","default=nw=1:nk=1",str(src)],
                     capture_output=True,text=True)
    if x.returncode: raise RuntimeError(x.stderr[-800:])
    a=x.stdout.strip().splitlines()
    if len(a)<2: raise RuntimeError("Video tidak dapat dibaca")
    return int(a[0]),int(a[1]),float(a[-1] or 0)

def analyze(src):
    if not FF: return .5,.20,.50,.50
    try:
        # Sample several frames. Mean, contrast spread and percentile-like range
        # let the filter adapt to indoor/outdoor, day/night and backlit footage.
        x=subprocess.run([FF,"-v","error","-i",str(src),
                          "-vf","fps=1,scale=128:-2,format=gray",
                          "-frames:v","8","-f","rawvideo","-pix_fmt","gray","pipe:1"],
                         capture_output=True,timeout=90)
        if not x.stdout: return .5,.20,.50,.50
        import numpy as np
        a=np.frombuffer(x.stdout,dtype=np.uint8).astype(np.float32)/255.0
        q10=float(np.quantile(a,.10)); q50=float(np.quantile(a,.50)); q90=float(np.quantile(a,.90))
        return float(a.mean()),float(a.std()),q10,q90
    except Exception:
        return .5,.20,.50,.50

def adaptive_filter(src):
    m,sd,q10,q90=analyze(src)

    # Universal conservative auto grade:
    # lift dark scenes, protect highlights, add useful local separation,
    # avoid over-saturation and oversharpening.
    b=max(-0.035,min(0.065,(0.50-m)*0.18))
    gamma=max(0.96,min(1.075,1.0+(0.50-m)*0.16))
    contrast=max(0.98,min(1.10,1.025+(0.20-sd)*0.20))
    saturation=max(1.00,min(1.09,1.045+(0.18-sd)*0.10))

    # Very flat footage gets slightly more separation; already punchy footage gets less.
    if (q90-q10)<0.36:
        contrast=min(1.10,contrast+0.025)
    if q10<0.10 and m<0.38:
        b=min(0.065,b+0.012)
        gamma=min(1.075,gamma+0.012)
    if q90>0.93:
        b=max(-0.035,b-0.010)
        contrast=min(1.10,contrast+0.010)

    # Noise reduction and sharpening scale with measured scene noise/contrast.
    denoise=max(0.10,min(0.55,0.42-(sd*0.55)))
    sharp=max(0.28,min(0.62,0.42+(sd*0.45)))

    return ",".join([
        "scale=ceil(iw*1.5/2)*2:ceil(ih*1.5/2)*2:flags=lanczos",
        f"hqdn3d={denoise:.3f}:{denoise:.3f}:3:3",
        f"eq=contrast={contrast:.4f}:brightness={b:.4f}:saturation={saturation:.4f}:gamma={gamma:.4f}",
        f"unsharp=5:5:{sharp:.3f}:5:5:0",
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1080:1920",
        "format=yuv420p"
    ])

def process(src,dst,cb):
    if not FF: raise RuntimeError("FFmpeg tidak ditemukan")
    _,_,dur=probe(src)
    vf=adaptive_filter(src)
    cmd=[FF,"-y","-hide_banner","-i",str(src),
         "-vf",vf,"-map","0:v:0","-map","0:a?",
         "-c:v","libx264","-preset","medium","-crf","18",
         "-c:a","aac","-b:a","160k","-ar","48000",
         "-movflags","+faststart",str(dst)]
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                       text=True,encoding="utf-8",errors="replace")
    for line in p.stdout:
        m=re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)",line)
        if m and dur:
            sec=int(m[1])*3600+int(m[2])*60+float(m[3])
            cb(min(100,sec/dur*100))
    if p.wait()!=0: raise RuntimeError("FFmpeg gagal memproses video")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Upscaller")
        self.geometry("760x560")
        self.files=[]
        self.out=Path.home()/"Videos"/"Upscaller"
        self.out.mkdir(parents=True,exist_ok=True)
        self.ui()

    def ui(self):
        ttk.Label(self,text="UPSCALLER",font=("Segoe UI",22,"bold")).pack(pady=(18,0))
        ttk.Label(self,text="Adaptive Video Enhancer • TikTok Affiliate").pack(pady=(0,14))
        bar=ttk.Frame(self);bar.pack(fill="x",padx=12)
        ttk.Button(bar,text="Tambah Video",command=self.add).pack(side="left")
        ttk.Button(bar,text="Hapus Semua",command=self.clear).pack(side="left",padx=8)
        ttk.Button(bar,text="Folder Output",command=self.folder).pack(side="right")
        self.lb=tk.Listbox(self,height=12)
        self.lb.pack(fill="both",expand=True,padx=12,pady=8)
        info=ttk.Frame(self);info.pack(fill="x",padx=12,pady=4)
        ttk.Label(info,text="Mode: AUTO ADAPTIVE",font=("Segoe UI",11,"bold")).pack(anchor="w")
        ttk.Label(info,text="Exposure • Brightness • Contrast • Gamma • Saturation • Denoise • Sharpen • 9:16").pack(anchor="w")
        ttk.Label(info,text="Output: 1080×1920 • H.264 CRF 18 • AAC • MP4").pack(anchor="w",pady=(3,0))
        self.pg=ttk.Progressbar(self,maximum=100);self.pg.pack(fill="x",padx=12,pady=8)
        self.st=ttk.Label(self,text="Siap.");self.st.pack(anchor="w",padx=12)
        self.btn=ttk.Button(self,text="PROSES VIDEO",command=self.start)
        self.btn.pack(fill="x",padx=12,pady=15,ipady=8)

    def add(self):
        for p in filedialog.askopenfilenames(filetypes=[("Video","*.mp4 *.mov *.mkv *.avi *.webm *.m4v")]):
            if Path(p).suffix.lower() in EXT and p not in self.files:
                self.files.append(p);self.lb.insert("end",p)

    def clear(self):
        self.files=[];self.lb.delete(0,"end")

    def folder(self):
        p=filedialog.askdirectory(initialdir=self.out)
        if p:self.out=Path(p)

    def start(self):
        if not self.files:
            return messagebox.showwarning("Upscaller","Tambahkan video terlebih dahulu.")
        self.btn.config(state="disabled")
        threading.Thread(target=self.work,daemon=True).start()

    def work(self):
        try:
            total=len(self.files)
            for i,s in enumerate(self.files):
                src=Path(s);dst=self.out/f"{src.stem}_upscalled.mp4"
                self.after(0,self.st.config,{"text":f"Menganalisis + memproses {i+1}/{total} • {src.name}"})
                process(src,dst,lambda v:self.after(0,self.pg.config,{"value":(i*100+v)/total}))
            self.after(0,lambda:messagebox.showinfo("Upscaller",f"Selesai.\n{self.out}"))
            self.after(0,self.st.config,{"text":"Selesai."})
        except Exception as e:
            self.after(0,lambda:messagebox.showerror("Upscaller",str(e)))
            self.after(0,self.st.config,{"text":"Gagal."})
        finally:
            self.after(0,self.btn.config,{"state":"normal"})

if __name__=="__main__":
    App().mainloop()
