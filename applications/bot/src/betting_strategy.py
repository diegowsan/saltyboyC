import math
from datetime import datetime, timezone
from sqlalchemy import text

# --- CONFIGURATION (Your Tuned Values) ---
MAX_BET_CAP = 300000          # Slightly raised for your $30M bankroll
X_TIER_CAP = 20000            # Kept strict for safety
EFFECTIVE_BALANCE_CAP = 5000000 # Wealth preservation active
MIN_MATCHES = 3               # Minimum sample size for H2H
STALE_THRESHOLD_HOURS = 24    # Streak expiration

class BettingEngine:
    def __init__(self, db_session, weights=None):
        self.db = db_session
        self.weights = weights if weights else {
            "intercept": -0.02,
            "tier_elo": 0.0055,
            "streak": 0.012,
            "h2h": 1.5,
            "comp": 0.16
        }

    def get_fighter(self, name):
        query = text("SELECT * FROM fighter WHERE name = :name")
        row = self.db.execute(query, {"name": name}).fetchone()
        return row

    def get_safe_streak(self, fighter):
        """Returns 0 if streak is stale (>24h), otherwise returns current streak."""
        if not fighter or not fighter.current_streak: return 0
        if not fighter.last_match_date: return 0
        
        now = datetime.now(timezone.utc)
        # Ensure timezone awareness
        last_match = fighter.last_match_date
        if last_match.tzinfo is None:
            last_match = last_match.replace(tzinfo=timezone.utc)
            
        if (now - last_match).total_seconds() > (STALE_THRESHOLD_HOURS * 3600):
            return 0
        return fighter.current_streak

    def get_h2h_score(self, red_id, blue_id):
        """Returns H2H advantage (-0.5 to 0.5) only if enough matches exist."""
        query = text("""SELECT winner FROM match WHERE (fighter_red = :r AND fighter_blue = :b) OR (fighter_red = :b AND fighter_blue = :r)""")
        matches = self.db.execute(query, {"r": red_id, "b": blue_id}).fetchall()
        
        if len(matches) < MIN_MATCHES: return 0.0 # Safety check
        
        red_wins = sum(1 for m in matches if m.winner == red_id)
        return (red_wins / len(matches)) - 0.5

    def get_comp_score(self, red_id, blue_id):
        """Returns Common Opponent advantage."""
        # Simplified query for speed
        q_red = text("SELECT fighter_red, fighter_blue, winner FROM match WHERE fighter_red = :id OR fighter_blue = :id LIMIT 100")
        q_blue = text("SELECT fighter_red, fighter_blue, winner FROM match WHERE fighter_red = :id OR fighter_blue = :id LIMIT 100")
        red_matches = self.db.execute(q_red, {"id": red_id}).fetchall()
        blue_matches = self.db.execute(q_blue, {"id": blue_id}).fetchall()
        
        def build_map(matches, self_id):
            opp_map = {}
            for m in matches:
                opp_id = m.fighter_blue if m.fighter_red == self_id else m.fighter_red
                res = 'win' if m.winner == self_id else 'loss'
                opp_map[opp_id] = res
            return opp_map

        red_opps = build_map(red_matches, red_id)
        blue_opps = build_map(blue_matches, blue_id)
        
        common_wins, common_total = 0, 0
        for opp_id, red_res in red_opps.items():
            if opp_id in blue_opps:
                blue_res = blue_opps[opp_id]
                # Triangle Theory: A > C > B implies A > B
                if red_res == 'win' and blue_res == 'loss': 
                    common_wins += 1; common_total += 1
                elif red_res == 'loss' and blue_res == 'win': 
                    common_total += 1
                    
        if common_total < MIN_MATCHES: return 0.0
        return (common_wins / common_total) - 0.5

    def get_bet(self, red_name, blue_name, balance):
        red = self.get_fighter(red_name)
        blue = self.get_fighter(blue_name)

        # --- TIER SAFETY ---
        # Potato Tier (P) is random. Bet minimum.
        if not red or not blue or red.tier == 'P' or blue.tier == 'P': 
            return 1, "red", 0.5

        # --- FEATURE CALCULATION ---
        streak_diff = self.get_safe_streak(red) - self.get_safe_streak(blue)
        elo_diff = red.tier_elo - blue.tier_elo
        h2h_val = self.get_h2h_score(red.id, blue.id)
        comp_val = self.get_comp_score(red.id, blue.id)

        z = (self.weights.get('intercept', 0.0) + 
             (self.weights.get('tier_elo', 0.0) * elo_diff) +
             (self.weights.get('streak', 0.0) * streak_diff) + 
             (self.weights.get('h2h', 0.0) * h2h_val) +
             (self.weights.get('comp', 0.0) * comp_val))
             
        try: prob_red = 1 / (1 + math.exp(-z))
        except OverflowError: prob_red = 0.0 if z < 0 else 1.0

        # --- SKEPTICISM ENGINE ---
        
        # 1. Clamp Confidence (Prevent 99% certainty)
        if prob_red > 0.85: prob_red = 0.85
        if prob_red < 0.15: prob_red = 0.15

        if prob_red > 0.5: color = "red"; confidence = prob_red
        else: color = "blue"; confidence = 1 - prob_red

        # 2. Wealth Preservation (Use Effective Cap)
        # We only bet a % of $5M, even if we have $30M.
        betting_balance = min(balance, EFFECTIVE_BALANCE_CAP)
        
        # 3. Dynamic Kelly (Risk Management)
        # 5% Base * Strength Factor (0 to 1)
        strength = (confidence - 0.5) * 2
        wager = int(betting_balance * 0.05 * strength)

        # 4. X-Tier Safety Cap (Gimmick Matches)
        if red.tier == 'X' or blue.tier == 'X': 
            wager = min(wager, X_TIER_CAP)

        # 5. Final Sanity Checks
        wager = min(max(1, wager), MAX_BET_CAP)
        
        return wager, color, confidence