"""

This bot can be restarted as many times without needing to subscribe or worry about tokens:
- Tokens are stored in '.tio.tokens.json' by default
- Subscriptions last 72 hours after the bot is disconnected and refresh when the bot starts.

"""
import os
import re
import asyncio
import logging
import random
import string
from typing import TYPE_CHECKING

import asqlite

import twitchio
from twitchio import eventsub
from twitchio.ext import commands


if TYPE_CHECKING:
    import sqlite3


LOGGER: logging.Logger = logging.getLogger("Bot")

# Consider using a .env or another form of Configuration file!
CLIENT_ID: str = os.getenv('TWITCH_CLIENT_ID')  # The CLIENT ID from the Twitch Dev Console
CLIENT_SECRET: str = os.getenv('TWITCH_CLIENT_SECRET')  # The CLIENT SECRET from the Twitch Dev Console
BOT_ID = "1388303571"  # The Account ID of the bot user...
OWNER_ID = "68184174"  # Your personal User ID..

# Characters to use for garbling text
GARBLE_CHARS = string.ascii_letters + string.digits + "!@#$%^&*()_+=-,/?<>:;|\\[]{}"

def glitch_text(text: str) -> str:
    """Replaces each character in a string with a random garbled character."""
    garbled_message = ""
    for _ in text:
        garbled_message += random.choice(GARBLE_CHARS)
    return garbled_message

# Our main Bot class
class Bot(commands.AutoBot):
    def __init__(self, *, token_database: asqlite.Pool, subs: list[eventsub.SubscriptionPayload]) -> None:
        self.token_database = token_database

        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix="!",
            subscriptions=subs,
            force_subscribe=True,
        )

    async def setup_hook(self) -> None:
        await self.add_component(MyComponent(self))

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

    async def event_ready(self) -> None:
        LOGGER.info("Successfully logged in as: %s", self.bot_id)

# Component containing commands
class MyComponent(commands.Component):
    # You can use Components within modules for a more organized codebase and hot-reloading.

    def __init__(self, bot: Bot) -> None:

        self.bot = bot

    @commands.Component.listener()
    async def event_message(self, payload) -> None:

        bot = self.bot

        if payload.chatter == bot.user:
            return

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
            await payload.respond(f"GREETING: Hello {payload.chatter.name}! Welcome to the stream, hope you enjoy your time here! itsmej18Love")

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


async def setup_database(db: asqlite.Pool) -> tuple[list[tuple[str, str]], list[eventsub.SubscriptionPayload]]:
    # Create our token table, if it doesn't exist..
    # You should add the created files to .gitignore or potentially store them somewhere safer
    # This is just for example purposes...

    query = """CREATE TABLE IF NOT EXISTS tokens(user_id TEXT PRIMARY KEY, token TEXT NOT NULL, refresh TEXT NOT NULL)"""
    async with db.acquire() as connection:
        await connection.execute(query)

        # Fetch any existing tokens...
        rows: list[sqlite3.Row] = await connection.fetchall("""SELECT * from tokens""")

        tokens: list[tuple[str, str]] = []
        subs: list[eventsub.SubscriptionPayload] = []

        for row in rows:
            tokens.append((row["token"], row["refresh"]))

            if row["user_id"] == BOT_ID:
                continue

            subs.extend([eventsub.ChatMessageSubscription(broadcaster_user_id=row["user_id"], user_id=BOT_ID)])

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