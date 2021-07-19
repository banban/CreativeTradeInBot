import os
import logging
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    PicklePersistence,
    CallbackContext,
)
import bot1_responses as R
import constants as C
#from constants import TELEGRAM_TOKEN, HEROKU_APP_NAME, HEROKU_PORT
import trade_types as T

# Enable logging
# logging.basicConfig(
#    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
# )
#logger = logging.getLogger(__name__)


def main():
    R.read_journal()
    # Create the Updater and pass it your bot's token.
    #persistence = PicklePersistence(filename='conversationbot')
    # , persistence=persistence)
    updater = Updater(C.TELEGRAM_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", R.start_command))
    dp.add_handler(CommandHandler("help", R.help_command))

    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('trade', R.start_conv)],
        states={
            T.Q1: [MessageHandler(Filters.regex('^(File|Coupon|Other)$'), R.type_conv)],
            T.Q2: [MessageHandler(Filters.text & ~Filters.command, R.item_conv)],
            T.Q3: [MessageHandler(Filters.text, R.value_conv)],#Filters.regex('^(\d*[.,]?[\d*]?)$')
            T.Q4: [MessageHandler(Filters.photo, R.photo_conv), CommandHandler('skip', R.skip_photo_conv)],
            T.Q5: [MessageHandler(Filters.document, R.document_conv), CommandHandler('skip', R.skip_document_conv)],
            T.Q6: [MessageHandler(Filters.text & ~Filters.command, R.location_conv), CommandHandler('skip', R.skip_location_conv)],
            T.Q7: [MessageHandler(Filters.text & ~Filters.command, R.description_conv)],
            T.Q8: [MessageHandler(Filters.regex('^(Confirm|Cancel)$'), R.commit_conv)],
            T.Q9: [MessageHandler(Filters.text & ~Filters.command, R.download_conv)],
        },
        fallbacks=[CommandHandler('stop', R.stop_conv)],
    )
    dp.add_handler(conv_handler)

    dp.add_handler(MessageHandler(Filters.text, R.handle_message))
    dp.add_error_handler(R.error)

    # start_polling() is non-blocking and will stop the bot gracefully.
    # updater.start_polling(1)
    #updater.start_webhook(listen="0.0.0.0", port=int(PORT), url_path=C.API_KEY)
    #updater.bot.setWebhook("https://{}.herokuapp.com/{}",C.HEROKU_APPNAME, C.API_KEY)


    # Run bot
    if C.HEROKU_APP_NAME=="":  # pooling mode
        print("Can't detect 'HEROKU_APP_NAME' env. Running bot in pooling mode.")
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
    main()