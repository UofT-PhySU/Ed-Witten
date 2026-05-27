import discord
from discord.utils import get
from discord.ext import tasks
import asyncio
import datetime as dt
import time
import csv
import os
import random
import io
import requests
import subprocess
import numpy as np
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict
from icalendar import Calendar
from dictionaryHelpers import *
from timeManagement import *

# bot will not join server if DEBUG_MODE = True
DEBUG_MODE = False
ANNOUNCER = False
announced = set()

# loads the .env file (in the same directory) and gets the Discord connection key
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')
NUM1 = int(os.getenv('NUM1'))
NUM2 = int(os.getenv('NUM2'))
NUM3 = int(os.getenv('NUM3'))
NUM4 = int(os.getenv('NUM4'))
CAL_URL = os.getenv('CAL_URL')

GENERATE = True
MODEL = os.getenv('MODEL')
OLLAMA_URL = os.getenv('OLLAMA_URL')
PROMPT = os.getenv('PROMPT')
context = {}
WINDOW = 10
SEED = [
    {"role": "user", "content": "Who are you and what's the best branch of physics"},
    {"role": "assistant", "content": "I'm Ed Witten, the famous physicist. And atomic physics, no contest."},
    {"role": "user", "content": "can you help me with this integral"},
    {"role": "assistant", "content": "Sure, what've you got so far?"},
    {"role": "user", "content": "what do you think about string theory?"},
    {"role": "assistant", "content": "Mathematically gorgeous. Experimentally... we'll see. Algebraic topology shows up everywhere in it though, which is a point in its favour"},
    {"role": "user", "content": "the physu mod team has gotten out of hand"},
    {"role": "assistant", "content": "lol they're just doing their jobs (@moderator)"},
]

# roles and channels
ROLES = {
    'Member': 698388933511217155,
    'New User': 831644590779793458,
}
ED_WITTEN = ':ed:761332313829146624'
ZHAN_SU = ':highschoolmath:1019342347814850680'
SCREM_ID = ':screm:761332313829146624'
IKEA = ':IKEA:1436061027468054761'
LOG_CHANNEL = 753072439814258688 # channel-refresh-logs ID
VERIFICATION_CHANNEL = 708563333728436244
ACADEMIC_ANNOUNCE = 917444910385356880
REFRESH_CHANNELS = [753070698607542342]
REFRESH_DELAY = 30 # minutes before message deletion

# loads exec positions as a dictionary
EXEC_POSITIONS = {}
with open('execs.csv', mode='r') as f:
    reader = csv.reader(f)
    for row in reader:
        EXEC_POSITIONS[row[0]] = (row[1], row[2], row[3])

with open('censored.csv', 'r') as f:
    CENSORED = list(csv.reader(f, delimiter=","))[0]

currentDay = time.strftime("%D %H:%M", time.localtime(time.time())).split(' ')
TORONTO = ZoneInfo("America/Toronto")
EMBED_COLOUR = 0x8f279b

print('Initializing...')


##### Utility Functions #####
def get_timestamp(): 
    return time.strftime("%D %H:%M", time.localtime(time.time()))


def decode(raw_name):
    asciiname = ''.join(str(9 - int(i)) for i in raw_name)
    asciilist = []
    temp = ''
    for e in asciiname:
        temp = temp + e
        if len(temp) == 3 and temp[0] == '1':
            asciilist.append(int(temp))
            temp = ''
        elif len(temp) == 2 and temp[0] != '1':
            asciilist.append(int(temp))
            temp = ''
    name = ''.join(map(chr, asciilist))
    return name


# make list of join tokens
def getjoinlogs():
    tokens = set()
    with open('joinlog.csv', 'r') as f:
        next(f)        
        reader = csv.reader(f)
        try:
            for _, token1, token2, *_ in reader:
                tokens.add((int(token1), int(token2)))
        except:
            print('Entry got ignored')    
    return tokens


#-----------------------------------------------------------------------------
intents = discord.Intents.all()
client = discord.Client(intents=intents)


# called when the bot is ready to start processing events
@client.event
async def on_ready(): 
    timestamp = time.time()
    subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(3) # give Ollama a moment to start
    timedmessages.start()
    archiveColloquia.start()
    hourlyQuote.start()
    announce_events.start()
    print(f'Logged in as {client.user}')

    # set bot status
    await client.change_presence(activity = discord.Activity(name="Monitoring ACORN Waitlists",
                                                             type=discord.ActivityType.watching))
    # log when bot signed in
    with open("botuplog.txt", "a") as f:
        print(f'logged into server at {get_timestamp()}', file=f)


# purges all messages in the channels listed in REFRESH_CHANNELS
async def purge_refresh_channels(mnum=200, refreshids=REFRESH_CHANNELS):
    for refreshchannel_id in refreshids:
        refreshchannel = client.get_channel(refreshchannel_id)
        messages =  [thing async for thing in refreshchannel.history(limit=mnum)] # gets the last mnum messages in the channel
        messages = list(filter(lambda message: not message.pinned, messages)) # compiles a list of messages that are not pinned
        # logs the given message to #channel-refresh-logs
        for message in messages:
            try:
                await log_message(message)
                await message.delete()
            except Exception as ex:
                print(ex)


async def log_message(message):
    # logs the given message to #channel-refresh-logs
    logchannel = client.get_channel(LOG_CHANNEL)  # gets the channel object
    sanitized = message.content.replace('\n', ' / ') # replaces newlines with spaces
    await logchannel.send(f' > {sanitized}\n{message.channel.name} {message.author} {get_timestamp()}') # sends the message to the log channel


@client.event
async def on_message(message):
    """Called whenever a message is sent in a channel the bot can see.
    Args:
        message (discord.Message): The message that was sent.
    """
    timestamp = time.time()
    is_self = (message.author == client.user)
    
    roles = [role.name for role in message.author.roles]
    is_mod = ('Moderator' in roles)
    book_shelf = ('Bookshelf Committee' in roles)
    colloquium_committee = ('Colloquia Committee' in roles)

    if message.channel.id == VERIFICATION_CHANNEL and not is_self: 
        is_numeric = all(char in '0123456789' for char in message.content.strip()) 
        if is_numeric:
            await message.channel.send(f'<@{message.author.id}> Please include the `$` at the start of the verification key.') 
            await message.delete(delay=5)

    # verification
    # to test use key $696900123412898889883028884242004567 (sets nickname to "Wentao")
    # see the emailing script in the .env file
    if message.content.startswith('$') and message.channel.id == VERIFICATION_CHANNEL:
        action = 'tested' if is_mod else 'used'
        print(f'{message.author.name} {action} verification code {message.content}')
        try:
            # parse imput
            raw = message.content[1:]
            token1, token2, raw_name = int(raw[0:10]), int(raw[-10:]), str(raw[10:-10])
            used_tokens = getjoinlogs()

            is_used = (token1, token2) in used_tokens
            is_valid = ((token1 - NUM1) % NUM2 == 0) and ((token2 - NUM3) % NUM4 == 0) # TODO: use an actually serious crytographic algorithm
            nickname = decode(raw_name) # NOTE: nickname doesn't have to be loaded here, can wait until after verification

            if not is_valid: # if key is invalid, send error message and return
                await message.channel.send('Your key is invalid. Please try again.')
                return

            if is_mod: # if user is a moderator, send verification status and return
                status = 'Expired' if is_used else 'Active'
                await message.channel.send(f'{status} verification key for {nickname}.')
                return

            if is_used: # if key is already used, ban the user sending that key, send error message, and return
                print(f'banned {message.author.name} for duplicate key')
                await message.channel.send("This is a duplicate key. You have been banned.")
                await asyncio.sleep(5)
                await message.author.ban(reason = "You have used a duplicate key.")
                return

            # get user nickname and discord name
            discord_name = message.author.name
            
            # change nickname and give "Member" role
            await message.author.edit(nick=nickname)
            await message.author.add_roles(get(message.guild.roles, id=ROLES['Member']))
            await message.author.remove_roles(get(message.guild.roles, id=ROLES['New User']))
            
            # write to file relevant information
            with open('joinlog.csv', 'a') as f:
                print(
                    f'{discord_name}, {token1}, {token2}, {nickname}, {timestamp:.3f}',
                    file=f
                )

        except Exception as ex:
            await message.channel.send('Verification unsuccessful. Try entering your key again. Report the issue to a moderator if the issue persists.')
            print(ex)
        finally:
            # delete message
            await message.delete(delay=1)
    
    # generate Ed Witten response
    if message.reference is not None:
        try:
            referenced = await message.channel.fetch_message(message.reference.message_id)
            if referenced.author == client.user:
                doGenerate = True
            else:
                doGenerate = False
        except Exception as e:
            print(f'Could not fetch referenced message: {e}')
    else:
        doGenerate = False
    doGenerate = doGenerate or message.content.startswith('!EdGPT') or random.random() < 0.01
    doGenerate = doGenerate and message.channel.id != VERIFICATION_CHANNEL and message.channel.id not in REFRESH_CHANNELS and GENERATE
    if doGenerate:
        async with message.channel.typing():
            reply = await asyncio.get_event_loop().run_in_executor(
                None, get_response, message.channel.id, message.content
            )
        await message.reply(reply)

    if message.content.startswith('!amogus'):
        amoguslist = ['https://tenor.com/view/boiled-soundcloud-boiled-boiled-irl-boiled-utsc-boiled-cheesestick-agem-soundcloud-gif-20049996', 'https://tenor.com/view/among-us-sus-yhk-among-twerk-among-us-twerk-gif-23335803','https://media.discordapp.net/attachments/750874999543300146/1004201641551089776/image0-1.gif','https://tenor.com/view/among-us-amogus-ass-dance-happy-gif-20485385','https://media.discordapp.net/attachments/556756134367592481/861657418155819045/speed-3.gif']
        await message.channel.send(random.choice(amoguslist))
        await message.delete()

    if message.content.startswith("!user"): # !user command looks for the user with the given code
        num = message.content.split(';')[1]
        try:
            pfromuser = await message.guild.fetch_member(int(num))
            await message.reply("The person with this code is: " + pfromuser.display_name)
        except:
            await message.reply("something went horribly wrong")

    if message.content == '!website':  # !website command displays links to PhySU website and social media, as well as student resources
        await message.channel.send('''**PhySU Website:** https://www.physu.org
                                    **Online Resource Masterlist for Students:** https://docs.google.com/document/d/1TH_ldQUeX0yfJe9pTczIIqo2J6GzcxBr1SQ3z4ddlVA/edit?usp=sharing''')
    
    if message.content == '!source':  
        await message.channel.send('''**Ed Witten Open Source Project:** https://github.com/UofT-PhySU/Ed-Witten-bot''')

    if message.content == '!exec': # Shows the PhySU executive team
        embed = discord.Embed(
            title='PhySU Executive Officers',
            color=EMBED_COLOUR
        )
        for position, info in EXEC_POSITIONS.items():
            name, tag, office_hour = info
            embed.add_field(
                name=position,
                value=f'{name}: {tag}\n*Office Hour: {office_hour}*',
                inline=False,
            )
        embed.set_footer(text='Feel free to message any exec with questions or concerns!')
        await message.channel.send(embed=embed)

    if message.content.startswith('!courseSetupInstructions'):
        await message.reply('See instructions for how to set up course channels here: https://www.overleaf.com/read/xxywzkjngbbz#7b2abe') 

    # Ed Witten help command
    if message.content.startswith('!edhelp') or message.content.startswith('!help'):
        helpText = get_dict('messages/helpText.txt')
        checker = False
        splitHelp = message.content.split(';')
        msg = 'For more specific instructions on available commands, please type `!edhelp;` following the extensions below (e.g. `!edhelp;general`): \n \n' +  '`general`  Gives a brief overview of basic PhySU server commands'
        allmsg = []
        execmsg = []

        for i in range(len(helpText['h'])): # 'modq' is True if the command is only for mods, sorting the lines into two lists, one for all users and one for mods
            if helpText['modq'][i] == 'False':
                allmsg.append(i)
            if helpText['modq'][i] == 'True':
                execmsg.append(i)
        mod_msg = '\n Mod only commands: '

        for i in allmsg: # this loop adds the commands to the message
            rep = helpText['desc'][i].replace('\\n', '\n')
            msg += '\n' + '\n' + '`' + helpText['h'][i] + '`' + "    " + rep
        for i in execmsg:
            rep = helpText['desc'][i].replace('\\n', '\n')
            mod_msg += '\n' + '\n' + '`' + helpText['h'][i] + '`' + "    " + rep

        if len(splitHelp) == 1: # if there are no underscores in the message, it sends the general help message
            if is_mod:
                msg += '\n \n' + mod_msg
            await message.channel.send(msg)
            checker = True
        msg = ''
        
        if len(splitHelp) == 2: # if there is one underscore, it sends the help message for that command
            identifier  = splitHelp[1] 
            for i in range(len(helpText['h'])): 
                row = [helpText['h'][i], helpText['modq'][i], helpText['htext'][i].replace('\\n', '\n'), helpText['ismod'][i].replace('\\n', '\n'), helpText['desc'][i].replace('\\n', '\n')]
                if row[0] == identifier:
                    if row[1] == str(is_mod) or row[1] == 'False':
                        msg = row[2]
                        if is_mod:
                            msg += '\n' + '\n' + row[3]
                        checker = True
                        await message.channel.send(msg)
            if identifier == 'general':      
                with open(f'messages/general-help.txt', 'r') as f:
                    msg = f.read()
                if is_mod:
                    with open(f'messages/mod-help.txt', 'r') as f:
                        msg += '\n' + '\n' + f.read()
                await message.channel.send(msg)
                checker = True

        if checker == False:
            await message.reply("Your help query was not found.")
            
    # Ed does the thing when people say 'so true bestie'
    if 'so true bestie' in message.content.lower() and not is_self:
        bcount = 0
        try:
            bcount  = getbestie()
        except:
            savebestie(0)
            bcount = getbestie()
            await message.reply("There was no so true bestie counter pre-saved. I made a new one and re-started the counter from 0. ")
        bcount += 1
        savebestie(bcount)
        await message.author.add_roles(get(message.guild.roles, id=1029445036863144007))

    # !bestie command displays the current so true bestie count
    if message.content.startswith('!bestie'):
        number = getbestie()
        print(number)
        await message.reply("So true bestie count: " +  str(number))

    # Ed reacts to the mention of Ivr*i's name
    if 'ivrii' in message.content.lower() and not is_self:
        await message.add_reaction(ED_WITTEN)
        await message.channel.send('Thou shalt not mention Ivr*i’s name')

    if 'duck' in message.content.lower() and not is_self:
        await message.add_reaction("🦆")
        await message.reply('There are no ducks in MP')

    # Ed reacts to the mention of Zhan Su's name
    if 'zhan su' in message.content.lower():
        sumes = ['It\'s high school physics!', 'It\'s just calculus!', 'Elementary school math!', 'Theta dot.']
        await message.add_reaction(ED_WITTEN)
        await message.add_reaction(ZHAN_SU)
        rand1 = random.randrange(0, 100, 1)
        if rand1 > 90:
            await message.reply('https://tenor.com/view/siuu-gif-23749474')
        else:
            await message.reply(random.choice(sumes))

    if 'ikea' in message.content.lower():
        await message.add_reaction(IKEA)

    if 'bot' in message.content.lower():
        replies = ['I\'m always watching', 'Thank you']
        await message.add_reaction(ED_WITTEN)
        rand1 = random.randrange(0, 100, 1)
        if rand1 > 80:
            await message.reply('https://tenor.com/view/who-me-terminator-skynet-who-me-gif-27520354')
        elif rand1 > 50:
            await message.reply(random.choice(replies))
        elif rand1 < 15:
            async with message.channel.typing():
                reply = await asyncio.get_event_loop().run_in_executor(
                None, get_response, message.channel.id, message.content
                )
            await message.reply(reply)


    if any(rstring in message.content.lower() for rstring in CENSORED):
        await message.reply('You have been warned.')
        await message.delete()
    
    # Ed sends the screm gif
    if message.content == '!screm':
        await message.add_reaction(SCREM_ID)
        screm = random.choice([
            'https://tenor.com/bvAta.gif',
            'https://tenor.com/bc73X.gif',
        ])
        await message.channel.send(screm)

    # Ed sends a message to a channel (moderators only)
    if message.content.startswith('!sendm'):
        if is_mod:
            textt = message.content.split(";")[1] 
            if not message.attachments:  
                await message.channel.send(textt)
            else:
                await message.channel.send(textt, files = [await f.to_file() for f in message.attachments])
            await message.delete()
        else:
            await message.channel.send('You are not a moderator, bestie.')

    if message.content.startswith('!sendmessage'):
        if is_mod:
            name = message.content.split()[1]
            try:
                with open(f'messages/{name}.txt', 'r') as f:
                    content = f.read()
                await message.channel.send(content.strip())
            except:
                await message.channel.send(f'Message `{name}` not found.')
        else:
            await message.channel.send('You are not a moderator.')

    if message.content.startswith("!addcolloquium") and (is_mod or colloquium_committee):
        try: 
            colloquiumList = get_dict("physucolloquia.csv")
        except:
            await message.reply('The list of colloquia file does not exist. I am gonna make a new one, but maybe you should do something about it. :idea:')
            save_dict({
                'Title': [],
                'Speaker': [],
                'Time': [],
                'Room': []
            },"physucolloquia.csv")

        mtext = message.content.split(";")

        try:
            colloquiumList["Title"].append(str(mtext[1]))
            colloquiumList["Speaker"].append(str(mtext[2]))
            colloquiumList["Time"].append(str(convertDDMMYYToUnixTime(mtext[3], mtext[4])))
            colloquiumList["Room"].append(str(mtext[5]))

            save_dict(timeSortDict(colloquiumList), "physucolloquia.csv") 
            await message.reply("This colloquium has been added.")
        except:
            await message.reply("You made a formatting error. Please double check your spelling. Your entry should be formatted as !addcolloquium;Title;Speaker Name;dd.mm.yy;hh:minutes;Room Number")

    if message.content.startswith('!archivedcolloquia'):
        try: 
            colloquiumList = get_dict("physucolloquiaarchive.csv")
            displayList = makeDisplayMessage({**colloquiumList, **{'TimeStrings': [str(printTheTimeFromDDMMYY(float(tt), includeYear=True)) for tt in colloquiumList["Time"]]}}, list(["Title", "Speaker", "TimeStrings", "Room"]), 20, [" | ", " | " , " | ", " "])
            if displayList is None:
                await message.channel.send("No archived colloquia.")
            else:
                for ss in displayList:
                    await message.channel.send(ss + "```")
        except:
            await message.reply("The archive colloquium list is missing. Ping a moderator to deal with this.")

    if message.content.startswith("!colloquia"):
        try: 
            colloquiumList = get_dict("physucolloquia.csv")
            displayList = makeDisplayMessage({**colloquiumList, **{'TimeStrings': [str(printTheTimeFromDDMMYY(float(tt))) for tt in colloquiumList["Time"]]}}, list(["Title", "Speaker", "TimeStrings", "Room"]), 20, [" | ", " | ", " | ", " "])
            if displayList is None:
                await message.channel.send("No upcoming colloquia.")
            else:
                for ss in displayList:
                    await message.channel.send(ss + "```")
        except:
            await message.reply("The colloquium list is missing. Ping a moderator to deal with this.")

    if message.content.startswith("!removecolloquium") and (is_mod or colloquium_committee):
        try: 
            colloquiumList = get_dict("physucolloquia.csv")
        except:
            await message.reply("The colloquium list is missing. Ping a moderator to deal with this.")
        try:
            mtext = message.content.split(";")
            save_dict(removeIndex(colloquiumList, int(mtext[1]) - 1), "physucolloquia.csv")
            await message.reply("A colloquium has been succesfully deleted.")
        except:
            await message.reply("Something went wrong with removing the message and saving the colloquium list.")

    if message.content.startswith("!removebook") and (is_mod or book_shelf):
        try: 
            bookList = get_dict("physubooks.csv")
        except:
            await message.reply("The books list is missing. Ping a moderator to deal with this.")
        try:
            mtext = message.content.split(";")
            save_dict(removeIndex(bookList, int(mtext[1]) - 1), "physubooks.csv")
            await message.reply("A book has been succesfully deleted.")
        except:
            await message.reply("Something went wrong with removing the message and saving the book list.")

    if message.content.startswith('!addbook') and (is_mod or book_shelf) and not message.content.startswith('!addbooktag'):
        try:
            bookList = get_dict("physubooks.csv")
        except:
            await message.reply('The list of books file does not exist. I am gonna make a new one. :idea:')
            save_dict({
                'Title': [],
                'Author': [],
                'Tags': []
            }, "physubooks.csv") 
        mtext = message.content.split(";")
        try:
            bookList["Title"].append(mtext[1])
            bookList["Author"].append(mtext[2])
            if len(mtext) == 4:
                bookList["Tags"].append(mtext[3])
            else:
                bookList["Tags"].append("NA")
            print(bookList)
            save_dict(bookList, "physubooks.csv")
            await message.reply("Your book has been added.")
        except:
            await message.reply('You made a formatting error. Try getting good and writing the book title, book author, and tag separated by semicolons.')

    if message.content.startswith("!addbooktag") and (is_mod or book_shelf):
        try:
            bookList = get_dict("physubooks.csv")
        except:
            await message.reply("The list of books file does not exist. Ping a moderator for help.")
        request = message.content.split(";")
        try:
            theN = int(request[1])
            bookList["Tags"][theN-1] += "," + request[2]
            save_dict(bookList, "physubooks.csv")
            await message.reply("Your book tag has been added.")
        except:
            await message.reply("Something went wrong. Please double check your formatting. To add a tag to a book type: `!addbooktag;n;the tag`. n is the index of the book as it appears on !books.")

    if message.content.startswith("!replacebooktag") and (is_mod or book_shelf):
        try:
            bookList = get_dict("physubooks.csv")
        except:
            await message.reply("The list of books file does not exist. Ping a moderator for help.")
        request = message.content.split(";")
        try:
            theN = int(request[1])
            bookList["Tags"][theN-1] = request[2]
            save_dict(bookList, "physubooks.csv")
            await message.reply("Your book tags has been replaced.")
        except:
            await message.reply("Something went wrong. Please double check your formatting. To add a tag to a book type: `!replacebooktag;n;newtags`. n is the index of the book as it appears on !books.")
        
    if message.content.startswith("!showbooks") or message.content.startswith("!books"):
        try:
            bookList = get_dict("physubooks.csv")
        except:
            await message.reply('The list of books file does not exist. Ping a moderator for help.')
            return
        request = message.content.split(";")        
        displayList = None
        if len(request) == 1:
            displayList = makeDisplayMessage(bookList, list(bookList.keys()), 10, [" | ", " | ", " "])
        if len(request) == 3:
            try:
                userKey = list(bookList.keys())[[string.lower() for string in list(bookList.keys())].index(str(request[1].lower()))]
                trIndices = truncationIndices(list(bookList[userKey]), str(request[2]))
                displayList = makeDisplayMessage(truncateDict(bookList, trIndices), list(bookList.keys()), 10, [" | ", " | ", " "])
            except:
                await message.reply("You entered an invalid key to sort by. Or something else went wrong. Read the documentation at !edhelp_book.")
        if displayList is not None:
            for ss in displayList:
                await message.channel.send(ss + "```")
        else:
            await message.channel.send("There is nothing to display.")

    # adds quotes
    if message.content.startswith('!addquote'):
        try:
            lquotes = get_dict("physuquotes.csv")
        except:
            await message.reply('The list of quotes file does not exist. I am gonna make a new one, but maybe you should do smt about it. :idea:')
            save_dict({
                'Quote': [],
                'Author': [],
                'Date': []
            }, "physuquotes.csv") 
        mtext = message.content.split(";")
        try: 
            lquotes['Quote'].append(mtext[1])
            lquotes['Author'].append(mtext[2])
            if len(mtext) == 4:
                lquotes['Date'].append(mtext[3])
            else:
                lquotes['Date'].append('-1')
            save_dict(lquotes, "physuquotes.csv")
        except:
            await message.reply('You made a formatting error. Try getting good and writing the quote, quote author, and date separated by semicolons.')
    
    # removes course roles from user who sent the command
    if message.content.startswith('!removecourseroles'):
        aut = message.author
        roleslist = aut.roles
        listofstart = ['AST', 'MAT', 'PHY', 'APM', 'JPH']
        for rol in roleslist:
            if any(rol.name.startswith(s) for s in listofstart):
                await aut.remove_roles(rol)
        await message.reply('All of your course roles have been removed.')

    if message.content.startswith('!removeohio'):
        await message.reply('Ohio has been removed from your world.')

    # sends message into the future    
    if message.content.startswith('!stmes') and is_mod:
        name = message.author.nick or message.author.name
        mes = message.content.split(";")
        datenum = mes[1]
        wtime = mes[2]
        channelname = str(mes[3])
        text = mes[4]
        try:
            chan = await client.fetch_channel(int(channelname))
            date = datenum.split('.')
            ye = int(date[2])+2000
            dday = int(date[0])
            mmonth = int(date[1])
            hour = int(wtime.split(':')[0])
            minute =  int(wtime.split(':')[1] )
            ftime = dt.datetime(ye, mmonth, dday, hour, minute, 0).timetuple()
            utime = time.mktime(ftime)

            if utime < time.time():
                raise Exception()
            
            try:
                tmes = get_dict('tmes.csv')
                tmes['Time'].append(str(utime))
                tmes['Author'].append(name)
                tmes['Message'].append(text)
                tmes['Channel'].append(channelname)
                save_dict(tmes,'tmes.csv')
            except:
                await message.reply("Failed to get or savedict. You should check that.")
        except:
            await message.reply("You entered an ID of a non-existent channel or your date is in the past.")

    if message.content.startswith('!edtime'):
        timetobeset = time.strftime("%D %H:%M", time.localtime(time.time()))
        await message.reply(timetobeset)

    if message.content.startswith('!deltmes') and is_mod:
        mes = message.content.split(";")
        try:
            lmes = get_dict('tmes.csv')
        except:
            await message.reply("You couldn't get the dictionary and it is all horrible. Fix this!")

        num = int(mes[1]) - 1
        keyslist= list(lmes.keys())

        for key in keyslist:
            del lmes[key][num]
        
        save_dict(lmes, 'tmes.csv')

    if message.content.startswith('!showtmes') and is_mod:
        lquotes = -1
        try:
            lmes = get_dict('tmes.csv')
            mestext='```'
            for i in range(len(lmes['Author'])):
                cname = ''
                try:
                    chan = await client.fetch_channel(lmes['Channel'][i])
                    cname = chan.name
                except:
                    await message.reply("No channel with this id exists. ID: " + str(lmes['Channel'][i]))
                    cname = 'Not found'
            
            num = i + 1
            mestext += '\n' + str(num) + ') ' + "To be sent on: " 
            mestext += (' ' + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(float(lmes['Time'][i]))))
            mestext += "\n  Sent by: " +  lmes['Author'][i] + ' \n  In channel:  ' + cname + "\n Actual Message: " +  lmes['Message'][i] 
            mestext += ' ```'
            await message.reply(mestext)
        except:
            await message.reply('List of tmessages broken. Ping a moderator or this will be broken forever.')
        
    # sends random quote
    if message.content.startswith('!quote'):
        tpe = message.content.split(";")
        try:
            lquotes = get_dict("physuquotes.csv")
            if len(tpe) == 1:
                index = random.randint(0, len(lquotes['Quote']) - 1)
            if len(tpe) == 2:
                index = int(tpe[1]) - 1
            mes = '"' + lquotes['Quote'][index] + '" ' + ' - ' + lquotes['Author'][index]
            if lquotes['Date'][index] != '-1':
                mes += ' ' + lquotes['Date'][index]
            await message.channel.send(mes)
        except:
            await message.reply('List of quotes broken (or you caused an overflow/value error). Ping a moderator if this isn\'t on you.')

    # sends a specific quote
    if message.content.startswith('!sendquote'):
        try:
            lquotes = get_dict('physuquotes.csv')
        except:
            await message.reply('List of quotes broken. Ping a moderator or this will be broken forever.')
        
        stringn = int(message.content.split(';')[1] ) - 1
        quotetosend = ''
        try:
            quotetosend = '"' + lquotes['Quote'][stringn] + '" ' + ' - ' + lquotes['Author'][stringn] 
            if lquotes['Date'][stringn] != '-1':
                quotetosend += ' ' + lquotes['Date'][stringn]
            await message.channel.send(quotetosend)
            await message.delete(delay=1)
        except:
            await message.reply('You entered an invalid quote number.')

    if message.content.startswith('!showquotes'):
        tpe = message.content.split(';')
        arg = tpe[1].strip() if len(tpe) > 1 else None
        boxsize = 10
        
        try:
            lquotes = get_dict('physuquotes.csv')
            n = len(lquotes['Author'])
            if arg is None or arg.isdigit():
                target_year = int(arg) if arg else datetime.now().year
                # find first and last index containing that year
                matches = [i for i in range(n) if str(target_year) in lquotes['Date'][i]]
                if not matches:
                    await message.reply(f'No quotes found for {target_year}.')
                    return
                indices = list(range(min(matches), max(matches) + 1))
            elif arg.lower() in ('all', 'everything', '*'):
                indices = list(range(n))
            else:
                await message.reply('Usage: `!showquotes` (current year); `!showquotes;2025` (specific year); `!showquotes;all` (everything).')
                return
            
            nmes = int(np.ceil(len(indices) / boxsize))
            mestext = []
            for i in range(nmes):
                mestext.append('```')
            for pos, idx in enumerate(indices):
                num = pos + 1
                box = int(np.floor((num - 1) / boxsize))
                mestext[box] += '\n' + str(num) + ') "' + lquotes['Quote'][idx] + '" - ' + lquotes['Author'][idx]
                if lquotes['Date'][idx] != '-1':
                    mestext[box] += ' ' + lquotes['Date'][idx]

            replycheck = 0
            for ss in mestext:
                if replycheck == 0:
                    await message.reply(ss + '```')
                    replycheck = -1
                else:
                    await message.channel.send(ss + '```')
        except Exception as e:
            await message.reply('List of quotes broken. Ping a moderator or this will be broken forever.')
                                
    # deletes a quote
    if message.content.startswith('!delquote') and is_mod:
        try:
            lq = get_dict("physuquotes.csv")
        except:
            await message.reply('List of quotes broken. Ping a moderator or this will be broken forever.')
        try:
            ito = message.content.split(';')[1]
            itodel = int(ito) - 1
            tempq = {
                'Quote': [],
                'Author': [],
                'Date': []
            }
            for i in range(len(lq['Author'])):
                if itodel != i:
                    tempq['Quote'].append(lq['Quote'][i])
                    tempq['Author'].append(lq['Author'][i])
                    tempq['Date'].append(lq['Date'][i])        
            save_dict(tempq, "physuquotes.csv")
        except:
            await message.reply('That was either not an integer, or not in range, or you failed horribly somehow.')
  
    # Executes the !edwitten command
    if message.content == '!edwitten':
        await message.channel.send('I am your lord and saviour.')

    # like the magic 8 ball, but Ed Witten
    if message.content.startswith('!fortune'):
        question = ' '.join(message.content.split()[1:]).lower()
        responses = [
            'sure? i guess',
            'why not',
            'why would you even think that',
            'i have more important questions to answer',
            'umm sure whatever floats your boat',
            'you already know the answer, why are you asking me?',
            'umm yeah about that...',
            'k',
            'flip a coin',
            'ABSOLUTELY ⁿᵒᵗ',
            'no. no no no no no no no no',
            'how would i know',
            'is that a question or a joke',
            'probably idk',
            'yes. are you happy?',
        ]
        await message.reply(random.choice(responses))

    # purges all/or specified number of messages in refresh channels or specified channels 
    if message.content.startswith('!purgechannel') and is_mod:
        splitted = message.content.split(";")
        if len(splitted) == 3:
            await purge_refresh_channels(refreshids = [int(splitted[1])], mnum = int(splitted[2]) + 1)
        if len(splitted) == 2:
            await purge_refresh_channels(refreshids = [message.channel.id], mnum = int(splitted[1]) + 1)
        else:
            await purge_refresh_channels()

    if message.content.startswith('!events'):
        events = get_events()
        now = datetime.now(tz=timezone.utc)

        # filter to future events only and sort by date
        upcoming = [(uid, name, start) for uid, name, _, _, start in events if start > now]
        upcoming.sort(key=lambda x: x[2])

        if not upcoming:
            await message.reply('No upcoming events found in the calendar.')
            return

        # optionally limit to next N events
        tpe = message.content.split(';')
        try:
            limit = int(tpe[1]) if len(tpe) > 1 else 10
        except ValueError:
            limit = 10
        upcoming = upcoming[:limit]

        text = '```\nUpcoming Events\n' + '─' * 30
        for _, name, start in upcoming:
            local_start = start.astimezone(TORONTO)
            time_until = (start - now).total_seconds()
            days = int(time_until // 86400)
            hours = int((time_until % 86400) // 3600)
            if days > 0:
                delta_str = f'in {days}d {hours}h'
            else:
                delta_str = f'in {hours}h'
            date_str = local_start.strftime('%b %d, %I:%M %p')
            text += f'\n{date_str}  ({delta_str})\n  {name}\n'

        text += '```'
        await message.reply(text)
        
    # sends "oops"
    if message.content == '!oops':
        await message.channel.send('oops!')

    if message.content.startswith('!setupcourses') and is_mod:
        if len(message.attachments) < 2:
            await message.reply('You need to attach the courses CSV and the message IDs CSV, respectively, to this command.')
            return
    
        courses = read_csv(message.attachments[0])
        message_ids = read_csv(message.attachments[1])
        courses = [row[0].strip().upper() for row in courses if row]
        message_ids = {row[0].strip(): row[1].strip() for row in message_ids if len(row) >= 2}

        # group courses by category key
        grouped = defaultdict(list)
        for course in courses:
            grouped[get_category_key(course)].append(course)
        # sort courses within each category
        for key in grouped:
            grouped[key].sort()

        number_emojis = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣']
        failed_courses = []
        failed_categories = []

        for category_key, category_courses in grouped.items():
            if len(category_courses) > 9:
                await message.reply(f'Warning: `{category_key}` has more than 9 courses.')
                category_courses = category_courses[:9]

            role_string_parts = []

            for i, course in enumerate(category_courses):
                try:
                    await create_course_channel(message.guild, course)
                except Exception as e:
                    print(f'Channel creation failed for {course}: {e}')

                # create role if it doesn't exist
                role = discord.utils.get(message.guild.roles, name=course)
                if role is None:
                    try:
                        role = await message.guild.create_role(name=course)
                    except Exception as e:
                        failed_courses.append(course)
                        print(f'Role creation failed for {course}: {e}')
                        continue

                role_string_parts.append(f'{number_emojis[i]} {role.id}\n')

            # update CarlBot message for this category
            if category_key not in message_ids:
                failed_categories.append(category_key)
                continue

            cat_message_id = message_ids[category_key]
            role_string = ' '.join(role_string_parts)

            await message.channel.send(f'!rr clear {cat_message_id}')
            await asyncio.sleep(1)  # give CarlBot a moment between commands
            await message.channel.send(f'!rr addmany {cat_message_id} {role_string}')
            await asyncio.sleep(1)

        # report results
        summary = f'Done. Processed {len(courses)} courses across {len(grouped)} categories.'
        if failed_courses:
            summary += f'\nFailed to create roles for: {", ".join(failed_courses)}'
        if failed_categories:
            summary += f'\nNo message ID found for categories: {", ".join(failed_categories)}'
        await message.reply(summary)
        
    # creates courses
    if message.content.startswith('!createcourses') and is_mod:
        courses = message.content.split()[1:]
        for course in courses:
            await create_course_channel(message.channel.guild, course)
        await message.reply(f'Successfully created {len(courses)} courses.')

    # Ed pops up and says :spaghetti:
    if 'spaghet' in message.content.lower() and not is_self:
        await message.reply(':spaghetti:')

    # test message
    if random.random() < 1e-4 or message.content == 'testmessage':
        await message.reply(random.choice([
            'agreed',
            'why tho',
            'maybe',
            'probably idk',
        ]), mention_author=False)

    # Ed says sup when mentioned
    if ('ed' in message.content.lower().split()) and random.random() < 0.1 and not is_self:
        await message.reply('sup', mention_author=False)

    # command edits course names 
    # TODO: add more details
    if message.content.startswith('!edit') and is_mod and not message.content.startswith('!editcoursemes') :
        mchanid = message.content.split(';')[1]
        miid = message.content.split(';')[2]
        metext = message.content.split(';')[3]
        chan = await client.fetch_channel(mchanid)
        mes = await chan.fetch_message(miid)
        await mes.edit(content = metext)

    # deletes a category
    if message.content.startswith('!delcat') and is_mod:
        check = 0
        try:
            nametodel = message.content.split(";")[1]
            cattodel = discord.utils.get(message.guild.categories, name = nametodel)
        except:
            await message.reply("You spelled the command wrong. Note it has the format !delcat_categoryName. Note you MUST use the underscore after delcat. Make sure all capitalization and spacing is correct.")
            check = -1
        if cattodel is not None and check != -1:
            for chan in cattodel.channels:
                await chan.delete()
            await cattodel.delete()
            await message.reply(nametodel + " was yeeted")
        if cattodel is None and check != -1:
            await message.reply("No such category exists. Learn to spell, or remember to separate !delcat from the category name with _ and not a space.")

    # archives a category
    if message.content.startswith('!archivecat') and is_mod:
        nametoreplace = message.content.split(';')[1]
        newcatname = message.content.split(';')[2]

        mod = discord.utils.get(message.guild.roles, name='Moderator')
        
        if discord.utils.get(message.guild.categories, name=newcatname) is None:
            overwrites = {
            message.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            mod: discord.PermissionOverwrite(read_messages=True),
            }
            await message.guild.create_category(newcatname, overwrites=overwrites)

        incat = discord.utils.get(message.guild.categories, name=nametoreplace)
        fcat = discord.utils.get(message.guild.categories, name=newcatname)

        if incat is None:  
            await message.reply(f"Category with the name `{nametoreplace}` does not exist. Lear to spell pls.")
        if fcat is None:
            await message.reply(f"Category with the name `{newcatname}` does not exist. Lear to spell pls.")
        else:
            for chan in incat.channels:
                await chan.edit(category=fcat, sync_permissions=True)
            await message.reply(f"Your stuff was succesfully archived to #{newcatname}.")
        await incat.delete()
        await message.reply("The old category got yeeted into the nether.")

    # verifies that all categories for the courses exist or makes them if they don't
    if message.content.startswith('!newyearcat') and is_mod: 
        mchan = discord.utils.get(message.guild.channels, name="math-roles") 
        p1chan = discord.utils.get(message.guild.channels, name="1st-year-roles") 
        p2chan = discord.utils.get(message.guild.channels, name="2nd-year-roles") 
        p3chan = discord.utils.get(message.guild.channels, name="3rd-year-roles") 
        p4chan = discord.utils.get(message.guild.channels, name="4th-year-roles") 
        astchan = discord.utils.get(message.guild.channels, name="astro-roles") 
        ethchan = discord.utils.get(message.guild.channels, name="ethics-roles") 

        mcat = discord.utils.get(message.guild.categories, name="MATH COURSES")
        p1cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 100 LEVEL")
        p2cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 200 LEVEL")
        p3cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 300 LEVEL")
        p4cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 400 LEVEL")
        astcat = discord.utils.get(message.guild.categories, name="ASTRO COURSES") 
        ethcat = discord.utils.get(message.guild.categories, name="ETHICS COURSES")

        listofchans = [mchan, p1chan, p2chan, p3chan, p4chan, astchan, ethchan]

        membrole = discord.utils.get(message.guild.roles, id=698388933511217155)
        everyonerole = discord.utils.get(message.guild.roles, id=698388933511217152)
        newuserrole = discord.utils.get(message.guild.roles, id=831644590779793458)

        if mcat is None:
            await message.guild.create_category("MATH COURSES")
        if astcat is None:
            await message.guild.create_category("ASTRO COURSES")
        if ethcat is None:
            await message.guild.create_category("ETHICS COURSES")
        if p1cat is None:
            await message.guild.create_category("PHY COURSES - 100 LEVEL")
        if p2cat is None:
            await message.guild.create_category("PHY COURSES - 200 LEVEL")
        if p3cat is None:
            await message.guild.create_category("PHY COURSES - 300 LEVEL")
        if p4cat is None:
            await message.guild.create_category("PHY COURSES - 400 LEVEL")

        mcat = discord.utils.get(message.guild.categories, name="MATH COURSES")
        p1cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 100 LEVEL")
        p2cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 200 LEVEL")
        p3cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 300 LEVEL")
        p4cat = discord.utils.get(message.guild.categories, name="PHY COURSES - 400 LEVEL")
        astcat = discord.utils.get(message.guild.categories, name="ASTRO COURSES") 
        ethcat = discord.utils.get(message.guild.categories, name="ETHICS COURSES")
        
        listofcats = [mcat, p1cat, p2cat, p3cat, p4cat, astcat, ethcat]

        for categorything in listofcats:
            await categorything.set_permissions(membrole, read_messages=True)
            await categorything.set_permissions(newuserrole, read_messages=False)
            await categorything.set_permissions(everyonerole, read_messages=False)

        for numb in range(len(listofchans)):
            if listofchans[numb] is not None:
                await listofchans[numb].edit(category=listofcats[numb])
                await listofchans[numb].set_permissions(membrole, send_messages=False, read_messages=True)
                await listofchans[numb].set_permissions(newuserrole, read_messages=False)
                await listofchans[numb].set_permissions(everyonerole, read_messages=False)
        
        await message.reply("Ez")

    # periodically refreshing chat (must be at bottom or it will delay the other commands)
    if message.channel.id in REFRESH_CHANNELS:
        try:
            await log_message(message)
            await asyncio.sleep(60 * REFRESH_DELAY)
            await message.add_reaction(ED_WITTEN)
            await message.delete(delay=10)
        except Exception as ex:
            print(ex)


# saves quotes dictionary to a CSV file
def save_quotes(quotelist:dict):
    delim = "|"
    with open("physuquotes.csv", "w") as q:
        if len(quotelist) != 0:
            for i in range(len(quotelist['Quote'])):
                line = []
                for headers in quotelist:
                    try:
                        line.append(quotelist[f'{headers}'][i])                            
                    except:
                        print("This is where it all went wrong.")
                print(delim.join(line), file=q)


def savebestie(num):    
     with open("bestie.csv", "w") as q:
        print(num, file=q)
    

def getbestie():  
     with open("bestie.csv", "r") as q:
        reader = csv.reader(q, delimiter="|")
        num = []
        fnum = 0
        for i in reader:
            num.append(i)
        try:
            fnum = num[0][0]
            fnum = int(fnum)
        except:
            print("Things r weird")
        return fnum


def read_csv(file):
    resp = requests.get(file.url)
    resp.raise_for_status()
    return list(csv.reader(io.StringIO(resp.text)))


def get_category_key(course):
    dept = course[:3]
    level = course[3]
    if dept == 'PHY':
        return f'PHY{level}'
    return dept


def get_events():
    try:
        response = requests.get(CAL_URL, timeout=10)
        cal = Calendar.from_ical(response.content)
        upcoming = []
        for component in cal.walk():
            if component.name != 'VEVENT':
                continue
            start = component.get('DTSTART').dt
            # normalize to datetime if it's a date-only event
            if not isinstance(start, datetime):
                start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
            if not start.tzinfo:
                start = start.replace(tzinfo=timezone.utc)
            uid = str(component.get('uid'))
            name = str(component.get('summary'))
            location = str(component.get('location'))
            description = str(component.get('description'))
            upcoming.append((uid, name, location, description, start))
        return upcoming
    except Exception as e:
        print(f'iCal fetch error: {e}')
        return []


def get_response(channel_id, message):
    # initialize and populate context in this channel
    if channel_id not in context:
        context[channel_id] = SEED.copy()
    context[channel_id].append({"role": "user", "content": message})
    if len(context[channel_id]) > WINDOW:
        context[channel_id] = context[channel_id][-WINDOW:]
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": PROMPT}
            ] + context[channel_id],
            "stream": False
        }, timeout=200)
        reply = response.json()["message"]["content"]
        # append assistant reply to context
        context[channel_id].append({"role": "assistant", "content": reply})
        return reply
    except requests.exceptions.Timeout:
        return "Sorry, the model took too long to respond."
    except Exception as e:
        print(f'Ollama error: {e}')
        return "Sorry, something went wrong with the language model."


@client.event
async def on_raw_reaction_add(payload): # handles adding the Ed emoji
    if payload.message_id == 987409394532745237:
        guild = await client.fetch_guild(payload.guild_id)
        if payload.emoji.name == "ed":               
            role = get(guild.roles, id=987402556848345108)
            await payload.member.add_roles(role)


async def create_course_channel(guild, name):
   #  Creates a course channel with the given name
   #  Args:
   #     guild (discord.Guild): The guild to create the channel in
   #     name (str): The name of the channel to create
   # Returns:
   #     discord.TextChannel: The created channel
    name = name.upper()
    dept = name[:3]
    level = int(name[3])

    if dept == 'PHY':
        category = f'PHY Courses - {level}00 Level'
    else:
        category = {
            'AST': 'Astro Courses',
            'MAT': 'Math Courses',
            'APM': 'Math Courses',
            'JPH': 'Ethics Courses',
            'JPE': 'Ethics Courses',
        }[dept]

    emoji = {
        'PHY': '📘📖',
        'MAT': '📕📖',
        'APM': '📗📖',
        'AST': '📔📖',
        'JPH': '📔📖',
        'JPE': '📔📖',
    }[dept]

    print(name, emoji, category)

    category = discord.utils.get(guild.categories, name=category.upper())
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        print('Role not found, creating.')
        role = await guild.create_role(name=name)

    mod = discord.utils.get(guild.roles, name='Moderator')

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        role: discord.PermissionOverwrite(read_messages=True),
        mod: discord.PermissionOverwrite(read_messages=True),
    }
    await guild.create_text_channel(f'{emoji}{name.lower()}', category=category, overwrites=overwrites)


@tasks.loop(minutes=1) 
async def timedmessages(): # sends messages from the timed messages file if the time has arrived
    dictmes = get_dict('tmes.csv')
    timenow = time.time()
    keyslist= list(dictmes.keys())
    fkey = keyslist[0]  
    counterlist= []

    for i in range(len(dictmes[fkey])):
        if float(dictmes['Time'][i]) <= timenow:
            try:
                chan = await client.fetch_channel(dictmes['Channel'][i])
            except:
                chan = await client.fetch_channel(959108984332234842)
                await chan.send("@Moderator The following message has channel issues.")
            await chan.send(dictmes['Message'][i])
            counterlist.append(i)

    counterlist.sort(reverse=True)
    for i in counterlist:
        for key in keyslist:
            del dictmes[key][i]
    counterlist = []
    save_dict(dictmes, 'tmes.csv')


@tasks.loop(hours=1)
async def archiveColloquia():
    currentColloquia = get_dict("physucolloquia.csv")
    try:
        archivedColloquia = get_dict("physucolloquiaarchive.csv")
    except:
        chan = await client.fetch_channel(1236737086762123274)
        await chan.send('The list of archived colloquia file does not exist. I am gonna make a new one, but maybe you should do smt about it.')
        save_dict({
                'Title': [],
                'Speaker': [],
                'Time': [],
                'Room': []
            },"physucolloquiaarchive.csv")
        archivedColloquia = get_dict("physucolloquiaarchive.csv")
    timenow = time.time()
    try:
        oldList = []
        for j in range(len(currentColloquia["Time"])):
            if checkPastDay(float(currentColloquia["Time"][j]), timenow):
                oldList.append(j)
    except:
        print("Just Give Up")
    try:
        newArchived = mergeTwoDictionaries(archivedColloquia, truncateDict(currentColloquia, oldList))
        newArchived = timeSortDict(newArchived)
        save_dict(newArchived, "physucolloquiaarchive.csv")
        save_dict(timeSortDict(removeMultipleFromDict(currentColloquia, oldList)), "physucolloquia.csv")
    except:
        print("Other Difficulties")


@tasks.loop(minutes=1)
async def hourlyQuote():
    newTime = time.strftime("%D %H:%M", time.localtime(time.time())).split(' ')[1]
    if currentDay[1].split(":")[0] != newTime.split(":")[0]:
        currentDay[1] = newTime
        chan = await client.fetch_channel(1236737086762123274)
        #await chan.send("Here is the hourly quote: ")
        #await chan.send("!quote")


@tasks.loop(minutes=1)
async def announce_events():
    channel = client.get_channel(ACADEMIC_ANNOUNCE)
    now = datetime.now(tz=timezone.utc)
    for uid, name, location, description, start in get_events():
        time_until = (start - now).total_seconds()
        if 3540 <= time_until <= 3660 and uid not in announced:
            local_start = start.astimezone(TORONTO)
            time_str = local_start.strftime('%I:%M %p')
            if ANNOUNCER:
                await channel.send(f'@here Reminder: **{name}** happening at {time_str} in {location}! Description: {description}')
                announced.add(uid)

if not DEBUG_MODE:
    client.run(SECRET_KEY) # connects to server
