import logging
import os
import re
import requests
from tenacity import retry, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)

class SaltyWebClient:
    LOGIN_URL = "https://www.saltybet.com/authenticate?signin=1"
    BET_URL = "https://www.saltybet.com/ajax_place_bet.php"
    INDEX_URL = "https://www.saltybet.com/"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.saltybet.com/",
        "Origin": "https://www.saltybet.com",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self.email = os.getenv("SALTY_EMAIL")
        self.password = os.getenv("SALTY_PASSWORD")
        self.is_logged_in = False

    def login(self):
        """
        Logs into SaltyBet using the proven 'Old School' logic.
        """
        if not self.email or not self.password:
            logger.error("Cannot login: SALTY_EMAIL or SALTY_PASSWORD not set in .env")
            return False

        payload = {
            "email": self.email,
            "pword": self.password,
            "authenticate": "signin"
        }

        try:
            # Direct POST (Proven to work)
            response = self.session.post(self.LOGIN_URL, data=payload)
            
            # Check for cookie
            if "PHPSESSID" in self.session.cookies:
                self.is_logged_in = True
                logger.info("Successfully logged into SaltyBet.")
                return True
            else:
                logger.error("Login failed. Check credentials.")
                return False
        except Exception as e:
            logger.error(f"Login connection error: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_wallet_balance(self) -> int:
        """
        Fetches the current wallet balance.
        """
        if not self.is_logged_in:
            if not self.login():
                return 0

        try:
            response = self.session.get(self.INDEX_URL)
            if response.status_code == 200:
                match = re.search(r'<span[^>]*id="balance"[^>]*>([\d,]+)<', response.text)
                if match:
                    return int(match.group(1).replace(",", ""))
                
                match_old = re.search(r'<span\s+id="b"[^>]*>([\d,]+)<', response.text)
                if match_old:
                    return int(match_old.group(1).replace(",", ""))
                    
                return 0
            return 0
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def place_bet(self, wager: int, color: str):
        """
        Places a bet.
        """
        if not self.is_logged_in:
            if not self.login():
                return

        selected_player = "player1" if color.lower() == "red" else "player2"
        payload = {
            "selectedplayer": selected_player,
            "wager": str(wager),
        }

        try:
            response = self.session.post(self.BET_URL, data=payload)
            if response.status_code == 200:
                logger.info(f"BET PLACED: ${wager} on {color.upper()}")
            else:
                logger.warning(f"Failed to place bet. Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Betting request failed: {e}")