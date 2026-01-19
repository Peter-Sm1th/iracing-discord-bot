import discord
from discord.ext import tasks
import requests
import json
from datetime import datetime
import base64
import hashlib

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CLIENT_ID = '1042800-pwlimited'
CLIENT_SECRET = 'LIKING-casually-occupancy-DETONATE-RINSING-GUTTER'
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

def mask_secret(secret, identifier):
    """
    Mask a secret using iRacing's masking algorithm.
    For client_secret: identifier is client_id
    For password: identifier is username (email)
    """
    normalized_id = identifier.strip().lower()
    combined = f"{secret}{normalized_id}"
    hasher = hashlib.sha256()
    hasher.update(combined.encode('utf-8'))
    return base64.b64encode(hasher.digest()).decode('utf-8')

class iRacingOAuth:
    def __init__(self, email, password, client_id, client_secret):
        self.email = email
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = requests.Session()
        self.base_url = 'https://members-ng.iracing.com'
        self.oauth_url = 'https://oauth.iracing.com/oauth2'
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.authenticate()
    
    def authenticate(self):
        """Get initial access token using Password Limited flow"""
        # Mask the client secret with client_id
        masked_secret = mask_secret(self.client_secret, self.client_id)
        
        # Mask the password with username
        masked_password = mask_secret(self.password, self.email)
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'password_limited',
            'client_id': self.client_id,
            'client_secret': masked_secret,
            'username': self.email,
            'password': masked_password,
            'scope': 'iracing.auth'
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
                self.refresh_token = token_data.get('refresh_token')
                self.token_expiry = datetime.now().timestamp() + token_data.get('expires_in', 600)
                print("✓ OAuth authentication successful!")
                print(f"  Token expires in: {token_data.get('expires_in')} seconds")
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
        if not self.refresh_token:
            print("No refresh token available, re-authenticating...")
            return self.authenticate()
        
        # Mask the client secret
        masked_secret = mask_secret(self.client_secret, self.client_id)
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': masked_secret,
            'refresh_token': self.refresh_token
        }
        
        try:
            print("Refreshing access token...")
            response = requests.post(
                f'{self.oauth_url}/token',
                headers=headers,
                data=data
            )
            
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.refresh_token = token_data.get('refresh_token')
                self.token_expiry = datetime.now().timestamp() + token_data.get('expires_in', 600)
                print("✓ Token refreshed")
                return True
            else:
                print(f"Token refresh failed: {response.text[:200]}")
                return self.authenticate()
        except Exception as e:
            print(f"Token refresh error: {e}")
            return self.authenticate()
    
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
    
    def get_subsession_results(self, subsession_id):
        """Get detailed results for a specific subsession including lap times"""
        if not self.ensure_valid_token():
            return None
        
        try:
            url = f'{self.base_url}/data/results/get'
            params = {'subsession_id': subsession_id}
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                # Check if it's a link response
                if 'link' in data:
                    link_response = requests.get(data['link'])
                    if link_response.status_code == 200:
                        return link_response.json()
                return data
            else:
                print(f"Subsession API call failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting subsession: {e}")
            return None
    
    def get_member_info(self, customer_ids):
        """Get member information including display name"""
        if not self.ensure_valid_token():
            return None
        
        try:
            url = f'{self.base_url}/data/member/get'
            # Convert list to comma-separated string
            if isinstance(customer_ids, list):
                customer_ids = ','.join(map(str, customer_ids))
            
            params = {'cust_ids': customer_ids}
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            response = requests.get(url, params=params, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                if 'link' in data:
                    link_response = requests.get(data['link'])
                    if link_response.status_code == 200:
                        return link_response.json()
                return data
            else:
                print(f"Member info API call failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting member info: {e}")
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
    
    async def on_message(self, message):
        """Handle Discord commands"""
        if message.author == self.user:
            return
        
        if message.content.startswith('!lastrace'):
            await self.handle_lastrace_command(message)
        elif message.content.startswith('!help'):
            await self.handle_help_command(message)
    
    async def handle_help_command(self, message):
        """Show available commands"""
        embed = discord.Embed(
            title="🏁 iRacing Bot Commands",
            description="Available commands for the After Hours Racing Bot",
            color=0x0099ff
        )
        
        embed.add_field(
            name="!lastrace",
            value="Shows your most recent race results with detailed stats",
            inline=False
        )
        embed.add_field(
            name="!lastrace @user",
            value="Shows another user's last race results",
            inline=False
        )
        
        embed.set_footer(text="After Hours Racing League")
        await message.channel.send(embed=embed)
    
    async def handle_lastrace_command(self, message):
        """Handle !lastrace command"""
        # Check if a user was mentioned
        customer_id = None
        driver_name = None
        
        if message.mentions:
            # For now, we'll need to map Discord users to iRacing customer IDs
            # You'll need to maintain this mapping
            await message.channel.send("🔧 User mention support coming soon! For now, showing your stats...")
            customer_id = CUSTOMER_IDS[0]  # Default to first customer
        else:
            # Default to first customer in list
            customer_id = CUSTOMER_IDS[0]
        
        if not self.iracing:
            await message.channel.send("❌ Bot not connected to iRacing. Please wait...")
            return
        
        try:
            # Show typing indicator
            async with message.channel.typing():
                # Get member info first to get display name
                member_info = self.iracing.get_member_info([customer_id])
                if member_info and 'members' in member_info and len(member_info['members']) > 0:
                    driver_name = member_info['members'][0].get('display_name', f'Driver {customer_id}')
                else:
                    driver_name = f'Driver {customer_id}'
                
                # Get recent races
                data = self.iracing.get_member_recent_races(customer_id)
                
                if not data:
                    await message.channel.send("❌ Could not fetch race data from iRacing.")
                    return
                
                # Handle different response formats
                races = None
                if isinstance(data, dict):
                    races = data.get('races')
                elif isinstance(data, list):
                    races = data
                
                if not races or len(races) == 0:
                    await message.channel.send("❌ No recent races found.")
                    return
                
                # Get the most recent race
                last_race = races[0]
                subsession_id = last_race.get('subsession_id')
                
                # Get detailed subsession data for lap times
                subsession_data = None
                avg_lap_time = 0
                best_lap_time = 0
                
                if subsession_id:
                    subsession_data = self.iracing.get_subsession_results(subsession_id)
                    if subsession_data and 'session_results' in subsession_data:
                        # Find this driver's results in the subsession
                        for session in subsession_data['session_results']:
                            if session.get('simsession_type') == 6:  # Race session
                                for result in session.get('results', []):
                                    if result.get('cust_id') == customer_id:
                                        avg_lap_time = result.get('average_lap', 0)
                                        best_lap_time = result.get('best_lap_time', 0)
                                        # Convert from centiseconds if needed
                                        if avg_lap_time > 10000:
                                            avg_lap_time = avg_lap_time / 10000.0
                                        if best_lap_time > 10000:
                                            best_lap_time = best_lap_time / 10000.0
                                        break
                
                # Extract race details
                series_name = last_race.get('series_name', 'Unknown Series')
                track_info = last_race.get('track', {})
                track_name = track_info.get('track_name', 'Unknown Track')
                config_name = track_info.get('config_name', '')
                
                # Full track name with config
                full_track_name = f"{track_name}"
                if config_name and config_name != track_name:
                    full_track_name += f" - {config_name}"
                
                # Position data (use correct field names from API)
                start_position = last_race.get('start_position', 'N/A')
                finish_position = last_race.get('finish_position', 'N/A')
                
                # Calculate position change
                position_change = ""
                if isinstance(start_position, int) and isinstance(finish_position, int):
                    change = start_position - finish_position
                    if change > 0:
                        position_change = f" ↑ (+{change})"
                    elif change < 0:
                        position_change = f" ↓ ({change})"
                    else:
                        position_change = " →"
                
                # Lap data (use correct field names)
                laps_complete = last_race.get('laps', 0)
                laps_lead = last_race.get('laps_led', 0)
                
                # Rating changes
                old_irating = last_race.get('oldi_rating', 0)
                new_irating = last_race.get('newi_rating', 0)
                irating_change = new_irating - old_irating
                
                old_safety_rating = last_race.get('old_sub_level', 0) / 100.0
                new_safety_rating = last_race.get('new_sub_level', 0) / 100.0
                safety_rating_change = new_safety_rating - old_safety_rating
                
                # Incidents
                incidents = last_race.get('incidents', 0)
                
                # Session time
                session_start = last_race.get('session_start_time')
                if session_start:
                    race_date = datetime.fromisoformat(session_start.replace('Z', '+00:00'))
                    race_date_str = race_date.strftime('%b %d, %Y at %I:%M %p')
                else:
                    race_date_str = 'Unknown'
                
                # Create embed
                embed = discord.Embed(
                    title=f"🏁 Last Race Results - {driver_name}",
                    color=0x00ff00 if irating_change >= 0 else 0xff4444,
                    timestamp=datetime.now()
                )
                
                embed.add_field(name="🏆 Series", value=series_name, inline=False)
                embed.add_field(name="🛣️ Track", value=full_track_name, inline=False)
                
                # Positions
                embed.add_field(
                    name="📍 Grid Position", 
                    value=f"P{start_position}" if isinstance(start_position, int) else str(start_position), 
                    inline=True
                )
                embed.add_field(
                    name="🏁 Finish Position", 
                    value=f"P{finish_position}{position_change}" if isinstance(finish_position, int) else str(finish_position), 
                    inline=True
                )
                embed.add_field(name="🔢 Incidents", value=str(incidents), inline=True)
                
                # Lap times
                embed.add_field(
                    name="⏱️ Average Lap", 
                    value=format_lap_time(avg_lap_time) if avg_lap_time > 0 else "N/A", 
                    inline=True
                )
                embed.add_field(
                    name="🚀 Best Lap", 
                    value=format_lap_time(best_lap_time) if best_lap_time > 0 else "N/A", 
                    inline=True
                )
                embed.add_field(
                    name="🔄 Laps",
                    value=f"{laps_complete} ({laps_lead} led)" if laps_lead > 0 else str(laps_complete),
                    inline=True
                )
                
                # Ratings
                irating_emoji = "📈" if irating_change >= 0 else "📉"
                safety_emoji = "📈" if safety_rating_change >= 0 else "📉"
                
                embed.add_field(
                    name=f"{irating_emoji} iRating",
                    value=f"{old_irating} → {new_irating} ({irating_change:+d})",
                    inline=True
                )
                embed.add_field(
                    name=f"{safety_emoji} Safety Rating",
                    value=f"{old_safety_rating:.2f} → {new_safety_rating:.2f} ({safety_rating_change:+.2f})",
                    inline=True
                )
                
                embed.set_footer(text=f"Race Date: {race_date_str}")
                
                await message.channel.send(embed=embed)
                
        except Exception as e:
            print(f"Error handling lastrace command: {e}")
            import traceback
            traceback.print_exc()
            await message.channel.send(f"❌ Error fetching race data: {str(e)}")
    
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
                
                for race in races[:10]:
                    track_name = race.get('track', {}).get('track_name', 'Unknown Track')
                    car_name = race.get('series_name', f"Series {race.get('series_id', 'Unknown')}")
                    
                    # Check both qualifying AND race best lap times
                    qualifying_time = race.get('qualifying_time', 0)
                    race_best_lap = race.get('best_lap_time', 0)
                    
                    # Convert from centiseconds if needed
                    if qualifying_time > 10000:
                        qualifying_time = qualifying_time / 10000.0
                    if race_best_lap > 10000:
                        race_best_lap = race_best_lap / 10000.0
                    
                    # Collect all valid lap times
                    lap_times_to_check = []
                    if qualifying_time > 0:
                        lap_times_to_check.append(('Qualifying', qualifying_time))
                    if race_best_lap > 0:
                        lap_times_to_check.append(('Race', race_best_lap))
                    
                    if not lap_times_to_check:
                        continue
                    
                    # Check each lap type
                    for lap_type, lap_time in lap_times_to_check:
                        record_key = f"{track_name}_{car_name}"
                        
                        is_new = False
                        prev_holder = None
                        prev_time = None
                        
                        if record_key not in current_records:
                            is_new = True
                            print(f"  ✓ First record: {track_name} / {car_name} ({lap_type}) - {format_lap_time(lap_time)}")
                        elif lap_time < current_records[record_key]['time']:
                            is_new = True
                            prev_holder = current_records[record_key]['driver']
                            prev_time = current_records[record_key]['time']
                            print(f"  ✓ New record ({lap_type}): beat previous by {prev_time - lap_time:.3f}s")
                        
                        if is_new:
                            current_records[record_key] = {
                                'time': lap_time,
                                'driver': driver_name,
                                'customer_id': customer_id,
                                'date': datetime.now().isoformat(),
                                'type': lap_type
                            }
                            
                            # Post to Discord
                            embed = discord.Embed(
                                title="🏁 NEW SERVER RECORD! 🏁",
                                description=f"**{driver_name}** just set a blistering lap in **{lap_type}**!",
                                color=0xFF1493,
                                timestamp=datetime.now()
                            )
                            
                            embed.add_field(name="🛣️ Track", value=track_name, inline=True)
                            embed.add_field(name="🏎️ Series", value=car_name, inline=True)
                            embed.add_field(name="⏱️ Time", value=format_lap_time(lap_time), inline=True)
                            embed.add_field(name="📋 Session", value=lap_type, inline=True)
                            
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
                            
                            # Only keep the fastest time for this track/car combo
                            break
                
                save_records(current_records)
                
            except Exception as e:
                print(f"✗ Error for customer {customer_id}: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    client = RecordBot()
    client.run(DISCORD_TOKEN)