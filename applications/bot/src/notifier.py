import os
import logging
import requests

logger = logging.getLogger(__name__)

def send_discord_alert(message: str):
    """Sends a message to the configured Discord Webhook."""
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        return

    data = {
        "content": message,
        "username": "SodiumTycoon AI"
    }

    try:
        response = requests.post(webhook_url, json=data, timeout=5)
        if response.status_code != 204:
            logger.warning(f"Failed to send Discord alert: {response.status_code}")
    except Exception as e:
        logger.warning(f"Discord connection failed: {e}")