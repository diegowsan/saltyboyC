import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sklearn.linear_model import LogisticRegression
from dotenv import load_dotenv
from collections import defaultdict

# Load DB credentials
load_dotenv()

# --- Configuration ---
# Match these to your JS file to ensure consistency
K_FACTOR = 32
STARTING_ELO = 1500
MIN_MATCHES_FOR_STATS = 3  # Min matches to trust H2H/Comp

def get_db_engine():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "saltyboy")
    
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url)

class FighterTracker:
    def __init__(self):
        self.elo = STARTING_ELO
        self.tier_elo = STARTING_ELO
        self.tier = None
        self.wins = 0
        self.losses = 0
        # History of opponents: {opponent_id: "win"|"loss"}
        self.match_history = [] 

fighters = defaultdict(FighterTracker)

def calculate_elo_change(winner_elo, loser_elo):
    expected_win = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    change = K_FACTOR * (1 - expected_win)
    return change

def get_h2h_win_rate(fighter_id, opponent_id):
    history = fighters[fighter_id].match_history
    wins = 0
    total = 0
    for m in history:
        if m['opponent'] == opponent_id:
            total += 1
            if m['result'] == 'win':
                wins += 1
    
    if total < MIN_MATCHES_FOR_STATS:
        return 0.5 # Neutral
    return wins / total

def get_comp_win_rate(red_id, blue_id):
    # Find common opponents
    red_history = fighters[red_id].match_history
    blue_history = fighters[blue_id].match_history
    
    red_opponents = {m['opponent']: m['result'] for m in red_history}
    
    common_wins = 0
    common_losses = 0
    
    for m in blue_history:
        opp_id = m['opponent']
        blue_res = m['result']
        
        if opp_id in red_opponents:
            red_res = red_opponents[opp_id]
            
            # Logic: Red Won + Blue Lost = Red Advantage
            if red_res == 'win' and blue_res == 'loss':
                common_wins += 1
            # Logic: Red Lost + Blue Won = Red Disadvantage
            elif red_res == 'loss' and blue_res == 'win':
                common_losses += 1
                
    total = common_wins + common_losses
    if total < MIN_MATCHES_FOR_STATS:
        return 0.5 # Neutral
        
    return common_wins / total

def main():
    print("Connecting to database...")
    engine = get_db_engine()
    
    # 1. Load all matches chronologically
    # Note: We assume 'id' sorts chronologically. Ideally use a 'date' column if consistent.
    query = """
        SELECT id, fighter_red, fighter_blue, winner, tier 
        FROM match 
        ORDER BY id ASC
    """
    
    print("Fetching match history...")
    with engine.connect() as conn:
        df_matches = pd.read_sql(text(query), conn)
        
    print(f"Loaded {len(df_matches)} matches. Re-simulating history to generate training features...")
    
    training_data = []
    
    for _, match in df_matches.iterrows():
        r_id = match['fighter_red']
        b_id = match['fighter_blue']
        winner = match['winner']
        tier = match['tier']
        
        # --- 2. Calculate Features (Before the match result is known) ---
        
        # Tier ELO Diff
        # Note: In a real implementation, we'd reset Tier ELO if tier changed. 
        # For simplicity, we track a continuous Tier ELO here.
        tier_elo_diff = fighters[r_id].tier_elo - fighters[b_id].tier_elo
        
        # H2H (Red's win rate against Blue - 0.5)
        h2h_raw = get_h2h_win_rate(r_id, b_id)
        h2h_feature = h2h_raw - 0.5
        
        # Comp Stats (Red's win rate vs common opponents - 0.5)
        comp_raw = get_comp_win_rate(r_id, b_id)
        comp_feature = comp_raw - 0.5
        
        # Target: Did Red win? (1 = Yes, 0 = No)
        # Assuming 'winner' column holds the ID of the winner
        red_won = 1 if winner == r_id else 0
        
        # Store for training
        training_data.append({
            'tier_elo_diff': tier_elo_diff,
            'h2h_feature': h2h_feature,
            'comp_feature': comp_feature,
            'red_won': red_won
        })
        
        # --- 3. Update State (After the match) ---
        # Update ELO
        change = calculate_elo_change(
            fighters[r_id].tier_elo if red_won else fighters[b_id].tier_elo,
            fighters[b_id].tier_elo if red_won else fighters[r_id].tier_elo
        )
        
        if red_won:
            fighters[r_id].tier_elo += change
            fighters[b_id].tier_elo -= change
            fighters[r_id].match_history.append({'opponent': b_id, 'result': 'win'})
            fighters[b_id].match_history.append({'opponent': r_id, 'result': 'loss'})
        else:
            fighters[r_id].tier_elo -= change
            fighters[b_id].tier_elo += change
            fighters[r_id].match_history.append({'opponent': b_id, 'result': 'loss'})
            fighters[b_id].match_history.append({'opponent': r_id, 'result': 'win'})

    # --- 4. Train Model ---
    print("Training Logistic Regression Model...")
    train_df = pd.DataFrame(training_data)
    
    # We want to predict 'red_won' using our features
    X = train_df[['tier_elo_diff', 'h2h_feature', 'comp_feature']]
    y = train_df['red_won']
    
    # Fit model (no intercept needed ideally if features are symmetric, but we'll include it)
    model = LogisticRegression(fit_intercept=True)
    model.fit(X, y)
    
    # --- 5. Output Results ---
    print("\n" + "="*30)
    print("OPTIMIZED COEFFICIENTS FOUND")
    print("="*30)
    print(f"Intercept:      {model.intercept_[0]:.4f}")
    print(f"Tier ELO Coeff: {model.coef_[0][0]:.4f}")
    print(f"H2H Coeff:      {model.coef_[0][1]:.4f}")
    print(f"Comp Coeff:     {model.coef_[0][2]:.4f}")
    print("="*30)
    print("\nUpdate your logistic.js file with these values!")

if __name__ == "__main__":
    main()