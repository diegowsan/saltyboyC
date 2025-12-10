import os
from collections import defaultdict
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
K_FACTOR = 32
STARTING_ELO = 1500
MIN_MATCHES_FOR_STATS = 1
WARMUP_MATCHES = 1000

class FighterTracker:
    def __init__(self):
        self.tier_elo = STARTING_ELO
        self.match_history = []
        self.current_streak = 0  # Simulation tracker

def get_db_engine():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "saltyboy")
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url)

def calculate_elo_change(winner_elo, loser_elo):
    expected_win = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    return K_FACTOR * (1 - expected_win)

def get_h2h_win_rate(fighters, fighter_id, opponent_id):
    history = fighters[fighter_id].match_history
    wins = 0
    total = 0
    for m in history:
        if m["opponent"] == opponent_id:
            total += 1
            if m["result"] == "win": wins += 1
    if total < MIN_MATCHES_FOR_STATS: return 0.5
    return wins / total

def get_comp_win_rate(fighters, red_id, blue_id):
    red_hist = fighters[red_id].match_history
    blue_hist = fighters[blue_id].match_history
    red_opps = {m["opponent"]: m["result"] for m in red_hist}
    wins = 0
    total = 0
    for m in blue_hist:
        opp_id = m["opponent"]
        blue_res = m["result"]
        if opp_id in red_opps:
            red_res = red_opps[opp_id]
            if red_res == "win" and blue_res == "loss":
                wins += 1; total += 1
            elif red_res == "loss" and blue_res == "win":
                total += 1
    if total < MIN_MATCHES_FOR_STATS: return 0.5
    return wins / total

def train_model():
    print("Training AI Model on current database...")
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM match")).scalar()
            if count < (WARMUP_MATCHES + 50):
                print(f"Not enough data to train ({count} matches).")
                return None
            query = "SELECT fighter_red, fighter_blue, winner, streak_red, streak_blue FROM match ORDER BY date ASC, id ASC"
            df_matches = pd.read_sql(text(query), conn)

        fighters = defaultdict(FighterTracker)
        training_data = []
        match_counter = 0

        for _, match in df_matches.iterrows():
            match_counter += 1
            r, b, w = match["fighter_red"], match["fighter_blue"], match["winner"]
            
            # Use SIMULATED streaks for training consistency
            r_streak = fighters[r].current_streak
            b_streak = fighters[b].current_streak
            
            elo_diff = fighters[r].tier_elo - fighters[b].tier_elo
            streak_diff = r_streak - b_streak
            h2h = get_h2h_win_rate(fighters, r, b) - 0.5
            comp = get_comp_win_rate(fighters, r, b) - 0.5
            target = 1 if w == r else 0

            if match_counter > WARMUP_MATCHES:
                training_data.append([elo_diff, streak_diff, h2h, comp, target])

            change = calculate_elo_change(fighters[r].tier_elo if target else fighters[b].tier_elo, fighters[b].tier_elo if target else fighters[r].tier_elo)
            if target:
                fighters[r].tier_elo += change
                fighters[b].tier_elo -= change
                fighters[r].match_history.append({"opponent": b, "result": "win"})
                fighters[b].match_history.append({"opponent": r, "result": "loss"})
                # Streak Logic
                fighters[r].current_streak = (fighters[r].current_streak + 1) if fighters[r].current_streak > 0 else 1
                fighters[b].current_streak = (fighters[b].current_streak - 1) if fighters[b].current_streak < 0 else -1
            else:
                fighters[r].tier_elo -= change
                fighters[b].tier_elo += change
                fighters[r].match_history.append({"opponent": b, "result": "loss"})
                fighters[b].match_history.append({"opponent": r, "result": "win"})
                # Streak Logic
                fighters[r].current_streak = (fighters[r].current_streak - 1) if fighters[r].current_streak < 0 else -1
                fighters[b].current_streak = (fighters[b].current_streak + 1) if fighters[b].current_streak > 0 else 1

        df = pd.DataFrame(training_data, columns=["elo", "streak", "h2h", "comp", "win"])
        model = LogisticRegression(fit_intercept=True)
        model.fit(df[["elo", "streak", "h2h", "comp"]], df["win"])

        weights = {
            "intercept": float(model.intercept_[0]),
            "tier_elo": float(model.coef_[0][0]),
            "streak": float(model.coef_[0][1]),
            "h2h": float(model.coef_[0][2]),
            "comp": float(model.coef_[0][3])
        }
        print(f"Training Complete. New Weights: {weights}")
        return weights
    except Exception as e:
        print(f"Training failed: {e}")
        return None