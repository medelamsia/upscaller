# Upscaller

Windows FFmpeg video enhancer untuk workflow TikTok Affiliate.

## Prinsip
**Tidak ada preset.** Semua video diproses dengan satu engine **AUTO ADAPTIVE**. Engine menganalisis sampel beberapa frame lalu menyesuaikan exposure, brightness, contrast, gamma, saturation, denoise, dan sharpening secara konservatif.

Targetnya adalah satu pipeline yang tetap natural untuk indoor siang, indoor malam, outdoor, sore, mixed lighting, dan footage backlit.

## Output
- 1080×1920, 9:16
- H.264 CRF 18 + AAC 160k
- MP4 + faststart
- Audio dipertahankan bila tersedia

## Build
Buat tag seperti `v1.0.0`. GitHub Actions akan membuat Windows EXE.

Catatan: tidak ada pemroses video yang dapat menjamin hasil optimal untuk setiap footage ekstrem atau file rusak. Engine dibuat adaptif dan konservatif agar tidak perlu pengguna memilih preset.
