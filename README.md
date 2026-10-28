# 🔥 Pantau Karhutla
**Indonesia Wildfire Monitoring & Forecasting** · *Pemantauan & Prediksi Kebakaran Hutan dan Lahan Indonesia*

🌐 **Live / Situs:** <https://karhutla.annasafyah.dev> (UI in Indonesian / antarmuka berbahasa Indonesia)

[English](#english) · [Bahasa Indonesia](#bahasa-indonesia)

---

## English

*Karhutla* = **kebakaran hutan dan lahan** (forest and land fires). Karhutla Watch answers one question: **when will this fire season end?**

### Features
- **Map** of satellite hotspots over the last 1, 3 or 7 days (NASA FIRMS, VIIRS 375 m).
- **Year-over-year comparison** of the current season against 2012 to today, by region.
- **End-of-season forecast:** probability that the 14-day mean hotspot count falls below 1,000 or 500 per day.
- **Monthly forecast** (experimental), 1 to 6 months ahead: Random Forest, Ridge, and their average.
- **Rainfall and ENSO/IOD** context.

### Data scale
~4.1M raw VIIRS detections (3.9M after quality filtering), 20 Jan 2012 to Oct 2026, 10 regions; 8,004 daily rainfall records; monthly Niño 3.4 and DMI. Each record is a satellite pixel detection, not an individual fire.

### How it works
GitHub Actions runs daily (03:30 UTC): NASA FIRMS → CHIRPS rainfall → NOAA ENSO/IOD → models → JSON → GitHub Pages. Tests: `pytest -q` (9 offline tests).

### Models and validation
- *End of season:* discrete-hazard logistic regression per threshold and horizon, leave-one-year-out CV, year-bootstrap intervals.
- *Monthly:* direct multi-horizon Random Forest and Ridge on anomalies vs. monthly climatology; rolling-origin backtest (549 forecasts since 2019) against climatology and seasonal-naive baselines.

### Limitations
Not an official forecast; follow BMKG and KLHK for operational decisions. Hotspots are not burned area. Trained on ~15 seasons; 2026 is at the edge of the training range. The monthly model **underpredicts peak months** (predicted/actual ≈ 0.2 to 0.7 in backtests); for the running month, use the daily-rate projection shown on the site. Regions are coarse coordinate boxes, not administrative borders.

### Run your own
1. Fork or upload this repo. 2. Add secret `FIRMS_MAP_KEY` (free: <https://firms.modaps.eosdis.nasa.gov/api/map_key/>). 3. Settings → Pages → Source: **GitHub Actions**; Actions → *Read and write permissions*. 4. Actions → *Update data dan deploy* → Run workflow. 5. Optional custom domain: CNAME → `<user>.github.io`, then set it under Settings → Pages.
Local: `pip install -r requirements.txt`, `pytest -q`, `python -m http.server -d docs`.

---

## Bahasa Indonesia

Karhutla Watch menjawab satu pertanyaan: **kapan musim kebakaran tahun ini berakhir?**

### Fitur
- **Peta** titik panas 1, 3, dan 7 hari terakhir (NASA FIRMS, VIIRS 375 m).
- **Bandingkan tahun ke tahun:** musim ini dibanding 2012 sampai sekarang, per wilayah.
- **Prediksi akhir musim:** peluang rata-rata 14 hari turun di bawah 1.000 atau 500 titik/hari.
- **Prakiraan bulanan** (eksperimental) 1 sampai 6 bulan: Random Forest, Ridge, dan rata-ratanya.
- **Hujan dan ENSO/IOD.**

### Skala data
±4,1 juta deteksi VIIRS mentah (3,9 juta setelah filter kualitas), 20 Jan 2012 sampai Okt 2026, 10 wilayah; 8.004 data hujan harian; Niño 3.4 dan DMI bulanan. Satu baris adalah deteksi piksel satelit, bukan satu kebakaran.

### Cara kerja
GitHub Actions berjalan tiap hari (03:30 UTC): NASA FIRMS → hujan CHIRPS → ENSO/IOD NOAA → model → JSON → GitHub Pages. Tes: `pytest -q` (9 tes tanpa jaringan).

### Batasan
Bukan prakiraan resmi; ikuti BMKG dan KLHK. Titik panas bukan luas lahan terbakar. Dilatih dari ±15 musim; 2026 berada di tepi data latih. Model bulanan **menaksir terlalu rendah di bulan puncak** (rasio prediksi/aktual ≈ 0,2 sampai 0,7); untuk bulan berjalan pakai proyeksi laju harian di situs. Wilayah memakai kotak koordinat kasar.

### Pasang sendiri
1. Fork atau unggah repo. 2. Tambah secret `FIRMS_MAP_KEY` (gratis di <https://firms.modaps.eosdis.nasa.gov/api/map_key/>). 3. Settings → Pages → Source: **GitHub Actions**; Actions → *Read and write permissions*. 4. Actions → *Update data dan deploy* → Run workflow. 5. Opsional domain sendiri: CNAME → `<user>.github.io`, lalu isi di Settings → Pages.

---
**Data:** NASA FIRMS · CHIRPS v3 (UCSB CHC) · NOAA PSL · map © OpenStreetMap.
