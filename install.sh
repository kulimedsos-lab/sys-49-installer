#!/bin/bash
echo "=================================================="
echo "🚀 AUTO INSTALLER NORTH49 WORKER NODE (VPS KLIEN) 🚀"
echo "=================================================="

WORKER_DIR="/home/ubuntu/mux_worker"
REPO_URL="https://raw.githubusercontent.com/kulimedsos-lab/north49live/main"

# Generate Kode Pairing Acak (6 Karakter Huruf Besar & Angka)
PAIRING_KEY=$(cat /dev/urandom | tr -dc 'A-Z0-9' | fold -w 6 | head -n 1)

echo -e "\n[1/7] Membuat Struktur Folder & Konfigurasi Awal..."
mkdir -p $WORKER_DIR/uploads/video_bg
mkdir -p $WORKER_DIR/uploads/audio
mkdir -p $WORKER_DIR/data
mkdir -p $WORKER_DIR/logs

# Injeksi config kosong. Rahasia Anda aman!
cat <<EOF > $WORKER_DIR/modul_config.py
import os

# Akan diisi otomatis oleh mesin saat Pairing
PANEL_URL = ""
WORKER_SECRET = ""
PAIRING_KEY = "$PAIRING_KEY"

WORKER_DIR = "$WORKER_DIR"
VIDEO_BG_DIR = os.path.join(WORKER_DIR, "uploads", "video_bg")
AUDIO_DIR = os.path.join(WORKER_DIR, "uploads", "audio")
DATA_DIR = os.path.join(WORKER_DIR, "data")
LOG_DIR = os.path.join(WORKER_DIR, "logs")
DB_PATH = os.path.join(DATA_DIR, "pusat_data.db")

os.makedirs(VIDEO_BG_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
EOF

echo -e "\n[2/7] Memperbarui Sistem & Menginstal Kebutuhan Dasar..."
sudo apt-get update -y
sudo apt-get install -y ffmpeg python3-pip curl software-properties-common

echo -e "\n[3/7] Menginstal Node.js & PM2..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2

echo -e "\n[4/7] Menginstal Library Python..."
sudo pip3 install fastapi uvicorn requests psutil python-multipart --break-system-packages

echo -e "\n[5/7] Mengunduh File Sistem dari GitHub..."
cd $WORKER_DIR
curl -sO $REPO_URL/api_gateway.py
curl -sO $REPO_URL/core_engine.py
curl -sO $REPO_URL/core_setup.py
curl -sO $REPO_URL/Roboto-Bold.ttf

echo -e "\n[6/7] Menginisialisasi Database SQLite..."
python3 core_setup.py

echo -e "\n[7/7] Menjalankan Mesin via PM2..."
pm2 start api_gateway.py --name "worker-api" --interpreter python3
pm2 start core_engine.py --name "worker-engine" --interpreter python3
pm2 save
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u ubuntu --hp /home/ubuntu

# Ambil IP VPS Klien untuk ditampilkan
CLIENT_IP=$(curl -s https://api.ipify.org)

echo "=================================================="
echo "✅ INSTALASI WORKER SELESAI!"
echo "Silakan kembali ke Panel Pusat North49 Anda."
echo "Klik 'Tambah Server' dan masukkan data berikut:"
echo ""
echo "IP Server    : $CLIENT_IP"
echo "Kode Pairing : $PAIRING_KEY"
echo "=================================================="
