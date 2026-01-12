import discord
from discord.ext import tasks
import requests
import json
import asyncio
from datetime import datetime

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CUSTOMER_IDS = [1042800]

# Store last known records
RECORDS_FILE = 'records.json'

class iRacingAPI:
    def __init__(self, email, password):
        self.base_url = 'https://members-ng.iracing.com'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.authenticate(email, password)
    
    def authenticate(self, email, password):
        # Try the authentication endpoint
        auth_url = f'{self.base_url}/auth'
        data = {
            'email': email,
            'password': password
        }
        
        try:
            response = self.session.post(auth_url, json=data)
            print(f"Auth response status: {response.status_code}")
            print(f"Auth response: {response.text[:200]}")  # Print first 200 chars for debugging
            
            if response.status_code == 200:
                print("Authentication successful!")
            else:
                raise Exception(f'iRacing authentication failed with status {response.status_code}')
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            raise
    
    def get_best_lap_times(self, customer_id):
        # Get recent sessions and extract best laps
        url = f'{self.base_url}/data/results/search_series'
        params = {
            'cust_id': customer_id,  # Changed from customer_id
            'official_only': 0
        }
        
        try:
            response = self.session.get(url, params=params)
            print(f"Lap times response status: {response.status_code}")
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error getting lap times: {str(e)}")
            return None

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
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:06.3f}"

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        self.iracing = iRacingAPI(IRACING_EMAIL, IRACING_PASSWORD)
        self.check_records.start()
    
    @tasks.loop(minutes=15)  # Check every 15 minutes
    async def check_records(self):
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            return
        
        current_records = load_records()
        
        for customer_id in CUSTOMER_IDS:
            try:
                data = self.iracing.get_best_lap_times(customer_id)
                if not data:
                    continue
                
                # Parse sessions and check for new records
                for session in data.get('data', []):
                    track_name = session.get('track_name')
                    car_name = session.get('car_name')
                    best_lap = session.get('best_lap_time')
                    driver_name = session.get('display_name')
                    
                    if not all([track_name, car_name, best_lap]):
                        continue
                    
                    # ONE record per track/car combo (server-wide)
                    record_key = f"{track_name}_{car_name}"
                    
                    # Check if this beats the current server record
                    is_new_record = False
                    previous_holder = None
                    previous_time = None
                    
                    if record_key not in current_records:
                        # First record for this track/car
                        is_new_record = True
                    elif best_lap < current_records[record_key]['time']:
                        # Beats existing record
                        is_new_record = True
                        previous_holder = current_records[record_key]['driver']
                        previous_time = current_records[record_key]['time']
                    
                    if is_new_record:
                        # Update the record
                        current_records[record_key] = {
                            'time': best_lap,
                            'driver': driver_name,
                            'customer_id': customer_id,
                            'date': datetime.now().isoformat()
                        }
                        
                        # Create Discord embed
                        embed = discord.Embed(
                            title="🏁 NEW SERVER RECORD! 🏁",
                            description=f"**{driver_name}** just set a blistering lap!",
                            color=0xFF1493,  # Neon pink - customize this!
                            timestamp=datetime.now()
                        )
                        
                        embed.add_field(name="🛣️ Track", value=track_name, inline=True)
                        embed.add_field(name="🏎️ Car", value=car_name, inline=True)
                        embed.add_field(name="⏱️ Time", value=format_lap_time(best_lap), inline=True)
                        
                        # Show previous record if exists
                        if previous_holder:
                            improvement = previous_time - best_lap
                            embed.add_field(
                                name="📊 Previous Record", 
                                value=f"{previous_holder}: {format_lap_time(previous_time)}", 
                                inline=False
                            )
                            embed.add_field(
                                name="🔥 Improvement", 
                                value=f"-{improvement:.3f}s", 
                                inline=False
                            )
                        
                        embed.set_footer(text="After Hours Racing League")
                        
                        await channel.send(embed=embed)
                
                save_records(current_records)
                
            except Exception as e:
                print(f'Error checking records for {customer_id}: {e}')
            
            # Be nice to iRacing API
            await asyncio.sleep(2)

# Run the bot
client = RecordBot()
client.run(DISCORD_TOKEN)