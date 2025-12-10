import logging
import math
import os
import time
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, BigInteger, Float
from sqlalchemy.orm import sessionmaker, declarative_base

from src.objects import Match as BotMatchObject, MatchFormat

# --- 1. SQLALCHEMY SETUP ---

Base = declarative_base()

def get_db_url():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "password")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB", "saltyboy")
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"

engine = create_engine(get_db_url())
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Match(Base):
    __tablename__ = "match"
    id = Column(BigInteger, primary_key=True, index=True)
    fighter_red = Column(Integer)
    fighter_blue = Column(Integer)
    winner = Column(Integer)
    match_format = Column(String)
    tier = Column(String)
    date = Column(DateTime)
    streak_red = Column(Integer)
    streak_blue = Column(Integer)
    bet_red = Column(BigInteger, nullable=True)
    bet_blue = Column(BigInteger, nullable=True)
    colour = Column(String, nullable=True)
    my_bet_on = Column(String, nullable=True) 
    my_wager = Column(BigInteger, nullable=True)
    match_balance = Column(BigInteger, nullable=True)
    expected_payout = Column(BigInteger, nullable=True)

class Fighter(Base):
    __tablename__ = "fighter"
    id = Column(BigInteger, primary_key=True) 
    name = Column(String)
    tier = Column(String)
    elo = Column(Integer)
    tier_elo = Column(Integer)
    best_streak = Column(Integer)
    created_time = Column(DateTime)
    last_updated = Column(DateTime)
    prev_tier = Column(String)
    current_streak = Column(Integer, default=0)
    last_match_date = Column(DateTime, nullable=True)

class ModelWeight(Base):
    __tablename__ = "model_weight"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))
    intercept = Column(Float)
    tier_elo = Column(Float)
    h2h = Column(Float)
    comp = Column(Float)
    streak = Column(Float, nullable=True) 

# --- 2. DATABASE CLASS ---

class Database:
    ACCEPTED_MATCH_FORMATS = [MatchFormat.MATCHMAKING, MatchFormat.TOURNAMENT]

    def __init__(
        self,
        dbname: str,
        user: str,
        password: str,
        host: str,
        port: int,
        logger: logging.Logger,
    ) -> None:
        self.logger = logger
        self.connection = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port,
            cursor_factory=psycopg2.extras.DictCursor,
        )
        self.run_migrations()

    def rollback(self):
        """Rollback the raw connection to recover from errors."""
        try:
            self.connection.rollback()
        except Exception as e:
            self.logger.error(f"Failed to rollback raw connection: {e}")

    def run_migrations(self):
        cursor = self.connection.cursor()
        try:
            # 1. Utility Tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_heartbeat (
                    heartbeat_time TIMESTAMP WITH TIME ZONE
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS current_match (
                    fighter_red VARCHAR,
                    fighter_blue VARCHAR,
                    tier VARCHAR,
                    match_format VARCHAR,
                    updated_at TIMESTAMP WITH TIME ZONE
                )
            """)

            # 2. Basic Columns
            cursor.execute("ALTER TABLE match ADD COLUMN IF NOT EXISTS my_bet_on VARCHAR(10)")
            cursor.execute("ALTER TABLE match ADD COLUMN IF NOT EXISTS my_wager BIGINT")
            cursor.execute("ALTER TABLE match ADD COLUMN IF NOT EXISTS match_balance BIGINT")
            cursor.execute("ALTER TABLE match ADD COLUMN IF NOT EXISTS expected_payout BIGINT")
            cursor.execute("ALTER TABLE fighter ADD COLUMN IF NOT EXISTS current_streak INTEGER DEFAULT 0")
            cursor.execute("ALTER TABLE fighter ADD COLUMN IF NOT EXISTS last_match_date TIMESTAMP WITH TIME ZONE")
            cursor.execute("ALTER TABLE model_weight ADD COLUMN IF NOT EXISTS streak FLOAT DEFAULT 0.0")
            
            # 3. THE BIGINT FIX (Safe IDs)
            try:
                cursor.execute("ALTER TABLE fighter ALTER COLUMN id DROP DEFAULT")
            except Exception:
                self.connection.rollback() 
            
            try:
                cursor.execute("ALTER TABLE match ALTER COLUMN id DROP DEFAULT")
            except Exception:
                self.connection.rollback()

            cursor.execute("ALTER TABLE fighter ALTER COLUMN id TYPE BIGINT")
            cursor.execute("ALTER TABLE match ALTER COLUMN id TYPE BIGINT")
            
            cursor.execute("ALTER TABLE match ALTER COLUMN fighter_red TYPE BIGINT")
            cursor.execute("ALTER TABLE match ALTER COLUMN fighter_blue TYPE BIGINT")
            cursor.execute("ALTER TABLE match ALTER COLUMN winner TYPE BIGINT")

            # 4. PERFORMANCE INDEXES
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fighter_red ON match (fighter_red)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_fighter_blue ON match (fighter_blue)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_date ON match (date)")
            
            self.connection.commit()
            self.logger.info("Database migrations & indexes applied successfully.")
        except Exception as e:
            self.connection.rollback()
            self.logger.warning(f"Migration check warning: {e}")
        finally:
            cursor.close()

    def generate_safe_id(self):
        """Generates a unique ID based on current timestamp (microseconds)."""
        return int(time.time() * 1000000)

    # --- NEW: REPORTING METHOD ---
    def get_recent_performance(self, limit=100):
        """Calculates Balance, Win Rate, and ROI for the last N matches."""
        cursor = self.connection.cursor()
        try:
            # 1. Get current balance
            cursor.execute("SELECT match_balance FROM match WHERE match_balance IS NOT NULL ORDER BY date DESC LIMIT 1")
            row = cursor.fetchone()
            current_balance = row[0] if row else 0

            # 2. Get last N bets for stats
            cursor.execute("""
                SELECT my_wager, my_bet_on, winner, fighter_red, fighter_blue, bet_red, bet_blue 
                FROM match 
                WHERE my_wager IS NOT NULL AND winner IS NOT NULL 
                ORDER BY date DESC LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()

            wins = 0
            total_invested = 0
            net_profit = 0
            
            for r in rows:
                wager = r[0]
                my_bet = r[1]
                winner_id = r[2]
                red_id, blue_id = r[3], r[4]
                pool_red, pool_blue = r[5], r[6]
                
                if not wager: continue
                total_invested += wager
                
                won = False
                if my_bet == 'Red' and winner_id == red_id: won = True
                elif my_bet == 'Blue' and winner_id == blue_id: won = True
                
                if won:
                    wins += 1
                    profit = 0
                    if my_bet == 'Red' and pool_red > 0:
                        profit = wager * (pool_blue / pool_red)
                    elif my_bet == 'Blue' and pool_blue > 0:
                        profit = wager * (pool_red / pool_blue)
                    net_profit += profit
                else:
                    net_profit -= wager

            total_bets = len(rows)
            win_rate = (wins / total_bets * 100) if total_bets > 0 else 0.0
            roi = (net_profit / total_invested * 100) if total_invested > 0 else 0.0
            
            return current_balance, win_rate, roi, total_bets

        except Exception as e:
            self.logger.error(f"Failed to calc stats: {e}")
            return 0, 0.0, 0.0, 0
        finally:
            cursor.close()
    # -----------------------------

    def record_match(self, match: BotMatchObject, my_bet: str = None, my_wager: int = None, match_balance: int = None, expected_payout: int = None) -> None:
        if match.match_format not in self.ACCEPTED_MATCH_FORMATS: return
        if match.streak_red is None or match.streak_blue is None: return

        fighter_red = self._get_or_create_fighter(match.fighter_red_name, match.tier, match.streak_red)
        fighter_blue = self._get_or_create_fighter(match.fighter_blue_name, match.tier, match.streak_blue)

        if match.bet_blue is None or match.bet_red is None or match.winner is None: return

        winner: int | None = None
        if fighter_red["name"] == match.winner: winner = fighter_red["id"]
        elif fighter_blue["name"] == match.winner: winner = fighter_blue["id"]
        else: return

        safe_id = self.generate_safe_id()

        insert_obj = {
            "id": safe_id,
            "date": datetime.now(timezone.utc),
            "fighter_red": fighter_red["id"],
            "fighter_blue": fighter_blue["id"],
            "winner": winner,
            "bet_red": match.bet_red,
            "bet_blue": match.bet_blue,
            "streak_red": match.streak_red,
            "streak_blue": match.streak_blue,
            "tier": match.tier,
            "match_format": match.match_format.value,
            "colour": match.colour,
            "my_bet_on": my_bet,
            "my_wager": my_wager,
            "match_balance": match_balance,
            "expected_payout": expected_payout
        }

        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO match
                    (id, date, fighter_red, fighter_blue, winner, bet_red, bet_blue, streak_red, streak_blue, tier, match_format, colour, my_bet_on, my_wager, match_balance, expected_payout)
                VALUES
                    (%(id)s, %(date)s, %(fighter_red)s, %(fighter_blue)s, %(winner)s, %(bet_red)s, %(bet_blue)s, %(streak_red)s, %(streak_blue)s, %(tier)s, %(match_format)s, %(colour)s, %(my_bet_on)s, %(my_wager)s, %(match_balance)s, %(expected_payout)s)
                """,
                insert_obj,
            )
            self.connection.commit()

            red_won = fighter_red["id"] == winner
            self._update_fighter(fighter_red, match.tier, match.streak_red, fighter_blue["elo"], fighter_blue["tier_elo"], red_won)
            self._update_fighter(fighter_blue, match.tier, match.streak_blue, fighter_red["elo"], fighter_red["tier_elo"], not red_won)
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            cursor.close()

    def update_current_match(self, fighter_red_name, fighter_blue_name, match_format, tier=None):
        cursor = self.connection.cursor()
        try:
            cursor.execute("DELETE FROM current_match")
            cursor.execute(
                "INSERT INTO current_match (fighter_red, fighter_blue, tier, match_format, updated_at) VALUES (%s, %s, %s, %s, %s)",
                (fighter_red_name, fighter_blue_name, tier, match_format.value, datetime.now(timezone.utc))
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
        finally:
            cursor.close()

    def update_bot_heartbeat(self) -> None:
        cursor = self.connection.cursor()
        try:
            cursor.execute("DELETE FROM bot_heartbeat")
            cursor.execute("INSERT INTO bot_heartbeat (heartbeat_time) VALUES (%s)", (datetime.now(timezone.utc),))
            self.connection.commit()
        except Exception:
            self.connection.rollback()
        finally:
            cursor.close()

    def get_bot_heartbeat(self) -> None | datetime:
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT * FROM bot_heartbeat LIMIT 1")
            row = cursor.fetchone()
            return row["heartbeat_time"].replace(tzinfo=timezone.utc) if row else None
        finally:
            cursor.close()

    def _get_or_create_fighter(self, name, tier, best_streak):
        fighter = self._get_fighter_by_name(name)
        if not fighter:
            fighter = self._create_fighter(name, tier, best_streak)
        return fighter

    def _create_fighter(self, name, tier, best_streak):
        cursor = self.connection.cursor()
        now = datetime.now(timezone.utc)
        safe_id = self.generate_safe_id() 
        try:
            cursor.execute(
                "INSERT INTO fighter (id, name, tier, prev_tier, best_streak, created_time, last_updated, elo, tier_elo, current_streak) VALUES (%s, %s, %s, %s, %s, %s, %s, 1500, 1500, 0) RETURNING id",
                (safe_id, name, tier, tier, best_streak, now, now)
            )
            fid = cursor.fetchone()[0]
            self.connection.commit()
            cursor.execute("SELECT * FROM fighter WHERE id = %s", (fid,))
            fighter = cursor.fetchone()
            return fighter
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def _update_fighter(self, fighter, tier, best_streak, opp_elo, opp_tier_elo, won):
        updated_tier = tier
        prev_tier = fighter["tier"]
        tier_elo = fighter["tier_elo"] if updated_tier == prev_tier else 1500
        
        old_streak = fighter.get("current_streak") or 0
        new_streak = 0
        if won:
            new_streak = (old_streak + 1) if old_streak > 0 else 1
        else:
            new_streak = (old_streak - 1) if old_streak < 0 else -1

        updated_streak = max(best_streak, fighter["best_streak"], new_streak)
        updated_elo = self._calculate_elo(fighter["elo"], opp_elo, won)
        updated_tier_elo = self._calculate_elo(tier_elo, opp_tier_elo, won)
        match_time = datetime.now(timezone.utc)

        cursor = self.connection.cursor()
        try:
            cursor.execute(
                """
                UPDATE fighter 
                SET last_updated=%s, best_streak=%s, current_streak=%s, last_match_date=%s, tier=%s, prev_tier=%s, tier_elo=%s, elo=%s 
                WHERE id=%s
                """,
                (match_time, updated_streak, new_streak, match_time, updated_tier, prev_tier, updated_tier_elo, updated_elo, fighter["id"])
            )
        finally:
            cursor.close()

    def _get_fighter_by_name(self, name):
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT * FROM fighter WHERE name = %s", (name,))
            fighter = cursor.fetchone()
            return fighter
        finally:
            cursor.close()

    @classmethod
    def _calculate_elo(cls, elo, opp_elo, won):
        tr_a = math.pow(10, elo / 400)
        tr_b = math.pow(10, opp_elo / 400)
        es_a = tr_a / (tr_a + tr_b)
        score = 1 if won else 0
        return int(elo + (32 * (score - es_a)))