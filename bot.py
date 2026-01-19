import discord
from discord.ext import tasks
import requests
import json
from datetime import datetime, timedelta
import base64
import hashlib
import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

# Load environment variables
load_dotenv()

# Configuration - USE ENVIRONMENT VARIABLES FOR SECURITY
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('CHANNEL_ID', '1460000687206175011'))
IRACING_EMAIL = os.getenv('IRACING_EMAIL')
IRACING_PASSWORD = os.getenv('IRACING_PASSWORD')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
CUSTOMER_IDS = [int(id.strip()) for id in os.getenv('CUSTOMER_IDS', '1042800').split(',')]
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

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

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'✓ Logged in as {self.user}')
        print(f'✓ Monitoring channel: {CHANNEL_ID}')
        print(f'✓ Tracking {len(CUSTOMER_IDS)} driver(s)')
        
        # Initialize iRacing connection
        self.iracing = iRacingOAuth(IRACING_EMAIL, IRACING_PASSWORD, CLIENT_ID, CLIENT_SECRET)
        
        # Start the background task
        self.check_records.start()
        print('✓ Record checker started!')
    
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.user:
            return
        
        # Handle !records command
        if message.content.lower() == '!records':
            await self.show_records(message)
        
        # Handle !lastrace command
        elif message.content.lower().startswith('!lastrace'):
            await self.show_last_race(message)
        
        # Handle !trackguide command - NEW!
        elif message.content.lower() == '!trackguide':
            await self.show_track_guide(message)
    
    async def show_records(self, message):
        """Show all current records"""
        records = load_records()
        
        if not records:
            await message.channel.send("No records yet! Go set some laps! 🏁")
            return
        
        # Sort records by track name
        sorted_records = sorted(records.items(), key=lambda x: x[0])
        
        embed = discord.Embed(
            title="🏆 After Hours Server Records",
            description=f"Total records: {len(sorted_records)}",
            color=0x00ff00,
            timestamp=datetime.now()
        )
        
        for record_key, record in sorted_records:
            track_car = record_key.split('_', 1)
            track = track_car[0] if len(track_car) > 0 else "Unknown"
            car = track_car[1] if len(track_car) > 1 else "Unknown"
            
            lap_time = format_lap_time(record['time'])
            driver = record['driver']
            lap_type = record.get('type', 'Unknown')
            date = datetime.fromisoformat(record['date']).strftime('%Y-%m-%d')
            
            field_name = f"🛣️ {track}"
            field_value = f"**{car}**\n⏱️ {lap_time} - {driver}\n📋 {lap_type} • {date}"
            
            embed.add_field(name=field_name, value=field_value, inline=False)
        
        embed.set_footer(text="After Hours Racing League")
        await message.channel.send(embed=embed)
    
    async def show_last_race(self, message):
        """Show details of the last completed race"""
        try:
            # Try to get the customer ID from the message (optional feature)
            # For now, just use the first customer ID
            customer_id = CUSTOMER_IDS[0]
            
            await message.channel.send("🔍 Fetching last race data...")
            
            data = self.iracing.get_member_recent_races(customer_id)
            
            if not data:
                await message.channel.send("❌ Could not fetch race data. Please try again later.")
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
            
            # Extract race information
            driver_name = last_race.get('display_name', 'Unknown Driver')
            series_name = last_race.get('series_name', 'Unknown Series')
            
            # Track info
            track_info = last_race.get('track', {})
            track_name = track_info.get('track_name', 'Unknown Track')
            config_name = track_info.get('config_name', '')
            full_track_name = f"{track_name} - {config_name}" if config_name else track_name
            
            # Race results
            start_position = last_race.get('starting_position', 'N/A')
            finish_position = last_race.get('finish_position', 'N/A')
            incidents = last_race.get('incidents', 0)
            
            # Calculate position change
            if isinstance(start_position, int) and isinstance(finish_position, int):
                change = start_position - finish_position
                if change > 0:
                    position_change = f" (↑{change})"
                elif change < 0:
                    position_change = f" (↓{abs(change)})"
                else:
                    position_change = " (→)"
            else:
                position_change = ""
            
            # Lap times (convert from centiseconds if needed)
            avg_lap_time = last_race.get('average_lap', 0)
            best_lap_time = last_race.get('best_lap_time', 0)
            if avg_lap_time > 10000:
                avg_lap_time = avg_lap_time / 10000.0
            if best_lap_time > 10000:
                best_lap_time = best_lap_time / 10000.0
            
            # Lap count
            laps_complete = last_race.get('laps_complete', 0)
            laps_lead = last_race.get('laps_lead', 0)
            
            # Ratings
            old_irating = last_race.get('oldi_rating', 0)
            new_irating = last_race.get('newi_rating', 0)
            irating_change = new_irating - old_irating
            
            old_safety_rating = last_race.get('old_sub_level', 0) / 100.0
            new_safety_rating = last_race.get('new_sub_level', 0) / 100.0
            safety_rating_change = new_safety_rating - old_safety_rating
            
            # Race date
            session_start_time = last_race.get('session_start_time', '')
            if session_start_time:
                race_date = datetime.fromisoformat(session_start_time.replace('Z', '+00:00'))
                race_date_str = race_date.strftime('%B %d, %Y at %H:%M UTC')
            else:
                race_date_str = "Unknown"
            
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
                value=format_lap_time(avg_lap_time), 
                inline=True
            )
            embed.add_field(
                name="🚀 Best Lap", 
                value=format_lap_time(best_lap_time), 
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
    
    async def show_track_guide(self, message):
        """Search YouTube for a track guide based on last practice session"""
        try:
            # Check if YouTube API key is set
            if not YOUTUBE_API_KEY:
                await message.channel.send("❌ YouTube API key not configured. Please set YOUTUBE_API_KEY environment variable.")
                return
            
            # Get the last race to extract track and car info
            customer_id = CUSTOMER_IDS[0]
            
            await message.channel.send("🔍 Fetching last session info...")
            
            data = self.iracing.get_member_recent_races(customer_id)
            
            if not data:
                await message.channel.send("❌ Could not fetch session data. Please try again later.")
                return
            
            # Handle different response formats
            races = None
            if isinstance(data, dict):
                races = data.get('races')
            elif isinstance(data, list):
                races = data
            
            if not races or len(races) == 0:
                await message.channel.send("❌ No recent sessions found.")
                return
            
            # Get the most recent session
            last_session = races[0]
            
            # Extract track and car info
            track_info = last_session.get('track', {})
            track_name = track_info.get('track_name', 'Unknown Track')
            config_name = track_info.get('config_name', '')
            car_name = last_session.get('car_name', last_session.get('series_name', 'Unknown Car'))
            
            # Build search query
            search_parts = ['iracing', 'track guide', track_name]
            if config_name:
                search_parts.append(config_name)
            # Only add car name if it's not too long (avoid overly specific searches)
            if len(car_name) < 30:
                search_parts.append(car_name)
            
            search_query = ' '.join(search_parts)
            
            await message.channel.send(f"🔍 Searching YouTube for: `{search_query}`")
            
            # Search YouTube
            youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
            
            # Get date from one year ago
            one_year_ago = (datetime.now() - timedelta(days=365)).isoformat() + 'Z'
            
            search_response = youtube.search().list(
                q=search_query,
                part='id,snippet',
                maxResults=5,
                order='viewCount',
                type='video',
                publishedAfter=one_year_ago,
                relevanceLanguage='en'
            ).execute()
            
            if not search_response.get('items'):
                await message.channel.send(f"❌ No track guides found for **{track_name}** with **{car_name}**")
                return
            
            # Get the top video
            top_video = search_response['items'][0]
            video_id = top_video['id']['videoId']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            video_title = top_video['snippet']['title']
            channel = top_video['snippet']['channelTitle']
            
            # Get view count
            video_stats = youtube.videos().list(
                part='statistics',
                id=video_id
            ).execute()
            
            view_count = int(video_stats['items'][0]['statistics']['viewCount'])
            
            # Create embed
            full_track = f"{track_name} - {config_name}" if config_name else track_name
            
            embed = discord.Embed(
                title="🏁 Track Guide Found",
                description=f"**{full_track}**\n**Car:** {car_name}",
                color=discord.Color.blue()
            )
            embed.add_field(name="📺 Video", value=f"[{video_title}]({video_url})", inline=False)
            embed.add_field(name="👁️ Views", value=f"{view_count:,}", inline=True)
            embed.add_field(name="📢 Channel", value=channel, inline=True)
            
            embed.set_footer(text="Based on your last iRacing session")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error in trackguide command: {e}")
            import traceback
            traceback.print_exc()
            await message.channel.send(f"❌ Error searching YouTube: {str(e)}")
    
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
