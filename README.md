# 🧂 SodiumTycoon (SaltyBoy Fork)

**An advanced, self-healing algorithmic trading bot for SaltyBet.com.**

SodiumTycoon is a fully containerized "Money Printer" designed to run 24/7 on a VPS. It uses a custom "Deep Learning" strategy that fetches comprehensive match history, calculates real-time odds using ELO/H2H/Streak, and manages risk using a dynamic Kelly Criterion.

![Status](https://img.shields.io/badge/Status-Online-success)
![Docker](https://img.shields.io/badge/Docker-Containerized-blue)
![Database](https://img.shields.io/badge/Postgres-16-336791)
![Language](https://img.shields.io/badge/Python-3.11-yellow)

## 📖 Overview

This project solves common SaltyBet botting issues like database ID collisions, blind betting on new characters, and bankroll exhaustion. It is built to be "set and forget."

## 🚀 Core Features

### 🧠 The Brain
* **Deep Backfill Protocol:** Automatically fetches the last 100 matches for any new fighter encountered, ensuring the bot never bets "blind."
* **"High Ground" Database:** Uses Time-based Safe IDs (`BigInt`) to record live matches instantly, preventing ID collisions with the official API.
* **Self-Healing Data:** Automatically detects temporary match IDs and migrates them to official API IDs in the background.

### 🛡️ Risk Management
* **Confidence Clamp:** Caps maximum confidence at 85% to account for upsets.
* **Whale Tax:** Automatically scales down bet percentage (from 5% to 2%) as your bankroll grows to preserve wealth.
* **Tier Safety:** Hard caps bets on high-variance tiers (Tier X/Exhibitions) to $20k.

### 📡 Infrastructure
* **Fully Dockerized:** Runs the Bot, Database, Dashboard, and Backups in isolated containers.
* **Discord Watchtower:** Sends startup alerts, crash reports, and **Daily Profit Reports** (08:00 & 17:00 GMT-3) directly to your phone.
* **The Vault:** A sidecar container that wakes up daily to backup the database and rotate old logs.

---

## 📂 Project Structure

    ├── applications
    │   ├── bot             # The Python logic (Brain)
    │   └── web             # The Flask Dashboard (Face)
    ├── backups             # Daily automated SQL dumps appear here
    ├── docker-compose.yml  # The Master Controller
    └── .env                # Secrets (Do not commit to GitHub!)

---

## 🛠️ Setup & Deployment

### 1. Prerequisites
* Docker & Docker Compose
* SaltyBet Account

### 2. Configuration
Create a file named `.env` in the root directory and define the following variables:

    # SaltyBet Credentials
    SALTY_EMAIL=your_email@example.com
    SALTY_PASSWORD=your_password

    # Twitch Credentials (for chat listening)
    TWITCH_USERNAME=your_twitch_username
    TWITCH_OAUTH_TOKEN=oauth:your_token_here

    # Discord (for notifications)
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your_webhook_url

    # Database Config
    POSTGRES_USER=postgres
    POSTGRES_PASSWORD=password
    POSTGRES_DB=saltyboy
    POSTGRES_HOST=db
    POSTGRES_PORT=5432
    POSTGRES_PORT_EXTERNAL=5432

    # Paths
    BOT_LOG_PATH=./logs/bot
    WEB_LOG_PATH=./logs/web

### 3. Run It
This single command builds the containers, sets up the network, and starts the bot.

    docker-compose up -d --build

* **Dashboard:** http://localhost:5000
* **Logs:** `docker-compose logs -f bot`

---

## 💾 Database Management

The database volume is persistent. Use these commands to manage your data when moving between local dev and VPS.

### Backup (Export to file)
Run this to save your current database to a file:

    docker exec -t saltyboyc-db-1 pg_dump -U postgres saltyboy > full_backup.sql

### Restore (Import from file)
Run this to load a backup file into the database:

    # 1. Stop the bot to prevent locks
    docker stop saltyboyc-bot-1

    # 2. Run the import
    cat full_backup.sql | docker exec -i saltyboyc-db-1 psql -U postgres -d saltyboy

    # 3. Restart bot
    docker start saltyboyc-bot-1

---

## 🔒 Security Notes (VPS)

* **Port Binding:** The `docker-compose.yml` binds the database port (5432) to `127.0.0.1`. This prevents external access. To access the DB remotely, use an SSH tunnel.
* **Log Rotation:** Logging is configured to rotate at 10MB to prevent disk space exhaustion on smaller servers.