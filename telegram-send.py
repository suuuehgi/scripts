#!/usr/bin/python3

# pip3 install --user --upgrade python-telegram-bot

import os, sys, telegram

if len([i for i in sys.argv if i in ['-h', '--help']]) > 0:
    print('Usage: telegram-send file/message')
    sys.exit(0)

bot = telegram.Bot('xxxxxxxxx:YYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYYY')
chat_id=111111111

payload = sys.argv[1:]

# Send (single) file
if len(payload) == 1 and os.path.isfile(payload[0]):
    bot.send_document(chat_id=chat_id, document=open(payload[0], 'rb'))

# Send message
else:
    message = ' '.join(payload)
    bot.send_message( chat_id=chat_id, text=message, parse_mode=telegram.ParseMode.MARKDOWN )
