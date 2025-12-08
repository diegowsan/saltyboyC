# SodiumTycoon

**A smarter betting bot for SaltyBet.**
[STILL IN DEVELOPMENT, USE AT YOUR ON RISK]

SodiumTycoon is a fork of [SaltyBoy](https://github.com/FranciscoAT/saltyboy) engineered for high-balance accounts. Unlike standard bots that simply bet on the favorite, SodiumTycoon operates like a quantitative hedge fund—managing risk, preventing market manipulation, and tracking your actual ROI in real-time.

## 🚀 Key Features

### 🧠 Smart Betting Engine
* **Logistic Regression:** Uses a weighted model of Tier ELO, Head-to-Head history, and Common Opponent performance to calculate win probabilities.
* **Auto-Retraining:** The bot monitors its own database and re-trains its AI weights every 100 matches to adapt to shifting trends.
* **Context Awareness:** Automatically detects the difference between Tournaments (low balance, aggressive) and Matchmaking (high balance, conservative).

### 🛡️ Whale-Proof Money Management
* **Market Maker Protection:** Automatically caps bets (default: $250k) to prevent your large bankroll from crashing the betting odds.
* **Effective Balance Scaling:** Uses a "Virtual Cap" for betting calculations, ensuring stakes remain proportional even when your bankroll exceeds $25M+.
* **P-Tier Safety:** Automatically detects volatile "Potato Tier" matches and minimizes risk to $1.

### 🏥 Self-Healing Database
* **Zombie Killer:** Automatically detects if SaltyBet changes a fighter's ID behind the scenes, migrates your historical data to the new ID, and cleans up the duplicate.
* **Auto-Migration:** Automatically updates your database schema (e.g., adding new tracking columns) without crashing or requiring manual SQL.

### 📊 Real-Time Analytics Dashboard
* **True ROI Tracking:** Tracks your *actual* bets and results (Green/Red badges), fixing the common issue where dashboards only show the match winner.
* **Live Confidence:** Displays the AI's exact confidence percentage for every bet in real-time.
* **Win Rate:** Tracks your personal win rate over the last 100 bets.

## Getting Started

### 1. Requirements
* **Python 3.12+**
* **PostgreSQL** (or just use the Docker setup below)
* **Twitch Account** (Dedicated bot account recommended)

### 2. Quick Start (Docker)
The easiest way to run SodiumTycoon is via Docker Compose.

1.  **Configure Environment:**
    ```bash
    cp .template.env .env
    # Edit .env with your SaltyBet email, password, and Twitch Token
    ```

2.  **Launch:**
    ```bash
    docker-compose up -d --build
    ```

3.  **Access Dashboard:**
    Open `http://localhost:5000` to see the bot in action.

### 3. Manual Setup
For local development without Docker, see [Setup](./docs/setup.md) and [Developing](./docs/developing.md).

---

## Architecture

* **Bot Engine:** Python (Handles Twitch chat, API syncing, and Betting Strategy).
* **Database:** PostgreSQL (Stores Fighters, Matches, and AI Weights).
* **Dashboard:** Flask (Live web interface).

## Acknowledgements

* **Original Project:** Forked from [SaltyBoy](https://github.com/FranciscoAT/saltyboy).
* **Salty Bet:** The mines never sleep. [saltybet.com](https://saltybet.com)
* **Contributors:** Built by [DiegoWSan](https://github.com/diegowsan) and the open-source community.