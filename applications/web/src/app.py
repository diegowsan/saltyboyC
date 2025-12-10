import os
from pathlib import Path

import psycopg2
from flask import render_template
from flask.helpers import send_file
from flask.json import jsonify
from flask_openapi3 import Info, OpenAPI, Tag
from sqlalchemy import create_engine, text

from src.biz import (
    get_current_match_info,
    get_fighter_by_id,
    get_match_by_id,
    list_fighters,
    list_matches,
)
from src.schemas import (
    CurrentMatchInfoResponse,
    FighterModel,
    IdPath,
    ListFighterQuery,
    ListFighterResponse,
    ListMatchQuery,
    ListMatchResponse,
    MatchModel,
)

info = Info(
    title="SaltyBoy API",
    version="2.1.0",
    description="SaltyBoy API",
)
app = OpenAPI(__name__, info=info)

pg_pool = psycopg2.pool.ThreadedConnectionPool(
    1,
    20,
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_HOST"],
    port=int(os.environ["POSTGRES_PORT"]),
    database=os.environ["POSTGRES_DB"],
)

def get_db_connection():
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url)

fighter_tag = Tag(name="Fighter", description="Fighters recorded by SaltyBoy.")
match_tag = Tag(name="Match", description="Matches recorded by SaltyBoy.")
current_match_tag = Tag(name="Current Match", description="Current match info.")
public_path = Path(__file__).parent.parent

@app.route("/", methods=["GET"])
def dashboard():
    engine = get_db_connection()
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM match")).scalar()
        
        # 1. Fetch Latest Matches
        query = text("""
            SELECT m.date, m.tier, m.match_format, 
                   m.fighter_red, m.fighter_blue, m.winner,
                   m.my_bet_on as bot_bet,
                   m.my_wager as wager,
                   m.match_balance as balance,
                   m.bet_red, m.bet_blue,
                   r.name as red_name, 
                   b.name as blue_name, 
                   w.name as winner_name
            FROM match m
            JOIN fighter r ON m.fighter_red = r.id
            JOIN fighter b ON m.fighter_blue = b.id
            JOIN fighter w ON m.winner = w.id
            ORDER BY m.date DESC LIMIT 15
        """)
        raw_matches = conn.execute(query).fetchall()
        
        # Process matches
        processed_matches = []
        for m in raw_matches:
            match_data = dict(m._mapping)
            match_data['profit'] = 0
            
            if match_data['bot_bet'] and match_data['wager']:
                won = False
                if match_data['bot_bet'] == 'Red' and m.winner == m.fighter_red: won = True
                elif match_data['bot_bet'] == 'Blue' and m.winner == m.fighter_blue: won = True
                
                if won:
                    # Pure Estimate Logic
                    wager = match_data['wager']
                    if m.winner == m.fighter_red and m.bet_red:
                        match_data['profit'] = int(wager * (m.bet_blue / m.bet_red))
                    elif m.winner == m.fighter_blue and m.bet_blue:
                        match_data['profit'] = int(wager * (m.bet_red / m.bet_blue))
                else:
                    match_data['profit'] = -match_data['wager']
            
            processed_matches.append(match_data)

        current_balance = 0
        if processed_matches and processed_matches[0]['balance']:
            current_balance = processed_matches[0]['balance']

        # 2. Metrics (Last 100)
        roi_query = text("""
            SELECT m.my_wager, m.my_bet_on, m.winner, m.fighter_red, m.fighter_blue, m.bet_red, m.bet_blue
            FROM match m
            WHERE m.my_wager IS NOT NULL AND m.winner IS NOT NULL
            ORDER BY m.date DESC LIMIT 100
        """)
        roi_rows = conn.execute(roi_query).fetchall()

        net_profit = 0
        total_invested = 0
        wins = 0
        total_bets = 0

        for row in roi_rows:
            wager = row.my_wager
            if not wager: continue
            total_bets += 1
            total_invested += wager
            
            won = False
            if row.my_bet_on == 'Red' and row.winner == row.fighter_red: won = True
            elif row.my_bet_on == 'Blue' and row.winner == row.fighter_blue: won = True
            
            if won:
                wins += 1
                profit = 0
                if row.winner == row.fighter_red and row.bet_red:
                    profit = wager * (row.bet_blue / row.bet_red)
                elif row.winner == row.fighter_blue and row.bet_blue:
                    profit = wager * (row.bet_red / row.bet_blue)
                net_profit += profit
            else:
                net_profit -= wager
        
        roi = (net_profit / total_invested * 100) if total_invested > 0 else 0
        accuracy = round((wins / total_bets * 100), 1) if total_bets > 0 else 0

        # 3. Weights
        try:
            w_query = text("SELECT intercept, tier_elo, h2h, comp, streak FROM model_weight ORDER BY timestamp DESC LIMIT 1")
            row = conn.execute(w_query).fetchone()
            weights = {
                "tier_elo": row[1], "h2h": row[2], "comp": row[3],
                "streak": row[4] if row[4] is not None else 0.0
            } if row else {"tier_elo": 0, "h2h": 0, "comp": 0, "streak": 0}
        except:
            weights = {"tier_elo": 0, "h2h": 0, "comp": 0, "streak": 0}

    return render_template("dashboard.html", 
        total_matches=total,
        matches=processed_matches,
        accuracy=accuracy,
        roi=roi,
        weights=weights,
        current_balance=current_balance
    )

@app.route("/favicon.ico", methods=["GET"])
def file_favicon_request():
    return send_file(public_path / "public/favicon.ico", mimetype="image/vdn.microsoft.icon")

@app.route("/robots.txt", methods=["GET"])
def file_robots_request():
    return send_file(public_path / "public/robots.txt", mimetype="text/plain")

@app.get("/api/fighter/", summary="List Fighters", responses={200: ListFighterResponse}, tags=[fighter_tag], strict_slashes=False)
def api_list_fighters(query: ListFighterQuery):
    return jsonify(list_fighters(pg_pool, query).model_dump())

@app.get("/api/fighter/<int:id_>/", summary="Get fighter", responses={200: FighterModel}, tags=[fighter_tag], strict_slashes=False)
def api_get_fighter(path: IdPath):
    if fighter := get_fighter_by_id(pg_pool, path.id_):
        return jsonify(fighter.model_dump())
    return "Fighter not found", 404

@app.get("/api/match/", summary="List Matches", responses={200: ListMatchResponse}, tags=[match_tag], strict_slashes=False)
def api_list_matches(query: ListMatchQuery):
    return jsonify(list_matches(pg_pool, query).model_dump())

@app.get("/api/match/<int:id_>/", summary="Get match", responses={200: MatchModel}, tags=[match_tag], strict_slashes=False)
def api_get_match(path: IdPath):
    if match_ := get_match_by_id(pg_pool, path.id_):
        return jsonify(match_.model_dump())
    return "Match not found", 404

@app.get("/api/current_match_info/", summary="Current Match Information", tags=[current_match_tag], responses={200: CurrentMatchInfoResponse}, strict_slashes=False)
def api_current_match_info():
    if current_match_info := get_current_match_info(pg_pool):
        return jsonify(current_match_info.model_dump())
    return jsonify({})