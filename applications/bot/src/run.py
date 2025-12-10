import os
import time
import requests
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from multiprocessing import Process, Queue
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_fixed
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.app_logging import (
    configure_process_logger,
    get_bot_logger,
    get_watchdog_logger,
    run_listener,
)
from src.database import Database, SessionLocal, Match as MatchDB, Fighter, ModelWeight, Base, engine
from src.irc import TwitchBot
from src.objects import (
    LockedBetMessage,
    Match,
    MatchFormat,
    OpenBetExhibitionMessage,
    OpenBetMessage,
    WinMessage,
)
from src.salty_client import SaltyWebClient
from src.betting_strategy import BettingEngine
from src.training import train_model
from src.notifier import send_discord_alert

SALTY_BOY_URL = "https://www.salty-boy.com"

# --- HELPER FUNCTIONS ---

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def get_current_match_info() -> dict:
    return requests.get(f"{SALTY_BOY_URL}/api/current_match_info", timeout=5).json()

@retry(stop=stop_after_attempt(3), wait=wait_fixed(5))
def get_fighter_history(fighter_id: int) -> list:
    try:
        url = f"{SALTY_BOY_URL}/api/match/?fighter={fighter_id}&page_size=100"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def get_fighter_details(fighter_id: int) -> dict | None:
    try:
        url = f"{SALTY_BOY_URL}/api/fighter/{fighter_id}/"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 404: return None
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None

def ensure_fighter_exists(fighter_info: dict, db_session: Session, logger) -> bool:
    if not fighter_info: return False
    f_id, f_name = fighter_info.get("id"), fighter_info.get("name")
    if not f_id or not f_name: return False

    if db_session.get(Fighter, f_id): return True
    existing_by_name = db_session.query(Fighter).filter(Fighter.name == f_name).first()
    if existing_by_name: return True

    new_fighter = Fighter(
        id=f_id, name=f_name, tier=fighter_info.get("tier", "U"),
        elo=fighter_info.get("elo", 1500), tier_elo=fighter_info.get("tier_elo", 1500),
        best_streak=0, created_time=datetime.now(timezone.utc),
        last_updated=datetime.now(timezone.utc), prev_tier=fighter_info.get("tier", "U")
    )
    new_fighter.current_streak = 0
    new_fighter.last_match_date = None
    
    db_session.add(new_fighter)
    try:
        db_session.commit()
        logger.info(f"Created new fighter: {f_name} (ID: {f_id})")
        return True
    except IntegrityError:
        db_session.rollback()
        return True
    except Exception as e:
        logger.error(f"Failed to create fighter {f_name}: {e}")
        db_session.rollback()
        return False

def sync_fighter_stats(fighter_info: dict, db_session: Session, logger) -> None:
    if not fighter_info: return
    f_id, f_name = fighter_info.get("id"), fighter_info.get("name")
    if not f_id or not f_name: return

    fighter = db_session.get(Fighter, f_id)
    api_elo = fighter_info.get("elo", 1500)
    api_tier_elo = fighter_info.get("tier_elo", 1500)
    api_tier = fighter_info.get("tier", "U")
    
    if not fighter:
        zombie = db_session.query(Fighter).filter(Fighter.name == f_name).first()
        if zombie:
            logger.warning(f"ID Mismatch for {f_name}. Migrating DB ID {zombie.id} to API ID {f_id}...")
            try:
                zombie.name = f"{f_name}_MIGRATING_{int(time.time())}"
                db_session.commit()
                
                new_fighter = Fighter(
                    id=f_id, name=f_name, tier=api_tier, elo=api_elo, tier_elo=api_tier_elo,
                    best_streak=0, created_time=datetime.now(timezone.utc),
                    last_updated=datetime.now(timezone.utc), prev_tier=api_tier
                )
                new_fighter.current_streak = 0
                new_fighter.last_match_date = None
                db_session.add(new_fighter)
                db_session.commit()
                
                db_session.execute(text("UPDATE match SET fighter_red = :new WHERE fighter_red = :old"), {"new": f_id, "old": zombie.id})
                db_session.execute(text("UPDATE match SET fighter_blue = :new WHERE fighter_blue = :old"), {"new": f_id, "old": zombie.id})
                db_session.execute(text("UPDATE match SET winner = :new WHERE winner = :old"), {"new": f_id, "old": zombie.id})
                
                db_session.delete(zombie)
                db_session.commit()
                logger.info(f"Migration successful for {f_name}.")
                return 
            except IntegrityError:
                db_session.rollback()
                return
            except Exception as e:
                logger.error(f"Migration failed for {f_name}: {e}")
                db_session.rollback()
                return

    if not fighter:
        new_fighter = Fighter(
            id=f_id, name=f_name, tier=api_tier, elo=api_elo, tier_elo=api_tier_elo,
            best_streak=0, created_time=datetime.now(timezone.utc),
            last_updated=datetime.now(timezone.utc), prev_tier=api_tier
        )
        new_fighter.current_streak = 0
        new_fighter.last_match_date = None
        db_session.add(new_fighter)
        try:
            db_session.commit()
            logger.info(f"Imported fighter from API: {f_name}")
        except IntegrityError:
            db_session.rollback()
    else:
        fighter.elo = api_elo
        fighter.tier_elo = api_tier_elo
        fighter.tier = api_tier
        fighter.last_updated = datetime.now(timezone.utc)
        logger.info(f"Synced fighter stats: {f_name}")
        try: db_session.commit()
        except: db_session.rollback()
        
def backfill_matches(fighter_info: dict, db_session: Session, logger, seen_ids: set) -> int:
    if not fighter_info or not fighter_info.get("id"): return 0
    
    history = get_fighter_history(fighter_info["id"])
    if not history: history = fighter_info.get("matches", [])

    new_matches_added = 0
    local_fighter_cache = set() 

    for match_data in history:
        try:
            match_id = match_data["id"]
            if match_id in seen_ids: continue
            if db_session.get(MatchDB, match_id): continue

            r_id, b_id = match_data["fighter_red"], match_data["fighter_blue"]
            
            if not db_session.get(Fighter, r_id) and r_id not in local_fighter_cache:
                f_data = get_fighter_details(r_id)
                if f_data:
                    if ensure_fighter_exists(f_data, db_session, logger):
                        local_fighter_cache.add(r_id)
            
            if not db_session.get(Fighter, b_id) and b_id not in local_fighter_cache:
                f_data = get_fighter_details(b_id)
                if f_data:
                    if ensure_fighter_exists(f_data, db_session, logger):
                        local_fighter_cache.add(b_id)

            if not db_session.get(Fighter, r_id) or not db_session.get(Fighter, b_id):
                continue

            match_date = datetime.fromisoformat(match_data["date"])
            time_window = match_date - timedelta(minutes=60)
            ghosts = db_session.query(MatchDB).filter(MatchDB.fighter_red == r_id, MatchDB.fighter_blue == b_id, MatchDB.date >= time_window).all()
            
            my_bet, my_wager, match_balance = None, None, None
            for g in ghosts:
                if g.my_bet_on: 
                    my_bet, my_wager, match_balance = g.my_bet_on, g.my_wager, g.match_balance
                db_session.delete(g)
            
            if my_bet: logger.info(f"Consolidated bet '{my_bet}' into ID {match_id}")

            new_match = MatchDB(
                id=match_id, fighter_red=r_id, fighter_blue=b_id, winner=match_data["winner"],
                match_format=match_data["match_format"], tier=match_data["tier"],
                date=match_date, streak_red=match_data["streak_red"], streak_blue=match_data["streak_blue"],
                bet_red=match_data.get("bet_red") or 0, bet_blue=match_data.get("bet_blue") or 0,
                colour=match_data.get("colour"), 
                my_bet_on=my_bet, my_wager=my_wager, match_balance=match_balance
            )
            db_session.add(new_match)
            seen_ids.add(match_id)
            new_matches_added += 1
        except Exception as e:
            logger.error(f"Failed to parse history: {e}")
            continue
            
    return new_matches_added

def save_weights_to_db(db_session: Session, weights: dict, logger):
    try:
        mw = ModelWeight(
            timestamp=datetime.now(timezone.utc),
            intercept=weights['intercept'],
            tier_elo=weights['tier_elo'],
            h2h=weights['h2h'],
            comp=weights['comp'],
        )
        db_session.add(mw)
        db_session.commit()
        logger.info("Saved new brain weights to database.")
    except Exception as e:
        logger.error(f"Failed to save weights: {e}")

class ReportProcess(Process):
    def __init__(self, db_params, queue):
        super().__init__(daemon=True)
        self.db_params = db_params
        self.queue = queue

    def run(self):
        configure_process_logger(self.queue)
        logger = get_bot_logger()
        logger.info("Reporter process started.")
        
        db = Database(*self.db_params, logger)
        
        # GMT-3 Timezone (Alagoas)
        BRT = timezone(timedelta(hours=-3))
        last_sent_hour = -1

        while True:
            try:
                now = datetime.now(BRT)
                # Report at 08:xx and 17:xx
                if now.hour in [8, 17]:
                    if now.hour != last_sent_hour:
                        balance, wr, roi, total_bets = db.get_recent_performance(limit=100)
                        bal_str = f"${balance:,}"
                        emoji = "📈" if roi > 0 else "📉"
                        
                        message = (
                            f"📊 **Daily Report ({now.strftime('%H:%M')} GMT-3)**\n"
                            f"💰 **Balance:** `{bal_str}`\n"
                            f"{emoji} **ROI (Last 100):** `{roi:.2f}%`\n"
                            f"🎯 **Win Rate:** `{wr:.1f}%`\n"
                            f"🎲 **Bets Placed:** {total_bets}"
                        )
                        
                        send_discord_alert(message)
                        logger.info(f"Sent scheduled report: ROI {roi:.2f}%")
                        last_sent_hour = now.hour
                else:
                    if last_sent_hour != -1:
                        last_sent_hour = -1
                
                time.sleep(60) 
            except Exception as e:
                logger.error(f"Reporter error: {e}")
                time.sleep(60)

class BotProcess(Process):
    def __init__(self, postgres_db, postgres_user, postgres_password, postgres_host, postgres_port, twitch_username, twitch_oauth_token, queue):
        super().__init__(daemon=True)
        self.postgres_db = postgres_db
        self.postgres_user = postgres_user
        self.postgres_password = postgres_password
        self.postgres_host = postgres_host
        self.postgres_port = postgres_port
        self.twitch_username = twitch_username
        self.twitch_oauth_token = twitch_oauth_token
        self.queue = queue

    def run(self) -> None:
        configure_process_logger(self.queue)
        bot_logger = get_bot_logger()
        bot_logger.info("Bot started")
        
        send_discord_alert("🤖 **SodiumTycoon AI is ONLINE.** Ready to print.")

        database = Database(self.postgres_db, self.postgres_user, self.postgres_password, self.postgres_host, self.postgres_port, bot_logger)
        web_client = SaltyWebClient()
        if web_client.login():
            bot_logger.info("Headless Betting: ENABLED (Logged in)")
        else:
            bot_logger.warning("Headless Betting: DISABLED (Login failed)")

        irc_bot = TwitchBot(self.twitch_username, self.twitch_oauth_token, bot_logger)
        
        bot_logger.info("Initializing AI Brain...")
        current_weights = train_model()
        if current_weights:
            bot_logger.info(f"Brain updated: {current_weights}")
            with SessionLocal() as session:
                save_weights_to_db(session, current_weights, bot_logger)
        else:
            bot_logger.info("Using default weights.")
        
        current_balance = 1000 
        matches_tracked = 0
        current_match: Match | None = None
        saved_match_info: dict | None = None
        current_bet_color: str | None = None
        current_wager: int | None = None
        current_balance_snapshot: int | None = None

        last_pool_red: int = 0
        last_pool_blue: int = 0

        for message in irc_bot.listen():
            db_session = SessionLocal()
            try:
                if message is None:
                    database.update_bot_heartbeat()
                    continue

                if isinstance(message, OpenBetMessage):
                    bot_logger.info("New match. %s VS. %s. Tier: %s.", message.fighter_red_name, message.fighter_blue_name, message.tier)
                    database.update_current_match(**asdict(message))

                    if message.match_format != MatchFormat.EXHIBITION:
                        current_match = Match(message, bot_logger)
                        try:
                            match_info = get_current_match_info()
                            saved_match_info = match_info
                            if match_info:
                                sync_fighter_stats(match_info.get("fighter_red_info"), db_session, bot_logger)
                                sync_fighter_stats(match_info.get("fighter_blue_info"), db_session, bot_logger)
                            
                            if web_client.is_logged_in:
                                real_balance = web_client.get_wallet_balance()
                                if real_balance > 0: current_balance = real_balance
                            
                            engine = BettingEngine(db_session, weights=current_weights)
                            wager, color, confidence = engine.get_bet(message.fighter_red_name, message.fighter_blue_name, current_balance)
                            
                            current_bet_color = color.capitalize()
                            current_wager = wager
                            current_balance_snapshot = current_balance
                            
                            if web_client.is_logged_in:
                                conf_str = f"{confidence:.1%}"
                                bot_logger.info(f"Placing bet: ${wager} on {color} (Confidence: {conf_str})")
                                web_client.place_bet(wager, color)
                        except Exception as e:
                            bot_logger.error(f"Error during betting: {e}")
                            saved_match_info = None
                    else:
                        current_match, saved_match_info, current_bet_color, current_wager = None, None, None, None

                elif isinstance(message, OpenBetExhibitionMessage):
                    bot_logger.info("New match. Exhibition.")
                    database.update_current_match(**asdict(message), match_format=MatchFormat.EXHIBITION)
                    current_match, saved_match_info, current_bet_color, current_wager = None, None, None, None

                elif current_match:
                    if isinstance(message, LockedBetMessage):
                        if current_match.update_locked(message):
                            bot_logger.info("Bets locked. Red: $%s. Blue: $%s.", f"{message.bet_red:,}", f"{message.bet_blue:,}")
                            last_pool_red = message.bet_red
                            last_pool_blue = message.bet_blue
                            
                            if saved_match_info:
                                bot_logger.info("Back-filling history...")
                                ensure_fighter_exists(saved_match_info.get("fighter_red_info"), db_session, bot_logger)
                                ensure_fighter_exists(saved_match_info.get("fighter_blue_info"), db_session, bot_logger)
                                seen_match_ids = set()
                                total = backfill_matches(saved_match_info.get("fighter_red_info"), db_session, bot_logger, seen_match_ids)
                                total += backfill_matches(saved_match_info.get("fighter_blue_info"), db_session, bot_logger, seen_match_ids)
                                if total > 0:
                                    db_session.commit()
                                    bot_logger.info(f"Back-filled {total} matches.")

                    elif isinstance(message, WinMessage):
                        if current_match.update_winner(message):
                            bot_logger.info("Winner: %s.", message.winner_name)
                            
                            if current_wager and current_bet_color:
                                profit = 0
                                won = False
                                if current_bet_color == "Red" and message.colour == "Red": won = True
                                elif current_bet_color == "Blue" and message.colour == "Blue": won = True
                                
                                if won:
                                    if current_bet_color == "Red" and last_pool_red > 0:
                                        profit = int(current_wager * (last_pool_blue / last_pool_red))
                                    elif current_bet_color == "Blue" and last_pool_blue > 0:
                                        profit = int(current_wager * (last_pool_red / last_pool_blue))
                                    
                                    if profit > 100_000:
                                        send_discord_alert(f"💸 **BIG WIN!** Profit: ${profit:,} ({message.winner_name})")

                            database.record_match(current_match, my_bet=current_bet_color, my_wager=current_wager, match_balance=current_balance_snapshot)
                            current_bet_color, current_wager = None, None
                            
                            matches_tracked += 1
                            if matches_tracked >= 100:
                                bot_logger.info("Re-training AI...")
                                new_weights = train_model()
                                if new_weights:
                                    current_weights = new_weights
                                    bot_logger.info("Brain updated!")
                                    save_weights_to_db(db_session, new_weights, bot_logger)
                                matches_tracked = 0
            except Exception as e:
                err_msg = f"⚠️ **CRITICAL ERROR**: {str(e)}"
                send_discord_alert(err_msg)
                
                bot_logger.error(f"Main loop error: {e}")
                db_session.rollback()
                database.rollback()
            finally:
                db_session.close()

def run(log_path: Path | None) -> None:
    queue: Queue = Queue(-1)
    log_listener = Process(target=run_listener, args=(queue, log_path))
    log_listener.start()
    configure_process_logger(queue)
    watchdog_logger = get_watchdog_logger()
    watchdog_logger.info("Running bot watchdog")
    
    Base.metadata.create_all(bind=engine)
    
    # DB Parameters passed to subprocesses
    db_params = (
        os.environ["POSTGRES_DB"], 
        os.environ["POSTGRES_USER"], 
        os.environ["POSTGRES_PASSWORD"], 
        os.environ["POSTGRES_HOST"], 
        int(os.environ["POSTGRES_PORT"])
    )

    # 1. Main Bot Process
    bot_process = new_bot_process(queue, db_params)
    
    # 2. Report Scheduler Process
    report_process = ReportProcess(db_params, queue)
    report_process.start()
    watchdog_logger.info("Report Scheduler started.")

    last_restart, last_health = datetime.now(timezone.utc), datetime.now(timezone.utc)
    database = Database(*db_params, watchdog_logger)

    while True:
        now = datetime.now(timezone.utc)
        heartbeat = database.get_bot_heartbeat()
        restart = False
        if heartbeat is None and last_health < now - timedelta(minutes=5): restart = True
        elif not bot_process.is_alive(): restart = True
        elif heartbeat and heartbeat < now - timedelta(minutes=2): restart = True
        else: last_health = now

        if restart:
            if last_restart < now - timedelta(minutes=5):
                watchdog_logger.info("Restarting bot...")
                close_bot_process(bot_process)
                bot_process = new_bot_process(queue, db_params)
                last_restart = now
            else:
                watchdog_logger.info("Refusing rapid restart.")
        
        # Keep Report Process Alive
        if not report_process.is_alive():
            watchdog_logger.warning("Restarting Report Process...")
            report_process = ReportProcess(db_params, queue)
            report_process.start()

        time.sleep(60)
        if not restart: watchdog_logger.info("Services healthy.")

def new_bot_process(queue: Queue, db_params) -> BotProcess:
    bot = BotProcess(*db_params, os.environ["TWITCH_USERNAME"], os.environ["TWITCH_OAUTH_TOKEN"], queue)
    bot.start()
    return bot

def close_bot_process(bot: BotProcess) -> None:
    try:
        if bot.is_alive(): bot.terminate()
        time.sleep(10)
        bot.close()
    except Exception:
        pass