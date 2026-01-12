import discord
from discord.ext import tasks
import requests
import json
from datetime import datetime
import hashlib
import base64

# Configuration
DISCORD_TOKEN = 'your_discord_bot_token_here'
CHANNEL_ID = 123456789
IRACING_EMAIL = 'your_iracing_email'
IRACING_PASSWORD = 'your_iracing_password'
CUSTOMER_IDS = [123456]  # Your customer ID

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

class iRacingAPI:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.base_url = 'https://members-ng.iracing.com'
        self.authenticate()
    
    def hash_password(self, password, email):
        """Hash password according to iRacing's requirements"""
        # Step 1-2: Convert email to lowercase and concatenate to password
        combined = password + email.lower()
        
        # Step 3: Create SHA256 hash (binary format)
        hash_binary = hashlib.sha256(combined.encode('utf-8')).digest()
        
        # Step 4: Encode in Base64
        hash_base64 = base64.b64encode(hash_binary).decode('utf-8')
        
        return hash_base64
    
    def authenticate(self):
        """Authenticate with iRacing using hashed password"""
        hashed_pw = self.hash_password(self.password, self.email)
        
        auth_data = {
            'email': self.email,
            'password': hashed_pw
        }
        
        try:
            response = self.session.post(
                f'{self.base_url}/auth',
                json=auth_data,
                headers={'Content-Type': 'application/json'}
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
        """Get last 10 official races"""
        try:
            url = f'{self.base_url}/data/stats/member_recent_races'
            params = {'cust_id': customer_id}
            
            response = self.session.get(url, params=params)
            
            if response.status_code == 200:
                return response.json()
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
            self.iracing = iRacingAPI(IRACING_EMAIL, IRACING_PASSWORD)
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
        print(f"\n--- Checking at {datetime.now().strftime('%H:%M:%S')} ---")
        
        for customer_id in CUSTOMER_IDS:
            try:
                print(f"Checking customer {customer_id}...")
                
                data = self.iracing.get_member_recent_races(customer_id)
                
                if not data or 'races' not in data:
                    print("  No race data")
                    continue
                
                print(f"  Found {len(data['races'])} races")
                
                # Get member info for display name
                member_url = f'{self.iracing.base_url}/data/member/info'
                member_response = self.iracing.session.get(member_url)
                driver_name = member_response.json().get('display_name', f'Driver {customer_id}') if member_response.status_code == 200 else f'Driver {customer_id}'
                
                for race in data['races']:
                    track_name = race['track']['track_name']
                    
                    # Get car name from car_id
                    car_id = race.get('car_id')
                    # For now, use car_id as placeholder - we'd need another API call to get car name
                    car_name = f"Car_{car_id}"
                    
                    # Get qualifying time (best lap in practice/quali)
                    lap_time = race.get('qualifying_time', 0)
                    
                    # Skip if no valid lap time
                    if lap_time <= 0:
                        continue
                    
                    # Convert from centiseconds if needed
                    if lap_time > 10000:
                        lap_time = lap_time / 10000.0
                    
                    record_key = f"{track_name}_{car_name}"
                    
                    # Check for new record
                    is_new = False
                    prev_holder = None
                    prev_time = None
                    
                    if record_key not in current_records:
                        is_new = True
                        print(f"  ✓ First record: {track_name} / {car_name}")
                    elif lap_time < current_records[record_key]['time']:
                        is_new = True
                        prev_holder = current_records[record_key]['driver']
                        prev_time = current_records[record_key]['time']
                        print(f"  ✓ New record!")
                    
                    if is_new:
                        current_records[record_key] = {
                            'time': lap_time,
                            'driver': driver_name,
                            'customer_id': customer_id,
                            'date': datetime.now().isoformat()
                        }
                        
                        # Post to Discord
                        embed = discord.Embed(
                            title="🏁 NEW SERVER RECORD! 🏁",
                            description=f"**{driver_name}** just set a blistering lap!",
                            color=0xFF1493,
                            timestamp=datetime.now()
                        )
                        
                        embed.add_field(name="🛣️ Track", value=track_name, inline=True)
                        embed.add_field(name="🏎️ Car", value=car_name, inline=True)
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

**And `requirements.txt`:**
```
discord.py
requests
