#!/bin/bash
set -e

echo "🚀 Iniciando Setup do Servidor TCC..."

# 1. Atualizar Sistema e Instalar Dependências Básicas
echo "📦 Atualizando sistema e instalando dependências..."
sudo apt-get update
sudo apt-get install -y git curl

# 2. Instalar Docker (Script Oficial)
if ! command -v docker &> /dev/null; then
    echo "🐳 Instalando Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "⚠️  Docker instalado. Talvez seja necessário fazer logout/login para usar sem sudo."
else
    echo "✅ Docker já instalado."
fi

# 3. Clonar/Atualizar Repositório
REPO_DIR="tcc2-agente-inteligente"
REPO_URL="https://github.com/yaguts1/tcc2-agente-inteligente.git"
BRANCH="feat/websocket-esp32"

if [ -d "$REPO_DIR" ]; then
    echo "📂 Diretório $REPO_DIR já existe. Atualizando..."
    cd $REPO_DIR
    git fetch origin
    git checkout $BRANCH
    git pull origin $BRANCH
else
    echo "📂 Clonando repositório..."
    git clone -b $BRANCH $REPO_URL
    cd $REPO_DIR
fi

# 4. Deploy com Docker Compose
echo "🚀 Subindo containers..."
sudo docker compose up -d --build

echo "---------------------------------------------------"
echo "✅ DEPLOY CONCLUÍDO COM SUCESSO!"
echo "---------------------------------------------------"
echo "📝 Logs: sudo docker compose logs -f"
echo "🌍 URL: http://$(curl -s ifconfig.me):8000/TCC"
echo "---------------------------------------------------"
