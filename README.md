# Upscaller

Windows video enhancer untuk workflow TikTok Affiliate.

## Prinsip

**Tidak ada preset.** Semua video diproses dengan satu engine **AUTO ADAPTIVE** yang menganalisis frame dan menyesuaikan exposure, brightness, contrast, gamma, saturation, denoise, sharpening, dan framing secara konservatif.

Targetnya satu pipeline yang tetap natural untuk indoor siang, indoor malam, outdoor, sore, mixed lighting, dan backlit.

## FFmpeg

Upscaller **tidak membundel FFmpeg ke dalam EXE**.

Urutan penggunaan:
1. Jika PC sudah memiliki `ffmpeg` + `ffprobe` di PATH, Upscaller memakai instalasi tersebut.
2. Jika belum ada, Upscaller mengunduh **FFmpeg Essentials** satu kali ke `%LOCALAPPDATA%\Upscaller\ffmpeg`.
3. Run berikutnya menggunakan cache lokal tanpa mengunduh ulang.

Gyan menyediakan Windows release essentials yang berisi `ffmpeg` dan `ffprobe`. citeturn466536search0

## Distribusi Windows

GitHub Release menghasilkan dua file:
- `Upscaller.exe` — portable, langsung buka tanpa installer.
- `Upscaller-Setup.exe` — installer Windows dengan shortcut Start Menu/Desktop.

## Output Video

- 1080×1920, 9:16
- H.264 CRF 18 + AAC 160k
- MP4 + faststart
- Audio dipertahankan bila tersedia

## Release

Dari GitHub Actions gunakan **Run workflow** dan masukkan versi, misalnya `1.0.1`. Workflow akan membangun EXE + installer lalu membuat GitHub Release dengan tag `v1.0.1`.

Catatan: tidak ada pemroses video yang dapat menjamin hasil optimal untuk setiap footage ekstrem atau file rusak. Engine dibuat adaptif dan konservatif agar pengguna tidak perlu memilih preset.
