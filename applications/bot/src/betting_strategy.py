import math
from sqlalchemy import text

# --- CONFIGURATION ---
MAX_BET_CAP = 250000          # HARD CEILING: Never bet more than this
X_TIER_CAP = 20000            # GIMMICK CEILING: Max risk for X-tier
EFFECTIVE_BALANCE_CAP = 5000000 # WHALE FIX: Pretend we only have $5M so bets vary
MIN_MATCHES = 3               # Minimum history

class BettingEngine:
    def __init__(self, db_session, weights=None):
        self.db = db_session
        self.weights = weights if weights else {
            "intercept": 0.0,
            "tier_elo": 0.0057,
            "h2h": 4.0,
            "comp": 2.0
        }

    def get_fighter(self, name):
        query = text("SELECT * FROM fighter WHERE name = :name")
        row = self.db.execute(query, {"name": name}).fetchone()
        return row

    def get_h2h_score(self, red_id, blue_id):
        query = text("""
            SELECT winner FROM match 
            WHERE (fighter_red = :r AND fighter_blue = :b) 
               OR (fighter_red = :b AND fighter_blue = :r)
        """)
        matches = self.db.execute(query, {"r": red_id, "b": blue_id}).fetchall()
        
        if len(matches) < MIN_MATCHES:
            return 0.0
            
        red_wins = sum(1 for m in matches if m.winner == red_id)
        win_rate = red_wins / len(matches)
        return win_rate - 0.5

    def get_comp_score(self, red_id, blue_id):
        q_red = text("SELECT fighter_red, fighter_blue, winner FROM match WHERE fighter_red = :id OR fighter_blue = :id")
        q_blue = text("SELECT fighter_red, fighter_blue, winner FROM match WHERE fighter_red = :id OR fighter_blue = :id")
        
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
        
        common_wins = 0
        common_total = 0
        
        for opp_id, red_res in red_opps.items():
            if opp_id in blue_opps:
                blue_res = blue_opps[opp_id]
                if red_res == 'win' and blue_res == 'loss':
                    common_wins += 1
                    common_total += 1
                elif red_res == 'loss' and blue_res == 'win':
                    common_total += 1 
                    
        if common_total < MIN_MATCHES:
            return 0.0
            
        return (common_wins / common_total) - 0.5

    def get_bet(self, red_name, blue_name, balance):
        """
        Returns (amount, color, confidence_percentage)
        """
        red = self.get_fighter(red_name)
        blue = self.get_fighter(blue_name)

        # 1. UNKNOWN or POTATO FIGHTERS
        if not red or not blue or red.tier == 'P' or blue.tier == 'P':
            return 1, "red", 0.5

        # 2. CALCULATE PROBABILITY
        elo_diff = red.tier_elo - blue.tier_elo
        h2h_val = self.get_h2h_score(red.id, blue.id)
        comp_val = self.get_comp_score(red.id, blue.id)

        z = (self.weights.get('intercept', 0.0) + 
             (self.weights.get('tier_elo', 0.0) * elo_diff) +
             (self.weights.get('h2h', 0.0) * h2h_val) +
             (self.weights.get('comp', 0.0) * comp_val))
             
        try:
            prob_red = 1 / (1 + math.exp(-z))
        except OverflowError:
            prob_red = 0.0 if z < 0 else 1.0

        # 3. DETERMINE WAGER
        if prob_red > 0.5:
            color = "red"
            confidence = prob_red
        else:
            color = "blue"
            confidence = 1 - prob_red

        # Kelly Criterion (Fractional 5%)
        wager_pct = 0.05 * (2 * confidence - 1)
        
        # --- WHALE FIX: Use Effective Balance ---
        # If real balance > $5M, we just use $5M for calculation.
        # This prevents "Infinite Wealth" from skewing every bet to max.
        calc_balance = min(balance, EFFECTIVE_BALANCE_CAP)
        
        wager = int(calc_balance * wager_pct)
        
        # 4. SAFETY CAPS
        if red.tier == 'X' or blue.tier == 'X':
            wager = min(wager, X_TIER_CAP)
        
        wager = min(wager, MAX_BET_CAP)
        wager = max(1, wager)

        return wager, color, confidence