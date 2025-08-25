
# KOT SMT 2025 — Live Scoreboard (Streamlit)

Aplikasi papan skor langsung untuk Kejohanan Olahraga Tahunan (KOT) sekolah.
- **Admin**: tambah rumah, cipta acara (kategori, jantina, umur, sistem mata), catat keputusan (kedudukan & catatan).
- **Paparan**: papan skor live (auto-refresh), kiraan pingat, senarai keputusan terkini.
- **Tetapan**: tetapkan PIN admin, tukar warna rumah, export CSV, import DB.

## Cara Jalankan (Laptop/PC)
1. Pastikan **Python 3.9+**.
2. Pasang kebergantungan:
   ```bash
   pip install -r requirements.txt
   ```
3. Jalankan:
   ```bash
   streamlit run app.py
   ```

## Deploy ke Streamlit Cloud
1. Letakkan fail dalam GitHub repo (cth: `KOT_SMT_2025`).
2. Di Streamlit Cloud: **New app** → pilih repo & branch → `app.py` → **Deploy**.
3. (Pilihan) Tetapkan custom domain agar mudah diingati.

## Nota
- Data disimpan dalam `data/sports.db` (SQLite). Gunakan menu **Tetapan** untuk import/export.
- Tukar sistem mata dengan format JSON semasa cipta acara, contoh:
  ```json
  {"1": 10, "2": 7, "3": 5, "4": 3, "5": 1}
  ```
