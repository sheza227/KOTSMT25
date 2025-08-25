
import sqlite3
import time
import io
import csv
from contextlib import closing
from pathlib import Path

import streamlit as st

DB_PATH = Path("data/sports.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS houses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT,
                gender TEXT,
                age_group TEXT,
                points_json TEXT DEFAULT '{"1": 5, "2": 3, "3": 1}',
                UNIQUE(name, category, gender, COALESCE(age_group,''))
            );
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                house_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                performance TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(event_id, position),
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY (house_id) REFERENCES houses(id) ON DELETE CASCADE
            );
            """
        )

def seed_demo():
    with get_conn() as conn:
        houses = [("Merah","#ff0000"), ("Biru","#0057ff"), ("Hijau","#0bbf5e"), ("Kuning","#ffcc00")]
        existing = conn.execute("SELECT COUNT(*) FROM houses").fetchone()[0]
        if existing == 0:
            for (h,c) in houses:
                conn.execute("INSERT INTO houses(name,color) VALUES (?,?)", (h,c))
        existing_e = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        if existing_e == 0:
            demo = [
                ("100m", "Balapan", "L", "Bawah 12", '{"1": 5, "2": 3, "3": 1}'),
                ("100m", "Balapan", "P", "Bawah 12", '{"1": 5, "2": 3, "3": 1}'),
                ("Lompat Jauh", "Padang", "L", "Terbuka", '{"1": 5, "2": 3, "3": 1}'),
                ("Lontar Peluru", "Padang", "P", "Terbuka", '{"1": 5, "2": 3, "3": 1}'),
            ]
            for (n,c,g,a,pj) in demo:
                conn.execute("INSERT OR IGNORE INTO events(name,category,gender,age_group,points_json) VALUES (?,?,?,?,?)",(n,c,g,a,pj))

def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default

def set_setting(key, value):
    with get_conn() as conn:
        conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

def get_points_from_event(event_row):
    import json
    try:
        points_map = json.loads(event_row[5] or '{"1":5,"2":3,"3":1}')
        points_map = {int(k): int(v) for k,v in points_map.items()}
    except Exception:
        points_map = {1:5,2:3,3:1}
    return points_map

def calc_house_totals(filters=None):
    filters = filters or {}
    where = []
    params = []
    if filters.get("gender"):
        where.append("e.gender=?")
        params.append(filters["gender"])
    if filters.get("category"):
        where.append("e.category=?")
        params.append(filters["category"])
    if filters.get("age_group"):
        where.append("COALESCE(e.age_group,'')=?")
        params.append(filters["age_group"])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_conn() as conn:
        houses = conn.execute("SELECT id, name, COALESCE(color,'') FROM houses ORDER BY name").fetchall()
        events = conn.execute(f"SELECT id, name, category, gender, age_group, points_json FROM events e {where_sql}", params).fetchall()
        event_ids = tuple([e[0] for e in events]) if events else tuple([-1])
        if events:
            q_marks = ','.join(['?']*len(event_ids))
            results = conn.execute(f"SELECT event_id, house_id, position FROM results WHERE event_id IN ({q_marks})", event_ids).fetchall()
        else:
            results = []
    points_by_event = {e[0]: get_points_from_event(e) for e in events}
    totals = {h[0]: {"name": h[1], "color": h[2], "points": 0, "gold":0,"silver":0,"bronze":0} for h in houses}
    for (event_id, house_id, position) in results:
        pts = points_by_event.get(event_id, {}).get(position, 0)
        if house_id in totals:
            totals[house_id]["points"] += pts
            if position == 1: totals[house_id]["gold"] += 1
            if position == 2: totals[house_id]["silver"] += 1
            if position == 3: totals[house_id]["bronze"] += 1
    ranked = sorted(totals.values(), key=lambda x: (x["points"], x["gold"], x["silver"], x["bronze"]), reverse=True)
    return ranked

def list_events():
    with get_conn() as conn:
        return conn.execute("SELECT id, name, category, gender, COALESCE(age_group,''), points_json FROM events ORDER BY category, name, gender, age_group").fetchall()

def list_houses():
    with get_conn() as conn:
        return conn.execute("SELECT id, name, COALESCE(color,'') FROM houses ORDER BY name").fetchall()

def list_results(event_id=None):
    with get_conn() as conn:
        if event_id:
            return conn.execute(
                "SELECT r.id, e.name, e.category, e.gender, COALESCE(e.age_group,''), h.name, r.position, COALESCE(r.performance,'') "
                "FROM results r JOIN events e ON r.event_id=e.id JOIN houses h ON r.house_id=h.id "
                "WHERE event_id=? ORDER BY position", (event_id,)
            ).fetchall()
        else:
            return conn.execute(
                "SELECT r.id, e.name, e.category, e.gender, COALESCE(e.age_group,''), h.name, r.position, COALESCE(r.performance,'') "
                "FROM results r JOIN events e ON r.event_id=e.id JOIN houses h ON r.house_id=h.id "
                "ORDER BY r.created_at DESC"
            ).fetchall()

st.set_page_config(page_title="KOT SMT 2025 - Live Scoreboard", layout="wide")

def require_admin_pin():
    saved_pin = get_setting("admin_pin", "")
    if not saved_pin:
        return True
    with st.sidebar:
        st.info("🔒 Masukkan PIN Admin untuk akses.")
        pin = st.text_input("PIN Admin", type="password")
        if st.button("Masuk", type="primary"):
            st.session_state["_pin_try"] = pin
    return st.session_state.get("_pin_try") == saved_pin

def page_admin():
    st.title("🔧 Admin: Urus Sukan Sekolah")
    st.caption("Tambah rumah sukan, acara, dan catat keputusan secara langsung.")
    if not require_admin_pin():
        st.stop()

    with st.expander("Rumah Sukan"):
        with get_conn() as conn:
            st.subheader("Tambah Rumah")
            c1, c2 = st.columns([3,1])
            with c1:
                name = st.text_input("Nama rumah", placeholder="Contoh: Merah")
            with c2:
                color = st.text_input("Warna (pilihan)", placeholder="contoh: #ff0000")
            if st.button("Simpan Rumah", type="primary", use_container_width=True):
                if not name.strip():
                    st.warning("Sila isi nama rumah.")
                else:
                    try:
                        conn.execute("INSERT INTO houses(name,color) VALUES (?,?)", (name.strip(), color.strip() or None))
                        st.success("Rumah ditambah.")
                    except sqlite3.IntegrityError:
                        st.warning("Nama rumah sudah wujud.")
        st.divider()
        st.subheader("Senarai Rumah")
        houses = list_houses()
        st.dataframe(houses, use_container_width=True)

    with st.expander("Acara Sukan"):
        with get_conn() as conn:
            st.subheader("Tambah Acara")
            name = st.text_input("Nama acara", placeholder="Contoh: 100m")
            category = st.selectbox("Kategori", ["Balapan","Padang","Permainan","Lain-lain"])
            gender = st.selectbox("Jantina", ["L","P","Campuran"])
            age_group = st.text_input("Kategori Umur (pilihan)", placeholder="Contoh: Bawah 12 / Terbuka")
            points_json = st.text_input("Sistem Mata (JSON)", value='{"1": 5, "2": 3, "3": 1}', help='Contoh: {"1":10,"2":7,"3":5,"4":3,"5":1}')
            if st.button("Simpan Acara", use_container_width=True):
                if not name.strip():
                    st.warning("Sila isi nama acara.")
                else:
                    try:
                        conn.execute("INSERT INTO events(name,category,gender,age_group,points_json) VALUES (?,?,?,?,?)", (name.strip(), category, gender, age_group.strip() or None, points_json.strip()))
                        st.success("Acara ditambah.")
                    except sqlite3.IntegrityError:
                        st.warning("Acara (nama+kategori+jantina+umur) sudah wujud.")

        st.divider()
        st.subheader("Senarai Acara")
        evs = list_events()
        st.dataframe(evs, use_container_width=True, height=240)

    with st.expander("Catat Keputusan"):
        events = list_events()
        if not events:
            st.info("Tiada acara. Tambah acara dahulu.")
            return
        event_label_map = {f"{e[1]} · {e[2]} · {e[3]} · {e[4]}": e[0] for e in events}
        chosen = st.selectbox("Pilih acara", options=list(event_label_map.keys()))
        event_id = event_label_map[chosen]
        houses = list_houses()
        house_label_map = {h[1]: h[0] for h in houses}

        c1, c2, c3 = st.columns(3)
        with c1:
            house_name = st.selectbox("Rumah", options=list(house_label_map.keys()))
        with c2:
            position = st.number_input("Kedudukan (1=emas, 2=perak, 3=gangsa, dll)", min_value=1, step=1, value=1)
        with c3:
            performance = st.text_input("Catatan/markah (pilihan)", placeholder="Contoh: 12.34s / 4.80m / 2-0")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Simpan Keputusan", type="primary"):
                try:
                    with get_conn() as conn:
                        conn.execute(
                            "INSERT INTO results(event_id, house_id, position, performance) VALUES (?,?,?,?)",
                            (event_id, house_label_map[house_name], int(position), performance.strip() or None)
                        )
                    st.success("Keputusan disimpan.")
                except sqlite3.IntegrityError:
                    st.error("Kedudukan untuk acara ini sudah diisi. Padam dahulu jika mahu tukar.")
        with c2:
            with get_conn() as conn:
                rows = conn.execute("SELECT id FROM results WHERE event_id=?", (event_id,)).fetchall()
            to_clear = st.checkbox("Padam semua keputusan acara ini")
            if to_clear and st.button("Sahkan Padam"):
                with get_conn() as conn:
                    conn.execute("DELETE FROM results WHERE event_id=?", (event_id,))
                st.success("Semua keputusan acara ini dipadam.")

        st.subheader("Keputusan Terkini Acara Ini")
        rows = list_results(event_id)
        st.dataframe(rows, use_container_width=True)

def page_scoreboard():
    st.title("🏆 Papan Skor Langsung - KOT SMT 2025")
    st.caption("Auto-refresh setiap 3 saat. Buka di skrin besar untuk paparan langsung.")
    st.experimental_set_query_params(ts=str(time.time()))
    st.markdown("<meta http-equiv='refresh' content='3'>", unsafe_allow_html=True)

    with st.expander("Tapis Paparan (pilihan)"):
        c1, c2, c3 = st.columns(3)
        with c1:
            gender = st.selectbox("Jantina", ["Semua","L","P","Campuran"], index=0)
        with c2:
            category = st.selectbox("Kategori", ["Semua","Balapan","Padang","Permainan","Lain-lain"], index=0)
        with c3:
            age_group = st.text_input("Kategori Umur", value="", placeholder="Contoh: Bawah 12 / Terbuka")
    filters = {}
    if gender != "Semua": filters["gender"] = gender
    if category != "Semua": filters["category"] = category
    if age_group.strip(): filters["age_group"] = age_group.strip()

    ranked = calc_house_totals(filters)

    c1, c2 = st.columns([2,1])
    with c1:
        st.subheader("Kedudukan Rumah")
        import pandas as pd
        df = pd.DataFrame(ranked)
        df.index = range(1, len(df)+1)
        df = df[["name","points","gold","silver","bronze"]]
        df.columns = ["Rumah","Mata","Emas","Perak","Gangsa"]
        st.dataframe(df, use_container_width=True, height=320)
    with c2:
        st.subheader("Jumlah Pingat")
        total_gold = sum(r["gold"] for r in ranked)
        total_silver = sum(r["silver"] for r in ranked)
        total_bronze = sum(r["bronze"] for r in ranked)
        st.metric("Emas", total_gold)
        st.metric("Perak", total_silver)
        st.metric("Gangsa", total_bronze)

    st.divider()
    st.subheader("Keputusan Terkini")
    rows = list_results()
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows, columns=["ID","Acara","Kategori","Jantina","Umur","Rumah","Kedudukan","Catatan"]
        )
        st.dataframe(df, use_container_width=True, height=400)
    else:
        st.info("Belum ada keputusan direkodkan.")

def page_settings():
    st.title("⚙️ Tetapan & Import/Export")
    st.caption("Konfigurasi pantas, sandaran data, dan keselamatan.")
    if not require_admin_pin():
        st.stop()
    with get_conn() as conn:
        st.subheader("PIN Admin")
        saved = get_setting("admin_pin", "")
        st.text_input("PIN semasa (kosong bermakna tiada)", value=saved, type="password", disabled=True)
        new_pin = st.text_input("Tetapkan/ubah PIN (pilihan)", type="password")
        if st.button("Simpan PIN"):
            set_setting("admin_pin", new_pin.strip())
            st.success("PIN dikemaskini.")

        st.divider()
        st.subheader("Tukar Warna Rumah")
        houses = list_houses()
        if houses:
            options = {f"{h[1]} ({h[2] or '-'})": h[0] for h in houses}
            label = st.selectbox("Rumah", list(options.keys()))
            new_color = st.text_input("Kod warna (contoh #ff0000)")
            if st.button("Simpan Warna"):
                conn.execute("UPDATE houses SET color=? WHERE id=?", (new_color.strip() or None, options[label]))
                st.success("Warna dikemaskini.")

        st.divider()
        st.subheader("Export CSV")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Export Houses CSV"):
                with get_conn() as c:
                    rows = c.execute("SELECT id,name,color FROM houses ORDER BY id").fetchall()
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["id","name","color"])
                writer.writerows(rows)
                st.download_button("Muat turun houses.csv", data=output.getvalue(), file_name="houses.csv")
        with c2:
            if st.button("Export Events CSV"):
                with get_conn() as c:
                    rows = c.execute("SELECT id,name,category,gender,age_group,points_json FROM events ORDER BY id").fetchall()
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["id","name","category","gender","age_group","points_json"])
                writer.writerows(rows)
                st.download_button("Muat turun events.csv", data=output.getvalue(), file_name="events.csv")
        with c3:
            if st.button("Export Results CSV"):
                with get_conn() as c:
                    rows = c.execute("SELECT id,event_id,house_id,position,performance,created_at FROM results ORDER BY id").fetchall()
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["id","event_id","house_id","position","performance","created_at"])
                writer.writerows(rows)
                st.download_button("Muat turun results.csv", data=output.getvalue(), file_name="results.csv")

        st.divider()
        st.subheader("Import DB (gantikan semua data)")
        uploaded = st.file_uploader("Muat Naik Fail DB (sports.db)", type=["db"])
        if uploaded:
            data = uploaded.read()
            with open(DB_PATH, "wb") as f:
                f.write(data)
            st.success("DB diganti. Muat semula halaman.")

def main():
    init_db()
    seed_demo()
    menu = st.sidebar.radio("Menu", ["Papan Skor", "Admin", "Tetapan"], index=0)
    if menu == "Papan Skor":
        page_scoreboard()
    elif menu == "Admin":
        page_admin()
    else:
        page_settings()

if __name__ == "__main__":
    main()
