#!/bin/bash
echo "=================================================="
echo "🚀 AUTO INSTALLER NORTH49 WORKER NODE (VPS KLIEN) 🚀"
echo "=================================================="

WORKER_DIR="/home/ubuntu/mux_worker"

echo -e "\n[1/6] Memperbarui Sistem & Menginstal Kebutuhan Dasar..."
sudo apt-get update -y
sudo apt-get install -y ffmpeg python3-pip curl software-properties-common

echo -e "\n[2/6] Menginstal Node.js & PM2 (Untuk menjaga server hidup 24/7)..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2

echo -e "\n[3/6] Menginstal Library Python (FastAPI, Uvicorn, Psutil, dll)..."
sudo pip3 install fastapi uvicorn requests psutil python-multipart --break-system-packages

echo -e "\n[4/6] Membangun Struktur Folder Mux Worker..."
mkdir -p $WORKER_DIR/uploads/video_bg
mkdir -p $WORKER_DIR/uploads/audio
mkdir -p $WORKER_DIR/data
mkdir -p $WORKER_DIR/logs

# Mengopi file dari folder git hasil download ke folder sistem Worker
echo "Memindahkan file sistem..."
cp api_gateway.py core_engine.py core_setup.py modul_config.py Roboto-Bold.ttf $WORKER_DIR/ 2>/dev/null || true
cd $WORKER_DIR

echo -e "\n[5/6] Menginisialisasi Database SQLite..."
python3 core_setup.py

echo -e "\n[6/6] Menjalankan Mesin via PM2..."
pm2 start api_gateway.py --name "worker-api" --interpreter python3
pm2 start core_engine.py --name "worker-engine" --interpreter python3
pm2 save
sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u ubuntu --hp /home/ubuntu

echo "=================================================="
echo "✅ INSTALASI SELESAI DENGAN SUKSES!"
echo "Worker API kini berjalan di Port 8007."
echo "=================================================="