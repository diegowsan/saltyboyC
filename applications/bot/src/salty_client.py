import logging
import os
import requests
import re
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
        """Logs into SaltyBet and saves the cookies."""
        if not self.email or not self.password:
            logger.error("Cannot login: SALTY_EMAIL or SALTY_PASSWORD not set in .env")
            return False

        payload = {
            "email": self.email,
            "pword": self.password,
            "authenticate": "signin"
        }

        try:
            response = self.session.post(self.LOGIN_URL, data=payload)
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
        Fetches the current wallet balance by scraping the homepage.
        Uses updated regex to find <span ... id="balance" ...>
        """
        if not self.is_logged_in:
            if not self.login():
                return 0

        try:
            response = self.session.get(self.INDEX_URL)
            if response.status_code == 200:
                # Target: <span class="dollar" id="balance" style="...">26,520,423</span>
                # Regex Explanation:
                # <span       : Starts with <span
                # [^>]* : Any characters (class="dollar" etc)
                # id="balance": Must contain this ID
                # [^>]* : Any characters (style="..." etc)
                # >           : Closing bracket
                # ([\d,]+)    : Capture digits and commas (e.g. 26,520,423)
                match = re.search(r'<span[^>]*id="balance"[^>]*>([\d,]+)<', response.text)
                
                if match:
                    balance_str = match.group(1).replace(",", "")
                    logger.info(f"Current Balance: ${balance_str}")
                    return int(balance_str)
                else:
                    # Fallback logic in case they revert to the old ID 'b'
                    match_old = re.search(r'<span\s+id="b"[^>]*>([\d,]+)<', response.text)
                    if match_old:
                        balance_str = match_old.group(1).replace(",", "")
                        logger.info(f"Current Balance (fallback): ${balance_str}")
                        return int(balance_str)
                        
                    logger.warning("Could not find balance element on page.")
                    # Log a snippet of the page for debugging if this persists
                    logger.debug(f"Page snippet: {response.text[:500]}")
                    return 0
            else:
                logger.error(f"Failed to fetch balance. Status: {response.status_code}")
                return 0
        except Exception as e:
            logger.error(f"Balance check failed: {e}")
            return 0

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def place_bet(self, wager: int, color: str):
        """
        Places a bet.
        :param wager: Amount to bet (integer)
        :param color: 'red' or 'blue'
        """
        if not self.is_logged_in:
            if not self.login():
                return

        # SaltyBet expects 'player1' for Red and 'player2' for Blue
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
            raise e