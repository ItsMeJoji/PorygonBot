"""

This bot can be restarted as many times without needing to subscribe or worry about tokens:
- Tokens are stored in '.tio.tokens.json' by default
- Subscriptions last 72 hours after the bot is disconnected and refresh when the bot starts.

"""
import json
import os
import re
import asyncio
import logging
import random
import string
from pathlib import Path
from typing import TYPE_CHECKING

import asqlite

import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from twitchio.user import PartialUser, User


if TYPE_CHECKING:
    import sqlite3


LOGGER: logging.Logger = logging.getLogger("Bot")

CLIENT_ID: str = os.getenv('TWITCH_CLIENT_ID')  # The CLIENT ID from the Twitch Dev Console
CLIENT_SECRET: str = os.getenv('TWITCH_CLIENT_SECRET')  # The CLIENT SECRET from the Twitch Dev Console
BOT_ID = "1388303571"  # The Account ID of the bot user...
OWNER_ID = "68184174"  # Your personal User ID..

# Characters to use for garbling text
GARBLE_CHARS = string.ascii_letters + string.digits + "!@#$%^&*()_+=-,/?<>:;|\\[]{}"
PROMO_CONFIG_PATH = Path(__file__).with_name("promo_messages.json")

def glitch_text(text: str) -> str:
    """Replaces each character in a string with a random garbled character."""
    garbled_message = ""
    for _ in text:
        garbled_message += random.choice(GARBLE_CHARS)
    return garbled_message


def _normalize_promo_entry(entry: object, *, index: int) -> dict[str, object] | None:
    """Validate a periodic message entry from the JSON config."""
    if not isinstance(entry, dict):
        LOGGER.warning("Skipping promo entry %s because it is not an object.", index + 1)
        return None

    interval = entry.get("interval_minutes")
    messages = entry.get("messages")

    if not isinstance(interval, (int, float)) or interval <= 0:
        LOGGER.warning("Skipping promo entry %s because interval_minutes is invalid.", index + 1)
        return None

    if isinstance(messages, str):
        normalized_messages = [messages.strip()]
    elif isinstance(messages, list):
        normalized_messages = [str(message).strip() for message in messages]
    else:
        LOGGER.warning("Skipping promo entry %s because messages is invalid.", index + 1)
        return None

    normalized_messages = [message for message in normalized_messages if message]
    if not normalized_messages:
        LOGGER.warning("Skipping promo entry %s because it has no usable messages.", index + 1)
        return None

    name = entry.get("name") or f"promo-{index + 1}"
    randomize = bool(entry.get("randomize", True))

    return {
        "name": str(name),
        "interval_minutes": float(interval),
        "messages": normalized_messages,
        "randomize": randomize,
    }

# Our main Bot class
class Bot(commands.AutoBot):
    def __init__(self, *, token_database: asqlite.Pool, subs: list[eventsub.SubscriptionPayload]) -> None:
        self.token_database = token_database
        self.initial_subs_count = len(subs)

        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix="!",
            subscriptions=subs,
            force_subscribe=True,
            redirect_uri="http://localhost:4343/oauth/callback",
            scopes=["user:read:chat", "user:write:chat", "user:bot"],
        )

    async def setup_hook(self) -> None:
        print("SETTING UP: Adding MyComponent...")
        await self.add_component(MyComponent(self))

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)
        print(f"BOT READY: {self.initial_subs_count} initial subscriptions.", flush=True)

        if self.initial_subs_count == 0:
            try:
                # In TwitchIO 3.1.0, we use the Scopes helper and the adapter
                scopes = twitchio.Scopes(
                    user_read_chat=True,
                    user_write_chat=True,
                    channel_bot=True
                )
                auth_url = self.adapter.get_authorization_url(scopes=scopes)
                
                print("\n" + "="*50, flush=True)
                print("NO ACTIVE SUBSCRIPTIONS FOUND!", flush=True)
                print("Please authorize the bot to read messages in your channel:", flush=True)
                print(f"{auth_url}", flush=True)
                print("="*50 + "\n", flush=True)
            except Exception as e:
                print(f"EXCEPTION generating Auth URL: {e}", flush=True)

    async def event_error(self, payload: twitchio.payloads.EventErrorPayload) -> None:
        # In TwitchIO 3.x, event_error receives an EventErrorPayload
        print(f"ERROR EVENT: {payload.event} | Message: {payload.message} | Error: {payload.error}", flush=True)

    async def event_oauth_authorized(self, payload: twitchio.authentication.UserTokenPayload) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)

        if not payload.user_id:
            return

        if payload.user_id == self.bot_id:
            return

        # A list of subscriptions we would like to make to the newly authorized channel...
        subs: list[eventsub.SubscriptionPayload] = [
            eventsub.ChatMessageSubscription(broadcaster_user_id=payload.user_id, user_id=self.bot_id),
        ]

        resp: twitchio.MultiSubscribePayload = await self.multi_subscribe(subs)
        if resp.errors:
            LOGGER.warning("Failed to subscribe to: %r, for user: %s", resp.errors, payload.user_id)

    async def add_token(self, token: str, refresh: str) -> twitchio.authentication.ValidateTokenPayload:
        # Make sure to call super() as it will add the tokens interally and return us some data...
        resp: twitchio.authentication.ValidateTokenPayload = await super().add_token(token, refresh)

        # Store our tokens in a simple SQLite Database when they are authorized...
        query = """
        INSERT INTO tokens (user_id, token, refresh)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            token = excluded.token,
            refresh = excluded.refresh;
        """

        async with self.token_database.acquire() as connection:
            await connection.execute(query, (resp.user_id, token, refresh))

        LOGGER.info("Added token to the database for user: %s", resp.user_id)
        return resp


# Component containing commands
class MyComponent(commands.Component):
    # You can use Components within modules for a more organized codebase and hot-reloading.

    def __init__(self, bot: Bot) -> None:
        print("COMPONENT INITIALIZING: MyComponent")
        self.bot = bot
        self.active_chatters: set[str] = set()
        self._promo_config_path = PROMO_CONFIG_PATH
        self._promo_tasks: list[asyncio.Task[None]] = []
        self._promo_entries: list[dict[str, object]] = []

    def _get_broadcaster(self) -> PartialUser | User | None:
        if self.bot.owner is not None:
            return self.bot.owner

        if not self.bot.owner_id:
            return None

        return PartialUser(id=self.bot.owner_id, http=self.bot._http)

    def _load_promo_entries(self) -> list[dict[str, object]]:
        if not self._promo_config_path.exists():
            LOGGER.warning("Promo config file not found at %s", self._promo_config_path)
            return []

        try:
            raw_config = json.loads(self._promo_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            LOGGER.error("Failed to parse promo config %s: %s", self._promo_config_path, exc)
            return []
        except OSError as exc:
            LOGGER.error("Failed to read promo config %s: %s", self._promo_config_path, exc)
            return []

        if isinstance(raw_config, dict):
            entries = raw_config.get("periodic_messages", [])
        elif isinstance(raw_config, list):
            entries = raw_config
        else:
            LOGGER.error("Promo config must be a list or a dict containing 'periodic_messages'.")
            return []

        if not isinstance(entries, list):
            LOGGER.error("Promo config 'periodic_messages' must be a list.")
            return []

        normalized_entries: list[dict[str, object]] = []
        for index, entry in enumerate(entries):
            normalized_entry = _normalize_promo_entry(entry, index=index)
            if normalized_entry is not None:
                normalized_entries.append(normalized_entry)

        return normalized_entries

    async def _stop_promo_tasks(self) -> None:
        if not self._promo_tasks:
            return

        tasks = list(self._promo_tasks)
        self._promo_tasks.clear()

        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_promo_entry(self, entry: dict[str, object]) -> None:
        await self.bot.wait_until_ready()

        name = str(entry["name"])
        interval_seconds = float(entry["interval_minutes"]) * 60.0
        messages = [str(message) for message in entry["messages"]]
        randomize = bool(entry.get("randomize", True))

        LOGGER.info("Starting promo task '%s' every %s minutes.", name, entry["interval_minutes"])

        try:
            while True:
                await asyncio.sleep(interval_seconds)

                message = random.choice(messages) if randomize else messages[0]
                if len(message) > 500:
                    LOGGER.warning("Skipping promo task '%s' because the message exceeds Twitch's 500 character limit.", name)
                    continue

                broadcaster = self._get_broadcaster()
                if broadcaster is None:
                    LOGGER.warning("Skipping promo task '%s' because the broadcaster could not be resolved.", name)
                    continue

                try:
                    await broadcaster.send_message(message=message, sender=self.bot.bot_id)
                    LOGGER.info("Sent promo task '%s' message.", name)
                except Exception as exc:
                    LOGGER.exception("Failed to send promo task '%s' message: %s", name, exc)
        except asyncio.CancelledError:
            LOGGER.info("Promo task '%s' stopped.", name)
            raise

    async def _reload_promo_tasks(self) -> None:
        await self._stop_promo_tasks()
        self._promo_entries = self._load_promo_entries()

        for entry in self._promo_entries:
            task = asyncio.create_task(self._run_promo_entry(entry))
            self._promo_tasks.append(task)

    async def component_load(self) -> None:
        await self._reload_promo_tasks()

    async def component_teardown(self) -> None:
        await self._stop_promo_tasks()

    @commands.Component.listener()
    async def event_chat_message(self, payload: twitchio.ChatMessage) -> None:

        bot = self.bot
        print(f"COMPONENT EVENT: {payload.chatter.name}: {payload.text}", flush=True)

        if payload.chatter.id == bot.bot_id:
            return

        # Explicitly handle commands
        await bot.handle_commands(payload)

        """For Logging Purposes."""
        print(f"[{payload.broadcaster.name}] - {payload.chatter.name}: {payload.text}")

        """For Parsing Purposes."""
        parsedMessage = re.split(r'\W+', payload.text.lower())
        # print(parsedMessage)

        """Garble message with a 1 in 50 chance"""
        if random.randint(1, 50) == 1:
            print(f"Garbling message from {payload.chatter.name}")
            garbled_content = glitch_text(payload.text)
            response = f"ATTENTION {payload.chatter.name}! ERROR: Message Integrity Compromised - {garbled_content}"
            await payload.respond(response)

        """Porygon Mentioned? Notify with a 1 in 10 chance"""
        if "porygon" in payload.text.lower() and random.randint(1, 10) == 1:
            await payload.respond("NOTICE: Superior Entity Mentioned!")

        """Blastoise Mentioned? Notify with a 1 in 10 chance"""
        if "blastoise" in payload.text.lower() and random.randint(1, 10) == 1:
            await payload.respond("NOTICE: Big Man Blastoise Mentioned!")

        """Lag Detected? Always notify."""
        lagTerms = ["lag", "lagging", "lagged"]
        if any(term in payload.text.lower() for term in lagTerms) and random.randint(1, 10) == 1:
            await payload.respond("ALERT: Lag Detected - Run Diagnostics...")

        """Greet Chatters on Hello messages"""
        greetingTerms = ["hello", "hi", "hey", "yo", "sup", "greetings", "good morning", "good afternoon", "good evening", "howdy", "how are you", "what's up"]

        """ Debug Prints """
        # print(any(term in payload.text.lower() for term in greetingTerms if ' ' in term))
        # print(any(word in greetingTerms for word in parsedMessage if ' ' not in word))

        if any(term in payload.text.lower() for term in greetingTerms if ' ' in term) or any(word in greetingTerms for word in parsedMessage if ' ' not in word):
            if payload.chatter.name not in self.active_chatters:
                await payload.respond(f"GREETING: Hello {payload.chatter.name}! Welcome to the stream, hope you enjoy your time here! itsmej18Love")

        self.active_chatters.add(payload.chatter.name)

    @commands.command()
    async def porygonbot(self, ctx: commands.Context) -> None:
        """A simple command which introduces the bot.

        !porygonbot
        """
        await ctx.send("NOTICE: I am Porygon Bot, a Twitch chat bot created by Joji! You can use commands like !lurk, !shinyroll, and !socials to interact with me! If you have any suggestions, feel free to let Joji know!")

    @commands.command()
    async def lurk(self, ctx: commands.Context) -> None:
        """A simple command which acknowledges the user going to lurk.

        !lurk
        """
        await ctx.send(f"LURK ACKNOWLEDGED - Thanks {ctx.chatter.name}!")

    # @commands.command()
    # async def uptime(self, ctx: commands.Context) -> None:
    #     """A simple command which tells how long the stream has been live.

    #     !uptime
    #     """
    #     stream = await ctx.get_stream()
    #     if stream is None:
    #         await ctx.send("ERROR: The stream is currently offline.")
    #         return

    #     uptime = twitchio.utils.format_timedelta(stream.uptime)
    #     await ctx.send(f"NOTICE: Stream has been live for {uptime}")

    @commands.group(invoke_fallback=True)
    async def socials(self, ctx: commands.Context) -> None:
        """Group command for our social links.

        !socials
        """
        await ctx.send("NOTICE: You can find all socials here: https://itsmejoji.com")

    @commands.command(name="discord")
    async def discord(self, ctx: commands.Context) -> None:
        """Sub command of socials that sends only our discord invite.

        !discord
        """
        await ctx.send("NOTICE: Join the Discord! https://discord.gg/N3QAw5ECSq")

    @commands.command()
    async def shinyroll(self, ctx: commands.Context) -> None:
        """A command that gives information about Shiny Luck.

        !shinyroll
        """
        shinyRoll = random.randint(1, 8192)

        if shinyRoll == 8192:
            await ctx.send(f"RESULT: AMAZING {ctx.chatter.name}! You rolled {shinyRoll}!!!")
        else:
            await ctx.send(f"RESULT: {ctx.chatter.name} rolled {shinyRoll}!")

    @commands.command()
    async def bingo(self, ctx: commands.Context) -> None:
        """A command that gives the current bingo link.

        !bingo
        """
        async with self.bot.token_database.acquire() as connection:
            row = await connection.fetchone("SELECT value FROM config WHERE key = 'bingo'")
            if row:
                await ctx.send(f"NOTICE: The current Bingo Link is: {row['value']}")
            else:
                await ctx.send("ERROR: No Bingo Link has been set yet.")

    @commands.command()
    async def setbingo(self, ctx: commands.Context, *, link: str) -> None:
        """A command that updates the bingo link. Only usable by the owner.

        !setbingo <link>
        """
        if str(ctx.author.id) != self.bot.owner_id:
            return

        async with self.bot.token_database.acquire() as connection:
            await connection.execute(
                "INSERT INTO config (key, value) VALUES ('bingo', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (link,)
            )

        await ctx.send(f"NOTICE: Bingo Link has been updated to: {link}")

    @commands.command()
    async def docket(self, ctx: commands.Context) -> None:
        """A command that gives the current docket link.

        !docket
        """
        await ctx.send("NOTICE: Today's Docket can be found here: https://itsmejoji.github.io/StreamAssets/docket.html")

    @commands.command()
    async def reloadpromos(self, ctx: commands.Context) -> None:
        """Reload the periodic message config file.

        !reloadpromos
        """
        if str(ctx.author.id) != self.bot.owner_id:
            return

        await self._reload_promo_tasks()
        await ctx.send("NOTICE: Periodic message config reloaded.")


async def setup_database(db: asqlite.Pool) -> tuple[list[tuple[str, str]], list[eventsub.SubscriptionPayload]]:
    print("DATABASE SETUP STARTING...", flush=True)
    # Create our token table, if it doesn't exist..
    # You should add the created files to .gitignore or potentially store them somewhere safer
    # This is just for example purposes...

    query = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""
    config_query = """CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY, value TEXT NOT NULL)"""
    
    async with db.acquire() as connection:
        await connection.execute(query)
        await connection.execute(config_query)

        # Seed default bingo link if not exists
        await connection.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('bingo', 'https://bingo.itsmejoji.com')")

        # Fetch any existing tokens...
        rows: list[sqlite3.Row] = await connection.fetchall("""SELECT * from tokens""")

        tokens: list[tuple[str, str]] = []
        subs: list[eventsub.SubscriptionPayload] = []

        for row in rows:
            print(f"DATABASE: Found token for user {row['user_id']}")
            tokens.append((row["token"], row["refresh"]))

            if row["user_id"] == BOT_ID:
                print(f"DATABASE: Skipping subscription for bot ID {BOT_ID}")
                continue

            print(f"DATABASE: Adding subscription for broadcaster {row['user_id']}", flush=True)
            subs.extend([eventsub.ChatMessageSubscription(broadcaster_user_id=row["user_id"], user_id=BOT_ID)])

    print(f"DATABASE SETUP COMPLETE: {len(tokens)} tokens, {len(subs)} subscriptions.", flush=True)
    return tokens, subs


# Our main entry point for our Bot
# Best to setup_logging here, before anything starts
def main() -> None:
    twitchio.utils.setup_logging(level=logging.INFO)

    async def runner() -> None:
        async with asqlite.create_pool("tokens.db") as tdb:
            tokens, subs = await setup_database(tdb)

            async with Bot(token_database=tdb, subs=subs) as bot:
                for pair in tokens:
                    await bot.add_token(*pair)

                await bot.start(load_tokens=False)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down due to KeyboardInterrupt")


if __name__ == "__main__":
    main()
