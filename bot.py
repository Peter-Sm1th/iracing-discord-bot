import discord
from discord.ext import tasks
import json
from datetime import datetime
from pyracing import client as pyracing_client

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CUSTOMER_IDS = [1042800]

RECORDS_FILE = 'records.json'

def load_records():
    try:
        with open(RECORDS_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_records(records):
    with open(RECORDS_FILE, 'w') as f:
        json.dump(records, f, indent=2)

def format_lap_time(seconds):
    if seconds <= 0:
        return "N/A"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:06.3f}"

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'✓ Logged in as {self.user}')
        try:
            self.iracing = pyracing_client.iRacingClient(
                username=IRACING_EMAIL,
                password=IRACING_PASSWORD
            )
            print("✓ iRacing client initialized")
            self.check_records.start()
        except Exception as e:
            print(f"✗ Failed to initialize: {e}")
            import traceback
            traceback.print_exc()
    
    @tasks.loop(minutes=15)
    async def check_records(self):
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            print(f"✗ Channel not found")
            return
        
        current_records = load_records()
        print(f"\n--- Checking at {datetime.now().strftime('%H:%M:%S')} ---")
        
        for customer_id in CUSTOMER_IDS:
            try:
                print(f"Checking customer {customer_id}...")
                
                # Get career stats which includes recent best times
                stats = self.iracing.stats_member_career(customer_id)
                
                if not stats:
                    print("  No stats returned")
                    continue
                
                print(f"  Stats received: {type(stats)}")
                
                # Try to find lap time data
                # This will depend on the actual structure returned
                # We'll need to inspect and adapt
                
                await channel.send("Bot is running and checking records!")
                
            except Exception as e:
                print(f"✗ Error: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    client = RecordBot()
    client.run(DISCORD_TOKEN)
