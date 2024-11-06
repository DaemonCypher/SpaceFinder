import discord
from discord.ext import commands
import sqlite3
from datetime import datetime, timedelta
import asyncio
from discord import Embed
import json
import geopy.distance
from geopy.geocoders import Nominatim

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

# Constants
EVENT_TYPES = ['social', 'academic', 'sports', 'gaming', 'study', 'food', 'other']
EVENT_SIZES = ['small (1-5)', 'medium (6-15)', 'large (16+)']
CODE_OF_CONDUCT = """
**Community Code of Conduct**

1. Respect & Inclusion
   • Treat all participants with respect and dignity
   • No discrimination or harassment of any kind
   • Be mindful of others' boundaries and comfort levels

2. Participation Guidelines
   • You have complete agency over your participation
   • Feel free to leave any event at any time
   • No pressure to participate beyond your comfort level

3. Safety & Privacy
   • Respect others' privacy and personal information
   • Report any concerning behavior to moderators
   • Follow safety guidelines for in-person meetings

4. Communication
   • Keep conversations respectful and constructive
   • Be open to different viewpoints and experiences
   • Use appropriate language and tone

5. Event Etiquette
   • Arrive on time for events you've committed to
   • Notify organizers if you can't attend
   • Follow event-specific guidelines

Remember: Everyone deserves to feel safe and welcome in our community.
"""

def parse_duration(duration_str):
    """Parse simple duration strings into a standardized format"""
    duration_str = duration_str.lower().strip()
    
    # Handle simple "X hours" format
    if "hour" in duration_str:
        try:
            hours = int(''.join(filter(str.isdigit, duration_str)))
            return f"{hours} hour{'s' if hours != 1 else ''}"
        except ValueError:
            return None
            
    # Handle simple "X minutes" format
    elif "minute" in duration_str or "min" in duration_str:
        try:
            minutes = int(''.join(filter(str.isdigit, duration_str)))
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        except ValueError:
            return None
    
    return duration_str  # Return as-is if no specific format is matched

def setup_database():
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    # Events table without geolocation fields
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            creator_id TEXT,
            creator_name TEXT,
            description TEXT,
            event_type TEXT,
            event_size TEXT,
            location TEXT,
            event_time TIMESTAMP,
            duration TEXT,
            created_at TIMESTAMP
        )
    ''')
    
    # Event interests table with UNIQUE constraint
    c.execute('''
        CREATE TABLE IF NOT EXISTS event_interests (
            interest_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER,
            user_id TEXT,
            username TEXT,
            interested_in_connection BOOLEAN,
            FOREIGN KEY (event_id) REFERENCES events (event_id),
            UNIQUE(event_id, user_id)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id TEXT PRIMARY KEY,
            username TEXT,
            preferred_types TEXT,
            preferred_sizes TEXT,
            notification_enabled BOOLEAN
        )
    ''')
    
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    setup_database()

class EventView(discord.ui.View):
    def __init__(self, event_id):
        super().__init__(timeout=None)
        self.event_id = event_id

    @discord.ui.button(label="I'm Interested!", style=discord.ButtonStyle.primary)
    async def interested_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await register_interest(interaction, self.event_id)

    @discord.ui.button(label="Connect with Others", style=discord.ButtonStyle.green)
    async def connect_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await toggle_connection_interest(interaction, self.event_id)

async def register_interest(interaction, event_id):
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    try:
        # Check if user is already interested
        c.execute('''
            SELECT * FROM event_interests 
            WHERE event_id = ? AND user_id = ?
        ''', (event_id, str(interaction.user.id)))
        
        existing_interest = c.fetchone()
        
        if existing_interest:
            await interaction.response.send_message("You're already registered for this event!", ephemeral=True)
            return
        
        # Register new interest
        c.execute('''
            INSERT INTO event_interests (event_id, user_id, username, interested_in_connection)
            VALUES (?, ?, ?, FALSE)
        ''', (event_id, str(interaction.user.id), interaction.user.name))
        
        conn.commit()
        await interaction.response.send_message("You're registered as interested in this event!", ephemeral=True)
        
    except sqlite3.IntegrityError:
        await interaction.response.send_message("You're already registered for this event!", ephemeral=True)
    finally:
        conn.close()

async def toggle_connection_interest(interaction, event_id):
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    c.execute('''
        UPDATE event_interests 
        SET interested_in_connection = NOT interested_in_connection
        WHERE event_id = ? AND user_id = ?
    ''', (event_id, str(interaction.user.id)))
    
    conn.commit()
    conn.close()
    
    await interaction.response.send_message("Your connection preference has been updated!", ephemeral=True)

def create_event_embed(description, event_type, event_size, location, event_time, duration, creator_name, distance=None):
    embed = Embed(title="📅 Event Details", color=0x00ff00)
    embed.add_field(name="Description", value=description, inline=False)
    embed.add_field(name="Type", value=event_type.title(), inline=True)
    embed.add_field(name="Size", value=event_size.title(), inline=True)
    embed.add_field(name="Location", value=location, inline=True)
    # Convert time format to use semicolon
    formatted_time = event_time.strftime("%Y-%m-%d %H:%M").replace(':', ';')
    embed.add_field(name="Date & Time", value=formatted_time, inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)
    if distance is not None:
        embed.add_field(name="Distance", value=f"{distance:.1f} miles", inline=True)
    embed.add_field(name="Organized by", value=creator_name, inline=False)
    return embed

@bot.command(name='setpreferences')
async def set_preferences(ctx):
    """Set your event preferences"""
    try:
        # Get preferred event types
        types_msg = "Select your preferred event types (comma-separated):\n"
        types_msg += ", ".join(EVENT_TYPES)
        await ctx.send(types_msg)
        types_response = await bot.wait_for('message', timeout=30.0,
                                          check=lambda m: m.author == ctx.author)
        preferred_types = [t.strip() for t in types_response.content.lower().split(',')]
        
        # Validate event types
        invalid_types = [t for t in preferred_types if t not in EVENT_TYPES]
        if invalid_types:
            await ctx.send(f"Invalid event type(s): {', '.join(invalid_types)}\nPlease try again with valid types.")
            return
        
        # Get preferred event sizes
        sizes_msg = "Select your preferred event sizes (comma-separated):\n"
        sizes_msg += ", ".join(EVENT_SIZES)
        await ctx.send(sizes_msg)
        sizes_response = await bot.wait_for('message', timeout=30.0,
                                          check=lambda m: m.author == ctx.author)
        
        # Simple size translation
        preferred_sizes = []
        for s in sizes_response.content.lower().split(','):
            size = s.strip()
            if size == 'small':
                preferred_sizes.append('small (1-5)')
            elif size == 'medium':
                preferred_sizes.append('medium (6-15)')
            elif size == 'large':
                preferred_sizes.append('large (16+)')
            elif size in EVENT_SIZES:  # Already in full format
                preferred_sizes.append(size)
            else:
                await ctx.send(f"Invalid event size(s): {size}\nPlease try again with valid sizes.")
                return
        
        # Save preferences
        conn = sqlite3.connect('discord_bot.db')
        c = conn.cursor()
        
        c.execute('''
            INSERT OR REPLACE INTO user_preferences 
            (user_id, username, preferred_types, preferred_sizes, notification_enabled)
            VALUES (?, ?, ?, ?, TRUE)
        ''', (
            str(ctx.author.id),
            ctx.author.name,
            json.dumps(preferred_types),
            json.dumps(preferred_sizes)
        ))
        
        conn.commit()
        conn.close()
        
        # Create and send confirmation embed
        embed = Embed(title="✅ Preferences Saved", color=0x00ff00)
        embed.add_field(name="Preferred Event Types", value=", ".join(preferred_types), inline=False)
        embed.add_field(name="Preferred Event Sizes", value=", ".join(preferred_sizes), inline=False)
        
        await ctx.send("Preferences saved successfully!", embed=embed)
        
    except asyncio.TimeoutError:
        await ctx.send("Timeout: Preference setting cancelled.")
    except Exception as e:
        await ctx.send(f"An error occurred while setting preferences: {str(e)}")

@bot.command(name='viewpreferences')
async def view_preferences(ctx):
    """View your current preferences"""
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    # Get user preferences
    c.execute('''
        SELECT preferred_types, preferred_sizes
        FROM user_preferences
        WHERE user_id = ?
    ''', (str(ctx.author.id),))
    
    prefs = c.fetchone()
    conn.close()
    
    if not prefs:
        await ctx.send("You haven't set any preferences yet. Use `!setpreferences` to set them.")
        return
    
    # Parse preferences
    preferred_types = json.loads(prefs[0])
    preferred_sizes = json.loads(prefs[1])
    
    # Create embed
    embed = Embed(title="🎯 Your Preferences", color=0x00ff00)
    embed.add_field(
        name="Preferred Event Types",
        value=", ".join(preferred_types) if preferred_types else "No preferences set",
        inline=False
    )
    embed.add_field(
        name="Preferred Event Sizes",
        value=", ".join(preferred_sizes) if preferred_sizes else "No preferences set",
        inline=False
    )
    
    # Add instructions for updating
    embed.set_footer(text="Use !setpreferences to update your preferences")
    
    await ctx.send(embed=embed)

@bot.command(name='clearpreferences')
async def clear_preferences(ctx):
    """Clear all your preferences"""
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    c.execute('DELETE FROM user_preferences WHERE user_id = ?', (str(ctx.author.id),))
    
    conn.commit()
    conn.close()
    
    await ctx.send("✅ Your preferences have been cleared. Use `!setpreferences` to set new ones.")

@bot.command(name='schedule')
async def schedule_event(ctx):
    """Schedule a new event"""
    try:
        # Get event description
        await ctx.send("Please provide the event description:")
        description_msg = await bot.wait_for('message', timeout=30.0,
                                           check=lambda m: m.author == ctx.author)
        
        # Get event type
        types_msg = "Select the event type:\n"
        types_msg += ", ".join(EVENT_TYPES)
        await ctx.send(types_msg)
        type_msg = await bot.wait_for('message', timeout=30.0,
                                     check=lambda m: m.author == ctx.author)
        
        # Get event size
        sizes_msg = "Select the event size:\n"
        sizes_msg += ", ".join(EVENT_SIZES)
        await ctx.send(sizes_msg)
        size_msg = await bot.wait_for('message', timeout=30.0,
                                     check=lambda m: m.author == ctx.author)
        
        # Get location as simple string
        await ctx.send("Please provide the event location:")
        location_msg = await bot.wait_for('message', timeout=30.0,
                                         check=lambda m: m.author == ctx.author)
        
        # Get date and time with smart parsing
        await ctx.send("Please provide the event time (format: HH;MM for today, or YYYY-MM-DD HH;MM for specific date):")
        time_msg = await bot.wait_for('message', timeout=30.0,
                                     check=lambda m: m.author == ctx.author)
        
        # Get duration
        await ctx.send("Please provide the event duration (e.g., '2 hours' or '30 minutes'):")
        duration_msg = await bot.wait_for('message', timeout=30.0,
                                         check=lambda m: m.author == ctx.author)
        
        # Parse and validate duration
        parsed_duration = parse_duration(duration_msg.content)
        if not parsed_duration:
            await ctx.send('Invalid duration format. Please use formats like "2 hours" or "30 minutes".')
            return
        
        try:
            # Smart time parsing
            time_input = time_msg.content.strip()
            
            # Check if input contains only time
            if ':' in time_input or ';' in time_input:
                if ' ' not in time_input and len(time_input.split(';' if ';' in time_input else ':')) == 2:
                    # Time only provided - use today's date
                    today = datetime.now().date()
                    time_input = f"{today} {time_input}"
            
            # Convert semicolon to colon for datetime parsing
            formatted_time = time_input.replace(';', ':')
            
            try:
                # Try parsing with full date-time format
                event_time = datetime.strptime(formatted_time, '%Y-%m-%d %H:%M')
            except ValueError:
                try:
                    # Try parsing with just date and time
                    event_time = datetime.strptime(formatted_time, '%Y-%m-%d %H:%M')
                except ValueError:
                    # Try parsing with today's date and time
                    try:
                        time_part = datetime.strptime(formatted_time, '%H:%M').time()
                        event_time = datetime.combine(datetime.now().date(), time_part)
                    except ValueError:
                        await ctx.send('Invalid time format. Please use HH;MM for today, or YYYY-MM-DD HH;MM for specific date.')
                        return
            
            # Check if event time is in the past
            if event_time < datetime.now():
                # If it's today's date and time is in the past, try tomorrow
                if event_time.date() == datetime.now().date():
                    event_time = event_time + timedelta(days=1)
                    await ctx.send(f"Note: Since the time is in the past, the event has been scheduled for tomorrow ({event_time.strftime('%Y-%m-%d')})")
                else:
                    await ctx.send('Cannot schedule events in the past!')
                    return
            
            # Save event
            conn = sqlite3.connect('discord_bot.db')
            c = conn.cursor()
            
            c.execute('''
                INSERT INTO events 
                (creator_id, creator_name, description, event_type, event_size, location, 
                event_time, duration, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(ctx.author.id),
                ctx.author.name,
                description_msg.content,
                type_msg.content.lower(),
                size_msg.content.lower(),
                location_msg.content,
                event_time,
                parsed_duration,
                datetime.now()
            ))
            
            event_id = c.lastrowid
            
            # Send confirmation
            embed = create_event_embed(
                description_msg.content,
                type_msg.content,
                size_msg.content,
                location_msg.content,
                event_time,
                parsed_duration,
                ctx.author.name
            )
            await ctx.send("Event scheduled successfully! ✅", embed=embed, view=EventView(event_id))
            
            conn.commit()
            conn.close()
            
        except ValueError as e:
            await ctx.send('Invalid time format. Please use HH;MM for today, or YYYY-MM-DD HH;MM for specific date.')
            
    except asyncio.TimeoutError:
        await ctx.send('Timeout: Event scheduling cancelled.')

# Modified create_event_embed function without distance
def create_event_embed(description, event_type, event_size, location, event_time, duration, creator_name):
    embed = Embed(title="📅 Event Details", color=0x00ff00)
    embed.add_field(name="Description", value=description, inline=False)
    embed.add_field(name="Type", value=event_type.title(), inline=True)
    embed.add_field(name="Size", value=event_size.title(), inline=True)
    embed.add_field(name="Location", value=location, inline=True)
    # Convert time format to use semicolon
    formatted_time = event_time.strftime("%Y-%m-%d %H:%M").replace(':', ';')
    embed.add_field(name="Date & Time", value=formatted_time, inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Organized by", value=creator_name, inline=False)
    return embed


@bot.command(name='events')
async def list_events(ctx, filter_type=None, *, filter_value=None):
    """View events with advanced filtering"""
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    query = '''
        SELECT e.event_id, e.creator_name, e.description, e.event_type, e.event_size, e.location,
               e.event_time, e.duration,
               COUNT(DISTINCT i.user_id) as interested_count
        FROM events e
        LEFT JOIN event_interests i ON e.event_id = i.event_id
        WHERE datetime(e.event_time) >= datetime('now', 'localtime')
    '''
    params = []
    
    if filter_type and filter_value:
        if filter_type.lower() == 'type':
            query += ' AND LOWER(e.event_type) = LOWER(?)'
            params.append(filter_value)
        elif filter_type.lower() == 'size':
            query += ' AND LOWER(e.event_size) = LOWER(?)'
            params.append(filter_value)
        elif filter_type.lower() == 'date':
            try:
                filter_date = datetime.strptime(filter_value, '%Y-%m-%d')
                query += ' AND DATE(e.event_time) = DATE(?)'
                params.append(filter_value)
            except ValueError:
                await ctx.send('Invalid date format. Please use YYYY-MM-DD')
                conn.close()
                return
    
    query += ' GROUP BY e.event_id ORDER BY e.event_time ASC'
    
    c.execute(query, params)
    events = c.fetchall()
    
    if not events:
        await ctx.send("No upcoming events found matching your criteria.")
        conn.close()
        return
    
    # Create embeddings for events
    embeds = []
    for event in events:
        (event_id, creator_name, description, event_type, event_size, location, 
         event_time, duration, interested_count) = event
        
        embed = Embed(title="📅 Event Details", color=0x00ff00)
        embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Type", value=event_type.title(), inline=True)
        embed.add_field(name="Size", value=event_size.title(), inline=True)
        embed.add_field(name="Location", value=location, inline=True)
        
        # Parse the event_time string into a datetime object first
        event_datetime = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S')
        formatted_time = event_datetime.strftime('%Y-%m-%d %H:%M').replace(':', ';')
        
        embed.add_field(name="Date & Time", value=formatted_time, inline=True)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Interested", value=f"{interested_count} people", inline=True)
        embed.add_field(name="Organized by", value=creator_name, inline=False)
        embed.set_footer(text=f"Event ID: {event_id}")
        
        embeds.append((embed, event_id))
    
    # Display events with pagination
    current_page = 0
    total_pages = len(embeds)
    
    while True:
        embed, event_id = embeds[current_page]
        embed.set_footer(text=f"Event ID: {event_id} | Page {current_page + 1} of {total_pages}")
        
        message = await ctx.send(
            embed=embed,
            view=EventView(event_id)
        )
        
        if total_pages > 1:
            await message.add_reaction('◀️')
            await message.add_reaction('▶️')
            
            try:
                reaction, user = await bot.wait_for(
                    'reaction_add',
                    timeout=30.0,
                    check=lambda r, u: u == ctx.author and str(r.emoji) in ['◀️', '▶️']
                )
                
                await message.delete()
                
                if str(reaction.emoji) == '◀️':
                    current_page = (current_page - 1) % total_pages
                elif str(reaction.emoji) == '▶️':
                    current_page = (current_page + 1) % total_pages
                    
            except asyncio.TimeoutError:
                break
        else:
            break
    
    conn.close()
    
@bot.command(name='interested')
async def view_interested_users(ctx, event_id: int = None):
    """View users interested in an event"""
    if not event_id:
        await ctx.send("Please provide an event ID. Example: !interested 123")
        return
        
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    # Get event details and count of interested users
    c.execute('''
        SELECT e.description, e.event_time, e.location, e.duration, e.creator_name,
               COUNT(i.user_id) as interested_count
        FROM events e
        LEFT JOIN event_interests i ON e.event_id = i.event_id
        WHERE e.event_id = ?
        GROUP BY e.event_id
    ''', (event_id,))
    
    event = c.fetchone()
    if not event:
        await ctx.send("Event not found.")
        conn.close()
        return
    
    description, event_time, location, duration, creator_name, interested_count = event
    
    # Get interested users with their preferences
    c.execute('''
        SELECT username, interested_in_connection
        FROM event_interests
        WHERE event_id = ?
        ORDER BY username
    ''', (event_id,))
    
    interested_users = c.fetchall()
    conn.close()
    
    # Create embed
    embed = Embed(title="🙋 Event Participants", color=0x00ff00)
    
    # Add event details
    formatted_time = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M').replace(':', ';')
    
    embed.add_field(name="Event", value=description, inline=False)
    embed.add_field(name="Time", value=formatted_time, inline=True)
    embed.add_field(name="Location", value=location, inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Organized by", value=creator_name, inline=True)
    
    # Separate users by their connection preference
    general_interest = []
    want_to_connect = []
    
    for username, wants_connection in interested_users:
        if wants_connection:
            want_to_connect.append(username)
        else:
            general_interest.append(username)
    
    if general_interest:
        embed.add_field(
            name="🎯 Interested in Attending",
            value="\n".join(general_interest) if general_interest else "None",
            inline=False
        )
    
    if want_to_connect:
        embed.add_field(
            name="🤝 Want to Connect",
            value="\n".join(want_to_connect) if want_to_connect else "None",
            inline=False
        )
    
    embed.set_footer(text=f"Total Interested: {interested_count}")
    
    await ctx.send(embed=embed)

@bot.command(name='myevents')
async def view_my_interests(ctx):
    """View all events you're interested in"""
    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()
    
    # Get all events the user is interested in
    c.execute('''
        SELECT e.event_id, e.description, e.event_time, e.location, 
               e.duration, e.creator_name, i.interested_in_connection,
               (SELECT COUNT(DISTINCT user_id) FROM event_interests WHERE event_id = e.event_id) as total_interested
        FROM events e
        JOIN event_interests i ON e.event_id = i.event_id
        WHERE i.user_id = ? AND datetime(e.event_time) >= datetime('now', 'localtime')
        ORDER BY e.event_time ASC
    ''', (str(ctx.author.id),))
    
    interested_events = c.fetchall()
    conn.close()
    
    if not interested_events:
        await ctx.send("You haven't expressed interest in any upcoming events.")
        return
    
    # Create embeds for events
    embeds = []
    for event in interested_events:
        event_id, description, event_time, location, duration, creator, wants_connection, total_interested = event
        
        embed = Embed(title="📅 Event Details", color=0x00ff00)
        embed.add_field(name="Description", value=description, inline=False)
        
        # Parse the event_time string into a datetime object first
        event_datetime = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S')
        formatted_time = event_datetime.strftime('%Y-%m-%d %H:%M').replace(':', ';')
        
        embed.add_field(name="Date & Time", value=formatted_time, inline=True)
        embed.add_field(name="Location", value=location, inline=True)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Organized by", value=creator, inline=True)
        embed.add_field(name="Total Interested", value=f"{total_interested} people", inline=True)
        embed.add_field(
            name="Your Status",
            value="🤝 Interested in connecting" if wants_connection else "🎯 Interested in attending",
            inline=True
        )
        embed.set_footer(text=f"Event ID: {event_id}")
        embeds.append(embed)
    
    # Display events with pagination
    current_page = 0
    total_pages = len(embeds)
    
    while True:
        embed = embeds[current_page]
        embed.set_footer(text=f"Event ID: {interested_events[current_page][0]} | Page {current_page + 1} of {total_pages}")
        
        message = await ctx.send(embed=embed)
        
        if total_pages > 1:
            await message.add_reaction('◀️')
            await message.add_reaction('▶️')
            
            try:
                reaction, user = await bot.wait_for(
                    'reaction_add',
                    timeout=30.0,
                    check=lambda r, u: u == ctx.author and str(r.emoji) in ['◀️', '▶️']
                )
                
                await message.delete()
                
                if str(reaction.emoji) == '◀️':
                    current_page = (current_page - 1) % total_pages
                elif str(reaction.emoji) == '▶️':
                    current_page = (current_page + 1) % total_pages
                    
            except asyncio.TimeoutError:
                break
        else:
            break

@bot.command(name='cancelinterest')
async def cancel_interest(ctx, event_id: int = None):
    """Cancel your interest in an event"""
    if not event_id:
        await ctx.send("Please provide an event ID. Example: `!cancelinterest 123`")
        return

    conn = sqlite3.connect('discord_bot.db')
    c = conn.cursor()

    # Check if event exists and get event details
    c.execute('''
        SELECT description, event_time 
        FROM events 
        WHERE event_id = ?
    ''', (event_id,))
    event = c.fetchone()

    if not event:
        await ctx.send("❌ Event not found. Please check the event ID.")
        conn.close()
        return

    # Check if user is interested in this event
    c.execute('''
        SELECT * FROM event_interests
        WHERE event_id = ? AND user_id = ?
    ''', (event_id, str(ctx.author.id)))

    if not c.fetchone():
        await ctx.send("❌ You are not registered for this event.")
        conn.close()
        return

    # Remove interest
    c.execute('''
        DELETE FROM event_interests
        WHERE event_id = ? AND user_id = ?
    ''', (event_id, str(ctx.author.id)))

    conn.commit()
    conn.close()

    # Create confirmation embed
    embed = Embed(title="Interest Cancelled", color=0xff0000)
    embed.add_field(name="Event", value=event[0], inline=False)
    event_time = datetime.strptime(event[1], '%Y-%m-%d %H:%M:%S')
    formatted_time = event_time.strftime('%Y-%m-%d %H:%M').replace(':', ';')
    embed.add_field(name="Date & Time", value=formatted_time, inline=True)

    await ctx.send("✅ Successfully cancelled your interest in the event.", embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Show help information about the bot"""
    embed = Embed(title="📚 Event Bot Help Guide", color=0x00ff00)

    # Event Commands
    event_commands = """
`!schedule` - Create a new event
`!events` - View all upcoming events
`!events type social` - View events filtered by type
`!events size small` - View events filtered by size
`!events date 2024-11-06` - View events for a specific date
`!interested <event_id>` - View who's interested in an event
`!cancelinterest <event_id>` - Cancel your interest in an event
"""
    embed.add_field(name="🎯 Event Commands", value=event_commands.strip(), inline=False)

    # Preference Commands
    pref_commands = """
`!setpreferences` - Set your event preferences
`!viewpreferences` - View your current preferences
`!clearpreferences` - Clear all your preferences
"""
    embed.add_field(name="⚙️ Preference Commands", value=pref_commands.strip(), inline=False)

    # Event Types
    types_str = ", ".join(EVENT_TYPES)
    embed.add_field(name="📋 Available Event Types", value=types_str, inline=False)

    # Event Sizes
    sizes_str = """
`small (1-5)` - Small gatherings
`medium (6-15)` - Medium-sized events
`large (16+)` - Large events
"""
    embed.add_field(name="👥 Event Sizes", value=sizes_str.strip(), inline=False)

    # Examples
    examples = """
1. Create an event:
   `!schedule`

2. View events:
   `!events`
   `!events type gaming`

3. Set preferences:
   `!setpreferences`

4. View event participants:
   `!interested 123`
"""
    embed.add_field(name="📝 Examples", value=examples.strip(), inline=False)

    # Add Code of Conduct note
    coc_note = "For detailed community guidelines, please refer to our Code of Conduct."
    embed.set_footer(text=coc_note)

    await ctx.send(embed=embed)

@bot.command(name='code')
async def code_of_conduct(ctx):
    """Display the Code of Conduct"""
    embed = Embed(title="📜 Community Code of Conduct", color=0x00ff00)
    embed.description = CODE_OF_CONDUCT
    await ctx.send(embed=embed)
# Run the bot
if __name__ == "__main__":
    bot.run(TOKEN)