#!/bin/bash
set -e

# ==========================================
# Vanguard Wire - VPS Deployment Script
# Designed for Ubuntu/Debian Servers (e.g. DigitalOcean)
# ==========================================

echo "🚀 Starting Vanguard Wire Deployment..."

# 1. System Updates and Dependencies
echo "📦 Installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

# 2. Clone the repository if it doesn't exist
APP_DIR="$HOME/vanguard-wire"
REPO_URL="https://github.com/BertNgomsi/vanguard-wire.git"

if [ ! -d "$APP_DIR" ]; then
    echo "📥 Cloning repository..."
    git clone "$REPO_URL" "$APP_DIR"
else
    echo "🔄 Pulling latest code..."
    cd "$APP_DIR"
    git pull origin main
fi

# 3. Setup Python Virtual Environment
echo "🐍 Setting up Python environment..."
cd "$APP_DIR/engine"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt || pip install requests flask google-genai python-dotenv feedparser

# 4. Prompt for .env variables if not exists
if [ ! -f ".env" ]; then
    echo "🔑 Configuring Environment Variables..."
    read -p "Enter GEMINI_API_KEY: " gemini_key
    read -p "Enter TELEGRAM_BOT_TOKEN: " telegram_token
    read -p "Enter TELEGRAM_CHAT_ID: " chat_id
    read -p "Enter GITHUB_TOKEN: " github_token
    
    cat <<EOF > .env
GEMINI_API_KEY="$gemini_key"
TELEGRAM_BOT_TOKEN="$telegram_token"
TELEGRAM_CHAT_ID="$chat_id"
GITHUB_TOKEN="$github_token"
EOF
    echo "✅ .env file created."
fi

# 5. Create Systemd Service for Webhook
echo "⚙️ Configuring Webhook Service..."
SERVICE_FILE="/etc/systemd/system/vanguard-webhook.service"
sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Vanguard Wire Telegram Webhook
After=network.target

[Service]
User=$USER
WorkingDirectory=$APP_DIR/engine
Environment=\"PATH=$APP_DIR/engine/venv/bin\"
ExecStart=$APP_DIR/engine/venv/bin/python webhook.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable vanguard-webhook
sudo systemctl restart vanguard-webhook
echo "✅ Webhook service started (runs on port 5001)."

# 6. Setup Hourly Cron Job for RSS Ingestion
echo "⏱️ Setting up Cron Job..."
CRON_JOB="0 * * * * cd $APP_DIR/engine && $APP_DIR/engine/venv/bin/python ingest.py >> $APP_DIR/engine/ingest.log 2>&1"
(crontab -l 2>/dev/null | grep -v "ingest.py"; echo "$CRON_JOB") | crontab -
echo "✅ Cron job installed (runs every hour at minute 0)."

echo ""
echo "🎉 DEPLOYMENT COMPLETE! 🎉"
echo "Next Steps:"
echo "1. Use Nginx or Caddy to proxy port 5001 and secure it with SSL (HTTPS)."
echo "2. Tell Telegram about your new server's webhook URL:"
echo "   https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://YOUR_DOMAIN/webhook/<YOUR_TOKEN>"
echo "3. You can manually test ingestion by running: cd $APP_DIR/engine && source venv/bin/activate && python ingest.py"
