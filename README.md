# SodiumTycoon (SaltyBoy)

A Python-based automation bot for SaltyBet.com, running on a Dockerized microservices architecture. It handles historical data scraping, real-time betting using a weighted strategy (ELO/H2H/Streak), and performance tracking via a Flask dashboard.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Postgres](https://img.shields.io/badge/Postgres-16-336791)
![Docker](https://img.shields.io/badge/Docker-Compose-green)

## Overview

This project is designed to run 24/7 on a VPS. It solves common SaltyBet botting issues like database ID collisions, blind betting on new characters, and bankroll exhaustion.

### Core Features

* **Collision-Proof DB:** Uses timestamp-based Safe IDs (`BigInt`) to record live matches locally, merging them with official API IDs later to prevent primary key errors.
* **Risk Management:**
    * **Kelly Criterion:** Adjusts bet size based on confidence and bankroll.
    * **Wealth Preservation:** Scales down aggression as the balance grows (capped at $5M effective bankroll calculation).
    * **Tier Safety:** Hard caps bets on high-variance tiers (Tier X/Exhibitions).
* **Discord Integration:** Sends daily profit reports (08:00 & 17:00 GMT-3) and critical crash alerts.

## Project Structure

The system runs as three isolated containers:

1.  **`bot`**: The logic core. Listens to Twitch chat, calculates odds, places bets, and manages the database.
2.  **`web`**: A lightweight Flask dashboard to view real-time ROI, win rates, and recent match history.
3.  **`db`**: PostgreSQL 16 database (optimized with indexes for fast H2H lookups).

There is also a sidecar service for daily automated backups.

## Setup & Deployment

### 1. Prerequisites
* Docker & Docker Compose
* SaltyBet Account

### 2. Configuration
Copy the example environment and fill in your credentials.

**`.env`**
```ini
# SaltyBet
SALTY_EMAIL=your_email
SALTY_PASSWORD=your_password

# Twitch (for chat parsing)
TWITCH_USERNAME=your_user
TWITCH_OAUTH_TOKEN=oauth:xyz

# Notifications
DISCORD_WEBHOOK_URL=[https://discord.com/api/webhooks/](https://discord.com/api/webhooks/)...

# Database (Default Docker values)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_DB=saltyboy
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_PORT_EXTERNAL=5432

# Paths
BOT_LOG_PATH=./logs/bot
WEB_LOG_PATH=./logs/web```

##3. Run (Docker)
Build and start the containers in detached mode.

```docker-compose up -d --build```

Dashboard: http://localhost:5000
Logs: docker-compose logs -f bot

###Database Management
The database volume is persistent. Use these commands to manage your data when moving between local dev and VPS.

###Backup (Export to file):

```docker exec -t saltyboyc-db-1 pg_dump -U postgres saltyboy > full_backup.sql```

###Restore (Import from file):
```
# 1. Stop the bot to prevent locks
docker stop saltyboyc-bot-1

# 2. Run the import
cat full_backup.sql | docker exec -i saltyboyc-db-1 psql -U postgres -d saltyboy

# 3. Restart bot
docker start saltyboyc-bot-1
```

###Security Notes (VPS)

Port Binding: The docker-compose.yml binds the database port (5432) to 127.0.0.1. This prevents external access. To access the DB remotely, use an SSH tunnel.

Log Rotation: Logging is configured to rotate at 10MB to prevent disk space exhaustion on smaller servers.