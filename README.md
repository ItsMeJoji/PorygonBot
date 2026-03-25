# PorygonBot - Twitch Chat Bot

PorygonBot is an automated Twitch chat assistant designed to enhance stream interaction with unique features and interactive commands.

## Features

- **Automated Greetings**: Greets chatters when they say hello or a similar phrase.
- **Lag Monitoring**: Automatically detects "lag" mentions and alerts the streamer.
- **Superior Entity Recognition**: Responds to any mention of "Porygon".
- **Message Integrity Audits**: Occasionally garbles messages to simulate "errors" in transmission.
- **Mini-games**: Includes a `!shinyroll` command to test your luck against standard shiny odds (1 in 8192).

## Commands

- `!porygonbot`: Introduction to the bot.
- `!lurk`: Acknowledge that you are lurking.
- `!socials`: Get links to the streamer's social media.
- `!discord`: Get the Discord invite link.
- `!shinyroll`: Roll a number from 1 to 8192 to see if you find a "shiny".

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

*Note: `BOT_ID` and `OWNER_ID` are currently configured in `porygon.py`.*

### Running the Bot

Start the bot by running:

```powershell
python porygon.py
```

The bot will automatically manage tokens in a local `tokens.db` file.
