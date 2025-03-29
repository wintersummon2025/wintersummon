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

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Set in your .env file

# Server & Channel IDs
SERVER_ID = 1341825447964577873
TICKETS_CHANNEL_ID = 1341825447964577880
LEVEL_CHANNEL_ID = 1353632560202256416

# Role IDs
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

# Shop Roles
SHOP_ROLES = [
    {"price": 3000, "role_id": 1354671043146682398, "name": "Minion ❄️"},
    {"price": 7000, "role_id": 1354672101180575795, "name": "Soldier 🧊"},
    {"price": 15000, "role_id": 1354672108508020818, "name": "Veteran 👑"}
]

# XP Ranges
XP_RANGE_NORMAL = (22, 33)
XP_RANGE_COOLDOWN = (3, 6)

# Spam Control Thresholds
SPAM_3SEC_LIMIT = 5
SPAM_6SEC_LIMIT = 10
SPAM_TIMEOUT_HOURS = 12

# Game GIFs
GAME_GIFS = {
    "win": "https://media.giphy.com/media/3o7aD2d7hy9ktXNDP2/giphy.gif",
    "lose": "https://media.giphy.com/media/l3q2EOu4nu1D8uJKU/giphy.gif",
    "slot_win": "https://media.giphy.com/media/3ohs4kI2X9r7O8ZtoA/giphy.gif",
    "lose_anime": "https://media.giphy.com/media/l46CkATpdyLwLI7vi/giphy.gif",
    "win_anime": "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif"
}

# Initialize Bot
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="w!", intents=intents, case_insensitive=True)

# Data stores
xp_data = {}         # { "user_id": {"xp": value} }
xp_cooldown = {}     # { "user_id": datetime }
messages_timestamps = {}  # { "user_id": [timestamps] }

##################################
# 2. Keep-Alive Flask App        #
##################################
app = Flask(__name__)

@app.route("/")
def home():
    return "WinterSummon Bot is running happily!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.start()

##################################
# 3. Snowcoins & Stats Database  #
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
    print(f"Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
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
        # Send cute anime welcome DM
        embed = discord.Embed(
            title="Welcome to Winter's Wonderland!",
            description="We’re so happy you’re here! ❄️ Grab some hot cocoa and let the winter magic begin!",
            color=0x00aaff,
            timestamp=datetime.utcnow()
        )
        embed.set_image(url="https://media.giphy.com/media/H6udV2MDcG9yQZIOHe/giphy.gif")
        embed.set_footer(text="Joined on")
        await member.send(embed=embed)
    except Exception as e:
        print(f"Error sending welcome DM: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Ticket System: Forward any DM to a specific user (ID: 973805949431218186)
    if isinstance(message.channel, discord.DMChannel):
        target_user = bot.get_user(973805949431218186)
        if target_user:
            embed = discord.Embed(
                title="New Ticket",
                description=f"From **{message.author}** (ID: {message.author.id}):\n{message.content}",
                color=0xff0000,
                timestamp=datetime.utcnow()
            )
            try:
                await target_user.send(embed=embed)
            except Exception as e:
                print(f"Error forwarding ticket: {e}")
        return

    # XP awarding
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

    # Level-up Roles
    current_xp = xp_data[user_id]["xp"]
    for threshold, role_id in LEVEL_ROLES:
        role = message.guild.get_role(role_id)
        if current_xp >= threshold and role and (role not in message.author.roles):
            await message.author.add_roles(role)
            level_channel = message.guild.get_channel(LEVEL_CHANNEL_ID)
            if level_channel:
                await level_channel.send(f"Congratulations {message.author.mention}! You've reached **{threshold}** snowdrops 💠 and earned a new role!")

    # Spam Control
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
# 7. Quiz, RPS & Additional Games#
##################################
async def start_countdown(message, duration, question_text, idx):
    remaining = duration
    while remaining > 0:
        try:
            await asyncio.sleep(1)
            remaining -= 1
            await message.edit(content=f"**Q{idx}:** {question_text}\nTime remaining: **{remaining}** seconds")
        except Exception:
            break
        
# --- Anime Quiz (Snowquiz) with 5 Rounds --
@bot.command(name="snowquiz", help="Start a fun anime quiz with 5 questions!")
async def snowquiz_prefix(ctx):
    await start_snowquiz(ctx, ctx.author)

@bot.tree.command(name="snowquiz", description="Play a fun anime quiz with 5 questions!")
async def snowquiz_slash(interaction: discord.Interaction):
    await interaction.response.send_message(f"{interaction.user.mention}, let's start the anime quiz!")
    await start_snowquiz(interaction, interaction.user)

async def start_snowquiz(context, user):
    channel = context.channel
    questions = [
        {"question": "Which anime features a notebook that kills anyone whose name is written in it?", "answer": "death note"},
        {"question": "Name the bald hero from One Punch Man", "answer": "saitama"},
        {"question": "In Naruto, who is known as the Copy Ninja?", "answer": "kakashi"},
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
        {"question": "Which anime features a notebook that kills anyone whose name is written in it?", "answer": "death note"},
        {"question": "Name the bald hero from One Punch Man", "answer": "saitama"},
        {"question": "In Naruto, who is known as the Copy Ninja?", "answer": "kakashi"}
    ]
    random.shuffle(questions)
    correct = 0
    for i, qa in enumerate(questions, start=1):
        msg = await channel.send(f"**Q{i}:** {qa['question']}\n(You have 10 seconds to answer!)")
        # Start live countdown
        countdown_task = asyncio.create_task(start_countdown(msg, 10, qa['question'], i))
        def check(m):
            return m.author == user and m.channel == channel
        try:
            guess = await bot.wait_for("message", check=check, timeout=10.0)
            countdown_task.cancel()
            if guess.content.lower().strip() == qa["answer"]:
                correct += 1
                add_snowcoins(user.id, 30)
                await channel.send("Correct! You earned 30 🍙 snowcoins.")
            else:
                await channel.send(f"Wrong! The correct answer was **{qa['answer']}**.")
        except asyncio.TimeoutError:
            countdown_task.cancel()
            await channel.send(f"Time's up! The correct answer was **{qa['answer']}**.")
    await channel.send(f"**Quiz Finished!** You answered **{correct}** out of **{len(questions)}** correctly.")

# --- Rock-Paper-Scissors (RPS) Multiplayer ---
class RPSChallengeView(ui.View):
    def __init__(self, challenger, challenged, rounds=3):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.challenged = challenged
        self.rounds = rounds
        self.accepted = False

    @ui.button(label="Accept Challenge", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.challenged:
            return await interaction.response.send_message("This challenge is not for you!", ephemeral=True)
        self.accepted = True
        await interaction.response.send_message("Challenge accepted! Starting RPS game...", ephemeral=True)
        self.stop()

    @ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.challenged:
            return await interaction.response.send_message("This challenge is not for you!", ephemeral=True)
        await interaction.response.send_message("Challenge declined.", ephemeral=True)
        self.stop()

@bot.command(name="rps", help="Challenge a user to Rock-Paper-Scissors!")
async def rps_command(ctx, opponent: discord.Member, rounds: int = 3):
    if opponent.bot:
        return await ctx.send("❄️ You can't challenge a bot!")
    if opponent == ctx.author:
        return await ctx.send("❄️ You can't challenge yourself!")
    view = RPSChallengeView(ctx.author, opponent, rounds)
    await ctx.send(f"{ctx.author.mention} challenges {opponent.mention} to RPS! {opponent.mention}, do you accept?", view=view)
    await view.wait()
    if not view.accepted:
        return await ctx.send("RPS challenge was declined or timed out.")
    rps_view = RPSGameView(ctx.author, opponent, rounds)
    await ctx.send(f"RPS game starting between {ctx.author.mention} and {opponent.mention}!", view=rps_view)
    await rps_view.wait()

class RPSGameView(ui.View):
    def __init__(self, player1, player2, rounds=3):
        super().__init__(timeout=120)
        self.player1 = player1
        self.player2 = player2
        self.rounds = rounds
        self.current_round = 0
        self.scores = {player1.id: 0, player2.id: 0}
        self.current_turn = player1

    async def end_game(self, interaction: discord.Interaction):
        p1 = self.scores[self.player1.id]
        p2 = self.scores[self.player2.id]
        if p1 > p2:
            winner = self.player1
            gif = GAME_GIFS["win_anime"]
        elif p2 > p1:
            winner = self.player2
            gif = GAME_GIFS["lose_anime"]
        else:
            winner = None
            gif = GAME_GIFS["lose"]
        result = f"Game Over! Score: {self.player1.display_name} {p1} - {self.player2.display_name} {p2}. "
        if winner:
            result += f"Congratulations {winner.mention}, you win!"
            add_snowcoins(winner.id, 50)
        else:
            result += "It's a tie!"
        await interaction.followup.send(content=result, embed=discord.Embed().set_image(url=gif))
        self.stop()

    async def rps_round(self, interaction: discord.Interaction, choice: str):
        bot_choice = random.choice(["Rock", "Paper", "Scissors"])
        if choice == bot_choice:
            result_text = "It's a tie this round!"
        elif (choice == "Rock" and bot_choice == "Scissors") or \
             (choice == "Paper" and bot_choice == "Rock") or \
             (choice == "Scissors" and bot_choice == "Paper"):
            self.scores[self.current_turn.id] += 1
            result_text = f"{self.current_turn.display_name} wins this round!"
        else:
            other = self.player2 if self.current_turn == self.player1 else self.player1
            self.scores[other.id] += 1
            result_text = f"{other.display_name} wins this round!"
        self.current_round += 1
        await interaction.response.send_message(
            content=f"Round {self.current_round}/{self.rounds}: {self.current_turn.display_name} chose **{choice}**; Bot chose **{bot_choice}**.\n{result_text}",
            ephemeral=True
        )
        if self.current_round >= self.rounds:
            await self.end_game(interaction)
        else:
            self.current_turn = self.player2 if self.current_turn == self.player1 else self.player1

    @ui.button(label="Rock", style=discord.ButtonStyle.primary)
    async def rock(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.current_turn:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await self.rps_round(interaction, "Rock")

    @ui.button(label="Paper", style=discord.ButtonStyle.primary)
    async def paper(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.current_turn:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await self.rps_round(interaction, "Paper")

    @ui.button(label="Scissors", style=discord.ButtonStyle.primary)
    async def scissors(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.current_turn:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await self.rps_round(interaction, "Scissors")

# --- Flip Game with Bet (Supports VS Bot and Multiplayer) ---
class FlipGameView(ui.View):
    def __init__(self, bet: int, challenger, opponent=None):
        super().__init__(timeout=15)
        self.bet = bet
        self.challenger = challenger
        self.opponent = opponent  # If None, play vs Bot
        self.choice = None

    @ui.button(label="Heads", style=discord.ButtonStyle.primary)
    async def heads(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user not in [self.challenger, self.opponent or self.challenger]:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.choice = "Heads"
        self.stop()

    @ui.button(label="Tails", style=discord.ButtonStyle.primary)
    async def tails(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user not in [self.challenger, self.opponent or self.challenger]:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        self.choice = "Tails"
        self.stop()

@bot.command(name="flip", help="Play a coin flip game. Use with an opponent for multiplayer or without for vs Bot.")
async def flip_command(ctx, bet: int = 10, opponent: discord.Member = None):
    if bet < 10:
        return await ctx.send("Minimum bet is 10 🍙!")
    if opponent:
        if opponent.bot:
            return await ctx.send("❄️ You can't challenge a bot!")
        view = FlipGameView(bet, ctx.author, opponent)
        await ctx.send(f"{ctx.author.mention} challenged {opponent.mention} to a coin flip! Both, choose Heads or Tails:", view=view)
    else:
        view = FlipGameView(bet, ctx.author)
        await ctx.send(f"{ctx.author.mention}, choose Heads or Tails to flip against the bot:", view=view)
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

@bot.tree.command(name="flip", description="Play a coin flip game!")
async def slash_flip(interaction: discord.Interaction, bet: int = 10, opponent: discord.Member = None):
    # Slash version calls the same logic as prefix
    ctx = await bot.get_context(interaction.message)
    await flip_command(ctx, bet, opponent)

# --- Roll (Dice Duel) with Multiplayer Option ---
@bot.command(name="roll", help="Roll dice vs Bot or challenge a user. In multiplayer, opponents DM a number.")
async def roll_command(ctx, bet: int = 20, opponent: discord.Member = None):
    if bet < 20:
        return await ctx.send("Minimum bet is 20 🍙!")
    if get_snowcoins(ctx.author.id) < bet:
        return await ctx.send("You don't have enough snowcoins! ❄️")
    if opponent is None:
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
    else:
        if opponent.bot:
            return await ctx.send("❄️ You can't challenge a bot!")
        try:
            await opponent.send(f"You have been challenged to a dice duel by {ctx.author.mention}! Please reply with a number (1-50) within 15 seconds.")
        except Exception:
            return await ctx.send("Could not DM the opponent. They might have DMs closed.")
        def check(m):
            return m.author == opponent and m.content.isdigit()
        try:
            dm_response = await bot.wait_for("message", check=check, timeout=15.0)
            opp_choice = int(dm_response.content)
            try:
                await ctx.author.send("Reply with a number (1-50) within 15 seconds for your roll.")
            except Exception:
                return await ctx.send("Could not DM you. Check your DM settings.")
            dm_response2 = await bot.wait_for("message", check=lambda m: m.author == ctx.author and m.content.isdigit(), timeout=15.0)
            chal_choice = int(dm_response2.content)
            embed = discord.Embed(title="🎲 Multiplayer Dice Duel 🎲", color=0x7289da)
            embed.add_field(name=f"{ctx.author.display_name}'s Choice", value=chal_choice, inline=True)
            embed.add_field(name=f"{opponent.display_name}'s Choice", value=opp_choice, inline=True)
            if chal_choice > opp_choice:
                add_snowcoins(ctx.author.id, bet)
                embed.description = f"🏆 {ctx.author.mention} wins {bet} 🍙 snowcoins!"
                embed.color = 0x00ff00
            elif chal_choice < opp_choice:
                add_snowcoins(ctx.author.id, -bet)
                embed.description = f"💔 {ctx.author.mention} loses {bet} 🍙 snowcoins!"
                embed.color = 0xff0000
            else:
                embed.description = "It's a tie!"
            await ctx.send(embed=embed)
        except asyncio.TimeoutError:
            await ctx.send("Time's up! Dice duel cancelled.")

@bot.tree.command(name="roll", description="Roll dice vs Bot or challenge a user!")
async def slash_roll(interaction: discord.Interaction, bet: int = 20, opponent: discord.Member = None):
    ctx = await bot.get_context(interaction.message)
    await roll_command(ctx, bet, opponent)

# --- Snowfight Game with Button "Throw" ---
class SnowfightView(ui.View):
    def __init__(self, player1, player2, rounds=3):
        super().__init__(timeout=120)
        self.player1 = player1
        self.player2 = player2
        self.rounds = rounds
        self.current_round = 0
        self.players = {
            player1.id: {"health": 70, "dodge": 10},
            player2.id: {"health": 70, "dodge": 10}
        }
        self.turn = player1

    @ui.button(label="Throw", style=discord.ButtonStyle.primary)
    async def throw_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.turn:
            return await interaction.response.send_message("Not your turn!", ephemeral=True)
        target = self.player2 if self.turn == self.player1 else self.player1
        if random.randint(1, 100) <= self.players[target.id]["dodge"]:
            outcome = f"{target.mention} dodged the snowball!"
        else:
            damage = random.randint(5, 25)
            self.players[target.id]["health"] -= damage
            outcome = f"{self.turn.mention} hit {target.mention} for {damage} damage!"
        self.current_round += 1
        await interaction.response.send_message(outcome)
        hp_update = f"HP Update: {self.player1.mention}: **{self.players[self.player1.id]['health']} HP** | {self.player2.mention}: **{self.players[self.player2.id]['health']} HP**"
        await interaction.followup.send(hp_update)
        if self.players[target.id]["health"] <= 0:
            await interaction.followup.send(f"🏆 {self.turn.mention} wins the snowfight!")
            add_snowcoins(self.turn.id, 50)
            return self.stop()
        if self.current_round < self.rounds:
            self.turn = target
            await interaction.followup.send(f"Round {self.current_round+1}: {self.turn.mention}, it's your turn! Press **Throw**.")
        else:
            p1_hp = self.players[self.player1.id]["health"]
            p2_hp = self.players[self.player2.id]["health"]
            if p1_hp > p2_hp:
                winner = self.player1
            elif p2_hp > p1_hp:
                winner = self.player2
            else:
                winner = None
            if winner:
                await interaction.followup.send(f"🏆 {winner.mention} wins the snowfight after {self.rounds} rounds!")
                add_snowcoins(winner.id, 50)
            else:
                await interaction.followup.send("The snowfight is a tie!")
            self.stop()

@bot.command(name="snowfight", help="Start a turn-based snowball fight!")
async def snowfight_command(ctx, opponent: discord.Member):
    if opponent.bot:
        return await ctx.send("❄️ You can't fight bots!")
    if opponent == ctx.author:
        return await ctx.send("❄️ You can't fight yourself!")
    view = SnowfightView(ctx.author, opponent, rounds=3)
    await ctx.send(f"❄️ Snowfight started between {ctx.author.mention} and {opponent.mention}! Each player has 70 HP. 3 rounds maximum. {ctx.author.mention} goes first. Press **Throw** to attack!", view=view)
    await view.wait()

@bot.tree.command(name="snowfight", description="Challenge someone to a snowfight!")
@app_commands.describe(opponent="The user you want to fight")
async def slash_snowfight(interaction: discord.Interaction, opponent: discord.Member):
    if opponent.bot:
        return await interaction.response.send_message("❄️ You can't fight bots!", ephemeral=True)
    if opponent == interaction.user:
        return await interaction.response.send_message("❄️ You can't fight yourself!", ephemeral=True)
    await interaction.response.send_message(f"❄️ {interaction.user.mention} challenged {opponent.mention} to a snowfight!\nType `w!snowfight @user` in the chat to start!")

# --- Additional Game: Maze Game ---
class MazeView(ui.View):
    def __init__(self, user, rounds=3):
        super().__init__(timeout=60)
        self.user = user
        self.rounds = rounds
        self.current_round = 0
        self.total_reward = 0
        self.directions = ["left", "right", "forward", "backward"]
        self.correct_path = [random.choice(self.directions) for _ in range(rounds)]

    async def end_maze(self, interaction: discord.Interaction):
        await interaction.followup.send(f"Game Over! You earned a total of {self.total_reward} 🍙 snowcoins!")
        add_snowcoins(self.user.id, self.total_reward)
        self.stop()

    @ui.button(label="Left", style=discord.ButtonStyle.primary)
    async def left_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_choice(interaction, "left")

    @ui.button(label="Right", style=discord.ButtonStyle.primary)
    async def right_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_choice(interaction, "right")

    @ui.button(label="Forward", style=discord.ButtonStyle.primary)
    async def forward_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_choice(interaction, "forward")

    @ui.button(label="Backward", style=discord.ButtonStyle.primary)
    async def backward_button(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_choice(interaction, "backward")

    async def process_choice(self, interaction: discord.Interaction, choice: str):
        if interaction.user != self.user:
            return await interaction.response.send_message("This is not your maze!", ephemeral=True)
        correct = self.correct_path[self.current_round]
        if choice == correct:
            reward = random.randint(30, 50)
            self.total_reward += reward
            await interaction.response.send_message(f"Correct! You earned {reward} 🍙. Moving on!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Wrong! The correct direction was **{correct}**. Maze failed!", ephemeral=True)
            self.stop()
            return
        self.current_round += 1
        if self.current_round >= self.rounds:
            await self.end_maze(interaction)
        else:
            await interaction.followup.send(f"Round {self.current_round+1}: Choose a direction.", ephemeral=True)

@bot.command(name="maze", help="Navigate the snow maze using buttons!")
async def maze(ctx):
    view = MazeView(ctx.author, rounds=3)
    await ctx.send(f"{ctx.author.mention}, welcome to the Snow Maze! Choose your direction wisely for 3 rounds. Good luck!", view=view)
    await view.wait()

@bot.tree.command(name="maze", description="Play the Snow Maze game!")
async def slash_maze(interaction: discord.Interaction):
    view = MazeView(interaction.user, rounds=3)
    await interaction.response.send_message(f"{interaction.user.mention}, welcome to the Snow Maze! Choose your direction wisely for 3 rounds. Good luck!", view=view)

# --- New Anime Word Scramble ---
@bot.command(name="scramble", help="Unscramble the anime word!")
async def scramble_command(ctx):
    anime_words = [
        {"word": "naruto", "hint": "Anime ninja"},
        {"word": "bleach", "hint": "Soul Reaper"},
        {"word": "goku", "hint": "Saiyan hero"},
        {"word": "luffy", "hint": "Straw hat pirate"},
        {"word": "ichigo", "hint": "Substitute Soul Reaper"},
    {"word": "eren", "hint": "Titan slayer"},
    {"word": "gon", "hint": "Hunter x Hunter protagonist"},
    {"word": "killua", "hint": "Zoldyck assassin"},
    {"word": "tanjiro", "hint": "Demon Slayer protagonist"},
    {"word": "nezuko", "hint": "Demon girl"},
    {"word": "asuna", "hint": "Sword Art Online heroine"},
    {"word": "kirito", "hint": "Black Swordsman"},
    {"word": "edward", "hint": "Fullmetal Alchemist"},
    {"word": "alphonse", "hint": "Armored brother"},
    {"word": "gojo", "hint": "Strongest sorcerer"},
    {"word": "itadori", "hint": "Jujutsu Kaisen protagonist"},
    {"word": "megumi", "hint": "Ten Shadows Technique user"},
    {"word": "nobara", "hint": "Hammer and nails fighter"},
    {"word": "saitama", "hint": "One Punch Man"},
    {"word": "genos", "hint": "Cyborg disciple"},
    {"word": "mob", "hint": "Esper with 100% potential"},
    {"word": "reigen", "hint": "Mob's mentor"},
    {"word": "kaneki", "hint": "Half-ghoul"},
    {"word": "todoroki", "hint": "Half hot, half cold"},
    {"word": "deku", "hint": "One For All successor"},
    {"word": "bakugo", "hint": "Explosive temper"},
    {"word": "allmight", "hint": "Symbol of Peace"},
    {"word": "shoto", "hint": "Uses fire and ice"},
    {"word": "senku", "hint": "Dr. Stone genius"},
    {"word": "ryuk", "hint": "Shinigami with an apple addiction"},
    {"word": "light", "hint": "Kira"},
    {"word": "lelouch", "hint": "Geass wielder"},
    {"word": "ciel", "hint": "Black Butler protagonist"},
    {"word": "sebastian", "hint": "One hell of a butler"},
    {"word": "yato", "hint": "Delivery god"},
    {"word": "hiyori", "hint": "Noragami heroine"},
    {"word": "vash", "hint": "Humanoid Typhoon"},
    {"word": "alucard", "hint": "Hellsing vampire"},
    {"word": "spike", "hint": "Cowboy Bebop bounty hunter"},
    {"word": "faye", "hint": "Cowboy Bebop femme fatale"},
    {"word": "edward", "hint": "Cowboy Bebop hacker"},
    {"word": "rem", "hint": "Blue-haired maid"},
    {"word": "ram", "hint": "Pink-haired maid"},
    {"word": "subaru", "hint": "Re:Zero protagonist"},
    {"word": "emilia", "hint": "Half-elf heroine"},
    {"word": "satella", "hint": "Witch of Envy"},
    {"word": "astolfo", "hint": "Pink-haired Rider"},
    {"word": "gilgamesh", "hint": "King of Heroes"},
    {"word": "shanks", "hint": "Red-haired pirate"},
    {"word": "law", "hint": "Surgeon of Death"},
    {"word": "zoro", "hint": "Three-sword style"},
    {"word": "sanji", "hint": "Black Leg cook"},
    {"word": "robin", "hint": "Archaeologist of the Straw Hats"},
    {"word": "nami", "hint": "Straw Hat navigator"},
    {"word": "chopper", "hint": "Cotton Candy Lover"},
    {"word": "brook", "hint": "Straw Hat skeleton"},
    {"word": "franky", "hint": "Cyborg shipwright"},
    {"word": "boa", "hint": "Snake princess"},
    {"word": "dazai", "hint": "Bungou Stray Dogs detective"},
    {"word": "ranpo", "hint": "Edogawa detective"},
    {"word": "tanizaki", "hint": "Illusion ability user"},
    {"word": "akutagawa", "hint": "Rashomon ability user"},
    {"word": "chuuya", "hint": "Gravity manipulator"},
    {"word": "akame", "hint": "Night Raid assassin"},
    {"word": "esdeath", "hint": "Ice general"},
    {"word": "tatsumi", "hint": "Night Raid recruit"},
    {"word": "yuno", "hint": "Four-leaf grimoire holder"},
    {"word": "asta", "hint": "Anti-magic swordsman"},
    {"word": "noelle", "hint": "Water magic princess"},
    {"word": "merlin", "hint": "Sin of Gluttony"},
    {"word": "meliodas", "hint": "Dragon Sin of Wrath"},
    {"word": "elizabeth", "hint": "Reincarnated goddess"},
    {"word": "escanor", "hint": "The One"},
    {"word": "ban", "hint": "Immortal Sin of Greed"},
    {"word": "diane", "hint": "Giantess Sin of Envy"},
    {"word": "king", "hint": "Fairy King Harlequin"},
    {"word": "hawks", "hint": "Seven Deadly Sins mascot"},
    {"word": "rimuru", "hint": "Reincarnated slime"},
    {"word": "shion", "hint": "Purple-haired ogre"},
    {"word": "benimaru", "hint": "Ogre samurai"},
    {"word": "gobta", "hint": "Goblin warrior"},
    {"word": "milim", "hint": "Demon Lord with pigtails"}
    ]
    game = random.choice(anime_words)
    word = game["word"]
    hint = game["hint"]
    scrambled = ''.join(random.sample(word, len(word)))
    message = await ctx.send(f"Unscramble this anime word: **{scrambled}**\nHint: {hint}\nTime remaining: **15** seconds")
    async def countdown():
        remaining = 15
        while remaining > 0:
            await asyncio.sleep(1)
            remaining -= 1
            try:
                await message.edit(content=f"Unscramble this anime word: **{scrambled}**\nHint: {hint}\nTime remaining: **{remaining}** seconds")
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
        await ctx.send(f"Time's up! The correct word was **{word}**.")

@bot.tree.command(name="scramble", description="Unscramble the anime word!")
async def slash_scramble(interaction: discord.Interaction):
    ctx = await bot.get_context(interaction.message)
    await scramble_command(ctx)

##################################
# 8. Additional Commands         #
##################################
@bot.command(name="level", help="Check your XP and level!")
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

@bot.tree.command(name="level", description="Check your XP and level!")
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

@bot.command(name="wallet", help="Check your snowcoins balance!")
async def wallet(ctx):
    coins = get_snowcoins(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, you have **{coins}** 🍙 snowcoins in your wallet!")

@bot.tree.command(name="wallet", description="Check your snowcoins balance!")
async def slash_wallet(interaction: discord.Interaction):
    coins = get_snowcoins(interaction.user.id)
    await interaction.response.send_message(f"{interaction.user.mention}, you have **{coins}** 🍙 snowcoins in your wallet!")

@bot.command(name="shop", help="Browse the Winter Shop!")
async def shop(ctx):
    embed = discord.Embed(title="❄️ Winter Shop ❄️", color=0x00ffcc)
    lines = []
    for item in SHOP_ROLES:
        lines.append(f"**{item['name']}** - Costs **{item['price']}** 🍙")
    embed.description = "\n".join(lines)
    embed.set_footer(text="Use w!buy <role name> to purchase a role!")
    await ctx.send(embed=embed)

@bot.command(name="buy", help="Purchase a role from the shop!")
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
    embed.set_footer(text="Use w!buy <role name> to purchase a role!")
    await interaction.response.send_message(embed=embed)

@bot.command(name="stats", help="Check your game statistics!")
async def stats(ctx):
    c.execute("SELECT games_played, wins, losses FROM users WHERE user_id=?", (ctx.author.id,))
    row = c.fetchone()
    if row:
        stats_data = {"games_played": row[0], "wins": row[1], "losses": row[2]}
    else:
        stats_data = {"games_played": 0, "wins": 0, "losses": 0}
    embed = discord.Embed(title="Your Game Stats", color=0x000000)
    if ctx.author.avatar:
        embed.set_thumbnail(url=ctx.author.avatar.url)
    embed.add_field(name="Games Played", value=str(stats_data["games_played"]), inline=True)
    embed.add_field(name="Wins", value=str(stats_data["wins"]), inline=True)
    embed.add_field(name="Losses", value=str(stats_data["losses"]), inline=True)
    embed.set_footer(text="Keep playing and improve!")
    await ctx.send(embed=embed)

@bot.tree.command(name="stats", description="Check your game statistics!")
async def slash_stats(interaction: discord.Interaction):
    c.execute("SELECT games_played, wins, losses FROM users WHERE user_id=?", (interaction.user.id,))
    row = c.fetchone()
    if row:
        stats_data = {"games_played": row[0], "wins": row[1], "losses": row[2]}
    else:
        stats_data = {"games_played": 0, "wins": 0, "losses": 0}
    embed = discord.Embed(title="Your Game Stats", color=0x000000)
    if interaction.user.avatar:
        embed.set_thumbnail(url=interaction.user.avatar.url)
    embed.add_field(name="Games Played", value=str(stats_data["games_played"]), inline=True)
    embed.add_field(name="Wins", value=str(stats_data["wins"]), inline=True)
    embed.add_field(name="Losses", value=str(stats_data["losses"]), inline=True)
    embed.set_footer(text="Keep playing and improve!")
    await interaction.response.send_message(embed=embed)

##################################
# 9. Run the Bot + KeepAlive     #
##################################
keep_alive()  # Start the Flask server for uptime
bot.run(BOT_TOKEN)
