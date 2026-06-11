import os
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

app = FastAPI(title="Saweria API Gateway V6 (SQLite Edition)")

api_key_header = APIKeyHeader(name="X-Worker-Token", auto_error=True)

def cek_token(api_key: str = Security(api_key_header)):
    if api_key != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Akses Ditolak")
    return api_key

# Instruksi kontrol tetap pakai JSON karena ini Komunikasi Antar Proses (IPC) yang sangat cepat
def simpan_kontrol(station_id: str, data: dict):
    path = os.path.join(DATA_DIR, f"control_{station_id}.json")
    with open(path + ".tmp", "w") as f: json.dump(data, f)
    os.replace(path + ".tmp", path)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 API Gateway Saweria (SQLite) Berjalan...")
    def jalankan_auto_resume():
        time.sleep(3)
        try:
            try: my_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
            except: my_ip = "127.0.0.1"
            requests.post(f"{PANEL_URL}/panel-donasi/api/auto-resume", json={"worker_ip": my_ip}, headers={"X-Worker-Token": WORKER_SECRET}, timeout=10)
        except: pass
    threading.Thread(target=jalankan_auto_resume, daemon=True).start()
    yield

app.router.lifespan_context = lifespan

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
    
    # 2. Disk Usage (Cek kapasitas di direktori utama Worker)
    disk = psutil.disk_usage(WORKER_DIR)
    disk_total_gb = round(disk.total / (1024**3), 2)
    disk_free_gb = round(disk.free / (1024**3), 2)
    disk_percent = disk.percent
    
    # 3. Network Speed (Kalkulasi 0.5 detik)
    net1 = psutil.net_io_counters()
    time.sleep(0.5)
    net2 = psutil.net_io_counters()
    
    # Hitung kecepatan (bytes per 0.5 detik diubah ke Megabytes per second)
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

@app.post("/api/download-gdrive")
async def worker_download_media(request: Request, api_key: str = Depends(cek_token)):
    data = await request.json()
    video_url = data.get("video_url")
    audio_url = data.get("audio_url")
    
    custom_name = data.get("custom_name", "media")
    username = data.get("username", "user")
    
    # RUMUS PENAMAAN PERSIS SEPERTI GALLERY.PY
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', custom_name)[:30]
    safe_user = re.sub(r'[^a-zA-Z0-9]', '_', username)[:20]
    
    hasil = []
    
    # 1. Download Video Background
    if video_url:
        vid_id = extract_gdrive_id(video_url)
        # CONTOH HASIL: Budi_Video_Mobil_a1b2c3_xxxxx.mp4
        nama_file_vid = f"{safe_user}_{safe_name}_{random_suffix}_{vid_id}.mp4"
        vid_path = os.path.join(WORKER_DIR, "uploads", "video_bg", nama_file_vid)
        
        sukses, msg = download_gdrive_worker(vid_id, vid_path)
        hasil.append({"tipe": "video", "status": sukses, "pesan": msg, "file": nama_file_vid})

    # 2. Download Audio (Jika ada)
    if audio_url:
        aud_id = extract_gdrive_id(audio_url)
        # CONTOH HASIL: Budi_Audio_Musik_z9y8x7_xxxxx.mp3
        nama_file_aud = f"{safe_user}_{safe_name}_{random_suffix}_{aud_id}.mp3"
        aud_path = os.path.join(WORKER_DIR, "uploads", "audio", nama_file_aud)
        
        sukses, msg = download_gdrive_worker(aud_id, aud_path)
        hasil.append({"tipe": "audio", "status": sukses, "pesan": msg, "file": nama_file_aud})

    return JSONResponse({"status": "success", "detail": hasil})
    
if __name__ == "__main__":
    uvicorn.run("api_gateway:app", host="0.0.0.0", port=8007, reload=False)