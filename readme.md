*@CreativeTradeInBot*
https://web.telegram.org/k/#/im?p=@CreativeTradeInBot
# Keep your token secure and store it safely, it can be used by anyone to control your bot.
# For a description of the Bot API, see this page: https://core.telegram.org/bots/api
# telegram.error.BadRequest: Bad webhook: webhook can be set up only on ports 80, 88, 443 or 8443

py -m venv env
.\env\Scripts\activate
deactivate
python.exe -m pip install --upgrade pip
pip3 install -r requirements.txt

pip3 install requests
#pip3 install python-telegram-bot
#pip3 install pillow
pip3 install dnspython
pip3 install pymongo[snappy,gssapi,srv,tls]
pip3 install --upgrade "ibm-watson>=5.2.0"

<!-- 
pymongo.errors.ConfigurationError: The "dnspython" module must be installed to use mongodb+srv:// URIs 

https://regex101.com/r/aW3pR4/25
-->


**DevOps CI/CD**
heroku login
git commit -am "make it better"
git push heroku main

**Monitoring**
heroku run bash -a creative-trade-in
heroku logs --tail
heroku status
heroku maintenance:on | heroku ps:scale web=0 | heroku restart
heroku maintenance:off
