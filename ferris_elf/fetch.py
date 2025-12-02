from typing import Final
import requests
import os
import sys

from datetime import datetime, timedelta, timezone
from os.path import isfile, join

year = "2025"
keys = list(
    filter(
        None,
        [os.getenv("AOC_TOKEN_1"), os.getenv("AOC_TOKEN_2"), os.getenv("AOC_TOKEN_3")],
    )
)

base_input_dir: Final = "aoc_inputs"


def get_year_input_dir(year: int | str) -> str:
    return f"{base_input_dir}/{year}"


def get_day_input_dir(year: int | str, day: int) -> str:
    return f"{get_year_input_dir(year)}/{day}"


class FetchError(Exception):
    __slots__ = ()


def get_input_filenames(year: str | int, day: int) -> list[str]:
    base_path = get_day_input_dir(year, day)

    try:
        return [f for f in os.listdir(base_path) if isfile(join(base_path, f))]
    except FileNotFoundError:
        try:
            get_inputs(str(year), day)
            return [f for f in os.listdir(base_path) if isfile(join(base_path, f))]
        except Exception as e:
            raise FetchError(e)


def get_inputs(year: str, day: int) -> None:
    print(f"Fetching {year}:{day}")
    for k in keys:
        r = requests.get(
            f"https://adventofcode.com/{year}/day/{day}/input", cookies=dict(session=k)
        )
        r.raise_for_status()
        if not os.path.exists(get_day_input_dir(year, day)):
            os.makedirs(get_day_input_dir(year, day))
        with open(f"{get_day_input_dir(year, day)}/{k}", "wb+") as f:
            f.write(r.content)


def today() -> int:
    utc = datetime.now(timezone.utc)
    offset = timedelta(hours=-5)
    return min((utc + offset).day, 25)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        get_inputs(year, int(sys.argv[1]))
    else:
        get_inputs(year, today())
