import discord
from discord.ext import tasks
import requests
import json
import asyncio
from datetime import datetime
import hashlib
import base64

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CUSTOMER_IDS = [1042800]  # Your and your friend's customer IDs

# Store last known records
RECORDS_FILE = 'records.json'

class iRacingAPI:
    def __init__(self, email, password):
        self.base_url = 'https://members-ng.iracing.com'
        self.session = requests.Session()
        self.authenticate(email, password)
    
    def authenticate(self, email, password):
        """Authenticate with iRacing using their current API"""
        auth_url = f'{self.base_url}/auth'
        
        # Encode password
        encoded_password = base64.b64encode(
            (password + email.lower()).encode('utf-8')
        ).decode('utf-8')
        
        payload = {
            'email': email,
            'password': encoded_password
        }
        
        try:
            response = self.session.post(
                auth_url,
                data=payload,  # Changed from json to data
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            
            print(f"Auth response status: {response.status_code}")
            
            if response.status_code == 200:
                print("Authentication successful!")
                return True
            else:
                print(f"Auth response: {response.text[:500]}")
                raise Exception(f'iRacing authentication failed with status {response.status_code}')
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            raise
    
    def get_last_series_results(self, customer_id):
        """Get recent racing results for a customer"""
        url = f'{self.base_url}/data/results/search_series'
        params = {
            'cust_id': customer_id,
            'official_only': 0
        }
        
        try:
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Error getting results: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error in get_last_series_results: {str(e)}")
            return None
    
    def get_best_lap_times(self, customer_id):
        """Extract best lap times from recent results"""
        results = self.get_last_series_results(customer_id)
        if not results:
            return None
        
        lap_times = []
        
        # Parse the results to extract lap time data
        # Structure may vary - adjust based on actual API response
        if 'data' in results:
            for session in results['data']:
                if 'best_lap_time' in session and session['best_lap_time'] > 0:
                    lap_times.append({
                        'track_name': session.get('track', {}).get('track_name', 'Unknown Track'),
                        'car_name': session.get('car_name', 'Unknown Car'),
                        'best_lap_time': session['best_lap_time'],
                        'display_name': session.get('display_name', 'Unknown Driver')
                    })
        
        return {'data': lap_times} if lap_times else None

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

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        try:
            self.iracing = iRacingAPI(IRACING_EMAIL, IRACING_PASSWORD)
            self.check_records.start()
        except Exception as e:
            print(f"Failed to initialize iRacing API: {e}")
    
    @tasks.loop(minutes=15)
    async def check_records(self):
        """Check for new lap records every 15 minutes"""
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            print(f"Could not find channel with ID {CHANNEL_ID}")
            return
        
        current_records = load_records()
        print(f"Checking records at {datetime.now()}")
        
        for customer_id in CUSTOMER_IDS:
            try:
                print(f"Checking customer {customer_id}")
                data = self.iracing.get_best_lap_times(customer_id)
                
                if not data or 'data' not in data:
                    print(f"No data for customer {customer_id}")
                    continue
                
                for lap_data in data['data']:
                    track_name = lap_data.get('track_name')
                    car_name = lap_data.get('car_name')
                    best_lap = lap_data.get('best_lap_time')
                    driver_name = lap_data.get('display_name')
                    
                    if not all([track_name, car_name, best_lap, driver_name]) or best_lap <= 0:
                        continue
                    
                    # Server-wide record key (track + car)
                    record_key = f"{track_name}_{car_name}"
                    
                    # Check if this beats the current server record
                    is_new_record = False
                    previous_holder = None
                    previous_time = None
                    
                    if record_key not in current_records:
                        # First record for this track/car
                        is_new_record = True
                        print(f"First record for {track_name} in {car_name}")
                    elif best_lap < current_records[record_key]['time']:
                        # Beats existing record
                        is_new_record = True
                        previous_holder = current_records[record_key]['driver']
                        previous_time = current_records[record_key]['time']
                        print(f"New record! {driver_name} beat {previous_holder}")
                    
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
                            color=0xFF1493,  # Neon pink
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
                        print(f"Posted record to Discord!")
                
                save_records(current_records)
                
            except Exception as e:
                print(f'Error checking records for {customer_id}: {e}')
                import traceback
                traceback.print_exc()
            
            # Be nice to iRacing API
            await asyncio.sleep(2)

# Run the bot
if __name__ == "__main__":
    client = RecordBot()
    client.run(DISCORD_TOKEN)