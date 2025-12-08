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
        
        # New Query: Select 'my_bet_on' as bot_bet
        query = text("""
            SELECT m.date, m.tier, m.match_format, 
                   m.fighter_red, m.fighter_blue, m.winner,
                   m.my_bet_on as bot_bet,
                   r.name as red_name, 
                   b.name as blue_name, 
                   w.name as winner_name
            FROM match m
            JOIN fighter r ON m.fighter_red = r.id
            JOIN fighter b ON m.fighter_blue = b.id
            JOIN fighter w ON m.winner = w.id
            ORDER BY m.date DESC LIMIT 15
        """)
        recent_matches = conn.execute(query).fetchall()
        
        # New Accuracy: Based on 'my_bet_on'
        acc_query = text("""
            SELECT count(*) FROM (
                SELECT winner,
                       CASE 
                           WHEN LOWER(my_bet_on) = 'red' AND winner = fighter_red THEN 1
                           WHEN LOWER(my_bet_on) = 'blue' AND winner = fighter_blue THEN 1
                           ELSE 0
                       END as won_bet
                FROM match 
                WHERE my_bet_on IS NOT NULL 
                ORDER BY date DESC LIMIT 100
            ) as recent
            WHERE won_bet = 1
        """)
        correct = conn.execute(acc_query).scalar()
        
        total_bets_query = text("SELECT count(*) FROM match WHERE my_bet_on IS NOT NULL ORDER BY date DESC LIMIT 100")
        total_bets = conn.execute(total_bets_query).scalar()
        
        limit_used = total_bets if total_bets > 0 else 1
        accuracy = round((correct / limit_used) * 100, 1)

        try:
            w_query = text("SELECT intercept, tier_elo, h2h, comp FROM model_weight ORDER BY timestamp DESC LIMIT 1")
            row = conn.execute(w_query).fetchone()
            if row:
                weights = {"tier_elo": row[1], "h2h": row[2], "comp": row[3]}
            else:
                weights = {"tier_elo": 0, "h2h": 0, "comp": 0}
        except Exception:
            weights = {"tier_elo": 0, "h2h": 0, "comp": 0}

    return render_template("dashboard.html", 
        total_matches=total,
        matches=recent_matches,
        accuracy=accuracy,
        weights=weights
    )

@app.route("/favicon.ico", methods=["GET"])
def file_favicon_request():
    return send_file(public_path / "public/favicon.ico", mimetype="image/vdn.microsoft.icon")

@app.route("/robots.txt", methods=["GET"])
def file_robots_request():
    return send_file(public_path / "public/robots.txt", mimetype="text/plain")

@app.get("/api/fighter/", summary="List Fighters", responses={200: ListFighterResponse}, tags=[fighter_tag])
def api_list_fighters(query: ListFighterQuery):
    return jsonify(list_fighters(pg_pool, query).model_dump())

@app.get("/api/fighter/<int:id_>/", summary="Get fighter", responses={200: FighterModel}, tags=[fighter_tag])
def api_get_fighter(path: IdPath):
    if fighter := get_fighter_by_id(pg_pool, path.id_):
        return jsonify(fighter.model_dump())
    return "Fighter not found", 404

@app.get("/api/match/", summary="List Matches", responses={200: ListMatchResponse}, tags=[match_tag])
def api_list_matches(query: ListMatchQuery):
    return jsonify(list_matches(pg_pool, query).model_dump())

@app.get("/api/match/<int:id_>/", summary="Get match", responses={200: MatchModel}, tags=[match_tag])
def api_get_match(path: IdPath):
    if match_ := get_match_by_id(pg_pool, path.id_):
        return jsonify(match_.model_dump())
    return "Match not found", 404

@app.get("/api/current_match_info/", summary="Current Match Information", tags=[current_match_tag], responses={200: CurrentMatchInfoResponse})
def api_current_match_info():
    if current_match_info := get_current_match_info(pg_pool):
        return jsonify(current_match_info.model_dump())
    return jsonify({})