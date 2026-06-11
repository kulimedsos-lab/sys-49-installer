import os

# ========================================================
# 1. URL PANEL PUSAT & TOKEN KEAMANAN
# ========================================================
PANEL_URL = "http://51.222.138.42:8000"
WORKER_SECRET = "North49_@dmin778_2026"

# ========================================================
# 2. PATH PENYIMPANAN LOKAL DI VPS WORKER INI
# ========================================================
WORKER_DIR = "/home/ubuntu/mux_worker"
VIDEO_BG_DIR = os.path.join(WORKER_DIR, "uploads", "video_bg")
AUDIO_DIR = os.path.join(WORKER_DIR, "uploads", "audio")

DATA_DIR = os.path.join(WORKER_DIR, "data")
LOG_DIR = os.path.join(WORKER_DIR, "logs")

# Path Database SQLite
DB_PATH = os.path.join(DATA_DIR, "pusat_data.db")

# Pastikan folder otomatis terbuat
os.makedirs(VIDEO_BG_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)