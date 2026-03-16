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
