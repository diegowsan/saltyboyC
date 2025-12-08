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
    description="""
Welcome to the SaltyBoy API. You are welcome to integrate with this API however please 
bear in mind the following:

- I'll do my best to not bork your integration by updating the endpoints, no promises 
    though.
- Do not abuse the API. By this I mean feel free to scrape in short high bursts but 
    don't spam the API with something in a constant `while` loop for example. After all 
    this runs on a very cheap Vultr instance :)
- If you want new endpoints or a Database dump please ping me on 
    [Github](https://github.com/FranciscoAT/saltyboy). I'm more than happy to review MRs
    for new features and provide PostgreSQL DB dumps.
- The API itself is extremely small so I won't be providing an SDK but there's no 
    authentication and it should be really easy to integrate around it.
- Any datetime strings should be returned in 
    [ISO 8601](https://en.wikipedia.org/wiki/ISO_8601) format.
""",
)
app = OpenAPI(__name__, info=info)

# --- Existing Connection Pool (Used by API Endpoints) ---
pg_pool = psycopg2.pool.ThreadedConnectionPool(
    1,
    20,
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.environ["POSTGRES_HOST"],
    port=int(os.environ["POSTGRES_PORT"]),
    database=os.environ["POSTGRES_DB"],
)

# --- New Connection Helper (Used by Dashboard) ---
def get_db_connection():
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ["POSTGRES_HOST"]
    port = os.environ["POSTGRES_PORT"]
    db_name = os.environ["POSTGRES_DB"]
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    return create_engine(url)

fighter_tag = Tag(name="Fighter", description="Fighters recorded by SaltyBoy.")
match_tag = Tag(
    name="Match",
    description=(
        "Matches recorded by SaltyBoy. Only Tournament, and Matchmaking matches are "
        "recorded. Exhibition matches are not."
    ),
)
current_match_tag = Tag(
    name="Current Match",
    description=(
        "Current match information. Mainly used to get detailed information about the "
        "current match by the SaltyBoy extension."
    ),
)

public_path = Path(__file__).parent.parent


# === Web Endpoints ===

@app.route("/", methods=["GET"])
def dashboard():
    """
    Serves the SaltyBoy AI Dashboard.
    Replaces the static index.html with a dynamic template.
    """
    engine = get_db_connection()
    with engine.connect() as conn:
        # 1. Total Count
        total = conn.execute(text("SELECT count(*) FROM match")).scalar()
        
        # 2. Recent Matches
        query = text("""
            SELECT m.date, m.tier, m.match_format, 
                   m.fighter_red, m.fighter_blue, m.winner,
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
        
        # 3. Accuracy Calculation (Last 100 matches)
        # Checks if the fighter with higher Tier ELO won
        acc_query = text("""
            SELECT count(*) FROM (
                SELECT m.winner, 
                       CASE WHEN fr.tier_elo > fb.tier_elo THEN m.fighter_red ELSE m.fighter_blue END as predicted
                FROM match m
                JOIN fighter fr ON m.fighter_red = fr.id
                JOIN fighter fb ON m.fighter_blue = fb.id
                ORDER BY m.date DESC LIMIT 100
            ) as recent
            WHERE winner = predicted
        """)
        correct = conn.execute(acc_query).scalar()
        accuracy = round((correct / 100) * 100, 1) if total >= 100 else 0

        # 4. Get Latest Brain Weights (Read from 'model_weight' table)
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
    return send_file(
        public_path / "public/favicon.ico", mimetype="image/vdn.microsoft.icon"
    )


@app.route("/robots.txt", methods=["GET"])
def file_robots_request():
    return send_file(public_path / "public/robots.txt", mimetype="text/plain")


# === API Endpoints ===
# Fighters
@app.get(
    "/api/fighter/",
    summary="List Fighters",
    responses={200: ListFighterResponse},
    tags=[fighter_tag],
    strict_slashes=False,
)
def api_list_fighters(query: ListFighterQuery):
    """
    Lists Fighters in a paginated format.
    """
    return jsonify(list_fighters(pg_pool, query).model_dump())


@app.get(
    "/api/fighter/<int:id_>/",
    summary="Get fighter",
    responses={200: FighterModel},
    tags=[fighter_tag],
    strict_slashes=False,
)
def api_get_fighter(path: IdPath):
    """
    Get a specific Fighter by ID.
    """
    if fighter := get_fighter_by_id(pg_pool, path.id_):
        return jsonify(fighter.model_dump())
    return "Fighter not found", 404


# Matches
@app.get(
    "/api/match/",
    summary="List Matches",
    responses={200: ListMatchResponse},
    tags=[match_tag],
    strict_slashes=False,
)
def api_list_matches(query: ListMatchQuery):
    """
    List Matches in a paginated format.
    """
    return jsonify(list_matches(pg_pool, query).model_dump())


@app.get(
    "/api/match/<int:id_>/",
    summary="Get match",
    responses={200: MatchModel},
    tags=[match_tag],
    strict_slashes=False,
)
def api_get_match(path: IdPath):
    """
    Get a specific Match by ID.
    """
    if match_ := get_match_by_id(pg_pool, path.id_):
        return jsonify(match_.model_dump())
    return "Match not found", 404


# Current Match Info
@app.get(
    "/api/current_match_info/",
    summary="Current Match Information",
    tags=[current_match_tag],
    responses={200: CurrentMatchInfoResponse},
    strict_slashes=False,
)
def api_current_match_info():
    """
    Returns the details of the current match from SaltyBet.
    """
    if current_match_info := get_current_match_info(pg_pool):
        return jsonify(current_match_info.model_dump())
    return jsonify({})