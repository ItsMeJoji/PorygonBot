# PorygonBot - Twitch Chat Bot

PorygonBot is a Twitch chat bot with a few automated responses and some simple chat commands.

## Features

- **Automated Greetings**: Greets chatters when they say hello or something similar.
- **Lag Monitoring**: Watches for "lag" mentions and alerts the streamer.
- **Porygon Mentions**: Replies to mentions of "Porygon".
- **Message Garbling**: Occasionally scrambles a message for fun.
- **Periodic Chat Messages**: Sends timed promotional messages from a JSON config file.
- **Mini-games**: Includes a `!shinyroll` command to test your luck against standard shiny odds (1 in 8192).

## Commands

- `!porygonbot`: Prints a short bot intro.
- `!lurk`: Acknowledges that you are lurking.
- `!socials`: Shows the streamer's social links.
- `!discord`: Shows the Discord invite link.
- `!shinyroll`: Rolls a number from 1 to 8192.
- `!bingo`: Shows the current bingo link.
- `!setbingo <link>`: (Owner only) Update the bingo link.
- `!reloadpromos`: (Owner only) Reload the periodic message config file without restarting.

## Setup

### Prerequisites

- Python 3.8+
- [Twitch Developer Account](https://dev.twitch.tv/) to get Client ID and Client Secret.

### Installation

1. Clone the repository and navigate to the project directory.
2. Install the required dependencies:

```powershell
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root with your Twitch credentials:

```env
TWITCH_CLIENT_ID=your_client_id
TWITCH_CLIENT_SECRET=your_client_secret
```

*Note: `BOT_ID` and `OWNER_ID` are set in `porygon.py`.*

### Periodic Messages

The bot reads periodic chat messages from [`promo_messages.json`](./promo_messages.json).

A typical entry looks like this:

```json
{
  "name": "socials",
  "interval_minutes": 30,
  "messages": [
    "NOTICE: You can find all socials here: https://itsmejoji.com"
  ],
  "randomize": false
}
```

- `interval_minutes` controls how often the message is sent.
- `messages` can be a single message or a list of messages.
- `randomize` picks a random message from the list when `true`.

After editing the file, restart the bot or use `!reloadpromos` to reload it without restarting.

### Running the Bot

Run the bot with:

```powershell
python porygon.py
```

The bot stores tokens in a local `tokens.db` file.
