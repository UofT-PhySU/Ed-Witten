# Ed Witten Bot — Developer Documentation

**Bot name:** Ed Witten  
**Server:** PhySU (Physics Student Union) Discord — University of Toronto  
**Language:** Python 3.10+  
**Main file:** `bot.py`  
**Written by:** Claude Sonnet 4.6
---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Setup and Configuration](#setup-and-configuration)
4. [Environment Variables](#environment-variables)
5. [Data Files](#data-files)
6. [Architecture](#architecture)
7. [Global Constants and State](#global-constants-and-state)
8. [Utility Functions](#utility-functions)
9. [Background Tasks](#background-tasks)
10. [Command Reference](#command-reference)
11. [Passive Triggers](#passive-triggers)
12. [Verification System](#verification-system)
13. [AI System](#ai-system)
14. [Helper Modules](#helper-modules)
15. [Known Issues and TODOs](#known-issues-and-todos)
16. [Adding New Commands](#adding-new-commands)

---

## Overview

Ed Witten is a discord.py bot for the PhySU server. Its responsibilities include:

- **Member verification** — new members paste a verification key to receive the Member role and have their nickname set
- **Course management** — creating course channels and reaction roles, removing course roles
- **Quote management** — storing, displaying, and retrieving quotes said by students and professors
- **Event announcements** — pulling events from a public Google Calendar iCal feed and announcing them one hour before they start
- **Colloquium management** — tracking upcoming and past PhySU colloquia
- **Bookshelf management** — listing books available in the PhySU physical bookshelf
- **AI responses** — an Ollama-backed language model responds to `!EdGPT` and replies to its own messages
- **Timed messages** — moderators can schedule messages to be sent in any channel at a future time
- **Moderation utilities** — purging channels, editing messages, archiving categories

---

## Project Structure

```
/
├── bot.py                    # Main bot file
├── dictionaryHelpers.py      # CSV ↔ dict helpers (get_dict, save_dict, etc.)
├── timeManagement.py         # Time/date conversion helpers
├── execs.csv                 # Executive team roster
├── censored.csv              # Blocked word list
├── physuquotes.csv           # Quotes database
├── physubooks.csv            # Bookshelf database
├── physucolloquia.csv        # Upcoming colloquia
├── physucolloquiaarchive.csv # Past colloquia
├── tmes.csv                  # Scheduled (timed) messages
├── joinlog.csv               # Verification log
├── bestie.csv                # "So true bestie" counter
├── botuplog.txt              # Bot startup log
├── .env                      # Secret keys and config (never commit)
└── messages/
    ├── helpText.txt          # Main help system data (pipe-delimited)
    ├── general-help.txt      # General help message template
    ├── mod-help.txt          # Mod-only help message template
    └── *.txt                 # Pre-written messages for !sendmessage
```

---

## Setup and Configuration

### Requirements

```bash
pip install discord.py python-dotenv numpy icalendar requests python-dateutil
```

Ollama must also be installed and available on `PATH` for AI responses. The bot launches it automatically via `subprocess.Popen` on startup.

### Running the bot

```bash
python bot.py
```

Set `DEBUG_MODE = True` at the top of `bot.py` to prevent the bot from connecting to Discord (useful for testing utility functions locally).

Set `GENERATE = False` to disable AI responses without modifying the prompt or model config.

Set `ANNOUNCER = False` to disable calendar event announcements (currently the default — set to `True` to enable).

---

## Environment Variables

All secrets and configuration are loaded from a `.env` file in the project root via `python-dotenv`. Never commit this file.

| Variable | Type | Description |
|---|---|---|
| `SECRET_KEY` | string | Discord bot token |
| `NUM1`, `NUM2`, `NUM3`, `NUM4` | int | Parameters for verification key arithmetic |
| `CAL_URL` | string | iCal URL for the PhySU Google Calendar |
| `MODEL` | string | Ollama model name (e.g. `mistral`, `llama3.1:8b`) |
| `OLLAMA_URL` | string | Ollama API endpoint (default: `http://localhost:11434/api/chat`) |
| `PROMPT` | string | System prompt for the AI persona |

### Example `.env`

```
SECRET_KEY=your-discord-bot-token
NUM1=12345
NUM2=67890
NUM3=11111
NUM4=22222
CAL_URL=https://calendar.google.com/calendar/ical/...
MODEL=mistral
OLLAMA_URL=http://localhost:11434/api/chat
PROMPT=You are Ed Witten, a Discord bot for PhySU...
```

---

## Data Files

All CSV data files use `|` as the delimiter (handled by `dictionaryHelpers.py`). The first row is the header. Each column becomes a list in the dictionary returned by `get_dict`.

### physuquotes.csv
| Column | Description |
|---|---|
| `Quote` | The quote text |
| `Author` | Person who said it |
| `Date` | Date string in any format; `-1` means no date |

### physubooks.csv
| Column | Description |
|---|---|
| `Title` | Book title |
| `Author` | Author name |
| `Tags` | Comma-separated tags |

### physucolloquia.csv / physucolloquiaarchive.csv
| Column | Description |
|---|---|
| `Title` | Talk title |
| `Speaker` | Speaker name |
| `Time` | Unix timestamp |
| `Room` | Room number/location |

### tmes.csv
| Column | Description |
|---|---|
| `Time` | Unix timestamp for when to send |
| `Author` | Discord name of who scheduled it |
| `Message` | Message text |
| `Channel` | Channel ID to send to |

### execs.csv
Three columns, no header: `Position`, `Name`, `Discord tag`, `Office hour`.  
Loaded at startup into `EXEC_POSITIONS` dict: `{position: (name, tag, office_hour)}`.

### censored.csv
Single row of comma-separated words. Any message containing one of these words triggers a warning and message deletion.

### joinlog.csv
One row per verified member: `discord_name, token1, token2, nickname, timestamp`.  
Used to detect duplicate verification key usage.

### messages/helpText.txt
Pipe-delimited file with columns: `h | modq | htext | ismod | desc`.  
- `h`: command identifier used in `!edhelp;identifier`
- `modq`: `True` if mod-only, `False` otherwise
- `htext`: full help text for all users
- `ismod`: additional help text shown only to mods
- `desc`: one-line description shown in the command list

---

## Architecture

The bot uses discord.py's async event model. All message handling happens in a single `on_message` function (~900 lines). Commands are a series of `if message.content.startswith(...)` checks — there is no command framework (no `@bot.command` decorators).

Background tasks run on independent loops using `discord.ext.tasks`.

```
on_ready()
├── subprocess.Popen('ollama serve')   # start Ollama
├── timedmessages.start()              # every 1 min
├── archiveColloquia.start()           # every 1 hour
├── hourlyQuote.start()                # every 1 min (stub)
└── announce_events.start()            # every 1 min

on_message()
├── Verification ($key)
├── AI response (!EdGPT / reply to bot / random 1%)
├── Commands (!quote, !events, !books, etc.)
├── Passive keyword triggers (duck, bot, zhan su, etc.)
└── Refresh channel handler
```

---

## Global Constants and State

| Name | Description |
|---|---|
| `DEBUG_MODE` | If `True`, bot does not connect to Discord |
| `GENERATE` | If `False`, AI responses are disabled |
| `ANNOUNCER` | If `False`, calendar event announcements are suppressed |
| `announced` | `set()` of event UIDs already announced this session; resets on restart |
| `context` | `dict` mapping channel ID → list of AI message dicts (rolling context window) |
| `WINDOW` | Number of messages to keep in AI context (default: 10) |
| `SEED` | List of example exchanges prepended to AI context for every new channel |
| `ROLES` | Dict mapping role name → role ID for `Member` and `New User` |
| `REFRESH_CHANNELS` | List of channel IDs whose messages are auto-deleted after `REFRESH_DELAY` minutes |
| `REFRESH_DELAY` | Minutes before messages in refresh channels are deleted (default: 30) |
| `LOG_CHANNEL` | Channel ID for the message deletion log |
| `VERIFICATION_CHANNEL` | Channel ID where members paste their verification keys |
| `ACADEMIC_ANNOUNCE` | Channel ID for calendar event announcements |
| `EMBED_COLOUR` | Hex colour for Discord embeds (purple: `0x8f279b`) |
| `TORONTO` | `ZoneInfo("America/Toronto")` timezone object |
| `EXEC_POSITIONS` | Dict loaded from `execs.csv`: `{position: (name, tag, office_hour)}` |
| `CENSORED` | List of blocked words loaded from `censored.csv` |

---

## Utility Functions

### `get_timestamp() → str`
Returns current local time as `MM/DD/YY HH:MM`.

### `decode(raw_name: str) → str`
Reverses the verification key name encoding. The encoding flips each ASCII digit (0↔9, 1↔8, etc.) and concatenates the ASCII codes. `decode` reconstructs the original name from this encoded string.

### `getjoinlogs() → set`
Reads `joinlog.csv` and returns a set of `(token1, token2)` tuples representing all previously used verification tokens. Used to detect duplicate key submissions.

### `get_timestamp() → str`
Returns the current local time formatted as `MM/DD/YY HH:MM`.

### `purge_refresh_channels(mnum=200, refreshids=REFRESH_CHANNELS)`
Deletes up to `mnum` non-pinned messages from each channel in `refreshids`, logging each to `LOG_CHANNEL` first.

### `log_message(message)`
Sends a sanitized single-line copy of a message to `LOG_CHANNEL` with channel name, author, and timestamp.

### `create_course_channel(guild, name)`
Creates a text channel for a course code with appropriate category and role-based permissions. Supports: `PHY`, `MAT`, `APM`, `AST`, `JPH`, `JPE`. Channel names follow the pattern `{emoji}{course_code}` (e.g. `📘📖phy132`). Also creates the course role if it does not already exist.

### `get_category_key(course: str) → str`
Returns the category key for a course code. PHY courses return `PHY{level}` (e.g. `PHY1`); other departments return the 3-letter department code.

### `get_events() → list`
Fetches the PhySU iCal feed from `CAL_URL` and returns a list of `(uid, name, location, description, start_datetime)` tuples for all events. Normalizes all-day events and naive datetimes to UTC.

### `get_response(channel_id, message) → str`
Calls the Ollama API with the channel's rolling context window and returns the model's reply. Initializes new channels with the `SEED` example exchanges. Trims context to `WINDOW` messages after each exchange.

### `read_csv(file) → list`
Reads a CSV from a Discord attachment URL and returns it as a list of rows.

### `save_quotes(quotelist: dict)`
Writes the quotes dictionary to `physuquotes.csv` using `|` as delimiter. (Note: largely superseded by `save_dict` from `dictionaryHelpers.py`.)

### `savebestie(num)` / `getbestie() → int`
Write/read the "so true bestie" counter from `bestie.csv`.

---

## Background Tasks

### `timedmessages` — every 1 minute
Reads `tmes.csv` and sends any messages whose scheduled Unix timestamp has passed. Sent messages are removed from the file. If the target channel is not found, falls back to channel ID `959108984332234842` and pings `@Moderator`.

### `archiveColloquia` — every 1 hour
Moves past colloquia from `physucolloquia.csv` to `physucolloquiaarchive.csv`. A colloquium is considered past if its timestamp is more than one day ago (determined by `checkPastDay` from `timeManagement.py`). Both files are kept sorted by time.

### `hourlyQuote` — every 1 minute
Checks if the hour has changed. The actual quote-sending logic is commented out — this is a stub for future use.

### `announce_events` — every 1 minute
Fetches the iCal calendar and sends an `@here` announcement to `ACADEMIC_ANNOUNCE` for any event starting in approximately one hour (between 59 and 61 minutes away). Uses the `announced` set to prevent duplicate announcements. Only fires if `ANNOUNCER = True`.

---

## Command Reference

Commands are processed in `on_message`. Unless noted, commands work in any channel the bot can see. Arguments are separated by `;`.

### General commands (all users)

| Command | Description |
|---|---|
| `!website` | Posts the PhySU website and student resource links |
| `!exec` | Displays an embed with the executive team's names, Discord tags, and office hours |
| `!edwitten` | Ed introduces himself |
| `!screm` | Sends a random screm GIF |
| `!fortune [question]` | Magic 8-ball style random response |
| `!bestie` | Displays the current "so true bestie" count |
| `!edtime` | Displays the current server time |
| `!amogus` | Sends a random Among Us GIF and deletes the triggering message |
| `!removeohio` | Removes Ohio |
| `!oops` | Ed says "oops!" |
| `!EdGPT [message]` | Sends message to the AI; also triggered by replying to any of Ed's messages, or randomly at ~1% probability |
| `!removecourseroles` | Removes all course roles (PHY, MAT, APM, AST, JPH) from the sender |
| `!events` | Lists next 10 upcoming events from the calendar |
| `!events;[n]` | Lists next n upcoming events |
| `!quote` | Sends a random quote |
| `!quote;[n]` | Sends quote number n (1-indexed) |
| `!quote;-[n]` | Sends the n+1th-from-last quote |
| `!showquotes` | Lists quotes from the current year (10 per message) |
| `!showquotes;[year]` | Lists quotes from a specific year (e.g. `!showquotes;2024`) |
| `!showquotes;all` | Lists all quotes |
| `!addquote;[quote];[author]` | Adds a quote without a date |
| `!addquote;[quote];[author];[date]` | Adds a quote with a date (any format) |
| `!books` / `!showbooks` | Lists all books on the PhySU bookshelf |
| `!books;[Author/Title/Tags];[search term]` | Searches books by field |
| `!colloquia` | Lists upcoming PhySU colloquia |
| `!archivedcolloquia` | Lists past colloquia |
| `!edhelp` / `!help` | Shows command list (mod commands shown if moderator) |
| `!edhelp;[identifier]` | Shows detailed help for a specific command |
| `!edhelp;general` | Shows the general help message |
| `!user;[discord id]` | Looks up a member by their Discord user ID |
| `!courseSetupInstructions` | Posts a link to the course setup guide |

### Bookshelf committee / moderator commands

| Command | Description |
|---|---|
| `!addbook;[title];[author];[tags]` | Adds a book to the shelf |
| `!removebook;[n]` | Removes book number n |
| `!addbooktag;[n];[tag]` | Appends a tag to book n |
| `!replacebooktag;[n];[new tags]` | Replaces all tags on book n |

### Colloquium committee / moderator commands

| Command | Description |
|---|---|
| `!addcolloquium;[title];[speaker];[dd.mm.yy];[hh:mm];[room]` | Adds an upcoming colloquium |
| `!removecolloquium;[n]` | Removes colloquium number n |

### Moderator-only commands

| Command | Description |
|---|---|
| `!sendm;[text]` | Sends text as Ed in the current channel; supports attachments; deletes the command message |
| `!sendmessage [name]` | Sends the contents of `messages/[name].txt` as Ed |
| `!sendquote;[n]` | Sends quote n cleanly (no command text visible); deletes the command message |
| `!delquote;[n]` | Deletes quote number n |
| `!stmes;[dd.mm.yy];[hh:mm];[channel id];[text]` | Schedules a message for future delivery |
| `!showtmes` | Lists all scheduled messages with index, time, author, channel, and text |
| `!deltmes;[n]` | Deletes scheduled message number n |
| `!purgechannel` | Purges up to 200 messages in the default refresh channel |
| `!purgechannel;[n]` | Purges n messages in the current channel |
| `!purgechannel;[channel id];[n]` | Purges n messages in the specified channel |
| `!edit;[channel id];[message id];[new text]` | Edits one of Ed's messages |
| `!createcourses [codes...]` | Creates course channels for space-separated course codes |
| `!setupcourses` (+ 2 attachments) | Bulk course setup from CSV attachments (courses + message IDs) |
| `!delcat;[category name]` | Deletes a category and all its channels |
| `!archivecat;[category];[archive name]` | Moves a category's channels to an archive category (mod-only visibility) |
| `!newyearcat` | Creates all course categories if missing; sets permissions; moves reaction role channels |

### Verification (verification channel only)

| Input | Description |
|---|---|
| `$[key]` | Verifies a new member: validates key, sets nickname, assigns Member role, logs to `joinlog.csv`. Mods can use it to check key status without consuming it. Duplicate keys result in a ban. |

---

## Passive Triggers

These fire automatically on any message without a command prefix.

| Trigger | Behaviour |
|---|---|
| `so true bestie` (case-insensitive) | Increments bestie counter; gives user the "So True Bestie" role |
| `ivrii` | Reacts with `:ed:` emoji; sends a warning message |
| `duck` | Reacts with 🦆; replies "There are no ducks in MP" |
| `zhan su` | Reacts with `:ed:` and `:highschoolmath:`; replies with a Zhan Su quote (10% chance of a different reply) |
| `ikea` | Reacts with the IKEA custom emoji |
| `bot` | Reacts with `:ed:`; 20% chance of a Terminator gif, 30% chance of a short reply, 15% chance of an AI response |
| `spaghet` | Replies with `:spaghetti:` |
| `ed` (as a standalone word) | 10% chance of replying "sup" |
| Any word in `CENSORED` | Warns the user and deletes the message |
| `testmessage` or 0.01% random | Sends a random short reply (no ping) |
| Message in a `REFRESH_CHANNEL` | Logs the message, waits `REFRESH_DELAY` minutes, then deletes it |
| Numeric message in verification channel | Reminds user to include the `$` prefix |

---

## AI System

The AI uses a locally-running Ollama model. The bot launches `ollama serve` as a subprocess on startup.

**Trigger conditions** (any one of):
- Message starts with `!EdGPT`
- Message is a reply to one of Ed's messages
- Random 1% chance on any message
- Message contains "bot" and passes a further random check (15% of the time)

**Blocked channels:** Verification channel and refresh channels never trigger AI responses.

**Context:** Each channel maintains its own rolling window of the last `WINDOW` (10) message exchanges. New channels are seeded with `SEED` — a list of example exchanges that establish Ed's persona. Context is in-memory only and resets on bot restart.

**System prompt:** Loaded from `PROMPT` in `.env`. Controls Ed's persona, tone, and rules.

---

## Helper Modules

### `dictionaryHelpers.py`
Provides CSV ↔ dictionary conversion. Key functions used throughout:
- `get_dict(filename)` — reads a `|`-delimited CSV into `{column: [values]}` dict
- `save_dict(dict, filename)` — writes a dict back to CSV
- `makeDisplayMessage(dict, keys, boxsize, delims)` — formats a dict into paginated Discord code blocks
- `truncateDict(dict, indices)` — returns a dict with only the rows at given indices
- `truncationIndices(list, search_term)` — returns indices where search term appears
- `removeIndex(dict, n)` — removes row n from a dict
- `mergeTwoDictionaries(d1, d2)` — concatenates two same-schema dicts
- `removeMultipleFromDict(dict, indices)` — removes multiple rows by index
- `timeSortDict(dict)` — sorts dict rows by the `Time` column

### `timeManagement.py`
Provides time conversion helpers. Key functions:
- `convertDDMMYYToUnixTime(date, time)` — converts `dd.mm.yy` + `hh:mm` to Unix timestamp
- `printTheTimeFromDDMMYY(unix_timestamp, includeYear)` — formats a Unix timestamp as a human-readable string
- `checkPastDay(event_time, now)` — returns True if `event_time` is more than one day before `now`

---

## Known Issues and TODOs

- **Verification cryptography** — the current arithmetic check (`(token - NUM) % STEP == 0`) is weak. The code comment acknowledges this. Should be replaced with HMAC.
- **`!showtmes` scoping bug** — `num`, `cname`, and `mestext` are only assigned correctly for the last item in the loop. The display logic needs to be moved inside the loop body.
- **Bare `except:` blocks** — many `except:` clauses swallow all exceptions silently. These should be changed to `except Exception as e:` with a `print(e)` for easier debugging.
- **`!addquote` sentinel** — the date sentinel should be the string `'-1'` not the integer `-1` to match the comparison `lquotes['Date'][i] != '-1'` used elsewhere.
- **Missing `return` after failed CSV loads** — several commands continue executing after a failed `get_dict` because the `except` block is missing a `return`, causing a `NameError` on the next line.
- **`hourlyQuote` stub** — the actual quote-sending is commented out. The task runs but does nothing.
- **`on_raw_reaction_add` hardcoded IDs** — the message ID and role ID for the Ed emoji reaction role are magic numbers with no explanation. Should be named constants.
- **`save_quotes`** — this function is a duplicate of functionality in `save_dict` from `dictionaryHelpers.py` and can be removed.

---

## Adding New Commands

1. Add a new `if` block inside `on_message` following the existing pattern:

```python
if message.content.startswith('!mycommand'):
    # optional: check permissions
    if not is_mod:
        await message.reply('You do not have permission to use this command.')
        return
    
    # parse arguments
    parts = message.content.split(';')
    if len(parts) < 2:
        await message.reply('Usage: `!mycommand;[arg]`')
        return
    
    # do the thing
    try:
        # ... your logic here
        await message.reply('Done.')
    except Exception as e:
        await message.reply('Something went wrong.')
        print(f'mycommand error: {e}')
```

2. Add an entry to `messages/helpText.txt` following the pipe-delimited format:
```
mycommand|False|Full help text here|Mod-only addendum here (or empty)|One-line description
```

3. If it is a general command, add it to `messages/general-help.txt` or `messages/mod-help.txt`.

4. If it needs a background task, use the `@tasks.loop` decorator and start it in `on_ready`:

```python
@tasks.loop(minutes=5)
async def my_task():
    # ...

async def on_ready():
    # ...
    my_task.start()
```
