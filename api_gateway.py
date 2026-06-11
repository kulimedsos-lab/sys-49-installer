import os
import sys
import json
import shutil
import time
import re
import requests
import psutil
import uvicorn
import threading
import random
import string
from fastapi import FastAPI, Request, File, UploadFile, Form, Security, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from contextlib import asynccontextmanager

from modul_config import PANEL_URL, WORKER_SECRET, WORKER_DIR, DATA_DIR
from core_setup import get_db_connection, system_log

try:
    from modul_config import PAIRING_KEY
except ImportError:
    PAIRING_KEY = ""

# ==========================================
# 1. INISIALISASI APLIKASI & KEAMANAN
# ==========================================
app = FastAPI(title="Saweria API Gateway V6 (SQLite Edition)")

api_key_header = APIKeyHeader(name="X-Worker-Token", auto_error=True)

def cek_token(api_key: str = Security(api_key_header)):
    if not WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Worker ini belum di-pairing!")
    if api_key != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Akses Ditolak")
    return api_key

# ==========================================
# 2. FUNGSI PEMBANTU (HELPERS)
# ==========================================
def simpan_kontrol(station_id: str, data: dict):
    """Menyimpan instruksi kontrol ke file JSON untuk dibaca oleh Engine (IPC)"""
    path = os.path.join(DATA_DIR, f"control_{station_id}.json")
    with open(path + ".tmp", "w") as f: 
        json.dump(data, f)
    os.replace(path + ".tmp", path)

def extract_gdrive_id(url: str):
    """Mengekstrak ID dari URL Google Drive"""
    match = re.search(r'(?:id=|/d/)([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else url

def download_gdrive_worker(gdrive_id: str, output_path: str):
    try:
        url = f"https://drive.usercontent.google.com/download?id={gdrive_id}&export=download&confirm=t"
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        response = session.get(url, stream=True, allow_redirects=True)
        if 'confirm=' in response.url:
            confirm = re.search(r'confirm=([^&]+)', response.url).group(1)
            url = f"https://drive.usercontent.google.com/download?id={gdrive_id}&export=download&confirm={confirm}"
            response = session.get(url, stream=True, allow_redirects=True)
            
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if chunk: f.write(chunk)
        return True, "Download sukses"
    except Exception as e:
        return False, str(e)

# ==========================================
# 3. LIFESPAN (AUTO-RESUME & STARTUP)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 API Gateway Saweria (SQLite) Berjalan...")
    def jalankan_auto_resume():
        time.sleep(3)
        try:
            try: 
                my_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
            except: 
                my_ip = "127.0.0.1"
            requests.post(
                f"{PANEL_URL}/panel-donasi/api/auto-resume", 
                json={"worker_ip": my_ip}, 
                headers={"X-Worker-Token": WORKER_SECRET}, 
                timeout=10
            )
        except: 
            pass
            
    threading.Thread(target=jalankan_auto_resume, daemon=True).start()
    yield

app.router.lifespan_context = lifespan

# ==========================================
# 4. ENDPOINT KEAMANAN & PAIRING
# ==========================================
@app.post("/api/pairing")
async def proses_pairing_handshake(request: Request):
    """Endpoint awal untuk suntik rahasia dari Panel Pusat. Tidak diproteksi Depends(cek_token)"""
    data = await request.json()
    input_key = data.get("pairing_key")
    
    # Kunci Keamanan: Jika rahasia sudah terisi, endpoint ini mati permanen
    if WORKER_SECRET != "":
        return JSONResponse({"status": "error", "message": "Akses Ditolak! Server ini sudah pernah di-pairing."}, status_code=403)
        
    # Cek apakah kode dari panel cocok dengan yang ada di layar terminal klien
    if input_key != PAIRING_KEY:
        return JSONResponse({"status": "error", "message": "Kode Pairing Salah atau Tidak Valid!"}, status_code=403)
        
    # Timpa file konfigurasi dengan rahasia asli dari Panel Pusat
    config_path = os.path.join(WORKER_DIR, "modul_config.py")
    try:
        with open(config_path, "r") as f:
            konten = f.read()
            
        konten = konten.replace('PANEL_URL = ""', f'PANEL_URL = "{data.get("panel_url")}"')
        konten = konten.replace('WORKER_SECRET = ""', f'WORKER_SECRET = "{data.get("worker_secret")}"')
        konten = konten.replace(f'PAIRING_KEY = "{PAIRING_KEY}"', 'PAIRING_KEY = ""')
        
        with open(config_path, "w") as f:
            f.write(konten)
            
        # Fungsi restart otomatis agar config baru langsung aktif via PM2
        def reboot_engine():
            time.sleep(2)
            os._exit(0)
            
        threading.Thread(target=reboot_engine, daemon=True).start()
        return JSONResponse({"status": "success", "message": "Pairing sukses! Worker siap digunakan."})
        
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"Gagal menulis konfigurasi: {e}"}, status_code=500)

# ==========================================
# 5. ENDPOINT KONTROL STREAM
# ==========================================
@app.post("/api/start")
async def start_stream(request: Request, api_key: str = Depends(cek_token)):
    data = await request.json()
    simpan_kontrol(data.get("station_id"), {"action": "START", "cmd": data.get("cmd"), "config": data.get("config", {})})
    return JSONResponse({"status": "success", "message": "START dikirim ke Engine!"})

@app.post("/api/stop")
async def stop_stream(request: Request, api_key: str = Depends(cek_token)):
    simpan_kontrol((await request.json()).get("station_id"), {"action": "STOP"})
    return JSONResponse({"status": "success", "message": "STOP dikirim ke Engine!"})

@app.post("/api/preset")
async def update_preset(request: Request, api_key: str = Depends(cek_token)):
    data = await request.json()
    simpan_kontrol(data.get("station_id"), {"action": "UPDATE_PRESET", "cmd": data.get("cmd"), "config": data.get("config", {})})
    return JSONResponse({"status": "success", "message": "Preset diperbarui!"})

@app.post("/api/donate")
async def inject_donation(request: Request, api_key: str = Depends(cek_token)):
    data = await request.json()
    station_id = data.get("station_id")
    
    # SIMPAN DONASI LANGSUNG KE SQLITE
    try:
        conn = get_db_connection()
        conn.execute("INSERT INTO donasi (station_id, nama, nominal, timestamp) VALUES (?, ?, ?, ?)",
                     (station_id, data.get("nama"), int(data.get("nominal", 0)), int(time.time())))
        conn.commit()
        conn.close()
    except Exception as e:
        system_log.error(f"Gagal simpan donasi DB: {e}")
        
    return JSONResponse({"status": "success", "message": "Donasi masuk ke Database!"})

# ==========================================
# 6. ENDPOINT MANAJEMEN MEDIA & STATS
# ==========================================
@app.post("/api/upload")
async def terima_file_dari_panel(file: UploadFile = File(...), tipe_media: str = Form(...), api_key: str = Depends(cek_token)):
    target_dir = os.path.join(WORKER_DIR, "uploads", tipe_media)
    with open(os.path.join(target_dir, file.filename), "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"status": "success"}

@app.get("/api/stats")
async def get_vps_stats(api_key: str = Depends(cek_token)):
    # 1. CPU & RAM (Interval 0.5 detik untuk akurasi)
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent
    
    # 2. Disk Usage
    disk = psutil.disk_usage(WORKER_DIR)
    disk_total_gb = round(disk.total / (1024**3), 2)
    disk_free_gb = round(disk.free / (1024**3), 2)
    disk_percent = disk.percent
    
    # 3. Network Speed
    net1 = psutil.net_io_counters()
    time.sleep(0.5)
    net2 = psutil.net_io_counters()
    
    upload_mbs = round(((net2.bytes_sent - net1.bytes_sent) * 2) / (1024 * 1024), 2)
    download_mbs = round(((net2.bytes_recv - net1.bytes_recv) * 2) / (1024 * 1024), 2)
    
    return {
        "status": "online",
        "cpu_percent": cpu,
        "ram_percent": ram,
        "disk": {
            "total_gb": disk_total_gb,
            "free_gb": disk_free_gb,
            "percent": disk_percent
        },
        "network": {
            "upload_mbs": upload_mbs,
            "download_mbs": download_mbs
        }
    }

@app.post("/api/download-gdrive")
async def worker_download_media(request: Request, api_key: str = Depends(cek_token)):
    data = await request.json()
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    
    custom_name = data.get("custom_name", "media")
    username = data.get("username", "user")
    
    # Rumus penamaan persis seperti panel pusat
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', custom_name)[:30]
    safe_user = re.sub(r'[^a-zA-Z0-9]', '_', username)[:20]
    
    hasil = []
    
    # Download Video Background
    if video_url:
        vid_id = extract_gdrive_id(video_url)
        nama_file_vid = f"{safe_user}_{safe_name}_{random_suffix}_{vid_id}.mp4"
        vid_path = os.path.join(WORKER_DIR, "uploads", "video_bg", nama_file_vid)
        
        sukses, msg = download_gdrive_worker(vid_id, vid_path)
        hasil.append({"tipe": "video", "status": sukses, "pesan": msg, "file": nama_file_vid})

    # Download Audio
    if audio_url:
        aud_id = extract_gdrive_id(audio_url)
        nama_file_aud = f"{safe_user}_{safe_name}_{random_suffix}_{aud_id}.mp3"
        aud_path = os.path.join(WORKER_DIR, "uploads", "audio", nama_file_aud)
        
        sukses, msg = download_gdrive_worker(aud_id, aud_path)
        hasil.append({"tipe": "audio", "status": sukses, "pesan": msg, "file": nama_file_aud})

    return JSONResponse({"status": "success", "detail": hasil})
    
# ==========================================
# 7. EKSEKUSI UTAMA
# ==========================================
if __name__ == "__main__":
    uvicorn.run("api_gateway:app", host="0.0.0.0", port=8007, reload=False)
