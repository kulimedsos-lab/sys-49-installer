import os
import json
import subprocess
import re
import threading
import time
from modul_config import DATA_DIR
from core_setup import get_db_connection

STATIONS = {}

def hapus_emotikon(teks):
    return re.sub(r'[^\x00-\x7F]+', '', str(teks)).strip() if teks else ""

def get_top_donasi_db(station_id, durasi_mode):
    now = int(time.time())
    batas = 0
    if durasi_mode == "7_days": batas = now - (7 * 86400)
    elif durasi_mode == "3_days": batas = now - (3 * 86400)

    # Database melakukan perhitungan SUM secara otomatis (Sangat Ringan untuk CPU)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT nama, SUM(nominal) as total 
        FROM donasi 
        WHERE station_id = ? AND timestamp >= ? 
        GROUP BY nama 
        ORDER BY total DESC 
        LIMIT 10
    """, (station_id, batas))
    hasil = cursor.fetchall()
    conn.close()
    
    return [{"nama": r["nama"], "nominal": r["total"]} for r in hasil]

def ticker_loop(station_id):
    state = STATIONS[station_id]
    overlay_dir = f"/dev/shm/overlays/{station_id}"
    os.makedirs(overlay_dir, exist_ok=True)
    
    f_b1 = os.path.join(overlay_dir, "baris1.txt")
    f_b1_sub = os.path.join(overlay_dir, "baris1_sub.txt") 
    f_b2 = os.path.join(overlay_dir, "baris2.txt")
    f_b3 = os.path.join(overlay_dir, "baris3.txt")

    counter = 0

    while state["is_running"]:
        config = state["config"]
        # Ambil data dari SQLite, bukan dari File JSON
        top10 = get_top_donasi_db(station_id, config.get("durasi_donasi", "all_time"))
        
        preset = config.get("preset", "top10_left")
        target_donasi = int(config.get("target_donasi", 0))
        
        text1 = hapus_emotikon(config.get("judul", "TOP DONASI"))
        text1_sub, text2, text3 = " ", " ", " "
        
        if target_donasi > 0:
            total_kumpul = sum(d["nominal"] for d in top10)
            t_k = target_donasi / 1000
            d_k = total_kumpul / 1000
            text1_sub = f"Harga {int(t_k) if t_k.is_integer() else round(t_k,1)}k | Donasi Masuk {int(d_k) if d_k.is_integer() else round(d_k,1)}k"

        if preset == "top10_left":
            text2 = "\n".join([f"RANK {i+1}: {hapus_emotikon(d['nama'])} - Rp {d['nominal']:,}".replace(',', '.') for i, d in enumerate(top10[:3])]) or " "
            text3 = "\n".join([f"#{i+4}. {hapus_emotikon(d['nama'])} - Rp {d['nominal']:,}".replace(',', '.') for i, d in enumerate(top10[3:10])]) or " "
            t1, t1_sub, t2, t3 = text1, text1_sub, text2, text3
        else:
            top1_3, top4_10 = top10[:3], top10[3:10]
            if top1_3:
                d = top1_3[(counter // 7) % len(top1_3)]
                text2 = f"RANK {((counter // 7) % len(top1_3)) + 1}: {hapus_emotikon(d['nama'])} - Rp {d['nominal']:,}".replace(',', '.')
            if top4_10:
                idx = (counter // 3) % len(top4_10)
                text3 = f"#{idx + 4}. {hapus_emotikon(top4_10[idx]['nama'])} - Rp {top4_10[idx]['nominal']:,}".replace(',', '.')

            max_len = max(len(text1), len(text1_sub), len(text2), len(text3))
            t1, t1_sub, t2, t3 = text1.center(max_len, " "), text1_sub.center(max_len, " "), text2.center(max_len, " "), text3.center(max_len, " ")

        for f_path, text in [(f_b1, t1), (f_b1_sub, t1_sub), (f_b2, t2), (f_b3, t3)]:
            with open(f_path+".tmp", "w", encoding="utf-8") as f: f.write(text if text.strip() else " ")
            os.replace(f_path+".tmp", f_path)

        time.sleep(1)
        counter += 1

def pantau_perintah_api():
    print("⚙️ Core Engine Aktif: Menunggu instruksi dari API Gateway...")
    while True:
        for file in os.listdir(DATA_DIR):
            if file.startswith("control_") and file.endswith(".json"):
                station_id = file.replace("control_", "").replace(".json", "")
                path = os.path.join(DATA_DIR, file)
                
                try:
                    with open(path, "r") as f: data = json.load(f)
                except: continue 
                
                action = data.get("action")
                if station_id not in STATIONS:
                    STATIONS[station_id] = {"process": None, "ticker_thread": None, "is_running": False, "config": {}}
                state = STATIONS[station_id]

                # --- BAGIAN INI YANG SEBELUMNYA HILANG & MEMBUAT INDENTASI ERROR ---
                if action in ["START", "RUNNING"]:
                    if not state["is_running"]:
                        print(f"🔄 [RESUME] Memulihkan Stream: {station_id}...")
                        
                        # ----------------------------------------------------
                        # ANTI CRASH: Buat file teks KOSONG sebelum FFmpeg dipanggil
                        # ----------------------------------------------------
                        overlay_dir = f"/dev/shm/overlays/{station_id}"
                        os.makedirs(overlay_dir, exist_ok=True)
                        for f_name in ["baris1.txt", "baris1_sub.txt", "baris2.txt", "baris3.txt"]:
                            f_path = os.path.join(overlay_dir, f_name)
                            if not os.path.exists(f_path):
                                with open(f_path, "w", encoding="utf-8") as f: 
                                    f.write(" ")
                        # ----------------------------------------------------
                        
                        # Keamanan: Bunuh proses FFmpeg lama yang mungkin nyangkut
                        try:
                            subprocess.run(["pkill", "-f", station_id], check=False)
                            time.sleep(1) # Beri jeda 1 detik agar port RTMP bersih
                        except: pass

                        state["is_running"] = True
                        state["process"] = subprocess.Popen(data["cmd"])
                        
                        # Jalankan ulang looping teks donasinya
                        t = threading.Thread(target=ticker_loop, args=(station_id,), daemon=True)
                        t.start()
                        state["ticker_thread"] = t
                        
                        print(f"▶️ [ACTIVE] {station_id} Berhasil Jalan Kembali.")
                    
                    # Pastikan status di file tetap RUNNING
                    if action != "RUNNING":
                        data["action"] = "RUNNING"
                        with open(path+".tmp", "w") as f: json.dump(data, f)
                        os.replace(path+".tmp", path)

                elif action == "STOP":
                    state["is_running"] = False
                    if state["process"]:
                        state["process"].terminate()
                        state["process"] = None
                    print(f"⏹️ [STOP] {station_id} Dihentikan.")
                    os.remove(path)

                elif action == "UPDATE_PRESET":
                    state["config"] = data.get("config", {})
                    if state["process"]:
                        state["process"].terminate()
                        time.sleep(1)
                        state["process"] = subprocess.Popen(data["cmd"])
                    print(f"🔄 [PRESET] {station_id} Diperbarui.")
                    data["action"] = "RUNNING"
                    with open(path+".tmp", "w") as f: json.dump(data, f)
                    os.replace(path+".tmp", path)

        time.sleep(1)

if __name__ == "__main__":
    pantau_perintah_api()
