#!/bin/bash
# run_ingest.sh - Wrapper for ingest.py with Telegram alerts
# This script runs the hourly cron job and sends a Telegram alert if it crashes.

cd "$(dirname "$0")"

# Activate the virtual environment
source venv/bin/activate

# Execute ingest.py and capture the exit code
if ! python ingest.py >> ingest.log 2>&1; then
    # The script crashed (exit code != 0)
    
    # Load environment variables (need TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
    export $(grep -v '^#' .env | xargs)
    
    # Send alert to Telegram
    ERROR_MSG="🚨 *CRITICAL ALERT* 🚨%0A%0AThe hourly Vanguard Wire ingestion script (\`ingest.py\`) just crashed on the server!%0A%0ACheck the VPS \`engine/ingest.log\` for details."
    
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d text="${ERROR_MSG}" \
        -d parse_mode="Markdown" > /dev/null
        
    echo "Ingestion failed! Alert sent to Telegram."
fi
