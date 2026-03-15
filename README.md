# iRacing Discord Bot

A Discord bot that tracks lap records and race results for a private iRacing league. Built as a personal experiment using **Claude Code** to explore AI-assisted development.

## What it does

- **Auto-detects new lap records** — polls the iRacing API every 15 minutes and posts to Discord when a driver sets a new server record in qualifying or race sessions
- **`!records`** — displays all current server records with track, car, lap time, and driver
- **`!lastrace`** — shows a detailed breakdown of the most recent race: finishing position, iRating change, safety rating change, lap times, and incidents
- **`!trackguide`** — searches YouTube for recent track guides based on your last session's track and car combo

## Stack

- Python
- [discord.py](https://discordpy.readthedocs.io/)
- iRacing OAuth2 API
- YouTube Data API v3

## Setup

1. Clone the repo
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with the following:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   CHANNEL_ID=your_discord_channel_id
   IRACING_EMAIL=your_iracing_email
   IRACING_PASSWORD=your_iracing_password
   CLIENT_ID=your_iracing_oauth_client_id
   CLIENT_SECRET=your_iracing_oauth_client_secret
   CUSTOMER_IDS=comma_separated_iracing_customer_ids
   YOUTUBE_API_KEY=your_youtube_api_key
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

## Notes

All credentials are managed via environment variables — never commit your `.env` file.
