import discord
from discord.ext import tasks
import requests
import json
from datetime import datetime
import base64

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CLIENT_ID = '1042800-pwlimited'
CLIENT_SECRET = 'LIKING-casually-occupancy-DETONATE-RINSING-GUTTER'
CUSTOMER_IDS = [1042800]  # Just you for now

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

class iRacingOAuth:
    def __init__(self, email, password, client_id, client_secret):
        self.email = email
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.base_url = 'https://members-ng.iracing.com'
        self.oauth_url = 'https://oauth.iracing.com'
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.authenticate()
    
    def authenticate(self):
        """Get initial access token using Password Limited flow"""
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'password_limited',
            'username': self.email,
            'password': self.password,
            'scope': 'iracing'
        }
        
        try:
            print("Authenticating with OAuth2...")
            response = requests.post(
                f'{self.oauth_url}/token',
                headers=headers,
                data=data
            )
            
            print(f"OAuth status: {response.status_code}")
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data['refresh_token']
                self.token_expiry = datetime.now().timestamp() + token_data.get('expires_in', 600)
                print("✓ OAuth authentication successful!")
                return True
            else:
                print(f"OAuth failed: {response.text[:500]}")
                return False
        except Exception as e:
            print(f"OAuth error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def refresh_access_token(self):
        """Refresh the access token when it expires"""
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }
        
        try:
            response = requests.post(
                f'{self.oauth_url}/token',
                headers=headers,
                data=data
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data['refresh_token']
                self.token_expiry = datetime.now().timestamp() + token_data.get('expires_in', 600)
                print("✓ Token refreshed")
                return True
            else:
                print(f"Token refresh failed: {response.text[:200]}")
                return False
        except Exception as e:
            print(f"Token refresh error: {e}")
            return False
    
    def ensure_valid_token(self):
        """Check if token is valid, refresh if needed"""
        if not self.access_token or datetime.now().timestamp() >= self.token_expiry - 30:
            return self.refresh_access_token()
        return True
    
    def get_member_recent_races(self, customer_id):
        """Get last 10 official races"""
        if not self.ensure_valid_token():
            return None
        
        try:
            url = f'{self.base_url}/data/stats/member_recent_races'
            params = {'cust_id': customer_id}
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                # Check if it's a link response
                if 'link' in data:
                    # Fetch the actual data from the link
                    link_response = requests.get(data['link'])
                    if link_response.status_code == 200:
                        return link_response.json()
                return data
            else:
                print(f"API call failed: {response.status_code}")
                print(f"Response: {response.text[:200]}")
                return None
        except Exception as e:
            print(f"Error getting races: {e}")
            import traceback
            traceback.print_exc()
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
            self.iracing = iRacingOAuth(IRACING_EMAIL, IRACING_PASSWORD, CLIENT_ID, CLIENT_SECRET)
            if self.iracing.access_token:
                print("✓ Starting record checker...")
                self.check_records.start()
            else:
                print("✗ Failed to get OAuth token")
        except Exception as e:
            print(f"✗ Failed to initialize: {e}")
            import traceback
            traceback.print_exc()
    
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
                
                if not data:
                    print("  No data returned")
                    continue
                
                # Handle different response formats
                races = None
                if isinstance(data, dict):
                    races = data.get('races')
                elif isinstance(data, list):
                    races = data
                
                if not races:
                    print(f"  No races found in data")
                    continue
                
                print(f"  Found {len(races)} races")
                
                # Get driver name from first race
                driver_name = races[0].get('display_name', f'Driver {customer_id}') if races else f'Driver {customer_id}'
                
                for race in races[:10]:  # Check last 10 races
                    track_name = race.get('track', {}).get('track_name', 'Unknown Track')
                    car_name = race.get('series_name', f"Series {race.get('series_id', 'Unknown')}")
                    
                    # Get qualifying time (best lap)
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
                        print(f"  ✓ First record: {track_name} / {car_name} - {format_lap_time(lap_time)}")
                    elif lap_time < current_records[record_key]['time']:
                        is_new = True
                        prev_holder = current_records[record_key]['driver']
                        prev_time = current_records[record_key]['time']
                        print(f"  ✓ New record: beat previous by {prev_time - lap_time:.3f}s")
                    
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
                        embed.add_field(name="🏎️ Series", value=car_name, inline=True)
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