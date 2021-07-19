from typing import Dict
import os.path
import re
from telegram.keyboardbutton import KeyboardButton
from telegram.keyboardbuttonpolltype import KeyboardButtonPollType
import trade_types as T
import constants as C
from datetime import datetime
from io import BytesIO
#from pathlib import Path
import glob
from PIL import Image, ImageDraw, ImageFont
from typing import ItemsView
from warnings import catch_warnings
#import csv
#import json

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update, InlineKeyboardButton, InlineKeyboardMarkup
#from telegram.ext import *
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    PicklePersistence,
    CallbackContext,
)

# global variables
bot_item = T.TradeItem("")  # bot holds current item to trade with
trade_items = {}  # collection of users' items in chat
journal_path = "{}/journal.csv".format(C.DATA_PATH.strip('/'))
images_dir = "{}/images/".format(C.DATA_PATH.strip('/'))
files_dir = "{}/files/".format(C.DATA_PATH.strip('/'))
thumbnails_dir = "{}/thumbnails/".format(C.DATA_PATH.strip('/'))
thumbnail_size = int(C.THUMBNAIL_SIZE)
bot_item_image_path = thumbnails_dir+"bot_image.jpg"


def read_journal():
    global bot_item
    if not os.path.exists(C.DATA_PATH):
        os.makedirs(C.DATA_PATH)
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)
    if not os.path.exists(files_dir):
        os.makedirs(files_dir)
    if not os.path.exists(thumbnails_dir):
        os.makedirs(thumbnails_dir)

    if (os.path.isfile(journal_path) == False):
        with open(journal_path, 'w+', encoding='utf-8') as j:
            j.write(T.TradeItem.header)
    else:
        with open(journal_path, 'r', encoding='utf-8') as j:
            bot_item = T.TradeItem(j.readlines()[-1])
            update_bot_image()


def write_journal():
    global bot_item
    if (os.path.isfile(journal_path) == True):
        with open(journal_path, 'a', encoding='utf-8') as j:
            j.write("\n{}".format(bot_item.to_string()))


def update_bot_image():
    global bot_item
    if (os.path.isfile(bot_item_image_path)):
        os.remove(bot_item_image_path)
    # print(bot_item.Images)
    if (bot_item.Images != ""):
        image_list = bot_item.Images.split(",")
        photos = []
        for image_name in image_list:
            path = images_dir + image_name
            pathThumbnail = thumbnails_dir + "t_" + image_name
            if (os.path.isfile(pathThumbnail) == False):
                try:
                    image = Image.open(path)
                    image.thumbnail((thumbnail_size, thumbnail_size))
                    image.save(pathThumbnail)
                except IOError:
                    pass

            if (os.path.isfile(pathThumbnail) == False):
                pathThumbnail = path
            photos.append(pathThumbnail)

        if (len(photos) == 1):
            new_image = Image.open(photos[0])
        else:
            new_image = Image.new(
                'RGB', (thumbnail_size * (len(photos)-1), thumbnail_size), (250, 250, 250))
            shift = 0
            for path in photos:
                image = Image.open(path)
                new_image.paste(image, (shift, 0))
                shift = shift + int(float(thumbnail_size)*0.8)
            new_image.save(bot_item_image_path, "JPEG")

        width, height = new_image.size
        draw = ImageDraw.Draw(new_image)
        text = "Creative Trade-in"

        font = ImageFont.truetype('arial.ttf', 18)
        textwidth, textheight = draw.textsize(text, font)

        # calculate the x,y coordinates of the text
        margin = 10
        x = margin  # width - textwidth - margin
        y = margin  # height - textheight - margin
        # draw watermark in the left top corner
        draw.text((x, y), text, font=font)
        x = margin  # width - textwidth - margin
        y = height - textheight - margin
        # draw watermark in the bottom left corner
        draw.text((x, y), text, font=font)
        new_image.save(bot_item_image_path)


def start_command(update: Update, context: CallbackContext):
    global bot_item
    # reset user's item
    if (os.path.isfile(bot_item_image_path) == False and bot_item.Images != ""):
        update_bot_image()
    response = "Hi {}! Here is my item \"{}\".\nLet's trade-in with your item valued higher than ${}.\nType /trade to initiate trad-in process...".format(
        update.message.from_user.first_name, bot_item.Item, bot_item.Value)
    update.message.reply_text(response)
    if (os.path.isfile(bot_item_image_path)):
        context.bot.send_photo(
            chat_id=update.message.chat_id, photo=open(bot_item_image_path, 'rb'))

def start_conv(update: Update, context: CallbackContext) -> int:
    """Starts the conversation and asks the user about the item."""
    global trade_items
    trade_items[update.message.from_user.id] = T.TradeItem("")
    reply_keyboard = [['File', 'Coupon', 'Other']]
    update.message.reply_text(
        'Please answer the following questions about your item.\nSend /stop to cancel conversation.\nWhat is type of your item?',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True),
    )
    return T.Q1


def type_conv(update: Update, context: CallbackContext) -> int:
    """Stores the selected type and asks for a item name."""
    global trade_items
    #print("Type:{}".format(update.message.text))
    trade_items[update.message.from_user.id].Type = update.message.text
    update.message.reply_text(
        'Now, tell me the name of your item.', reply_markup=ReplyKeyboardRemove())
    return T.Q2


def item_conv(update: Update, context: CallbackContext) -> int:
    #global bot_item
    global trade_items
    trade_items[update.message.from_user.id].Item = update.message.text
    update.message.reply_text(
        'Please tell me the value of your item named "{}".\nIt must be higher than my item value ${}!'.format(update.message.text, bot_item.Value))
    return T.Q3


def value_conv(update: Update, context: CallbackContext) -> int:
    #global bot_item
    global trade_items
    try:
        #https://regex101.com/r/aW3pR4/25
        r = re.compile(r"^(\d+[.,]?[\d*]?)$")
        if r.match(update.message.text):
            trade_items[update.message.from_user.id].Value = float(r.match(update.message.text)[0])
        else:    
            trade_items[update.message.from_user.id].Value = float(update.message.text)
    except:
        pass

    if (trade_items[update.message.from_user.id].Value < bot_item.Value):
        update.message.reply_text(
            "Sorry, your item value should be higher than ${}. Try again.".format(bot_item.Value))
        return T.Q3

    update.message.reply_text(
        'Please send me a photo(s) of your item with size less than 5MB each, or type /skip.')
    return T.Q4


def photo_conv(update: Update, context: CallbackContext) -> int:
    """Stores the photo and asks for a file."""
    global trade_items
    #https://api.telegram.org/file/bot<token>/<file_path>, where <file_path> is 
    trade_items[update.message.from_user.id].Images = ""
    for photo in update.message.photo:
        #ignore thumbnails and small files sizes
        if (photo.height> 1000 and photo.file_size < 5000000):
            file = photo.get_file()
            fileName = "{}_{}.jpg".format(update.message.from_user.id, file.file_id) #file_name.replace(",","").replace("|","")
            file.download(images_dir + fileName)
            trade_items[update.message.from_user.id].Images += "," + fileName
    trade_items[update.message.from_user.id].Images = trade_items[update.message.from_user.id].Images.strip(',')

    if (trade_items[update.message.from_user.id].Type == "File"):
        update.message.reply_text(
            'Looks gorgeous! Now, send me the file, or type /skip .')
        return T.Q5
    else:
        update.message.reply_text(
            'Looks gorgeous! Now, send me location where to pickup the item after deal, or type /skip .')
        return T.Q6


def skip_photo_conv(update: Update, context: CallbackContext) -> int:
    global trade_items
    """Skips the photo and asks for a file."""
    if (trade_items[update.message.from_user.id].Type == "File"):
        update.message.reply_text(
            'I bet it looks great! Now, send me you item file(s) with size less than 10MB each, or type /skip if you will orgonize delivery after trade.')
        return T.Q5
    else:
        update.message.reply_text(
            'Looks gorgeous! Now, send me location where to pickup the item after deal confirmed.')
        return T.Q6


def document_conv(update: Update, context: CallbackContext) -> int:
    global trade_items
    """Stores the file and asks for a location."""
    doc = update.message.document
    if (doc.file_size < 10000000):
        fileName = "{}_{}".format(update.message.from_user.id, doc.file_name.replace(",",".").replace("|","."))
        file = doc.get_file()
        file.download(files_dir + fileName)
        trade_items[update.message.from_user.id].Location += "," + fileName
    trade_items[update.message.from_user.id].Location = trade_items[update.message.from_user.id].Location.strip(',')

    update.message.reply_text('At last, describe your item.')
    return T.Q7


def skip_document_conv(update: Update, context: CallbackContext) -> int:
    """Skips the file and asks for a location."""
    update.message.reply_text('At last, describe your item.')
    return T.Q7


def location_conv(update: Update, context: CallbackContext) -> int:
    global trade_items
    trade_items[update.message.from_user.id].Item = update.message.text
    #logger.info("Location of %s: %f / %f", user.first_name, user_location.latitude, user_location.longitude)
    update.message.reply_text('At last, describe your item.')
    return T.Q7


def skip_location_conv(update: Update, context: CallbackContext) -> int:
    global trade_items
    #trade_items[update.message.from_user.id].Location = update.message.location
    update.message.reply_text(
        'I see that location is not defined. You have to orgonize drop-pickup.')
    return T.Q7


def description_conv(update: Update, context: CallbackContext) -> int:
    global trade_items
    trade_items[update.message.from_user.id].Description = update.message.text
    reply_keyboard = [['Confirm', 'Cancel']]
    update.message.reply_text(
        'Thank you! I have enough.\nPlease press [Confirm] button to commit the deal or [Cancel] to try again:',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True),
    )
    return T.Q8

def commit_conv(update: Update, context: CallbackContext):
    global bot_item
    global trade_items

    if (update.message.text == "Confirm"):
        response = "Done!\n"
        if update.message.from_user.id in trade_items:
            userItem = trade_items[update.message.from_user.id]

            reply_keyboard=[]
            if ((bot_item.Type == "File") and (bot_item.Location != "")):
                files_list = bot_item.Location.split(",")
                reply_keyboard = [files_list]

            bot_item.Owner = "{}_{}".format(update.message.from_user.first_name, update.message.from_user.id)
            bot_item.Type = userItem.Type
            bot_item.Item = userItem.Item
            bot_item.Date = userItem.Date
            bot_item.Value = userItem.Value
            bot_item.Location = userItem.Location
            bot_item.Description = userItem.Description
            bot_item.Images = userItem.Images
            write_journal()
            update_bot_image()
            # reset user's item
            userItem = T.TradeItem("")

            if (len(reply_keyboard)>0):
                update.message.reply_text(
                    'Please choose file to download:',
                    reply_markup=ReplyKeyboardMarkup(
                        reply_keyboard, one_time_keyboard=True),
                )
                return T.Q9
            elif (bot_item.Location != ""):
                response += "You can grab my item from the following location: {}".format(
                    bot_item.Location)
            else:
                response += "Owner will contact you shortly to swap the items."
            
        update.message.reply_text(response, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

#ensure that docs you send are below 20 MB as per https://core.telegram.org/bots/api#sending-files
#update.message.reply_document(update.effective_message.chat_id, bot_item.Location)
def download_conv(update: Update, context: CallbackContext):
    global bot_item
    global trade_items
    #ensure that docs you send are below 20 MB as per https://core.telegram.org/bots/api#sending-files
    #update.message.reply_document(update.effective_message.chat_id, bot_item.Location)
    file_path = update.message.text
    if (os.path.isfile(files_dir + file_path) == True):
        update.message.reply_text("Please wait arrival...", reply_markup=ReplyKeyboardRemove())
        context.bot.sendDocument(chat_id=update.message.chat_id, document=open(files_dir + file_path, 'rb'))
    return ConversationHandler.END


def stop_conv(update: Update, context: CallbackContext) -> int:
    """Ends the conversation."""
    user = update.message.from_user
    #logger.info("User %s canceled the conversation.", user.first_name)
    update.message.reply_text(
        'Bye! I hope we can trade-in again some day.', reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def help_command(update: Update, context: CallbackContext):
    update.message.reply_text(
        'Type /start to see what I have\nThen you will get other instructions')


def error(update: Update, context: CallbackContext):
    print(f"Update: {update}; caused error: {context.error}")
    #logger.info(f"Update: {update}; caused error: {context.error}")


def handle_message(update: Update, context: CallbackContext):
    #context.bot.edit_message_text(chat_id=update.message.chat.id,
    #                      text="Here are the values of stringList", message_id=update.message.message_id,
    #                      reply_markup=makeKeyboard(), parse_mode='HTML')

    response = simple_responses(update.message.text)
    update.message.reply_text(response)


def simple_responses(input_text):
    user_message = str(input_text).lower()
    if user_message in ("hello", "hi", ""):
        return "G'Day! Please type /start to trade with me"

    if user_message in ("who are you", "who are you?"):
        return "I am your traider bot"

    if user_message in ("time?", "now?"):
        return datetime.now().strftime("%d/%m/%y %H:%M:%S")

    return "Please type /help"