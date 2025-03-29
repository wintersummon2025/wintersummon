#############################
#  WinterSummon Bot Code   #
#############################

import os
import discord
from discord.ext import commands, tasks
import random
import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from discord import app_commands, ui
from flask import Flask
import threading

##################################
# 1. Configuration & Setup       #
##################################

# === SENSITIVE TOKENS (Demo Only) ===
# In production, use environment variables or a .env file.
BOT_TOKEN = "MTM1NDgxNDAyNjY5MzA4MzI4OA.GIQZAS.F63fTH3l7dLrv9jJbpLRqdH521OorMeUDAVj10"

# === Discord Settings ===
SERVER_ID = 1341825447964577873
TICKETS_CHANNEL_ID = 1341825447964577880
LEVEL_CHANNEL_ID = 1353632560202256416
# (AI features removed)

# === Role IDs ===
JOIN_ROLE_ID = 1343099678392057878
BOOSTER_ROLE_ID = 1343235254827094120
LEVEL_ROLES = [
    (1000, 1342071099629899856),
    (3000, 1342073153391689789),
    (5000, 1342073623422304267),
    (8000, 1342073617005019146),
    (10000, 1342073619949293580),
    (25000, 1342073626429489182),
    (30000, 1342073631580098600),
    (60000, 1342074938722488472)
]

# === Shop Roles ===
SHOP_ROLES = [
    {"price": 3000,  "role_id": 1354671043146682398, "name": "Snow Guardian ❄️"},
    {"price": 7000,  "role_id": 1354672101180575795, "name": "Ice Noble 🧊"},
    {"price": 15000, "role_id": 1354672108508020818, "name": "Arctic King 👑"}
]

# === XP Random Ranges ===
XP_RANGE_NORMAL = (22, 33)
XP_RANGE_COOLDOWN = (3, 6)

# === Spam Control Thresholds ===
SPAM_3SEC_LIMIT = 5
SPAM_6SEC_LIMIT = 10
SPAM_TIMEOUT_HOURS = 12

# === Game GIFs ===
GAME_GIFS = {
    "win": "https://media.giphy.com/media/3o7aD2d7hy9ktXNDP2/giphy.gif",
    "lose": "https://media.giphy.com/media/l3q2EOu4nu1D8uJKU/giphy.gif",
    "slot_win": "https://media.giphy.com/media/3ohs4kI2X9r7O8ZtoA/giphy.gif"
}

# === Bot Initialization ===
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="w!", intents=intents, case_insensitive=True)

# Data stores for XP, snowcoins, and message timestamps
xp_data = {}              
xp_cooldown = {}          
messages_timestamps = {}  

##################################
# 2. Keep-Alive Flask App        #
##################################
app = Flask(__name__)

@app.route("/")
def home():
    return "WinterSummon Bot is running happily!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

##################################
# 3. Snowcoins & Stats Database #
##################################
conn = sqlite3.connect('winter_games.db', check_same_thread=False)
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    snowcoins INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    games_played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    losses INTEGER DEFAULT 0
)
''')
conn.commit()

def get_snowcoins(user_id: int):
    c.execute("SELECT snowcoins FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        return row[0]
    else:
        c.execute("INSERT INTO users (user_id, snowcoins) VALUES (?, 0)", (user_id,))
        conn.commit()
        return 0

def add_snowcoins(user_id: int, amount: int):
    c.execute("SELECT snowcoins FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    current = row[0] if row else 0
    new_total = current + amount
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    c.execute("UPDATE users SET snowcoins=? WHERE user_id=?", (new_total, user_id))
    conn.commit()
    return new_total

def update_stats(user_id: int, win: bool):
    c.execute("INSERT OR IGNORE INTO users (user_id, games_played, wins, losses) VALUES (?, 0, 0, 0)", (user_id,))
    c.execute("UPDATE users SET games_played = games_played + 1 WHERE user_id=?", (user_id,))
    if win:
        c.execute("UPDATE users SET wins = wins + 1 WHERE user_id=?", (user_id,))
    else:
        c.execute("UPDATE users SET losses = losses + 1 WHERE user_id=?", (user_id,))
    conn.commit()

def get_stats(user_id: int):
    c.execute("SELECT games_played, wins, losses FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        return {"games_played": row[0], "wins": row[1], "losses": row[2]}
    return {"games_played": 0, "wins": 0, "losses": 0}

##################################
# 4. XP Persistence              #
##################################
XP_DATA_FILE = "xp_data.json"

def load_xp():
    global xp_data
    if os.path.exists(XP_DATA_FILE):
        with open(XP_DATA_FILE, "r") as f:
            xp_data = json.load(f)
    else:
        xp_data = {}

def save_xp():
    with open(XP_DATA_FILE, "w") as f:
        json.dump(xp_data, f)

##################################
# 5. Bot Events                  #
##################################
@bot.event
async def on_ready():
    load_xp()
    print(f"Logged in as {bot.user}!")
    try:
        await bot.tree.sync()
        print("Slash commands synced successfully.")
    except Exception as e:
        print(f"Error syncing slash commands: {e}")
    spam_cleaner.start()

@bot.event
async def on_member_join(member):
    if member.guild.id != SERVER_ID:
        return
    try:
        role = member.guild.get_role(JOIN_ROLE_ID)
        if role:
            await member.add_roles(role)
        embed = discord.Embed(
            title="Welcome to Winter's Wonderland!",
            description="Stay frosty ❄️ and enjoy your magical journey!",
            color=0x00aaff,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1181457905820647484/1353765131699621969/welcome_bubbly_wiggle.gif")
        embed.set_footer(text="Joined on")
        await member.send(embed=embed)
    except Exception as e:
        print(f"Error sending welcome DM: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ticket System: Forward DMs to ticket channel
    if isinstance(message.channel, discord.DMChannel):
        server = bot.get_guild(SERVER_ID)
        tickets_channel = server.get_channel(TICKETS_CHANNEL_ID)
        if tickets_channel:
            embed = discord.Embed(
                title="New Ticket",
                description=f"From **{message.author}** (ID: {message.author.id}):\n{message.content}",
                color=0xff0000,
                timestamp=datetime.utcnow()
            )
            await tickets_channel.send(embed=embed)
        return

    # XP System: Award XP for messages
    user_id = str(message.author.id)
    now = datetime.utcnow()
    last_time = xp_cooldown.get(user_id)
    if last_time and (now - last_time).total_seconds() < 60:
        xp_gain = random.randint(XP_RANGE_COOLDOWN[0], XP_RANGE_COOLDOWN[1])
    else:
        xp_gain = random.randint(XP_RANGE_NORMAL[0], XP_RANGE_NORMAL[1])
        xp_cooldown[user_id] = now
    if user_id not in xp_data:
        xp_data[user_id] = {"xp": 0}
    xp_data[user_id]["xp"] += xp_gain
    save_xp()

    # Level-up Roles: Grant roles when XP thresholds are met
    current_xp = xp_data[user_id]["xp"]
    for threshold, role_id in LEVEL_ROLES:
        role = message.guild.get_role(role_id)
        if current_xp >= threshold and role and (role not in message.author.roles):
            await message.author.add_roles(role)
            level_channel = message.guild.get_channel(LEVEL_CHANNEL_ID)
            if level_channel:
                await level_channel.send(
                    f"Congratulations {message.author.mention}! You've reached **{threshold}** snowdrops 💠 and earned a new role!"
                )

    # Spam Control: Timeout if too many messages are sent too quickly
    now_ts = now.timestamp()
    messages_timestamps.setdefault(user_id, []).append(now_ts)
    messages_timestamps[user_id] = [t for t in messages_timestamps[user_id] if now_ts - t < 6]
    count_3sec = len([t for t in messages_timestamps[user_id] if now_ts - t < 3])
    count_6sec = len(messages_timestamps[user_id])
    if count_3sec > SPAM_3SEC_LIMIT or count_6sec > SPAM_6SEC_LIMIT:
        try:
            timeout_until = datetime.utcnow() + timedelta(hours=SPAM_TIMEOUT_HOURS)
            await message.author.edit(timeout=timeout_until, reason="Spam")
            await message.channel.send(f"{message.author.mention} has been timed out for spamming!")
        except Exception as e:
            print(f"Error applying timeout: {e}")

    await bot.process_commands(message)

##################################
# 6. Spam Cleaner Loop           #
##################################
@tasks.loop(seconds=10)
async def spam_cleaner():
    now_ts = datetime.utcnow().timestamp()
    for user_id in list(messages_timestamps.keys()):
        messages_timestamps[user_id] = [t for t in messages_timestamps[user_id] if now_ts - t < 6]
        if not messages_timestamps[user_id]:
            del messages_timestamps[user_id]

##################################
# 7. Quiz & Trivia Battle Setup  #
##################################
# Define 10 unique anime quiz questions 
unique_quiz_questions = [
{"question": "In Naruto, what is the name of the guy who never skips leg day?", "answer": "rock lee"},
{"question": "What is the name of the most overpowered bald guy in anime?", "answer": "saitama"},
{"question": "Which anime features a book that lets you play God with people's lives?", "answer": "death note"},
{"question": "In One Piece, what does Luffy want to become? (Hint: Not a chef!)", "answer": "pirate king"},
{"question": "What anime features a yellow octopus teaching kids how to kill him?", "answer": "assassination classroom"},
{"question": "Which anime character eats so much but never gains weight? (Hint: Orange jumpsuit)", "answer": "naruto"},
{"question": "What is the famous attack Goku always yells dramatically?", "answer": "kamehameha"},
{"question": "Which anime has a notebook that makes you say 'Oops, guess I'm dead'?", "answer": "death note"},
{"question": "In Attack on Titan, what’s the best way to avoid getting eaten?", "answer": "don't be in the anime"},
{"question": "What is the most famous redhead with anger issues in anime?", "answer": "shanks"},
{"question": "Which anime character can turn anything into gold… except their social skills?", "answer": "king midas"},
{"question": "Who is the best 'cool but lazy' teacher in Naruto?", "answer": "kakashi"},
{"question": "In JoJo's Bizarre Adventure, what does Dio say before wrecking everyone?", "answer": "za warudo"},
{"question": "What’s the most effective way to power up in Dragon Ball?", "answer": "scream louder"},
{"question": "Which anime has more episodes than your grandma's life stories?", "answer": "one piece"},
{"question": "Who is the most terrifying little psychic kid in anime?", "answer": "mob"},
{"question": "Which anime is basically 'Pokemon but deadly'?", "answer": "digimon"},
{"question": "What is the anime where people battle using their cooking skills?", "answer": "food wars"},
{"question": "What anime is about overthinking chess matches with death on the line?", "answer": "death note"},
{"question": "Which anime character uses a sword but never cuts anyone?", "answer": "kenshin"},
{"question": "In Bleach, what does Ichigo’s name actually mean?", "answer": "strawberry"},
{"question": "Which anime is just high school kids screaming about volleyball?", "answer": "haikyuu"},
{"question": "Who is the most fashionable villain in My Hero Academia?", "answer": "dabi"},
{"question": "What anime features a sad kid making bad deals with a demon butler?", "answer": "black butler"},
{"question": "Which anime character has a quirk that literally makes them explode?", "answer": "bakugo"},
{"question": "Who is the most relatable anime character because they just want to sleep?", "answer": "shikamaru"},
{"question": "Which anime protagonist has a talking cat that’s sassier than them?", "answer": "sailor moon"},
{"question": "What’s the best way to win a fight in Yu-Gi-Oh?", "answer": "believe in the heart of the cards"},
{"question": "Which anime character has a habit of dying and coming back a lot?", "answer": "krillin"},
{"question": "Who is the biggest ‘I hate my dad’ character in anime?", "answer": "todoroki"},
{"question": "Which anime features butlers who could probably destroy the world?", "answer": "black butler"},
{"question": "What anime is basically 'Cooking Mama but with actual battles'?", "answer": "food wars"},
{"question": "Who is the most dramatic 'I will never lose' character in anime?", "answer": "light yagami"},
{"question": "Which anime has a skeleton that laughs way too much?", "answer": "one piece"},
{"question": "In Hunter x Hunter, what is the most feared exam in the world?", "answer": "hunter exam"},
{"question": "Which anime has the most ridiculous hair physics?", "answer": "yu-gi-oh"},
{"question": "Which anime character drinks more milk than the average cow?", "answer": "edward elric"},
{"question": "What anime is just 'pretty boys playing basketball and acting dramatic'?", "answer": "kuroko no basket"},
{"question": "What’s the most used excuse for anime fights taking forever?", "answer": "powering up"},
{"question": "Which anime character gets cooler every time he loses an arm?", "answer": "shanks"},
{"question": "What anime character can take a punch but refuses to throw one?", "answer": "tanjiro"},
{"question": "Which anime villain always has the best outfits?", "answer": "hisoka"},
{"question": "Which anime girl has the strongest slap in history?", "answer": "nami"},
{"question": "Which anime features a guy who turns super strong by doing push-ups?", "answer": "one punch man"},
{"question": "Which anime character is the best at playing the 'my power is friendship' card?", "answer": "natsu"},
{"question": "What anime has a hero who literally needs a nap to win fights?", "answer": "attack on titan"},
{"question": "Which anime character has eaten more food than they should be able to?", "answer": "goku"},
{"question": "Which anime protagonist is the biggest overthinker?", "answer": "light yagami"},
{"question": "Which anime character screams his attacks before using them?", "answer": "goku"},
{"question": "Which anime villain has a laugh that sounds like pure evil?", "answer": "frieza"},
{"question": "What anime is about people fighting in their underwear but make it dramatic?", "answer": "kill la kill"},
{"question": "Who is the most unbothered anime protagonist ever?", "answer": "saitama"},
{"question": "Which anime character wears orange and causes chaos?", "answer": "naruto"},
{"question": "What anime has a guy who can’t swim but is a pirate?", "answer": "one piece"},
{"question": "Which anime features students trying not to die in a death game?", "answer": "danganronpa"},
{"question": "Which anime character spends the most time standing on a building looking cool?", "answer": "sasuke"},
{"question": "Which anime character is both terrifying and oddly attractive?", "answer": "hisoka"},
{"question": "Who is the most reckless, self-sacrificing, overpowered anime protagonist?", "answer": "eren yeager"},
{"question": "Which anime character says 'Believe it!' way too much?", "answer": "naruto"},
     {"question": "In Naruto, which character has mastered the ancient art of ‘talk no jutsu’?", "answer": "naruto"},
        {"question": "Which anime features a guy who gets stronger by doing 100 push-ups a day?", "answer": "one punch man"},
        {"question": "In Dragon Ball, what is the universal rule of power-ups? ", "answer": "scream louder"},
        {"question": "Which anime is basically ‘MasterChef but with dramatic foodgasms’?", "answer": "food wars"},
        {"question": "What’s the most effective strategy in Yu-Gi-Oh? ", "answer": "believe in the heart of the cards"},
        {"question": "In One Piece, what is Luffy’s life goal? (Hint: Not to find a good hat store)", "answer": "pirate king"},
        {"question": "Which anime has more episodes than your age?", "answer": "one piece"},
        {"question": "Who is the most famous overpowered bald dude in anime?", "answer": "saitama"},
        {"question": "Which anime is about sad teenagers fighting depression robots?", "answer": "neon genesis evangelion"},
        {"question": "In Attack on Titan, what is the best way to not get eaten?", "answer": "don't be in the anime"},
        {"question": "Which anime character needs GPS because he gets lost just walking straight?", "answer": "zoro"},
        {"question": "In Death Note, what’s the ultimate way to win an argument?", "answer": "write their name in the notebook"},
        {"question": "Who is the biggest ‘my dad left for milk and never came back’ character?", "answer": "gon"},
        {"question": "Which anime features a butler so OP, he makes James Bond look like an intern?", "answer": "black butler"},
        {"question": "What’s the most common injury in My Hero Academia?", "answer": "broken arms"},
        {"question": "Which anime character wears an orange jumpsuit and causes absolute chaos?", "answer": "naruto"},
        {"question": "Which anime makes volleyball look like a life-or-death situation?", "answer": "haikyuu"},
        {"question": "What anime features students in school uniforms fighting each other dramatically?", "answer": "kill la kill"},
        {"question": "In One Punch Man, how does Saitama defeat enemies?", "answer": "one punch"},
        {"question": "Which anime features a skeleton pirate who laughs at everything?", "answer": "one piece"},
        {"question": "Which anime is just ‘dramatic chess with gods’?", "answer": "death note"},
        {"question": "Who is the king of ‘power of friendship’ anime moments?", "answer": "natsu"},
        {"question": "What anime has a main character who dies more times than he should?", "answer": "re:zero"},
        {"question": "Which anime character has more hairstyles than you have socks?", "answer": "yugi"},
        {"question": "In My Hero Academia, which character has anger issues and needs therapy?", "answer": "bakugo"},
        {"question": "What’s the most famous ‘not today’ dodge in anime?", "answer": "ultra instinct"},
        {"question": "Which anime is about ‘hot people fighting demons with flashy swords’?", "answer": "demon slayer"},
        {"question": "Who is the biggest anime villain with the best hair game?", "answer": "hisoka"},
        {"question": "Which anime has the best dramatic running scenes?", "answer": "naruto"},
        {"question": "Which anime has a school where people use magic but still have homework?", "answer": "little witch academia"},
        {"question": "What anime has a coffee shop where the workers are, um, not human?", "answer": "tokyo ghoul"},
        {"question": "In Hunter x Hunter, what is the worst father-of-the-year award winner?", "answer": "ging freecss"},
        {"question": "Which anime is basically ‘Pokémon but with higher stakes’?", "answer": "digimon"},
        {"question": "What anime has characters yelling their attacks before using them?", "answer": "dragon ball"},
        {"question": "Who is the most iconic ‘cool teacher who actually does nothing’?", "answer": "kakashi"},
        {"question": "What anime is just ‘screaming until you win’?", "answer": "dragon ball"},
        {"question": "Which anime has the most extra way of eating a potato?", "answer": "attack on titan"},
        {"question": "What anime has the most ridiculous tournament arcs?", "answer": "dragon ball"},
        {"question": "Who is the most dramatic ‘I am the chosen one’ anime protagonist?", "answer": "light yagami"},
        {"question": "Which anime features a cat that talks like an old-timey grandma?", "answer": "sailor moon"},
        {"question": "What anime is just ‘cute girls doing murdery things’?", "answer": "madoka magica"},
        {"question": "Who is the most terrifyingly cute pink-haired girl in anime?", "answer": "yuno gasai"},
        {"question": "What anime is just ‘sassy butlers and sad rich kids’?", "answer": "black butler"},
        {"question": "Which anime character has an IQ of 200 but zero common sense?", "answer": "lelouch"},
        {"question": "What anime is basically ‘Harry Potter but everyone is on steroids’?", "answer": "fairy tail"},
        {"question": "Who is the most fashionable villain in anime history?", "answer": "dabi"},
        {"question": "What anime character has the strongest ‘can’t die’ energy?", "answer": "gojo satoru"},
        {"question": "What anime has a character who is too pretty to die?", "answer": "jujutsu kaisen"},
        {"question": "Which anime character is the master of the 'I'm too old for this' look?", "answer": "kakashi"},
        {"question": "Which anime is just ‘angry short guy fights for respect’?", "answer": "fullmetal alchemist"},
        {"question": "Which anime features a talking notebook that ruins lives?", "answer": "death note"},
        {"question": "Who is the ‘I could take over the world, but I just wanna vibe’ character?", "answer": "shikamaru"},
        {"question": "Which anime is about ‘pretty boys playing basketball and being dramatic’?", "answer": "kuroko no basket"},
        {"question": "Which anime character loves sleep more than life itself?", "answer": "shikamaru"},
        {"question": "What anime has the most ridiculous plot twists?", "answer": "code geass"},
        {"question": "Which anime villain is just ‘evil Michael Jackson’?", "answer": "muzan"},
        {"question": "Which anime character wears the most ridiculous outfits and somehow pulls them off?", "answer": "hisoka"},
        {"question": "Which anime has the longest ‘five minutes’ in history?", "answer": "dragon ball"},
        {"question": "What anime has the most dramatic betrayals?", "answer": "attack on titan"},
        {"question": "Which anime protagonist is the biggest overthinker ever?", "answer": "light yagami"},
        {"question": "Which anime is basically ‘chess but people die’?", "answer": "no game no life"},
        {"question": "Which anime has a main character who spends half the time sleeping?", "answer": "one punch man"},
    ]
# Multiply to reach 500 questions and shuffle (ensuring low probability of repeats)
ANIME_QUIZ_QUESTIONS = unique_quiz_questions * 120
random.shuffle(ANIME_QUIZ_QUESTIONS)

# Helper function for live countdown timer for quiz questions
async def start_countdown(message, duration, question_text, idx):
    remaining = duration
    while remaining > 0:
        try:
            await asyncio.sleep(1)
            remaining -= 1
            await message.edit(content=f"**Q{idx}:** {question_text}\nTime remaining: **{remaining}** seconds")
        except Exception:
            break

##################################
# 8. Commands (Prefix + Slash)   #
##################################

# --- XP/Level Command ---
@bot.command()
async def level(ctx):
    user_id = str(ctx.author.id)
    xp_amount = xp_data.get(user_id, {"xp": 0})["xp"]
    lvl = xp_amount // 1000
    booster = ctx.author.get_role(BOOSTER_ROLE_ID) is not None
    embed = discord.Embed(
        title=f"{ctx.author.name}'s Level Card",
        color=0xfb5ffc,
        timestamp=datetime.utcnow()
    )
    if ctx.author.avatar:
        embed.set_thumbnail(url=ctx.author.avatar.url)
    embed.add_field(name="XP (Snowdrops 💠)", value=f"{xp_amount}", inline=True)
    embed.add_field(name="Level", value=f"{lvl}", inline=True)
    embed.add_field(name="Server", value=ctx.guild.name, inline=False)
    embed.set_footer(text="Winter's Wonderland Server" if not booster else "Server Booster! ❄️")
    await ctx.send(embed=embed)

@bot.tree.command(name="level", description="Check your XP and level.")
async def slash_level(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    xp_amount = xp_data.get(user_id, {"xp": 0})["xp"]
    lvl = xp_amount // 1000
    booster = interaction.user.get_role(BOOSTER_ROLE_ID) is not None
    embed = discord.Embed(
        title=f"{interaction.user.name}'s Level Card",
        color=0xfb5ffc,
        timestamp=datetime.utcnow()
    )
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)
    embed.add_field(name="XP (Snowdrops 💠)", value=f"{xp_amount}", inline=True)
    embed.add_field(name="Level", value=f"{lvl}", inline=True)
    embed.add_field(name="Server", value=interaction.guild.name, inline=False)
    embed.set_footer(text="Winter's Wonderland Server" if not booster else "Server Booster! ❄️")
    await interaction.response.send_message(embed=embed)

# --- Snowcoins Wallet ---
@bot.command()
async def wallet(ctx):
    coins = get_snowcoins(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, you have **{coins}** 🍙 snowcoins in your wallet!")

@bot.tree.command(name="wallet", description="Check your snowcoins balance.")
async def slash_wallet(interaction: discord.Interaction):
    coins = get_snowcoins(interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have **{coins}** 🍙 snowcoins in your wallet!")

# --- Stats Command ---
@bot.command()
async def stats(ctx):
    stats_data = get_stats(ctx.author.id)
    embed = discord.Embed(title="Your Trivia Battle Stats", color=0x000000)
    if ctx.author.avatar:
        embed.set_thumbnail(url=ctx.author.avatar.url)
    embed.add_field(name="Games Played", value=str(stats_data["games_played"]), inline=True)
    embed.add_field(name="Wins", value=str(stats_data["wins"]), inline=True)
    embed.add_field(name="Losses", value=str(stats_data["losses"]), inline=True)
    embed.set_footer(text="Good luck in your battles!")
    await ctx.send(embed=embed)

# --- Shop & Buy Commands ---
@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="❄️ Winter Shop ❄️", color=0x00ffcc)
    lines = []
    for item in SHOP_ROLES:
        lines.append(f"**{item['name']}** - Costs **{item['price']}** 🍙")
    embed.description = "\n".join(lines)
    embed.set_footer(text="Use w!buy <role_name> to purchase a role!")
    await ctx.send(embed=embed)

@bot.command()
async def buy(ctx, *, role_name: str):
    role_name_lower = role_name.lower().strip()
    for item in SHOP_ROLES:
        if role_name_lower in item["name"].lower():
            price = item["price"]
            role_id = item["role_id"]
            user_coins = get_snowcoins(ctx.author.id)
            if user_coins >= price:
                role_obj = ctx.guild.get_role(role_id)
                if not role_obj:
                    return await ctx.send("That role doesn't exist on the server. Contact an admin.")
                if role_obj in ctx.author.roles:
                    return await ctx.send("You already have that role!")
                add_snowcoins(ctx.author.id, -price)
                await ctx.author.add_roles(role_obj)
                return await ctx.send(f"Congrats {ctx.author.mention}, you purchased **{item['name']}** for **{price}** 🍙!")
            else:
                return await ctx.send(f"You don't have enough 🍙 snowcoins to buy **{item['name']}**.")
    await ctx.send("That item/role doesn't exist in the shop. Check your spelling or see w!shop.")

@bot.tree.command(name="shop", description="Browse the Winter Shop!")
async def slash_shop(interaction: discord.Interaction):
    embed = discord.Embed(title="❄️ Winter Shop ❄️", color=0x00ffcc)
    lines = []
    for item in SHOP_ROLES:
        lines.append(f"**{item['name']}** - Costs **{item['price']}** 🍙")
    embed.description = "\n".join(lines)
    embed.set_footer(text="Use w!buy <role_name> to purchase a role!")
    await interaction.response.send_message(embed=embed)

# --- Fun Commands: Roll & Flip ---
@bot.command()
async def roll(ctx, bet: int = 20):
    if bet < 20:
        return await ctx.send("Minimum bet is 20 🍙!")
    user_coins = get_snowcoins(ctx.author.id)
    if user_coins < bet:
        return await ctx.send("You don't have enough snowcoins! ❄️")
    player_roll = random.randint(1, 100)
    bot_roll = random.randint(1, 100)
    embed = discord.Embed(title="🎲 Dice Duel 🎲", color=0x7289da)
    embed.add_field(name="Your Roll", value=f"```{player_roll}```", inline=True)
    embed.add_field(name="Bot's Roll", value=f"```{bot_roll}```", inline=True)
    if player_roll > bot_roll:
        add_snowcoins(ctx.author.id, bet)
        embed.description = f"🏆 You won {bet} 🍙 snowcoins!"
        embed.color = 0x00ff00
    elif player_roll < bot_roll:
        add_snowcoins(ctx.author.id, -bet)
        embed.description = f"💔 You lost {bet} 🍙 snowcoins!"
        embed.color = 0xff0000
    else:
        embed.description = "It's a tie!"
    await ctx.send(f"{ctx.author.mention}", embed=embed)

# --- Flip Game with Button Interaction ---
class FlipView(ui.View):
    def __init__(self, bet, user):
        super().__init__(timeout=15)
        self.bet = bet
        self.user = user
        self.choice = None

    @ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.choice = "Heads"
        self.stop()

    @ui.button(label="Tails", style=discord.ButtonStyle.primary)
    async def tails(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.choice = "Tails"
        self.stop()

@bot.command()
async def flip(ctx, bet: int = 10):
    if bet < 10:
        return await ctx.send("Minimum bet is 10 🍙!")
    user_coins = get_snowcoins(ctx.author.id)
    if user_coins < bet:
        return await ctx.send("You don't have enough snowcoins! ❄️")
    view = FlipView(bet, ctx.author)
    await ctx.send("Choose Heads or Tails:", view=view)
    await view.wait()
    if view.choice is None:
        return await ctx.send("Time's up!")
    bot_choice = random.choice(["Heads", "Tails"])
    embed = discord.Embed(title="❄️ Coin Flip Battle ❄️", color=0x00ffff)
    embed.add_field(name="Your Choice", value=view.choice, inline=True)
    embed.add_field(name="Bot's Choice", value=bot_choice, inline=True)
    if view.choice == bot_choice:
        add_snowcoins(ctx.author.id, bet)
        embed.description = f"🎉 You won {bet} 🍙 snowcoins!"
        embed.color = 0x00ff00
    else:
        add_snowcoins(ctx.author.id, -bet)
        embed.description = f"💔 You lost {bet} 🍙 snowcoins!"
        embed.color = 0xff0000
    await ctx.send(embed=embed)

# --- Additional Game 1: Rock-Paper-Scissors (Multiplayer/Vs Bot) ---
class RPSView(ui.View):
    def __init__(self, user, rounds=3):
        super().__init__(timeout=20)
        self.user = user
        self.choices = None
        self.rounds = rounds
        self.current_round = 0
        self.user_score = 0
        self.bot_score = 0

    @ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Rock")
    @ui.button(label="Paper", style=discord.ButtonStyle.primary)
    async def paper(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Paper")
    @ui.button(label="Scissors", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction: discord.Interaction, button: ui.Button):
        await self.make_choice(interaction, "Scissors")

    async def make_choice(self, interaction, choice):
        if interaction.user != self.user:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        bot_choice = random.choice(["Rock", "Paper", "Scissors"])
        result = ""
        if choice == bot_choice:
            result = "It's a tie!"
        elif (choice == "Rock" and bot_choice == "Scissors") or (choice == "Paper" and bot_choice == "Rock") or (choice == "Scissors" and bot_choice == "Paper"):
            self.user_score += 1
            result = "You win this round!"
        else:
            self.bot_score += 1
            result = "Bot wins this round!"
        self.current_round += 1
        await interaction.response.send_message(f"You chose **{choice}**. Bot chose **{bot_choice}**. {result}")
        if self.current_round >= self.rounds:
            self.stop()

@bot.command()
async def rps(ctx, rounds: int = 3):
    view = RPSView(ctx.author, rounds)
    await ctx.send(f"{ctx.author.mention} started a Rock-Paper-Scissors game for {rounds} rounds!", view=view)
    await view.wait()
    if view.user_score > view.bot_score:
        outcome = "You win the game!"
        add_snowcoins(ctx.author.id, 50)
    elif view.user_score < view.bot_score:
        outcome = "Bot wins the game!"
        add_snowcoins(ctx.author.id, -50)
    else:
        outcome = "The game is a tie!"
    await ctx.send(f"Game Over! Score: You {view.user_score} - Bot {view.bot_score}. {outcome}")

# --- Additional Game 2: Word Scramble (Guess the Word) ---
# A simple game where the bot sends a scrambled word, and the user must guess the correct word within a time limit.
scramble_words = [
    {"word": "naruto", "hint": "Anime ninja"},
    {"word": "bleach", "hint": "Soul Reaper"},
    {"word": "goku", "hint": "Saiyan hero"},
    {"word": "luffy", "hint": "Straw hat pirate"},
    {"word": "ichigo", "hint": "Substitute Soul Reaper"}
]

@bot.command()
async def scramble(ctx):
    game = random.choice(scramble_words)
    word = game["word"]
    hint = game["hint"]
    scrambled = ''.join(random.sample(word, len(word)))
    message = await ctx.send(f"Unscramble this word: **{scrambled}**\nHint: {hint}\nTime remaining: **15** seconds")

    # Countdown timer
    async def countdown():
        remaining = 15
        while remaining > 0:
            await asyncio.sleep(1)
            remaining -= 1
            try:
                await message.edit(content=f"Unscramble this word: **{scrambled}**\nHint: {hint}\nTime remaining: **{remaining}** seconds")
            except Exception:
                break
        return remaining

    countdown_task = asyncio.create_task(countdown())
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    try:
        guess_msg = await bot.wait_for("message", check=check, timeout=15.0)
        countdown_task.cancel()
        if guess_msg.content.lower().strip() == word:
            add_snowcoins(ctx.author.id, 40)
            await ctx.send("Correct! You earned 40 🍙 snowcoins!")
        else:
            await ctx.send(f"Wrong! The correct word was **{word}**.")
    except asyncio.TimeoutError:
        countdown_task.cancel()
        await ctx.send("👻 Boo! Time over!")
        await ctx.send(f"The correct word was **{word}**.")

# --- Snowfight Game (Turn-based Battle) with 70 HP and Limited Rounds ---
@bot.command(name="snowfight", help="Start a turn-based snowball fight!")
async def snowfight(ctx, opponent: discord.Member):
    if opponent.bot:
        return await ctx.send("❄️ You can't fight bots!")
    if opponent == ctx.author:
        return await ctx.send("❄️ You can't fight yourself!")
    rounds = 5  # maximum rounds
    players = {
        ctx.author.id: {"health": 70, "dodge": 10},
        opponent.id: {"health": 70, "dodge": 10}
    }
    update_stats(ctx.author.id, win=False)
    update_stats(opponent.id, win=False)
    current_round = 0
    turn = ctx.author
    await ctx.send(f"❄️ Snowfight started between {ctx.author.mention} and {opponent.mention}! Each player has 70 HP. Maximum {rounds} rounds.")
    while current_round < rounds:
        await ctx.send(f"Round {current_round+1}: {turn.mention}, type `w!throw` to attack!")
        try:
            throw_msg = await bot.wait_for("message", check=lambda m: m.author == turn and m.channel == ctx.channel, timeout=20.0)
        except asyncio.TimeoutError:
            await ctx.send("Time's up for this round!")
            break
        # Attack logic
        target = opponent if turn == ctx.author else ctx.author
        if random.randint(1, 100) <= players[target.id]["dodge"]:
            await ctx.send(f"❄️ {target.mention} dodged the snowball!")
        else:
            damage = random.randint(5, 25)
            players[target.id]["health"] -= damage
            await ctx.send(f"❄️ {turn.mention} hit {target.mention} for {damage} damage!")
            # Show remaining health for both
            await ctx.send(f"HP Update: {ctx.author.mention}: **{players[ctx.author.id]['health']} HP** | {opponent.mention}: **{players[opponent.id]['health']} HP**")
            if players[target.id]["health"] <= 0:
                await ctx.send(f"🏆 {turn.mention} wins the snowfight!")
                update_stats(turn.id, win=True)
                update_stats(target.id, win=False)
                add_snowcoins(turn.id, 50)
                return
        # Switch turn and increment round if both have attacked
        turn = opponent if turn == ctx.author else ctx.author
        current_round += 1
    # Determine winner based on remaining HP
    if players[ctx.author.id]["health"] > players[opponent.id]["health"]:
        winner = ctx.author
    elif players[ctx.author.id]["health"] < players[opponent.id]["health"]:
        winner = opponent
    else:
        winner = None
    if winner:
        await ctx.send(f"🏆 {winner.mention} wins the snowfight after {current_round} rounds!")
        update_stats(winner.id, win=True)
        loser = opponent if winner == ctx.author else ctx.author
        update_stats(loser.id, win=False)
        add_snowcoins(winner.id, 50)
    else:
        await ctx.send("The snowfight is a tie!")

@bot.tree.command(name="snowfight", description="Challenge someone to a snowfight!")
@app_commands.describe(opponent="The user you want to fight")
async def slash_snowfight(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.bot:
        return await interaction.response.send_message("❄️ You can't fight bots!", ephemeral=True)
    if opponent == interaction.user:
        return await interaction.response.send_message("❄️ You can't fight yourself!", ephemeral=True)
    await interaction.response.send_message(
        f"❄️ {interaction.user.mention} challenged {opponent.mention} to a snowfight!\nType `w!snowfight @user` in the chat to start!"
    )

##################################
# 9. Run the Bot + KeepAlive     #
##################################
keep_alive()  # Starts the Flask web server (for uptime pings)
bot.run(BOT_TOKEN)
