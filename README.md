```
echo 'export AOC_TOKEN_1=<AOC TOKEN 1>' >> .env
echo 'export AOC_TOKEN_2=<AOC TOKEN 2>' >> .env
echo 'export AOC_TOKEN_3=<AOC TOKEN 3>' >> .env
echo 'export DISCORD_TOKEN=<DISCORD TOKEN>' >> .env
source .env
uv run fetch.py 1
uv run bot.py 2>&1 | tee -a logs.txt
sqlite3
# > .open database.db
```

