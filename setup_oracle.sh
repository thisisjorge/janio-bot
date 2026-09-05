#!/bin/bash
echo "🚀 Iniciando a instalação automática do Janio Bot na Oracle Cloud..."

# Atualizar o sistema e instalar dependências
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-v2

# Iniciar o Docker
sudo systemctl enable --now docker

# Baixar o código do GitHub
if [ -d "janio-bot" ]; then
    echo "Atualizando código existente..."
    cd janio-bot
    git pull
else
    echo "Baixando o Janio Bot..."
    git clone https://github.com/thisisjorge/janio-bot.git
    cd janio-bot
fi

# Criar o arquivo .env
echo ""
echo "⚠️ PRECISAMOS DO SEU TOKEN DO DISCORD!"
read -p "Cole o Token do Bot aqui: " DISCORD_TOKEN
read -p "Cole a Chave da Riot API aqui (ou aperte Enter para ignorar): " RIOT_API_KEY

echo "DISCORD_TOKEN=$DISCORD_TOKEN" > .env
if [ ! -z "$RIOT_API_KEY" ]; then
    echo "RIOT_API_KEY=$RIOT_API_KEY" >> .env
fi
echo "SYNC_COMMANDS=true" >> .env
echo "JANIO_MODE=community" >> .env

echo "✅ Arquivo .env criado com sucesso!"

# Construir e rodar a máquina
echo "🐳 Construindo o servidor (isso pode demorar uns minutos na primeira vez)..."
sudo docker build -t janio-bot .

echo "🔥 Ligando o Janio Bot!"
sudo docker run -d --name janio --restart unless-stopped --env-file .env janio-bot

echo "🎉 PRONTO! O bot já está rodando 24 horas por dia de graça!"
echo "Para ver os logs do bot, digite: sudo docker logs -f janio"
