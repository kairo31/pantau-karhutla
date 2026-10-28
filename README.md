# 🔥 Pantau Karhutla
**Kapan asap reda?** Pantauan titik panas Indonesia, perbandingan tahun ke tahun, dan prediksi akhir musim kebakaran, diperbarui otomatis setiap hari.

🌐 **Situs:** <[https://domain-](https://kairo31.github.io/pantau-karhutla/)>


## Apa yang bisa dilihat
- **Peta** titik panas 1, 3, dan 7 hari terakhir (NASA FIRMS, VIIRS 375 m).
- **Bandingkan tahun:** musim ini dibanding 2012 sampai sekarang, per wilayah (Kalimantan, Sumatera, Papua, dan lainnya).
- **Prediksi akhir musim:** peluang rata-rata 14 hari turun di bawah ambang 1.000 atau 500 titik/hari.
- **Prakiraan bulanan** (eksperimental) 1–6 bulan ke depan.
- **Hujan dan ENSO/IOD:** kenapa 2026 begitu parah dan apa hubungannya dengan kemarau.

## Temuan utama
- Keparahan musim sangat terkait ENSO (korelasi peringkat ≈ 0,83) dan hujan Agustus–September.
- 2026 mencatat Agustus–September terkering sepanjang data untuk Kalimantan dan Papua.
- Waktu berakhirnya musim jauh lebih sulit diprediksi daripada keparahannya.

## Cara kerja
GitHub Actions berjalan setiap hari (03:30 UTC):
NASA FIRMS → CHIRPS (hujan) → NOAA (Niño 3.4, DMI) → model → JSON → GitHub Pages.

## Pasang sendiri
1. Fork atau unggah repo ini.
2. Simpan secret `FIRMS_MAP_KEY` (gratis di https://firms.modaps.eosdis.nasa.gov/api/map_key/).
3. Settings → Pages → Source: **GitHub Actions**; Actions → Read and write permissions.
4. Actions → *Update data dan deploy* → Run workflow.

## Batasan
Bukan prakiraan resmi; untuk keputusan operasional ikuti BMKG dan KLHK. Titik panas bukan luas lahan terbakar. Model dilatih dari belasan musim dan 2026 berada di tepi data latih; prakiraan bulanan cenderung terlalu rendah di bulan puncak. Wilayah memakai kotak koordinat kasar.

## Sumber data
NASA FIRMS · CHIRPS v3 (UCSB CHC) · NOAA PSL · peta © OpenStreetMap.
