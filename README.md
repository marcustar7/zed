# Discord Report Bot

Watches specific channels across multiple Discord servers and sends you (and
anyone else you choose) a daily DM digest — plus a full PDF — covering
announcements, news, events, and livestreams (both Twitch/YouTube-style links
and Discord's native "Go Live" streaming).

---

## 1. Create the bot application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application**. Name it whatever you like.
2. In the left sidebar, click **Bot** → **Add Bot**.
3. Under **Privileged Gateway Intents**, turn ON:
   - **Message Content Intent** (required to read message text)
   - **Server Members Intent** is not required for this bot, you can leave it off.
4. Click **Reset Token** and copy the token somewhere safe — you'll paste it into `.env` shortly. Treat it like a password; never commit it to GitHub.

## 2. Generate an invite link (per server)

1. In the Developer Portal, go to **OAuth2 → URL Generator**.
2. Under **Scopes**, check `bot`.
3. Under **Bot Permissions**, check only:
   - `View Channels`
   - `Read Message History`
4. Copy the generated URL and send it to whoever administers each server you have permission to monitor. They'll use it to add the bot — it doesn't need to post anything, so this minimal permission set is all it needs.

## 3. Get the IDs you need

Turn on Developer Mode in Discord: **User Settings → Advanced → Developer Mode**.

Then right-click to copy IDs for:
- Each **server** (guild) you want to watch
- Each **channel** within it you want monitored
- Your own **user account** (and anyone else who should receive the DM report)

## 4. Configure the bot

```bash
cp .env.example .env
cp config.example.json config.json
```

Edit `.env` and paste your bot token:
```
DISCORD_TOKEN=the-token-you-copied
```

Optionally, also add an OpenAI key (see [AI cleanup & translation](#7-ai-cleanup--translation-optional) below) if you want the daily report cleaned up and translated to English automatically:
```
OPENAI_API_KEY=the-openai-key-you-copied
```

Edit `config.json`:
- Add one entry under `"guilds"` per server, with its channels tagged by `category`:
  `"announcements"`, `"news"`, `"events"`, or `"livestreams"`
- Set `"track_native_streams": true` on any guild where you also want Discord's
  built-in "Go Live" screen-share detected (via voice channel activity)
- List every recipient's user ID under `"recipients"`
- `report_hour_utc` / `report_minute_utc` control what time the daily digest goes out

> **Note on DMs:** the bot can only DM a user if that user shares a server with
> the bot and hasn't disabled DMs from server members. If a recipient isn't in
> any of the watched servers, add them to at least one, or have them send the
> bot a DM first.

## 5. Run it locally to test

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

You should see `Logged in as YourBotName`. Post a test message in a watched
channel — it'll get silently captured. The digest only sends once per day at
the configured time, so for a quick end-to-end test you can temporarily set
`report_hour_utc`/`report_minute_utc` to a couple minutes from now.

## 6. Deploy to Railway (keeps it running 24/7)

1. Push this folder to a new GitHub repo (the `.gitignore` already excludes your token and config, so double-check `config.json` and `.env` aren't committed — if you want your config to persist, set it up as a Railway **variable** or **volume** instead of a plain file, or just re-add it via Railway's shell after deploying).
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → select your repo.
3. In the project's **Variables** tab, add `DISCORD_TOKEN` with your token, and `OPENAI_API_KEY` too if you're using AI cleanup (see below).
4. Railway will detect the `Procfile` and run `python bot.py` automatically. If it doesn't, set the **Start Command** manually to `python bot.py` under Settings.
5. `config.json` only contains server/channel IDs and recipient user IDs — no secrets — so it's meant to be committed and tracked in git normally, and it'll deploy along with the rest of the code automatically.

Once deployed, Railway keeps the process running continuously, and you'll get your first DM digest at the next configured report time.

## 7. AI cleanup & translation (optional)

If `OPENAI_API_KEY` is set in `.env` (or as a Railway variable), the bot sends each day's captured messages to OpenAI in one batched request before building the report. It fixes typos/grammar, translates anything non-English into clear English, and tightens wording — without inventing facts, links, or details that weren't in the original message.

- **Get a key**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys). This is separate from a ChatGPT subscription — you'll need to add a small prepaid balance to the account.
- **Model**: defaults to `gpt-4o-mini`, a cheap, capable model well suited to this kind of cleanup task. Override it by setting `OPENAI_MODEL` in `.env` if you want to try a different one.
- **Cost**: for a daily digest of this size (a few dozen short messages), expect a small fraction of a cent to a few cents per day — negligible next to hosting.
- **Fallback behavior**: if the key is missing, invalid, or the API call fails for any reason, the report is still sent — just with the raw, untranslated text instead. A bad API call never blocks the digest.
- **Your stored data is untouched**: cleanup only affects the copy of the text used to build that day's report. The raw, original message text stays in `reports.db` exactly as captured.

## Customizing further

- **Change categories**: add more `category` values and matching entries in `CATEGORY_LABELS` in `digest.py`.
- **Change report frequency**: adjust the `@tasks.loop(hours=24)` in `bot.py`.
- **Add more servers**: just add another object under `"guilds"` in `config.json` — no code changes needed.
