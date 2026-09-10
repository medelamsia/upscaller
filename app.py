import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_NAME = "Upscaller"
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".3gp", ".ts", ".mts", ".m2ts"}
FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
TOOL_DIR = Path.home() / "AppData" / "Local" / APP_NAME / "ffmpeg"


def find_system_binary(name):
    return shutil.which(name) or shutil.which(name + ".exe")


def find_local_binary(name):
    path = ROOT / name
    return str(path) if path.exists() else None


def tools_from_dir(directory):
    ff = Path(directory) / "ffmpeg.exe"
    fp = Path(directory) / "ffprobe.exe"
    return (str(ff), str(fp)) if ff.exists() and fp.exists() else (None, None)


def locate_ffmpeg():
    # Prefer a real system installation so an existing FFmpeg is never duplicated.
    system_ff = find_system_binary("ffmpeg")
    system_fp = find_system_binary("ffprobe")
    if system_ff and system_fp:
        return system_ff, system_fp, "system"

    cached = tools_from_dir(TOOL_DIR)
    if cached[0]:
        return cached[0], cached[1], "downloaded"

    local = tools_from_dir(ROOT)
    if local[0]:
        return local[0], local[1], "bundled"

    return None, None, None


def ensure_ffmpeg(status_cb=None):
    ff, fp, source = locate_ffmpeg()
    if ff:
        return ff, fp

    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = Path(tempfile.gettempdir()) / "upscaller-ffmpeg.zip"
    if status_cb:
        status_cb("FFmpeg tidak ditemukan. Mengunduh FFmpeg Essentials satu kali...")

    try:
        with urllib.request.urlopen(FFMPEG_URL, timeout=60) as response, open(zip_path, "wb") as out:
            total = int(response.headers.get("Content-Length", "0") or 0)
            done = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if status_cb and total:
                    status_cb(f"Mengunduh FFmpeg... {done * 100 // total}%")

        with zipfile.ZipFile(zip_path) as z:
            members = z.namelist()
            ff_member = next((m for m in members if m.lower().endswith("/bin/ffmpeg.exe")), None)
            fp_member = next((m for m in members if m.lower().endswith("/bin/ffprobe.exe")), None)
            if not ff_member or not fp_member:
                raise RuntimeError("Paket FFmpeg tidak berisi ffmpeg.exe/ffprobe.exe.")
            z.extract(ff_member, TOOL_DIR)
            z.extract(fp_member, TOOL_DIR)

        extracted_root = next((p for p in TOOL_DIR.rglob("ffmpeg.exe") if p.name == "ffmpeg.exe"), None)
        if not extracted_root:
            raise RuntimeError("FFmpeg berhasil diunduh tetapi executable tidak ditemukan.")
        base = extracted_root.parent
        ff_target = TOOL_DIR / "ffmpeg.exe"
        fp_target = TOOL_DIR / "ffprobe.exe"
        shutil.copy2(extracted_root, ff_target)
        extracted_probe = base / "ffprobe.exe"
        if not extracted_probe.exists():
            extracted_probe = next((p for p in TOOL_DIR.rglob("ffprobe.exe") if p.name == "ffprobe.exe"), None)
        if not extracted_probe:
            raise RuntimeError("ffprobe.exe tidak ditemukan setelah ekstraksi.")
        shutil.copy2(extracted_probe, fp_target)
        return str(ff_target), str(fp_target)
    except Exception as exc:
        raise RuntimeError(
            "FFmpeg belum tersedia dan gagal diunduh otomatis. "
            "Pastikan internet aktif atau install FFmpeg Essentials lalu jalankan lagi.\n\n"
            f"Detail: {exc}"
        ) from exc
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except Exception:
            pass


def probe(src, ffprobe):
    x = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(src)],
        capture_output=True, text=True
    )
    if x.returncode:
        raise RuntimeError(x.stderr[-800:])
    lines = x.stdout.strip().splitlines()
    if len(lines) < 2:
        raise RuntimeError("Video tidak dapat dibaca")
    return int(lines[0]), int(lines[1]), float(lines[-1] or 0)


def analyze(src, ffmpeg):
    try:
        x = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(src),
             "-vf", "fps=1,scale=128:-2,format=gray",
             "-frames:v", "8", "-f", "rawvideo", "-pix_fmt", "gray", "pipe:1"],
            capture_output=True, timeout=90
        )
        if not x.stdout:
            return 0.5, 0.20, 0.50, 0.50
        values = [b / 255.0 for b in x.stdout]
        values.sort()
        n = len(values)
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        std = variance ** 0.5
        q10 = values[min(n - 1, int(n * 0.10))]
        q90 = values[min(n - 1, int(n * 0.90))]
        return mean, std, q10, q90
    except Exception:
        return 0.5, 0.20, 0.50, 0.50


def adaptive_filter(src, ffmpeg):
    m, sd, q10, q90 = analyze(src, ffmpeg)
    brightness = max(-0.035, min(0.065, (0.50 - m) * 0.18))
    gamma = max(0.96, min(1.075, 1.0 + (0.50 - m) * 0.16))
    contrast = max(0.98, min(1.10, 1.025 + (0.20 - sd) * 0.20))
    saturation = max(1.00, min(1.09, 1.045 + (0.18 - sd) * 0.10))

    if (q90 - q10) < 0.36:
        contrast = min(1.10, contrast + 0.025)
    if q10 < 0.10 and m < 0.38:
        brightness = min(0.065, brightness + 0.012)
        gamma = min(1.075, gamma + 0.012)
    if q90 > 0.93:
        brightness = max(-0.035, brightness - 0.010)
        contrast = min(1.10, contrast + 0.010)

    denoise = max(0.10, min(0.55, 0.42 - (sd * 0.55)))
    sharp = max(0.28, min(0.62, 0.42 + (sd * 0.45)))

    return ",".join([
        "scale=ceil(iw*1.5/2)*2:ceil(ih*1.5/2)*2:flags=lanczos",
        f"hqdn3d={denoise:.3f}:{denoise:.3f}:3:3",
        f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}:saturation={saturation:.4f}:gamma={gamma:.4f}",
        f"unsharp=5:5:{sharp:.3f}:5:5:0",
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1080:1920",
        "format=yuv420p"
    ])


def process(src, dst, cb):
    ffmpeg, ffprobe = ensure_ffmpeg(cb)
    _, _, duration = probe(src, ffprobe)
    vf = adaptive_filter(src, ffmpeg)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-i", str(src),
        "-vf", vf, "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart", str(dst)
    ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        m = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
        if m and duration:
            sec = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            cb(min(100, sec / duration * 100))
    if p.wait() != 0:
        raise RuntimeError("FFmpeg gagal memproses video")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x560")
        self.files = []
        self.out = Path.home() / "Videos" / APP_NAME
        self.out.mkdir(parents=True, exist_ok=True)
        self.ui()

    def ui(self):
        ttk.Label(self, text="UPSCALLER", font=("Segoe UI", 22, "bold")).pack(pady=(18, 0))
        ttk.Label(self, text="Adaptive Video Enhancer • TikTok Affiliate").pack(pady=(0, 14))
        bar = ttk.Frame(self); bar.pack(fill="x", padx=12)
        ttk.Button(bar, text="Tambah Video", command=self.add).pack(side="left")
        ttk.Button(bar, text="Hapus Semua", command=self.clear).pack(side="left", padx=8)
        ttk.Button(bar, text="Folder Output", command=self.folder).pack(side="right")
        self.lb = tk.Listbox(self, height=12); self.lb.pack(fill="both", expand=True, padx=12, pady=8)
        info = ttk.Frame(self); info.pack(fill="x", padx=12, pady=4)
        ttk.Label(info, text="Mode: AUTO ADAPTIVE", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(info, text="Exposure • Brightness • Contrast • Gamma • Saturation • Denoise • Sharpen • 9:16").pack(anchor="w")
        ttk.Label(info, text="FFmpeg: pakai instalasi PC jika tersedia; download otomatis hanya jika diperlukan").pack(anchor="w", pady=(3, 0))
        ttk.Label(info, text="Output: 1080×1920 • H.264 CRF 18 • AAC • MP4").pack(anchor="w")
        self.pg = ttk.Progressbar(self, maximum=100); self.pg.pack(fill="x", padx=12, pady=8)
        self.st = ttk.Label(self, text="Siap."); self.st.pack(anchor="w", padx=12)
        self.btn = ttk.Button(self, text="PROSES VIDEO", command=self.start)
        self.btn.pack(fill="x", padx=12, pady=15, ipady=8)

    def add(self):
        for p in filedialog.askopenfilenames(filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.3gp *.ts *.mts *.m2ts")]):
            if Path(p).suffix.lower() in EXT and p not in self.files:
                self.files.append(p); self.lb.insert("end", p)

    def clear(self):
        self.files = []; self.lb.delete(0, "end")

    def folder(self):
        p = filedialog.askdirectory(initialdir=self.out)
        if p: self.out = Path(p)

    def start(self):
        if not self.files:
            return messagebox.showwarning(APP_NAME, "Tambahkan video terlebih dahulu.")
        self.pg["value"] = 0
        self.btn.config(state="disabled")
        threading.Thread(target=self.work, daemon=True).start()

    def work(self):
        try:
            total = len(self.files)
            for i, s in enumerate(self.files):
                src = Path(s); dst = self.out / f"{src.stem}_upscalled.mp4"
                def status(text):
                    self.after(0, self.st.config, {"text": text})
                status(f"Menganalisis + memproses {i + 1}/{total} • {src.name}")
                process(src, dst, lambda v: self.after(0, self.pg.config, {"value": (i * 100 + v) / total}))
            self.after(0, lambda: messagebox.showinfo(APP_NAME, f"Selesai.\n{self.out}"))
            self.after(0, self.st.config, {"text": "Selesai."})
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(APP_NAME, str(e)))
            self.after(0, self.st.config, {"text": "Gagal."})
        finally:
            self.after(0, self.btn.config, {"state": "normal"})


if __name__ == "__main__":
    App().mainloop()
