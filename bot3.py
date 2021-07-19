#!/usr/bin/env python
# pylint: disable=C0116,W0613
# This program is dedicated to the public domain under the CC0 license.

"""
First, a few callback functions are defined. Then, those functions are passed to
the Dispatcher and registered at their respective places.
Then, the bot is started and runs until we press Ctrl-C on the command line.

Usage:
Example of a bot-user conversation using nested ConversationHandlers.
Send /start to initiate the conversation.
Press Ctrl-C on the command line or send a signal to the process to stop the
bot.
"""
import sys
import os
import logging
import pymongo
from pymongo.message import query
from bson.objectid import ObjectId
import constants as C
from datetime import datetime
import json
from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

import logging
from typing import Tuple, Dict, Any

from telegram import (InlineKeyboardMarkup, InlineKeyboardButton, Update, chat)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackQueryHandler,
    CallbackContext,
)
from telegram.utils import helpers
#from telegram.utils.helpers import escape_markdown, helpers

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING
)

logger = logging.getLogger(__name__)

# State definitions for top level conversation
SELECTING_ACTION, TRADING, EDITING, DOWNLOADING = map(chr, range(4))
# State definitions for item 
SELECTING_FEATURE, SELECTING_CATEGORY, TYPING, SAVING = map(chr, range(4, 8))
# Meta states
STOPPING, SHOWING, REPLYING, CALLING, SEARCHING, TRACKING, PAGE_MASSAGES, PAGE_ITEMS, PREV_PAGE, NEXT_PAGE = map(chr, range(8, 18))
# Shortcut for ConversationHandler.END
END = ConversationHandler.END

# Different constants for editing item
(
    FEATURE, 
        NAME,
        VALUE,
        DESCRIPTION,
    CATEGORY, 
        #CATEGORY_VALUE,
    IMAGE,
    DOCUMENT,
    VOICE
) = map(chr, range(18, 26))

class Bot:
    # static helpers
    def facts_to_str(user_data: Dict[str, str]) -> str:
        """Helper function for formatting the gathered user info."""
        excludeKeys = {PREV_PAGE, NEXT_PAGE, PAGE_MASSAGES, PAGE_ITEMS, TRADING, REPLYING, CALLING, VOICE, '_id', 'chat_id', 'Images', 'Files'}
        #translation_table = dict.fromkeys(map(ord, '!$*-`_()[].'), "\\")
        #value.translate(translation_table)
        facts = [f'*{key}*: `{helpers.escape_markdown(str(value), version=2)}`' for key, value in user_data.items() if key not in excludeKeys]
        result = "\n".join(facts).join(['\n', '\n'])
        #print(result)
        return result

    def facts_to_save(user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Helper function for saving in database."""
        excludeKeys = {PREV_PAGE, NEXT_PAGE, PAGE_MASSAGES, PAGE_ITEMS, TRADING, REPLYING, CALLING, VOICE, '_id'}
        return {x: user_data[x] for x in user_data if x not in excludeKeys}

    def get_value_from_string(data):
        #int(''.join(c for c in s if c.isdigit()))
        #import re
        #re.findall("\d+\.\d+", "Current Level: 13.4 db.")
        value = 0.0
        if data is None:
            return value
        try:
            value = float(str(data).replace(',', '').replace('$', '').strip(' '))
        except:
            pass
        return value

    # instance members
    def __init__(self):
        self.myclient = pymongo.MongoClient(C.MONGODB_CONNECTION_URL)
        self.botDB = self.myclient["botDB"]
        authenticator = IAMAuthenticator(C.IBM_KEY)
        self.speech_to_text = SpeechToTextV1(authenticator=authenticator)
        self.speech_to_text.set_service_url(C.IBM_SERVICE_URL)
        #InsecureRequestWarning: Unverified HTTPS request is being made to host 'api.au-syd.speech-to-text.watson.cloud.ibm.com'. Adding certificate verification is strongly advised. See: https://urllib3.readthedocs.io/en/1.2
        #self.speech_to_text.set_disable_ssl_verification(True)

    def remove_page_messages(self, update: Update, context: CallbackContext):
        #print("remove_page_messages")
        try:
            _chat_id = update.callback_query.message.chat_id
        except:
            _chat_id = update.message.chat_id

        #print("remove_page_messages: 2")
        chat_data = context.chat_data
        if PAGE_MASSAGES in chat_data and _chat_id:
            #print("remove_page_messages: 3")
            for _id in chat_data[PAGE_MASSAGES]:
                try:
                    context.bot.delete_message(chat_id=_chat_id, message_id=_id)
                except:
                    pass
        chat_data[PAGE_MASSAGES] = []
        #print("remove_page_messages: 4")

    # Top level conversation callbacks
    def start(self, update: Update, context: CallbackContext) -> str:
        """Select an action: Adding parent/child or show data."""
        #print("start")
        #print("update.callback_query:"+ str(bool(update.callback_query)))
        #print("update.message:"+ str(bool(update.message)))
        self.remove_page_messages(update,  context)

        buttons = [
            [
                InlineKeyboardButton(text='✏️Update Item', callback_data=str(EDITING)),
                InlineKeyboardButton(text='ℹ️Show Item', callback_data=str(SHOWING)),
            ],
            [
                InlineKeyboardButton(text=f"🔎Search & Trade", callback_data=str(SEARCHING)),
                InlineKeyboardButton(text=f"⛓Trades History", callback_data=str(TRACKING)),
            ],
            [
                InlineKeyboardButton(text='⏹Exit Conversation', callback_data=str(END)),
            ],
        ]
        keyboard = InlineKeyboardMarkup(buttons)
        _text="To abort session, type /stop or click [Stop]."
        # If we're calling, don't need to send a new message
        if bool(update.callback_query):
            #print("start:CALLING")
            if (_text != update.callback_query.message.text):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=_text, reply_markup=keyboard)
        elif bool(update.message):
            #print("start:REPLYING")
            update.message.reply_text(
                "Hi {}, Let's trade-in!".format(update.message.from_user.first_name)
            )
            update.message.reply_text(text=_text, reply_markup=keyboard)

        #print("start:redirecting")
        return SELECTING_ACTION


    def history(self, update: Update, context: CallbackContext) -> str:
        #print("history of otcoming trades")
        self.remove_page_messages(update,  context)
        try:
            chat_id = update.callback_query.message.chat_id
        except:
            chat_id = update.message.chat_id
        count = self.botDB["transactions"].count_documents( { "from_chat_id" : chat_id } )
        trans = self.botDB["transactions"].find( { "from_chat_id" : chat_id } )
        chat_data = context.chat_data
        user_data = context.user_data

        #print(f"count:{count}, offset:{offset}")
        buttons = []
        # if (offset > 0 and offset >= PAGE_SIZE):
        #     buttons.append(InlineKeyboardButton(text='⬅️Prev page', callback_data=str(PREV_PAGE)))
        # if (offset + PAGE_SIZE < count):
        #     buttons.append(InlineKeyboardButton(text='➡️Next page', callback_data=str(NEXT_PAGE)))
        buttons.append(InlineKeyboardButton(text='🔙Back to main menu', callback_data=str(END)))
        keyboard = InlineKeyboardMarkup([buttons])

        if bool(update.callback_query):
            _text = (f"{count} historical trade-in(s) found")
            if (_text != update.callback_query.message.text):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=_text, reply_markup=keyboard)
        transNo = 0
        for tran in trans:
            item = self.botDB["items"].find_one({"_id": ObjectId(tran['item_id'])})
            _text = ""
            _image_ids = ""
            transNo +=1
            facts={'Trans No': str(transNo), 'Trade Date': str(tran['trans_date'])[0:16]} #"%d/%m/%y %H:%M"
            #facts["To owner"] = str(tran['to_chat_id'])
            for key, value in item.items():
                facts[key] = str(value)
            _text = Bot.facts_to_str(facts)
            item_message = context.bot.send_message(chat_id=update.callback_query.message.chat_id
                ,text=_text
                #, reply_markup=InlineKeyboardMarkup([[
                #        InlineKeyboardButton(text='ℹ️SHOWING', callback_data=str(SAVING))
                #    ]])
                #, reply_to_message_id=update.callback_query.message.message_id
                , parse_mode='MarkdownV2') #ParseMode.MARKDOWN_V2
            chat_data[PAGE_MASSAGES].append(item_message.message_id)
            #context.bot.send_media_group(chat_id=get_chat_id(update, context), media=list)
            if (_image_ids != ""):
               for image_id in _image_ids.split('|'):
                   if (image_id != ""):
                       try:
                           image_message = context.bot.send_photo(chat_id=update.callback_query.message.chat_id
                               , reply_to_message_id=item_message.message_id
                               , photo=image_id
                               , caption="Attached image")
                           chat_data[PAGE_MASSAGES].append(image_message.message_id)
                       except:
                           pass

        return TRACKING #SEARCHING is ok as well

    #not implemented yet
    def search_text_filter(self, update: Update, context: CallbackContext) -> str:
        chat_data = context.chat_data
        user_data = context.user_data
        return SEARCHING

    def search(self, update: Update, context: CallbackContext) -> str:
        #print("search")
        self.remove_page_messages(update,  context)
        chat_data = context.chat_data
        user_data = context.user_data
        PAGE_SIZE = 5
        try:
            chat_id = update.callback_query.message.chat_id
        except:
            chat_id = update.message.chat_id

        trans = self.botDB["transactions"].find( { "from_chat_id" : chat_id } , projection = { "item_id" : True } )
        exsclude_preowned_items = [None]
        for tran in trans:
            exsclude_preowned_items.append(tran['item_id'])

        condition = {"$and": [
                { "chat_id" : { "$nin": [None, chat_id] } },    #exclude currently owned item
                { "_id" : { "$nin": exsclude_preowned_items } } #exclude preowned items
            ]
        }
        #DEBIG condition = { "_id" : { "$ne": None } }
        count = self.botDB["items"].count_documents(condition)

        if PREV_PAGE not in user_data:
            user_data[PREV_PAGE] = 0
        if PAGE_ITEMS not in user_data:
            user_data[PAGE_ITEMS] = {}


        offset = int(user_data[PREV_PAGE])
        if (update.callback_query.data == PREV_PAGE):
            offset = offset - PAGE_SIZE
        elif (update.callback_query.data == NEXT_PAGE):
            offset = offset + PAGE_SIZE
        user_data[PREV_PAGE] = offset
        #print(f"count:{count}, offset:{offset}")
        buttons = []
        if (offset > 0 and offset >= PAGE_SIZE):
            buttons.append(InlineKeyboardButton(text='⬅️Prev page', callback_data=str(PREV_PAGE)))
        if (offset + PAGE_SIZE < count):
            buttons.append(InlineKeyboardButton(text='➡️Next page', callback_data=str(NEXT_PAGE)))
        buttons.append(InlineKeyboardButton(text='🔙Back to main menu', callback_data=str(END)))
        keyboard = InlineKeyboardMarkup([buttons])

        items = self.botDB["items"].find(condition).skip(offset).limit(PAGE_SIZE)

        if bool(update.callback_query):
            pagesTotal = int(count/PAGE_SIZE)
            if (count % PAGE_SIZE)>0:
                pagesTotal +=1
            _text = (f"Page {int(offset/PAGE_SIZE) + 1} of {pagesTotal}. {count} item(s) found in total.") #You can type to search by text
            if (_text != update.callback_query.message.text):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=_text, reply_markup=keyboard)
        itemNo = int(offset * PAGE_SIZE)
        for item in items:
            _text = ""
            _image_ids = ""
            itemNo +=1
            facts={'Item No': str(itemNo)}
            for key, value in item.items():
                facts[key] = str(value)
                if (key =='Images'):
                    _image_ids = str(value)
            _text = Bot.facts_to_str(facts)
            item_message = context.bot.send_message(chat_id=update.callback_query.message.chat_id
                ,text=_text
                , reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(text='🛒Trade Item No: '+str(itemNo), callback_data=str(SAVING))
                    ]])
                #, reply_to_message_id=update.callback_query.message.message_id
                , parse_mode='MarkdownV2') #ParseMode.MARKDOWN_V2
            chat_data[PAGE_MASSAGES].append(item_message.message_id)
            user_data[PAGE_ITEMS][item_message.message_id] = item['_id']

            #context.bot.send_media_group(chat_id=get_chat_id(update, context), media=list)
            if (_image_ids != ""):
                for image_id in _image_ids.split('|'):
                    if (image_id != ""):
                        try:
                            image_message = context.bot.send_photo(chat_id=update.callback_query.message.chat_id
                                , reply_to_message_id=item_message.message_id
                                , photo=image_id
                                , caption="Attached image")
                            chat_data[PAGE_MASSAGES].append(image_message.message_id)
                        except:
                            pass

        return SEARCHING

    def item_details(self, update: Update, context: CallbackContext) -> str:
        """Pretty print gathered data."""
        #print("item_details")
        item = self.botDB["items"].find_one({"chat_id": update.callback_query.message.chat_id})
        chat_data = context.chat_data

        if (item is not None and update.callback_query.data == DOWNLOADING):
            _ids = str(item['Files']).strip('|').split('|')
            for file_id in _ids:
                if (file_id != ""):
                    try:
                        message = context.bot.sendDocument(chat_id=update.callback_query.message.chat_id,
                        document=file_id,
                        caption = 'Attached file')
                        chat_data[PAGE_MASSAGES].append(message.message_id)
                    except:
                        pass
            return SHOWING

        buttons = [InlineKeyboardButton(text='🔙Back', callback_data=str(END))]
        if (item is None):
            _text='*No information yet*\. Please setup your item first'
        else:
            _text="Here is your item details:"
            self.remove_page_messages(update,  context)
            facts={}
            for key, value in item.items():
                facts[key] = str(value)
                if (key == 'Files'):
                    buttons.insert(0, InlineKeyboardButton(text='💾Download', callback_data=str(DOWNLOADING)))
                elif (key =='Images'):
                    _ids = str(value).strip('|').split('|')
                    for image_id in _ids:
                        if (image_id != ""):
                            try:
                                message = context.bot.send_photo(chat_id=update.callback_query.message.chat_id
                                    , reply_to_message_id=update.callback_query.message.message_id
                                    , photo=image_id
                                    , caption="Attached image")
                                chat_data[PAGE_MASSAGES].append(message.message_id)
                            except:
                                pass
            _text += Bot.facts_to_str(facts)
            url = helpers.create_deep_linked_url(bot_username=context.bot.name.strip('@'), payload=f"{item['_id']}") #, group=False
            #https://t.me/{context.bot.name.strip('@')}?trade={item['_id']}
            _text += f"\nUse [▶️this link]({url}) to promote your item"

        keyboard = InlineKeyboardMarkup([buttons])
        if bool(update.callback_query):
            if (_text != update.callback_query.message.text):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=_text
                    , reply_markup=keyboard
                    , parse_mode='MarkdownV2') #ParseMode.MARKDOWN_V2
        elif bool(update.message):
            update.message.reply_text(text=_text
                , reply_markup=keyboard
                , parse_mode='MarkdownV2') #ParseMode.MARKDOWN_V2

        #user_data[CALLING] = True
        return SHOWING


    def item_edit(self, update: Update, context: CallbackContext):
        #print('item_edit')
        edit_item_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(text='❕Name', callback_data=str(NAME)),
                InlineKeyboardButton(text='❕Value', callback_data=str(VALUE)),
            ],
            [
                InlineKeyboardButton(text='Description', callback_data=str(DESCRIPTION)),
                InlineKeyboardButton(text='Other Category', callback_data=str(CATEGORY)),
            ],
            [
                InlineKeyboardButton(text='💾Save', callback_data=str(SAVING)),
                InlineKeyboardButton(text='🔙Back', callback_data=str(END)),
            ]
        ])
        chat_data = context.chat_data
        user_data = context.user_data
        #print ('user_data.get(CALLING):' + str(user_data.get(CALLING)))
        _text="Did not get chages yet :("
        if bool(update.callback_query):
            _text = "Update your item details.\nYou can also attach photos and files"
            if (_text != update.callback_query.message.text):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=_text, reply_markup=edit_item_keyboard)
        elif bool(update.message):
            if VOICE in user_data:
                _text = "Oh, did you say this? "+ user_data[VOICE]
                update.message.reply_text(text=_text, reply_markup=edit_item_keyboard, parse_mode='MarkdownV2')
                del user_data[VOICE]
            else:
                if ('Files' in user_data and bool(update.message.document)):
                    _text = "\nThe file will be visible for *you only* until new owner\!"
                    reply_to_file = context.bot.send_message(chat_id=update.message.chat_id
                        , reply_to_message_id=update.message.message_id
                        , text=_text, parse_mode='MarkdownV2')
                    chat_data[PAGE_MASSAGES].append(reply_to_file.message_id)
                elif ('Images' in user_data and bool(update.message.photo)):
                    _text = "The photo will be visible *for all*\!"
                    reply_to_file = context.bot.send_message(chat_id=update.message.chat_id
                        , reply_to_message_id=update.message.message_id
                        , text=_text, parse_mode='MarkdownV2')
                    chat_data[PAGE_MASSAGES].append(reply_to_file.message_id)
                else:
                    _text = ("Got it\! Keep changing and click *💾Save* to finish update, or *Back* to cancel and return"
                        f"{Bot.facts_to_str(user_data)}")
                    update.message.reply_text(text=_text, reply_markup=edit_item_keyboard, parse_mode='MarkdownV2')
        return SELECTING_FEATURE

    def regular_choice(self, update: Update, context: CallbackContext) -> int:
        """Ask the user for info about the selected predefined choice."""
        if (update.callback_query.data == NAME):
            text = "Name"
        elif (update.callback_query.data == VALUE):
            text = "Value"
        elif (update.callback_query.data == DESCRIPTION):
            text = "Description"
        else: #Categoty
            text = "Unknown"
        #print('regular_choice:'+ text)

        user_data = context.user_data
        user_data[CATEGORY] = text
        update.callback_query.answer()
        update.callback_query.edit_message_text(f'Item {text.lower()}? Please type the value:')
        return TYPING

    def custom_choice(self, update: Update, context: CallbackContext) -> int:
        #print('custom_choice:'+update.callback_query.id)
        """Ask the user for a description of a custom category."""
        update.callback_query.answer()
        update.callback_query.edit_message_text(text="Describe the category, for example *Colour* or *Size*", parse_mode='MarkdownV2')
        return SELECTING_CATEGORY

    def custom_text(self, update: Update, context: CallbackContext) -> int:
        """Ask the user for info about the selected predefined choice."""
        text = update.message.text
        #print('custom_text:'+text)

        user_data = context.user_data
        user_data[CATEGORY] = text
        update.message.reply_text(f'Item {text.lower()}? Please type the value:')
        return TYPING

    def received_information(self, update: Update, context: CallbackContext) -> int:
        """Store info provided by user and ask for the next category."""
        user_data = context.user_data
        text = update.message.text
        #print('received_information:'+ text)
        if CATEGORY in user_data:
            category = user_data[CATEGORY]
            user_data[category] = text
            del user_data[CATEGORY]

        #go to the start again
        return self.item_edit(update, context)


    def edit_commit(self, update: Update, context: CallbackContext) -> int:
        """Display the gathered info and end the conversation."""
        #print("edit_commit")
        user_data = context.user_data

        if CATEGORY in user_data:
            del user_data[CATEGORY]
        
        facts = Bot.facts_to_save(user_data)
        facts['chat_id'] = update.callback_query.message.chat_id
        items_coll = self.botDB["items"]
        item = items_coll.find_one({"chat_id": facts['chat_id']})
        if (item is None):
            inserted_item = items_coll.insert_one(facts)
            if (bool(inserted_item)):
                _id = str(inserted_item.inserted_id)
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=f"The item {_id} is inserted")
        elif (bool(item)):
            _id = item['_id']
            edited_item = items_coll.find_one_and_update(filter={"_id": ObjectId(_id), "chat_id": facts['chat_id']}, 
                update={"$set": facts}, upsert=True, return_document=True)
            if (bool(edited_item)):
                update.callback_query.answer()
                update.callback_query.edit_message_text(text=f"👏Welldone! The item is updated and ready to trade")

        user_data.clear()
        self.remove_page_messages(update,  context)
        return self.start(update, context)
        #return END


    def received_photo(self, update: Update, context: CallbackContext):
        """
        bot sends image in multiple resolutions, last one is the highest one
        """
        user_data = context.user_data
        chat_data = context.chat_data
        if 'Images' in user_data:
            user_data['Images'] += "|"
        else:
            user_data['Images'] = ""
        if update.message.photo[0].file_id not in user_data['Images']: 
            user_data['Images'] += (update.message.photo[0].file_id).strip('|')

        chat_data[PAGE_MASSAGES].append(update.message.message_id)

        return self.item_edit(update, context)

    def received_voice(self, update: Update, context: CallbackContext):
        """
        bot sends audio to IBM Speech to Text: 
        https://cloud.ibm.com/catalog/services/speech-to-text
        https://cloud.ibm.com/apidocs/speech-to-text?code=python#recognize
        """
        # print(update.message.voice)
        #voice_content = update.message.voice.get_file()
        # context.bot.get_file(update.message.voice.file_id)
        voice_content = update.message.voice.get_file()
        chat_data = context.chat_data
        chat_data[PAGE_MASSAGES].append(update.message.message_id)

        user_data = context.user_data
        #try:
        speech_recognition_results = self.speech_to_text.recognize(
            audio=voice_content.download_as_bytearray(),
            #https://cloud.ibm.com/apidocs/speech-to-text-icp?code=python
            content_type='audio/l16', #Audio formats (content types)
            
            word_alternatives_threshold=0.9,
            keywords=['name', 'value', 'description', 'category', 'save', 'back'],
            keywords_threshold=0.5
        ).get_result()

        if speech_recognition_results.status_code != 200 or not speech_recognition_results:
            user_data[VOICE] = "Sorry, I could not hear you well :("
        else:
            user_data[VOICE] = str(json.dumps(speech_recognition_results, indent=2))
            print("VOICE"+ user_data[VOICE])
        #except:
        #    print("Unexpected voice error:", sys.exc_info()[0])
        #    pass

        return self.item_edit(update, context)

    def trade_command(self, update: Update, context: CallbackContext):
        print('trade_command')
        user_data = context.user_data
        chat_data = context.chat_data
        validation_error=""
        item_id = None
        if (len(context.args) <= 0):
            validation_error = "❌Please provide correct item id for direct trade"
        else:
            item_id = context.args[0]

        print('trade_command item_id:'+str(item_id))
        try:            
            if bool(update.callback_query):
                chat_id = update.callback_query.message.chat_id
            elif bool(update.message):
                chat_id = update.message.chat_id
        except:
            chat_id = None

        print('trade_command chat_id:'+str(chat_id))

        item = None
        if (item_id != None):
            try:
                item = self.botDB["items"].find_one(filter={"_id": ObjectId(item_id)})
            except:
                item = None

        if (item is None):
            validation_error = "❌Sorry, this item id is incorrect or not avaialable anymore!"
        elif (item['chat_id'] == chat_id):
            validation_error = "❌Sorry, this item is already owned by you"
        if (validation_error !=""):
            #print ("trade_command validation error:"+validation_error)
            reply_message = context.bot.send_message(chat_id=chat_id ,text=validation_error)
            chat_data[PAGE_MASSAGES].append(reply_message.message_id)
            return SEARCHING

        if PAGE_ITEMS not in user_data:
            user_data[PAGE_ITEMS] = {}

        self.remove_page_messages(update,  context)
        facts={}
        _image_ids =""
        for key, value in item.items():
            facts[key] = str(value)
            if (key == 'Images'):
                _image_ids = str(value).strip('|')

        _text = Bot.facts_to_str(facts)
        if (_text != ""):
            _text = "Here is item details:"+ _text
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(text='🛒Trade', callback_data=str(SAVING)),
                    InlineKeyboardButton(text='🔙Back', callback_data=str(END)),
                ]
            ])
            #print('trade_command _text:'+_text)
            message_id = 0
            if (bool(update.callback_query) and update.callback_query.message is not None and update.callback_query.message.text != ""):
                print("trade_command response1")
                if (_text != update.callback_query.message.text):
                    update.callback_query.answer()
                    update.callback_query.edit_message_text(text=_text, reply_markup=keyboard, parse_mode='MarkdownV2')
                    message_id = update.callback_query.message.message_id
            elif bool(update.message):
                print("trade_command response2")
                update.message.reply_text(text=_text, reply_markup=keyboard, parse_mode='MarkdownV2')
                message_id = update.message.message_id
            else:
                print("trade_command response3")
                reply_message = context.bot.send_message(chat_id=chat_id, text=_text, reply_markup=keyboard, parse_mode='MarkdownV2')
                chat_data[PAGE_MASSAGES].append(reply_message.message_id)
                message_id = reply_message.message_id

            if (message_id > 0 and _image_ids !=""):
                for image_id in _image_ids.split('|'):
                    if (image_id != ""):
                        image_message = context.bot.send_photo(chat_id=chat_id
                            , reply_to_message_id=message_id
                            , photo=_image_ids[0]
                            , caption="Attached image")
                        chat_data[PAGE_MASSAGES].append(image_message.message_id)

            user_data[PAGE_ITEMS][message_id] = item_id
            print("trade_command redirect:"+ item_id)
            return SEARCHING #self.trade_commit(update, context)

    def trade_commit(self, update: Update, context: CallbackContext) -> int:
        """Display the gathered info and end the conversation."""
        print("trade_commit")
        user_data = context.user_data
        chat_data = context.chat_data
        self.remove_page_messages(update,  context)
        chat_id1 = None
        item1 = None
        item2 = None
        message_id = None
        validation_error=""
        if PAGE_ITEMS not in user_data:
            user_data[PAGE_ITEMS] = {}

        try:            
            if bool(update.callback_query):
                chat_id1 = update.callback_query.message.chat_id
                message_id = update.callback_query.message.message_id
            elif bool(update.message):
                chat_id1 = update.message.chat_id
                message_id = update.message.message_id
        except:
            chat_id1 = None

        print('trade_commmit chat_id:'+str(chat_id1))

        items_coll = self.botDB["items"]
        if (chat_id1 != None):
            try:
                item1 = items_coll.find_one({"chat_id": chat_id1})
            except:
                pass

        if (message_id != None):
            try:
                if message_id in user_data[PAGE_ITEMS]:
                    item2 = items_coll.find_one(filter={"_id": ObjectId(user_data[PAGE_ITEMS][message_id])})
                    del user_data[PAGE_ITEMS][message_id]
            except:
                item2=None

        if (item1 is None):
            validation_error = "❌Sorry, you have no item to trade-in with others yet, please update you item first!"
        elif (item2 is None):
            validation_error = "❌Sorry, that item is not avaialable anymore!"
        elif (item1['_id'] == item2['_id']):
            validation_error = "❌Sorry, the item for trade is the same"
        elif (item1['chat_id'] == item2['chat_id']):
            validation_error = "❌Sorry, both items have the same owner"
        elif (Bot.get_value_from_string(item1['Value']) < Bot.get_value_from_string(item2['Value'])):
            validation_error = "❌Sorry, your item has lower value."
        else:
            #check if owner2 traded item1 before
            trade_count = self.botDB["transactions"].count_documents(filter={"item_id": item1['_id'], "from_chat_id": item2['chat_id']})
            if (trade_count>0):
                validation_error = f"❌Sorry, Your item {item1['Name']} was already preowned by that person and can't be trade-in again"
            else:
                #check if owner1 traded item2 before
                trade_count = self.botDB["transactions"].count_documents(filter={"item_id": item2['_id'], "from_chat_id": item1['chat_id']})
                if (trade_count>0):
                    validation_error = f"❌Sorry, that {item2['Name']} was already preowned by you and can't be trade-in again"

        if (validation_error !=""):
            reply_message = context.bot.send_message(chat_id=item1['chat_id'] ,text=validation_error)
            chat_data[PAGE_MASSAGES].append(reply_message.message_id)

            return SEARCHING

        trans_coll = self.botDB["transactions"]
        trans1 = dict() #Dict[str, Any]
        trans1['trans_date'] = datetime.now()
        trans1['item_id'] = item1['_id']
        trans1['from_chat_id'] = item1['chat_id']
        trans1['to_chat_id'] = item2['chat_id']
        trans2 = dict()
        trans2['trans_date'] = trans1['trans_date']
        trans2['item_id'] = item2['_id']
        trans2['from_chat_id'] = item2['chat_id']
        trans2['to_chat_id'] = item1['chat_id']

        #print("start multi-document transaction") 
        #https://pymongo.readthedocs.io/en/stable/api/pymongo/client_session.html
        with self.myclient.start_session() as session:
            with session.start_transaction():
                reply1 = trans_coll.insert_many([trans1, trans2], session=session)
                if (reply1.acknowledged==True and len(reply1.inserted_ids)==2):
                    items_coll.find_one_and_update(filter={'_id': ObjectId(item1['_id']), 'chat_id': item1['chat_id']}, 
                            update={'$set': {'chat_id': item2['chat_id'] } },
                            projection = { "_id" : True }, 
                            session=session) #, upsert=True, return_document = True
                    items_coll.find_one_and_update(filter={'_id': ObjectId(item2['_id']), 'chat_id': item2['chat_id']}, 
                            update={'$set': {'chat_id': item1['chat_id'] } },
                            projection = { "_id" : True }, 
                            session=session) #, upsert=True, return_document = True
                    session.commit_transaction()
                    #print("transaction commited")
                    try: #try to notify owners, do not use answer/reply, parent message does not already exist
                        _text = "👏The trade-in is done! Check your new item details by running /start command"
                        reply_message = context.bot.send_message(chat_id=item1['chat_id'], text=_text)
                        chat_data[PAGE_MASSAGES].append(reply_message.message_id)
                        
                        context.bot.send_message(chat_id=item2['chat_id'] ,text=_text)
                    except:
                        pass
        #print("end transaction")
        user_data.clear()
        #return self.start(update, context)
        return END


    def received_document(self, update: Update, context: CallbackContext):
        """
        bot sends 1 document, calling this function multiple times
        """
        #doc = update.message.document
        user_data = context.user_data
        chat_data = context.chat_data

        fileType = 'Files'
        if update.message.document.file_name.lower().split('.')[-1] in ['jpg','jpeg','png','bmp','tiff']:
            fileType = 'Images'

        if fileType not in user_data:
            user_data[fileType] = ""
        else:
            user_data[fileType] += "|"

        if update.message.document.file_id not in user_data[fileType]: 
            user_data[fileType] += (update.message.document.file_id).strip('|')

        chat_data[PAGE_MASSAGES].append(update.message.message_id)

        return self.item_edit(update, context)


    def end(self, update: Update, context: CallbackContext) -> int:
        """End conversation from InlineKeyboardButton."""
        _chat_id = 0
        try:
            _chat_id = update.callback_query.message.chat_id
        except:
            _chat_id = update.message.chat_id

        context.user_data.clear()
        self.remove_page_messages(update,  context)
        if (_chat_id> 0):
            context.bot.send_message(chat_id = _chat_id
                ,text='🏁Thank you. See you next time!')
        return END

    #stop and stop_nested are similar but operates on different levels
    def stop(self, update: Update, context: CallbackContext) -> int:
        """End Conversation by command."""
        context.user_data.clear()
        self.remove_page_messages(update,  context)
        update.message.reply_text('🏁Okay, bye')
        return END


    def error(self, update: Update, context: CallbackContext):
        logger.error(f"Update: {update}; caused error: {context.error}")

    def handle_message(self, update: Update, context: CallbackContext):
        # context.bot.edit_message_text(chat_id=update.message.chat.id,
        #                      text="Here are the values of stringList", message_id=update.message.message_id,
        #                      reply_markup=makeKeyboard(), parse_mode='HTML')
        user_message = str(update.message.text).lower()
        if user_message.strip('!') in ("hello", "hi"):
            response = f"🤟G'Day {update.message.from_user.first_name}!"
        elif user_message.strip('?') in ("who are you", "who is this", "what is this"):
            # creative traid-in bot
            response = (f"🤖I am {context.bot.name}."
                "This marketplace allowing to trade-in items with identical (or higher) value."
                "Type /start to init new session, or /help for more options")
        else:
            response = "😏hmm, looks like you need some /help"
        update.message.reply_text(response)

    def help_command(self, update: Update, context: CallbackContext):
        #chat_id = update.message.chat_id
        message_id = update.message.message_id
        reply=update.message.reply_text(
            "Type one of the following commands:"
            "\n/start - to initiate guided session"
            "\n/stop - to stop conversation"
            "\n/trade item_id - to trade directly with advertised item"
            "\nThere are some rules behind the scene:"
            "\n-Bot represents many owners, but each owner can have only one item at the same time."
            "\n-Owners can advertise their items externally. Bot will process provided deep links from external redirects."
            "\n-Comprehensive search by pages. Owners can see details and photos of other items and choose which one to trade-in with."
            "\n-Private content (files) is available only after transfer item ownership to new owner."
            "\n-The winner is the owner with maximum number of trades in history OR acquiring highest value item."
            "\n-👍Good luck in your trade-in process!"
        )
        chat_data = context.chat_data
        if PAGE_MASSAGES not in chat_data:
            chat_data[PAGE_MASSAGES] = []
        chat_data[PAGE_MASSAGES].append(reply.message_id)
        
    def run(self) -> None:
        """Run the bot."""
        # Create the Updater and pass it your bot's token.
        updater = Updater(C.TELEGRAM_TOKEN)
        # Get the dispatcher to register handlers
        dispatcher = updater.dispatcher

        # Set up top level ConversationHandler (selecting action)
        conv_handler = ConversationHandler(
            entry_points=[
                #deep link start from promoted deep link like: https://t.me/CreativeTradeInBot/trade=60e91064f508f554a10a3847
                CommandHandler('start', self.trade_command, Filters.regex('[a-z0-9]{24}'), pass_args=True), 
                #normal start
                CommandHandler('start', self.start),
            ],
            states={
                SELECTING_ACTION: [
                    CallbackQueryHandler(self.item_edit, pattern='^' + str(EDITING) + '$'),
                    CallbackQueryHandler(self.item_details, pattern='^' + str(SHOWING) + '$'),
                    CallbackQueryHandler(self.search, pattern='^' + str(SEARCHING) +"|"+ str(PREV_PAGE) +"|"+ str(NEXT_PAGE) + '$'),
                    CallbackQueryHandler(self.history, pattern='^' + str(TRACKING) + '$'),
                    
                    CallbackQueryHandler(self.end, pattern='^' + str(END) + '$'), #Back button
                ],
                #these states are used by Back buttons
                EDITING: [CallbackQueryHandler(self.start, pattern='^' + str(SELECTING_FEATURE) + '$')],
                SHOWING: [
                    CallbackQueryHandler(self.item_details, pattern='^' + str(DOWNLOADING) + '$'),
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                ],
                SEARCHING:[
                    CallbackQueryHandler(self.search, pattern='^' + str(SEARCHING) +"|"+ str(PREV_PAGE) +"|"+ str(NEXT_PAGE) + '$'),
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                    CallbackQueryHandler(self.trade_commit, pattern='^' + str(SAVING) + '$'),
                    MessageHandler(Filters.text & ~Filters.command, self.search_text_filter),
                ],
                TRACKING:[
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                    #CallbackQueryHandler(self.ext_item_details, pattern='^' + str(SHOWING) + '$'),
                ],

                TRADING: [
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                ],

                SELECTING_FEATURE: [
                    CallbackQueryHandler(self.regular_choice, pattern='^' + str(NAME) + '|' + str(VALUE) + '|' + str(DESCRIPTION) + '$'),
                    CallbackQueryHandler(self.custom_choice, pattern='^' + str(CATEGORY) + '$'),
                    CallbackQueryHandler(self.edit_commit, pattern='^' + str(SAVING) + '$'),
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                    MessageHandler(Filters.photo, self.received_photo),
                    MessageHandler(Filters.document, self.received_document),
                    MessageHandler(Filters.voice, self.received_voice),
                    #MessageHandler(Filters.text & ~Filters.command, self.regular_choice),
                ],
                SELECTING_CATEGORY: [
                    MessageHandler(Filters.text & ~Filters.command, self.custom_text),
                ],
                TYPING: [
                    MessageHandler(Filters.text & ~Filters.command, self.received_information),
                ],
                #SAVING:[CallbackQueryHandler(self.edit_commit, pattern='^' + str(END) + '$'),],

                STOPPING: [CommandHandler('start', self.start)],
            },
            fallbacks=[
                CommandHandler('stop', self.stop),
            ],
            #all entry points and state handlers must be 'CallbackQueryHandler', since no other handlers have a message context
            #per_message=True # tracked for every message.
            #per_message=False
        )
        dispatcher.add_handler(conv_handler)

        #direct trading
        direct_trade_handler = ConversationHandler(
            entry_points=[CommandHandler('trade', self.trade_command, Filters.regex('[a-z0-9]{24}'), pass_args=True)], 
            states={
                SEARCHING:[
                    CallbackQueryHandler(self.trade_commit, pattern='^' + str(SAVING) + '$'),
                    CallbackQueryHandler(self.start, pattern='^' + str(END) + '$'), #Back button
                ],

                STOPPING: [CommandHandler('start', self.start)],
            },
            fallbacks=[
                CommandHandler('stop', self.stop),
            ],
        )
        dispatcher.add_handler(direct_trade_handler)

        #help handler
        dispatcher.add_handler(CommandHandler('stop', self.stop))
        dispatcher.add_handler(CommandHandler("help", self.help_command))
        #general conversation
        dispatcher.add_handler(MessageHandler(Filters.text, self.handle_message))
        dispatcher.add_error_handler(self.error)


        # Run bot
        if C.HEROKU_APP_NAME == "":  #pooling mode
            logger.info(
                "Can't detect 'HEROKU_APP_NAME' env. Running bot in pooling mode.")
            updater.start_polling(1)
        else:  #webhook mode
            PORT = int(os.environ.get('PORT', C.HEROKU_PORT))
            updater.start_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=C.TELEGRAM_TOKEN,
                webhook_url=f"https://{C.HEROKU_APP_NAME}.herokuapp.com/{C.TELEGRAM_TOKEN}"
            )

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()


if __name__ == '__main__':
    bot = Bot()
    bot.run()
