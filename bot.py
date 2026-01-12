import discord
from discord.ext import tasks
import json
from datetime import datetime
from iracingdataapi.client import irDataClient

# Configuration
DISCORD_TOKEN = 'MTQ2MDM3MTMyODczMjIzMzk0MQ.GalAxr.QC2K2wHvjo4hSIqKGH6r21EqIR-6UxU0Be2SCs'
CHANNEL_ID = 1460000687206175011
IRACING_EMAIL = 'pjsmithdesigns@gmail.com'
IRACING_PASSWORD = 'Blackracing33!'
CUSTOMER_IDS = [1042800]

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

class RecordBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.iracing = None
    
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        try:
            # Initialize iRacing data client
            self.iracing = irDataClient(
                username=IRACING_EMAIL,
                password=IRACING_PASSWORD
            )
            print("iRacing authentication successful!")
            self.check_records.start()
        except Exception as e:
            print(f"Failed to initialize iRacing API: {e}")
            import traceback
            traceback.print_exc()
    
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
                
                # Get member's recent races
                member_recent = self.iracing.stats_member_recent_races(
                    cust_id=customer_id
                )
                
                if not member_recent or 'races' not in member_recent:
                    print(f"No race data for customer {customer_id}")
                    continue
                
                # Get member info for display name
                member_info = self.iracing.stats_member_info(cust_id=customer_id)
                driver_name = member_info.get('display_name', f'Driver {customer_id}')
                
                # Process each recent race
                for race in member_recent['races']:
                    track_name = race.get('track_name', 'Unknown Track')
                    car_name = race.get('car_name', 'Unknown Car')
                    best_lap = race.get('best_lap_time', 0)
                    
                    # Convert lap time from milliseconds to seconds if needed
                    if best_lap > 1000:
                        best_lap = best_lap / 10000.0
                    
                    if not all([track_name, car_name]) or best_lap <= 0:
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
                        print(f"First record for {track_name} in {car_name}: {best_lap}s")
                    elif best_lap < current_records[record_key]['time']:
                        # Beats existing record
                        is_new_record = True
                        previous_holder = current_records[record_key]['driver']
                        previous_time = current_records[record_key]['time']
                        print(f"New record! {driver_name} ({best_lap}s) beat {previous_holder} ({previous_time}s)")
                    
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
            await self.wait_for(2)
    
    async def wait_for(self, seconds):
        """Helper to wait asynchronously"""
        import asyncio
        await asyncio.sleep(seconds)

# Run the bot
if __name__ == "__main__":
    client = RecordBot()
    client.run(DISCORD_TOKEN)