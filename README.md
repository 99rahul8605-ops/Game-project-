# 🎮 Telegram Game Bot

A feature‑rich Telegram game bot where users can earn virtual money, kill/rob each other, buy protection, and climb the leaderboard.  
Built with Python, `python-telegram-bot`, and MongoDB.  
Designed to run 24/7 on **Render’s free tier** using Docker.

---

## ✨ Features

- **Auto‑registration** – any command automatically creates an account with 1000 Rs.
- **Daily reward** – claim 2000 Rs every 24 hours with `/daily`.
- **Kill** – reply to someone to kill them: you gain 500 Rs, they die for 5 hours.  
  - 1‑minute cooldown, max 10 kills per 12‑hour rolling window.
  - Funny random messages after each kill.
- **Revive** – revive yourself (cost 100 Rs) or reply to revive someone else.
- **Rob** – reply to steal a random amount (100–3000 Rs in hundreds).  
  - 1‑minute cooldown, max 10 robs per 12‑hour rolling window.
  - Cannot rob protected users.
  - Hilarious random robbery messages.
- **Protection** – buy immunity from being killed or robbed. Plans via inline buttons:  
  - 1 hour – 100 Rs  
  - 2 hours – 1000 Rs  
  - 5 hours – 2000 Rs  
  - 12 hours – 3000 Rs  
  - If already protected, purchase menu is hidden.
- **Give** – transfer money to another user with a 10% fee deducted from the amount.  
  Usage: `/give <amount>` (reply to the receiver).
- **Invite system** – each user gets a personal invite link.  
  When a new user joins via that link, the referrer receives **5000 Rs** and a notification.
- **Leaderboard** – `/top` shows the 10 richest players (username or first name).
- **Balance check** – `/bal` shows your profile. Reply to a message to see someone else’s profile.
- **Bot protection** – the bot itself cannot be targeted (kill, rob, give, etc.).
- **Add to Group** button on the welcome message for easy installation.
- **Owner commands** (hidden from normal users):
  - `/stats` – total users, total balance, alive/dead counts.
  - `/broadcast` – reply to any message (text, sticker, photo, video, document) to forward it to **all registered users**. Shows progress and sample failures.
- **Persistent storage** – all data (balance, status, protection expiry, kill/rob timestamps, last daily claim) stored in MongoDB.
- **Cooldowns and limits** – kill/rob cooldowns (1 min) and 12‑hour limits (10 each) are stored in MongoDB, so they survive restarts.
- **Friendly display names** – never show raw user IDs; use `@username` or first name.

---

## 🤖 Commands

| Command | Description |
|--------|-------------|
| `/start` | Register and get 1000 Rs |
| `/daily` | Claim 2000 Rs daily reward (once per 24h) |
| `/bal` | Check your balance & status (reply to check others) |
| `/top` | Show top 10 richest players |
| `/kill` | Reply to kill someone (gain 500 Rs, target dies 5h, max 10/12h, 1min cooldown) |
| `/revive` | Revive yourself or reply to revive someone (cost 100 Rs) |
| `/rob` | Reply to rob someone (steal 100‑3000 Rs in hundreds, max 10/12h, 1min cooldown, cannot rob protected) |
| `/protect` | Buy protection plans via inline buttons |
| `/give <amount>` | Reply to give money (10% fee deducted from amount) |
| `/invite` | Get your personal invite link (DM only) |
| `/help` | Show this command list |

*Owner‑only commands (hidden from menu):*  
- `/stats` – bot statistics  
- `/broadcast` – forward a replied message to all users

---

## 🛠 Prerequisites

- **Telegram Bot Token** – get it from [@BotFather](https://t.me/botfather).
- **MongoDB URI** – e.g. from [MongoDB Atlas](https://www.mongodb.com/atlas) (free tier works).
- **Owner Telegram User ID(s)** – your numeric ID (get it from [@userinfobot](https://t.me/userinfobot)). For multiple owners, use a comma‑separated list.

---

## 🚀 Setup & Deployment

### 1. Clone / create the repository

Place the following files in your project folder:
- `bot.py` (the complete code)
- `requirements.txt`
- `Dockerfile`

### 2. Environment variables

Create a `.env` file (for local testing) or set these variables on Render:

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Your Telegram bot token |
| `MONGO_URI` | MongoDB connection string |
| `OWNER_ID` | Comma‑separated list of owner user IDs (e.g., `123456,789012`) |

### 3. Run locally with Docker

```bash
docker build -t game-bot .
docker run -e BOT_TOKEN=your_token -e MONGO_URI=your_uri -e OWNER_ID=your_id game-bot
