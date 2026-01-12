import discord
from discord.ext import tasks
import json
from datetime import datetime
import requests
import hashlib

# Configuration
DISCORD_TOKEN = 'your_discord_bot_token_here'
CHANNEL_ID = 123456789  # Your channel ID
IRACING_EMAIL = 'your_iracing_email'
IRACING_PASSWORD = 'your_iracing_password'
CUSTOMER_IDS = [123456]  # Your customer ID

# Store last known records
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
    """Format lap time in MM:SS.mmm format"""
    if seconds <= 0:
        return "N/A"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes}:{secs:06.3f}"

class SimpleIRacingAPI:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.base_url = 'https://members-ng.iracing.com'
        self.authenticate()
    
    def authenticate(self):
        """Authenticate with iRacing"""
        # Hash password with SHA-256
        encoded_pw = hashlib.sha256((self.password + self.email.lower()).encode('utf-8')).hexdigest()
        
        auth_data = {
            'email': self.email,
            'password': encoded_pw
        }
        
        try:
            response = self.session.post(
                f'{self.base_url}/auth',
                data=auth_data
            )
            
            print(f"Auth status: {response.status_code}")
            
            if response.status_code == 200:
                print("✓ iRacing authentication successful!")
                return True
            else:
                print(f"Auth failed: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"Auth error: {e}")
            return False
    
    def get_member_recent_races(self, customer_id):
        """Get recent races for a member"""
        try:
            url = f'{self.base_url}/data/stats/member_recent_races'
            params = {'cust_id': customer_id}
            
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"API call failed: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting races: {e}")
            return None

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'✓ Logged in as {self.user}')
        try:
            self.iracing = SimpleIRacingAPI(IRACING_EMAIL, IRACING_PASSWORD)
            print("✓ Starting record checker...")
            self.check_records.start()
        except Exception as e:
            print(f"✗ Failed to initialize: {e}")
    
    @tasks.loop(minutes=15)
    async def check_records(self):
        """Check for new lap records"""
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            print(f"✗ Could not find channel {CHANNEL_ID}")
            return
        
        current_records = load_records()
        print(f"\n--- Checking records at {datetime.now().strftime('%H:%M:%S')} ---")
        
        for customer_id in CUSTOMER_IDS:
            try:
                print(f"Checking customer {customer_id}...")
                
                data = self.iracing.get_member_recent_races(customer_id)
                
                if not data:
                    print("  No data returned")
                    continue
                
                # Debug: print structure
                print(f"  Data keys: {data.keys() if isinstance(data, dict) else 'not a dict'}")
                
                # Try different possible data structures
                races = None
                if isinstance(data, dict):
                    races = data.get('races') or data.get('data') or data.get('results')
                elif isinstance(data, list):
                    races = data
                
                if not races:
                    print(f"  No races found in data")
                    continue
                
                print(f"  Found {len(races)} races")
                
                for race in races[:10]:  # Check last 10 races
                    # Try to extract data with multiple possible field names
                    track = race.get('track_name') or race.get('track', {}).get('track_name', 'Unknown Track')
                    car = race.get('car_name') or race.get('car_class_name', 'Unknown Car')
                    lap_time = race.get('best_lap_time') or race.get('best_nlaps_time', 0)
                    driver = race.get('display_name') or race.get('driver_name', f'Driver {customer_id}')
                    
                    # Convert from centiseconds if needed
                    if lap_time > 10000:
                        lap_time = lap_time / 10000.0
                    
                    if not track or not car or lap_time <= 0:
                        continue
                    
                    record_key = f"{track}_{car}"
                    
                    # Check for new record
                    is_new = False
                    prev_holder = None
                    prev_time = None
                    
                    if record_key not in current_records:
                        is_new = True
                        print(f"  ✓ First record: {track} / {car} - {format_lap_time(lap_time)}")
                    elif lap_time < current_records[record_key]['time']:
                        is_new = True
                        prev_holder = current_records[record_key]['driver']
                        prev_time = current_records[record_key]['time']
                        print(f"  ✓ New record: {driver} beat {prev_holder}!")
                    
                    if is_new:
                        current_records[record_key] = {
                            'time': lap_time,
                            'driver': driver,
                            'customer_id': customer_id,
                            'date': datetime.now().isoformat()
                        }
                        
                        # Post to Discord
                        embed = discord.Embed(
                            title="🏁 NEW SERVER RECORD! 🏁",
                            description=f"**{driver}** just set a blistering lap!",
                            color=0xFF1493,
                            timestamp=datetime.now()
                        )
                        
                        embed.add_field(name="🛣️ Track", value=track, inline=True)
                        embed.add_field(name="🏎️ Car", value=car, inline=True)
                        embed.add_field(name="⏱️ Time", value=format_lap_time(lap_time), inline=True)
                        
                        if prev_holder:
                            improvement = prev_time - lap_time
                            embed.add_field(
                                name="📊 Previous Record",
                                value=f"{prev_holder}: {format_lap_time(prev_time)}",
                                inline=False
                            )
                            embed.add_field(
                                name="🔥 Improvement",
                                value=f"-{improvement:.3f}s",
                                inline=False
                            )
                        
                        embed.set_footer(text="After Hours Racing League")
                        
                        await channel.send(embed=embed)
                        print(f"  ✓ Posted to Discord!")
                
                save_records(current_records)
                
            except Exception as e:
                print(f"✗ Error for customer {customer_id}: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    client = RecordBot()
    client.run(DISCORD_TOKEN)
```

**And update `requirements.txt` to just:**
```
discord.py
requests
