```
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
# pip install docker
# pip install discord
# pip freeze > requirements.txt
pip install -r requirements.txt
echo 'export AOC_TOKEN_1=<AOC TOKEN 1>' >> .env
echo 'export AOC_TOKEN_2=<AOC TOKEN 2>' >> .env
echo 'export AOC_TOKEN_3=<AOC TOKEN 3>' >> .env
echo 'export DISCORD_TOKEN=<DISCORD TOKEN>' >> .env
source .env
python fetch.py 1
python bot.py
sqlite3
# > .open database.db
```

