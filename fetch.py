import requests
import os, sys
from datetime import datetime, timedelta, timezone

year = "2024"
root = f"/home/indiv0/src/ferris-elf"
keys = filter(None, [os.getenv("AOC_TOKEN_1"), os.getenv("AOC_TOKEN_2"), os.getenv("AOC_TOKEN_3")])

def get(day: int | str) -> None:
    print(f"Fetching {day}")
    for k in keys:
        r = requests.get(f"https://adventofcode.com/{year}/day/{day}/input", cookies=dict(session=k))
        r.raise_for_status()
        if not os.path.exists(f"{root}/{day}"):
            os.makedirs(f"{root}/{day}")
        with open(f"{root}/{day}/{k}", "wb+") as f:
            f.write(r.content)

def today() -> int:
    utc = datetime.now(timezone.utc)
    offset = timedelta(hours=-5)
    return min((utc + offset).day, 25)

if len(sys.argv) > 1:
    get(int(sys.argv[1]))
else:
    get(today())
