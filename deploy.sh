#!/bin/bash
# Script de Instalação e Configuração Automatizada na VPS

echo "=== [1/5] Atualizando pacotes do sistema e instalando dependências base ==="
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip ffmpeg nodejs npm git curl build-essential

echo "=== [2/5] Configurando ambiente virtual Python ==="
cd /root/shorts_cortes_ai
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r vps_requirements.txt

echo "=== [3/5] Instalando e construindo frontend Next.js ==="
# Instalar PM2 globalmente
sudo npm install -g pm2

# Instalar dependências e compilar frontend
cd /root/shorts_cortes_ai/web
npm install
npm run build

echo "=== [4/5] Configurando serviço Systemd para o Backend FastAPI ==="
# Mover o arquivo de serviço para o diretório do systemd
sudo cp /root/shorts_cortes_ai/shorts-backend.service /etc/systemd/system/shorts-backend.service
sudo systemctl daemon-reload
sudo systemctl start shorts-backend
sudo systemctl enable shorts-backend

echo "=== [5/5] Iniciando Frontend Next.js com PM2 ==="
cd /root/shorts_cortes_ai
pm2 start ecosystem.config.js
pm2 save
pm2 startup

echo "=== INSTALAÇÃO CONCLUÍDA COM SUCESSO! ==="
echo "FastAPI Backend rodando na porta 8000"
echo "Next.js Frontend rodando na porta 3000"
echo "Verifique o status do backend com: systemctl status shorts-backend"
echo "Verifique o status do frontend com: pm2 status"
