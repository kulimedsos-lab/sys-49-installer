import sqlite3
import logging
from logging.handlers import RotatingFileHandler
import os
import time

# Mengambil jalur konfigurasi langsung dari modul_config agar seragam
from modul_config import DATA_DIR, LOG_DIR, DB_PATH

# ==========================================
# 1. SISTEM LOGGING (ROTASI MAX 1MB)
# ==========================================
LOG_PATH = os.path.join(LOG_DIR, "worker_system.log")

def get_logger(name="North49_Worker"):
    logger = logging.getLogger(name)
    
    # Mencegah log tercetak ganda jika modul dipanggil berkali-kali
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        
        # FileHandler dengan rotasi otomatis: Maksimal 1MB (1024 * 1024 bytes)
        # Jika penuh, otomatis membuat worker_system.log.1, log.2, dst (backupCount=3)
        file_handler = RotatingFileHandler(
            LOG_PATH, mode='a', maxBytes=1024 * 1024, backupCount=3, encoding='utf-8'
        )
        
        # Format rapi: [WAKTU] - [LEVEL] - PESAN
        formatter = logging.Formatter(
            '%(asctime)s - [%(levelname)s] - %(message)s', 
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
    return logger

system_log = get_logger()

# ==========================================
# 3. SISTEM DATABASE SQLITE (WAL MODE)
# ==========================================
def get_db_connection():
    """Membuka koneksi ke SQLite dengan pengamanan bentrokan (WAL Mode)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    
    # AKTIFKAN WAL MODE: Agar API dan Engine bisa membaca/menulis bersamaan tanpa error
    conn.execute('pragma journal_mode=wal')
    conn.execute('pragma synchronous=normal')
    
    # Ubah format hasil query menjadi dictionary agar mudah diolah (seperti JSON)
    conn.row_factory = sqlite3.Row  
    return conn

def init_database():
    """Fungsi eksekutor untuk meng-generate tabel-tabel secara otomatis."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        system_log.info("Memulai inisialisasi struktur database pekerja...")

        # TABEL 1: Manajemen Station (Menyimpan status mesin)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_status (
                station_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'stopped',
                pid INTEGER,
                module_type TEXT DEFAULT 'saweria',
                config_json TEXT,
                last_updated INTEGER
            )
        ''')

        # TABEL 2: Modul Donasi
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS donasi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id TEXT,
                nama TEXT,
                nominal INTEGER,
                timestamp INTEGER
            )
        ''')
        # Buat Index untuk mempercepat kalkulasi ranking sum(nominal) tanpa makan CPU
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_donasi ON donasi(station_id, timestamp)')

        # TABEL 3: Modul Playlist Interaktif (Masa Depan)
        # Tabel ini dirancang untuk memastikan beberapa video diputar terus sampai durasi audio habis tanpa freeze
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS playlist_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id TEXT,
                file_path TEXT,
                media_type TEXT,
                status TEXT DEFAULT 'waiting',
                created_at INTEGER
            )
        ''')

        # TABEL 4: Modul Custom Stream (Masa Depan)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_stream (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id TEXT,
                cmd_overlay TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')

        conn.commit()
        system_log.info("Database berhasil diinisialisasi dan siap digunakan.")
        
        print(f"✅ GENERATE SUKSES!")
        print(f"📁 Lokasi DB   : {DB_PATH}")
        print(f"📁 Lokasi Log  : {LOG_PATH} (Max 1MB Auto-Rotate)")

    except Exception as e:
        error_msg = f"Gagal membuat database: {e}"
        system_log.error(error_msg)
        print(f"❌ ERROR: {error_msg}")
    finally:
        conn.close()

# Jalankan generator otomatis jika file ini dieksekusi langsung
if __name__ == "__main__":
    init_database()