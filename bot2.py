from bot3 import EDITING
import os
import logging
import pymongo
from pymongo.message import query
from bson.objectid import ObjectId
import requests
import json
from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from typing import Dict
#from datetime import datetime
import constants as C
#from constants import TELEGRAM_TOKEN, HEROKU_APP_NAME, HEROKU_PORT
#import database as DB
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
#from telegram.ext import *
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    PicklePersistence,
    CallbackContext,
    CallbackQueryHandler
)

# Enable debug logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)


class Bot:
    # static members
    CHOOSING, TYPING_REPLY, TYPING_CHOICE, EDITING, DELETING = range(5)
    END = ConversationHandler.END

    def facts_to_str(user_data: Dict[str, str]) -> str:
        """Helper function for formatting the gathered user info."""
        facts = [f'{key} - {value}' for key, value in user_data.items()]
        return "\n".join(facts).join(['\n', '\n'])

    # instance members
    def __init__(self):
        myclient = pymongo.MongoClient(C.MONGODB_CONNECTION_URL)
        self.botDB = myclient["botDB"]
        authenticator = IAMAuthenticator(C.IBM_KEY)
        self.speech_to_text = SpeechToTextV1(
            authenticator=authenticator
        )
        self.speech_to_text.set_service_url(C.IBM_SERVICE_URL)
        self.speech_to_text.set_disable_ssl_verification(True)

        # R.read_journal()

    def handle_message(self, update: Update, context: CallbackContext):
        # context.bot.edit_message_text(chat_id=update.message.chat.id,
        #                      text="Here are the values of stringList", message_id=update.message.message_id,
        #                      reply_markup=makeKeyboard(), parse_mode='HTML')
        user_message = str(update.message.text).lower()
        if user_message in ("hello", "hi", ""):
            response = f"G'Day {update.message.from_user.first_name}!"
        elif user_message in ("who are you", "who are you?"):
            # creative traid-in bot
            response = f"I am {context.bot.name}. Type /start to talk"
        else:
            response = "Please type /help for more details"
        update.message.reply_text(response)

    def help_command(self, update: Update, context: CallbackContext):
        update.message.reply_text(
            "This marketplace allows to trade-in items with identical (or higher) value."
            "\nHere is list of available commands:"
            "\n/items show all my items"
            "\n/create new my item"
            "\n/search other owners' items ready to trade-in with me"
        )

    def error(self, update: Update, context: CallbackContext):
        logger.error(f"Update: {update}; caused error: {context.error}")

    def photo_choice(self, update: Update, context: CallbackContext):
        """
        bot sends image in multiple resolutions, last one the highest one
        """
        #photo = update.message.photo[-1]
        if (len(update.message.photo)>1):
            context.user_data['Image_thumbnail'] = update.message.photo[-2].file_id
            context.user_data['Image'] = update.message.photo[-1].file_id
        update.message.reply_text(
            "Got photo! Just so you know, this is what you already told me:"
            f"{Bot.facts_to_str(context.user_data)} You can tell me more, or change your opinion"
            " on something.",
            reply_markup=self.markup,
        )
        return Bot.CHOOSING

    def voice_choice(self, update: Update, context: CallbackContext):
        """
        bot sends audio to IBM Speech to Text: 
        https://cloud.ibm.com/catalog/services/speech-to-text
        https://cloud.ibm.com/apidocs/speech-to-text?code=python#recognize
        """
        # print(update.message.voice)
        #voice_content = update.message.voice.get_file()
        # context.bot.get_file(update.message.voice.file_id)
        voice_content = update.message.voice.get_file()

        speech_recognition_results = self.speech_to_text.recognize(
            audio=voice_content.download_as_bytearray(),
            content_type='audio/flac',
            word_alternatives_threshold=0.9,
            #keywords=['colorado', 'tornado', 'tornadoes'],
            keywords_threshold=0.5
        ).get_result()
        print(json.dumps(speech_recognition_results, indent=2))

        if speech_recognition_results.status_code != 200 or not speech_recognition_results:
            update.message.reply_text("Could not hear you well!",
                                      reply_markup=self.markup,
                                      )
        else:
            text = json.dumps(speech_recognition_results, indent=2)
            update.message.reply_text(
                "Got your voice! Just so you know, this is what you already told me:"
                f"{text} You can tell me more, or change your opinion",
                reply_markup=self.markup,
            )

        return Bot.CHOOSING

    def document_choice(self, update: Update, context: CallbackContext):
        """
        bot sends 1 document, calling this function multiple times
        """
        #doc = update.message.document
        context.user_data['File'] = update.message.document.file_id

        update.message.reply_text(
            "Got file! Just so you know, this is what you already told me:"
            f"{Bot.facts_to_str(context.user_data)} You can tell me more, or change your opinion"
            " on something.",
            reply_markup=self.markup,
        )
        return Bot.CHOOSING

    def create_command(self, update: Update, context: CallbackContext):
        self.reply_keyboard = [
            ['Name', 'Value'],
            ['Description', 'Location'],
            ['Something else...'],
        ]
        self.markup = ReplyKeyboardMarkup(
            self.reply_keyboard, one_time_keyboard=True)
        update.message.reply_text(
            "Please answer the following questions about your item:",
            reply_markup=self.markup,
        )

        return Bot.CHOOSING

    def regular_choice(self, update: Update, context: CallbackContext) -> int:
        """Ask the user for info about the selected predefined choice."""
        text = update.message.text
        context.user_data['choice'] = text
        update.message.reply_text(
            f'Item {text.lower()}? Yes, I would love to hear about that!')

        return Bot.TYPING_REPLY

    def custom_choice(self, update: Update, context: CallbackContext) -> int:
        """Ask the user for a description of a custom category."""
        update.message.reply_text(
            'Alright, please send me the category first, for example "Colour"'
        )

        return Bot.TYPING_CHOICE

    def received_information(self, update: Update, context: CallbackContext) -> int:
        """Store info provided by user and ask for the next category."""
        user_data = context.user_data
        text = update.message.text
        category = user_data['choice']
        user_data[category] = text
        del user_data['choice']

        # if all compulsory attributes defined, add Done button
        if ('Name' in user_data and 'Value' in user_data and not ['Done'] in self.reply_keyboard[-1]):
            self.reply_keyboard.append(['Done'])
            self.markup = ReplyKeyboardMarkup(
                self.reply_keyboard, one_time_keyboard=True)

        update.message.reply_text(
            "Neat! Just so you know, this is what you already told me:"
            f"{Bot.facts_to_str(user_data)} You can tell me more, or change your opinion"
            " on something.",
            reply_markup=self.markup,
        )

        return Bot.CHOOSING

    def create_commit(self, update: Update, context: CallbackContext) -> int:
        """Display the gathered info and end the conversation."""
        user_data = context.user_data
        if 'choice' in user_data:
            del user_data['choice']

        user_data['owner_id'] = update.message.from_user.id
        items_coll = self.botDB["items"]
        #item = { "name": "John", "address": "Highway 37" }
        x = items_coll.insert_one(user_data)

        update.message.reply_text(
            # these facts about your item: {Bot.facts_to_str(user_data)} Until next time!",
            f"The item is saved database with id: {x.inserted_id}",
            reply_markup=ReplyKeyboardRemove(),
        )

        user_data.clear()
        return ConversationHandler.END

    def cancel_conv(self, update: Update, context: CallbackContext) -> int:
        """Remove the gathered info and end the conversation."""
        user_data = context.user_data
        if 'choice' in user_data:
            del user_data['choice']

        update.message.reply_text(
            'Operation canceled.', reply_markup=ReplyKeyboardRemove()
        )

        user_data.clear()
        return ConversationHandler.END

    def edit_command(self, update: Update, context: CallbackContext):
        print('edit_command')
        if (len(context.args) == 0):
            return ConversationHandler.END
        #update.message.reply_text("Let's edit record {} owned by {}".format(context.args[0], update.message.from_user.id))
        #print("edit_command user Id:{}, item id:{}".format(update.message.from_user.id, context.args[0]))
        #print("edit_command Message Id:{}".format(update.message.message_id))
        # print(item)
        user_data = context.user_data
        user_data.clear()
        item = self.botDB["items"].find_one(
            {"owner_id": update.message.from_user.id, "_id": ObjectId(context.args[0])})
        # print(item)
        for key, value in item.items():
            #print("key:{}, value {}".format(key, value))
            user_data[key] = value
        # print(user_data)

        self.reply_keyboard = [
            ['Name', 'Value'],
            ['Description', 'Location'],
            ['Something else...'],
            ['Done']
        ]
        self.markup = ReplyKeyboardMarkup(
            self.reply_keyboard, one_time_keyboard=True)
        update.message.reply_text(
            "Please choose fields of your item to update:",
            reply_markup=self.markup,
        )
        return Bot.CHOOSING

    def edit_confirm(self, update: Update, context: CallbackContext) -> int:
        """Display the gathered info and end the conversation."""
        user_data = context.user_data
        _id = user_data['_id']
        if '_id' in user_data:
            del user_data['_id']
        #print(user_data)
        edited_item = self.botDB["items"].find_one_and_update(filter={"_id": ObjectId(_id), "owner_id": update.message.from_user.id}, 
            update={"$set": user_data}, upsert=True, return_document=True)
        if (bool(edited_item)):
            update.message.reply_text(
                f"Done. The item with id: {_id} was updated.",
                reply_markup=ReplyKeyboardRemove(),
            )

        user_data.clear()
        return ConversationHandler.END

    def delete_command(self, update: Update, context: CallbackContext):
        print('delete_command')
        #update.message.reply_text("Let's delete record {} owned by {}".format(context.args[0], update.message.from_user.id))
        if (len(context.args) == 0):
            return ConversationHandler.END

        item = self.botDB["items"].find_one(
            {"_id": ObjectId(context.args[0]), "owner_id": update.message.from_user.id})
        user_data = context.user_data
        if (bool(item)):
            user_data['_id'] = item['_id']

        update.message.reply_text(
            #f"{Bot.facts_to_str(user_data)}\n"
            "Are you sure your want to delete this item?",
            reply_markup=ReplyKeyboardMarkup(
                [['Confirm', 'Cancel']], one_time_keyboard=True),
        )
        return Bot.CHOOSING

    def delete_confirm(self, update: Update, context: CallbackContext) -> int:
        """Delete and end the conversation."""
        if (update.message.text != "Confirm"):
            update.message.reply_text(
                f"Delete is canceled. The item was NOT deleted.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ConversationHandler.END

        #print("delete_confirmed")
        user_data = context.user_data
        if '_id' in user_data:
            _id = user_data['_id']
            deleted_item = self.botDB["items"].find_one_and_delete(
                filter={"_id": ObjectId(_id), "owner_id": update.message.from_user.id})
            if (bool(deleted_item)):
                update.message.reply_text(
                    f"Done. The item with id: {_id} was deleted.",
                    reply_markup=ReplyKeyboardRemove(),
                )

        user_data.clear()
        return ConversationHandler.END

    def start_command(self, update: Update, context: CallbackContext):
        update.message.reply_text("Hi {}!\nLet's trade-in!\nType /help for assistance.".format(
            update.message.from_user.first_name))

    def items_command(self, update: Update, context: CallbackContext):
        """Get user items"""
        #print("items_command Message Id:{}".format(update.message.message_id))
        #'Here is your items:'
        translation_table = dict.fromkeys(map(ord, '*-`_()[].'), "\\")
        for item in self.botDB["items"].find({"owner_id": update.message.from_user.id}).sort("Name"):
            reply_markup=InlineKeyboardMarkup([
                    #[InlineKeyboardButton(text='Edit', callback_data=str(Bot.EDITING)],
                    [InlineKeyboardButton(text='Edit', callback_data='/edit {}'.format(item.get('_id')))],
                    [InlineKeyboardButton(text='Delete', callback_data='/delete {}'.format(item.get('_id')))],
                ])
            #reply_keyboard = [['/edit {}'.format(item.get('_id')), '/delete {}'.format(item.get('_id'))]]
            #reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)

            replytext = ""
            for key, value in item.items():
                if (key not in ['_id', 'owner_id']):
                    #print("key:{}, value {}".format(key, value))
                    if (key == 'Image_thumbnail'):
                        context.bot.send_photo(update.message.chat_id, item['Image_thumbnail'])
                    elif (key == 'Image'):
                        context.bot.send_photo(update.message.chat_id, item['Image'])
                    else:
                        replytext += "*{}:* `{}` \n".format(str(key).translate(
                            translation_table), str(value).translate(translation_table))

            update.message.reply_text(
                replytext,
                reply_markup=reply_markup, parse_mode='MarkdownV2'
            )
        return Bot.CHOOSING


    def search_command(self, update: Update, context: CallbackContext):
        update.message.reply_text("Ok! Let's see what I have based on your request: {}".format(
            context.args))

    def callback_query_handler(self, update: Update, context: CallbackContext):
        #print("callback_query_handler: {}".format(update.callback_query.data))
        query = update.callback_query
        query.answer()
        query.edit_message_text(text=update.callback_query.data) #, reply_markup=entry_keyboard()
        #context.bot.edit_message_text(chat_id=query.message.chat_id, message_id=query.message.message_id, text=query.data)
        #if cqd.startswith("/edit "):
        #    self.edit_handler(update, context)
        #elif cqd.startswith("/delete "):
        #    self.delete_handler(update, context)
        return Bot.TYPING_REPLY

    def next_page(self, update: Update, context: CallbackContext):
        print('TBD!go next page')
        return ConversationHandler.END

    def run(self):
        # Create the Updater and pass it your bot's token.
        #persistence = PicklePersistence(filename='conversationbot')
        # , persistence=persistence)
        updater = Updater(C.TELEGRAM_TOKEN, use_context=True)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(CommandHandler("start", self.start_command))
        dispatcher.add_handler(CommandHandler(
            "search", self.search_command, pass_args=True))
        dispatcher.add_handler(CommandHandler("help", self.help_command))

       
        #depricated simple commands replaced with conversations below
        #dispatcher.add_handler(CommandHandler('edit', self.edit_command, pass_args=True))
        #dispatcher.add_handler(CommandHandler('delete', self.delete_command, pass_args=True))

        #Create item conversation handler
        create_handler = ConversationHandler(
            entry_points=[CommandHandler('create', self.create_command)],
            states={
                Bot.CHOOSING: [
                    MessageHandler(
                        Filters.regex('^(Name|Value|Description|Location)$'),
                        self.regular_choice
                    ),
                    MessageHandler(Filters.regex(
                        '^Something else...$'), self.custom_choice),
                    MessageHandler(Filters.voice, self.voice_choice),
                    MessageHandler(Filters.photo, self.photo_choice),
                    MessageHandler(Filters.document, self.document_choice)
                ],
                Bot.TYPING_CHOICE: [
                    MessageHandler(
                        Filters.text & ~(Filters.command |
                                         Filters.regex('^Done$')),
                        self.regular_choice
                    )
                ],
                Bot.TYPING_REPLY: [
                    MessageHandler(
                        Filters.text & ~(Filters.command |
                                         Filters.regex('^Done$')),
                        self.received_information,
                    )
                ],
            },
            fallbacks=[MessageHandler(
                Filters.regex('^Done$'), self.create_commit)],
            #fallbacks=[CommandHandler(Filters.regex('^Cancel$'), self.cancel_conv)],
        )
        dispatcher.add_handler(create_handler)
        
        edit_handler = ConversationHandler(
            entry_points=[CommandHandler('edit', self.edit_command, pass_args=True)],
            states={
                Bot.CHOOSING: [
                    MessageHandler(
                        Filters.regex('^(Name|Value|Description|Location)$'),
                        self.regular_choice
                    ),
                    MessageHandler(Filters.regex(
                        '^Something else...$'), self.custom_choice),
                    MessageHandler(Filters.voice, self.voice_choice),
                    MessageHandler(Filters.photo, self.photo_choice),
                    MessageHandler(Filters.document, self.document_choice)
                ],
                Bot.TYPING_CHOICE: [
                    MessageHandler(
                        Filters.text & ~(Filters.command |
                                         Filters.regex('^Done$')),
                        self.regular_choice
                    )
                ],
                Bot.TYPING_REPLY: [
                    MessageHandler(
                        Filters.text & ~(Filters.command |
                                         Filters.regex('^Done$')),
                        self.received_information,
                    )
                ],
            },
            fallbacks=[MessageHandler(Filters.regex('^Done$'), self.edit_confirm)],
            #fallbacks=[CommandHandler(Filters.regex('^Cancel$'), self.cancel_conv)],
        )
        dispatcher.add_handler(edit_handler)

        delete_handler = ConversationHandler(
            entry_points=[CommandHandler('delete', self.delete_command, pass_args=True)],
            states={
                Bot.CHOOSING: [MessageHandler(Filters.regex('^(Confirm|Cancel)$'), self.delete_confirm)],
            },
            #fallbacks=[MessageHandler(Filters.regex('^Cancel$'), self.edit_confirm)]
            fallbacks=[CommandHandler('Cancel', self.delete_confirm)],
        )
        dispatcher.add_handler(delete_handler)

        dispatcher.add_handler(CommandHandler("items", self.items_command))

        dispatcher.add_handler(MessageHandler(
            Filters.text, self.handle_message))

        dispatcher.add_error_handler(self.error)

        # Run bot
        if C.HEROKU_APP_NAME == "":  # pooling mode
            logger.info(
                "Can't detect 'HEROKU_APP_NAME' env. Running bot in pooling mode.")
            #print("Note: this is not a great way to deploy the bot in Heroku.")
            updater.start_polling(1)
        else:  # webhook mode
            #print(f"Running bot in webhook mode. Make sure that this url is correct: https://{C.HEROKU_APP_NAME}.herokuapp.com/")
            PORT = int(os.environ.get('PORT', C.HEROKU_PORT))
            updater.start_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=C.TELEGRAM_TOKEN,
                webhook_url=f"https://{C.HEROKU_APP_NAME}.herokuapp.com/{C.TELEGRAM_TOKEN}"
            )

        updater.idle()


if __name__ == '__main__':
    bot = Bot()
    bot.run()
