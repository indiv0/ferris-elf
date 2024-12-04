import docker
import discord
import asyncio
import sqlite3
import io
import functools
import os
import typing
from typing import Iterator, Optional, Union
from time import monotonic_ns
from os import listdir
from os.path import isfile, join
from datetime import datetime, timedelta, timezone
doc = docker.from_env()
db = sqlite3.connect("database.db")

cur = db.cursor()
cur.execute("""CREATE TABLE IF NOT EXISTS runs 
    (user TEXT, code TEXT, day INTEGER, part INTEGER, time REAL, answer INTEGER, answer2)""")
cur.execute("""CREATE TABLE IF NOT EXISTS solutions 
    (key TEXT, day INTEGER, part INTEGER, answer INTEGER, answer2)""")

# Implementation details: https://github.com/indiv0/ferris-elf/issues/7
cur.execute("CREATE INDEX IF NOT EXISTS runs_index ON runs (day, part, user, time)")

# run these on startup to clean up database
print("Running database maintenance tasks, this may take a while")
cur.execute("VACUUM")
cur.execute("ANALYZE")

db.commit()

def today() -> int:
    utc = datetime.now(timezone.utc)
    offset = timedelta(hours=-5)
    return min((utc + offset).day, 25)

async def build_image(msg: discord.Message, solution: bytes) -> bool:
    print(f"Building for {msg.author.name}")
    #status = await msg.reply("Building...", mention_author=False)
    with open("runner/src/code.rs", "wb+") as f:
        f.write(solution)

    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(None, functools.partial(doc.images.build, path="runner", tag=f"ferris-elf-{msg.author.id}"))
        return True
    except docker.errors.BuildError as err:
        print(f"Build error: {err}")
        e = ""
        for chunk in err.build_log:
            e += chunk.get("stream") or ""
        if "Compiling[0m ferris-elf" in e:
            e = e[e.index("Compiling[0m ferris-elf")-18:]
            if len(e) < 2000:
                await msg.reply(f"Error building benchmark: ```ansi{e}\n```")
                return False
        from strip_ansi import strip_ansi
        e = strip_ansi(e)
        await msg.reply(f"Error building benchmark: {err}", file=discord.File(io.BytesIO(e.encode("utf-8")), "build_log.txt"))
        return False
    #finally:
    #    await status.delete()

async def run_image(msg: discord.Message, input: str) -> typing.Optional[str]:
    print(f"Running for {msg.author.name}")
    # input = ','.join([str(int(x)) for x in input])
    #status = await msg.reply("Running benchmark...", mention_author=False)
    loop = asyncio.get_event_loop()
    try:
        #os.environ['NVIDIA_VISIBLE_DEVICES']='all'
        #os.environ['NVIDIA_DRIVER_CAPABILITIES']='compute,utility'
        #out = await loop.run_in_executor(None, functools.partial(doc.containers.run, f"ferris-elf-{msg.author.id}", f"timeout 180 ./target/release/ferris-elf", environment=dict(INPUT=input), remove=True, stdout=True, mem_limit="120g", network_mode="none", runtime="nvidia"))
        out = await loop.run_in_executor(None, functools.partial(doc.containers.run, f"ferris-elf-{msg.author.id}", f"timeout 180 ./profile.sh", environment=dict(INPUT=input), remove=True, stdout=True, mem_limit="120g", network_mode="none"))
        out = out.decode("utf-8")
        print(out)
        return str(out)
    except docker.errors.ContainerError as err:
        print(f"Run error: {err}")
        await msg.reply(f"Error running benchmark: {err}", file=discord.File(io.BytesIO(err.stderr), "stderr.txt"))
        return None
    #finally:
    #    await status.delete()

def avg(l: list[float]) -> float:
    return sum(l) / len(l)

def ns(v: float) -> str:
    if v > 1e9:
        return f"{v / 1e9:.2f}s"
    if v > 1e6:
        return f"{v / 1e6:.2f}ms"
    if v > 1e3:
        return f"{v / 1e3:.2f}µs"
    # dont push padding zeroes because resolution is 1 ns
    return f"{v:.0f}ns"


class ResultDict(typing.TypedDict, total=False):
    answer: str
    average: int
    median: int
    max: int
    min: int


async def benchmark(msg: discord.Message, code: bytes, day: int, part: int) -> None:
    build = await build_image(msg, code)
    if not build:
        return

    day_path = f"{day}/"
    try:
        onlyfiles = [f for f in listdir(day_path) if isfile(join(day_path, f))]
    except:
        await msg.reply(f"Failed to read input files for day {day}, part {part}")
        return

    verified = False
    results = []
    for (i, file) in enumerate(onlyfiles):
        rows = db.cursor().execute("SELECT answer2 FROM solutions WHERE key = ? AND day = ? AND part = ?", (file, day, part))
        verify = None
        for row in rows:
            print("Verify", row[0], "file", file)
            verify = str(row[0]).strip()

        with open(join(day_path, file), "r") as f:
            input = f.read()

        #status = await msg.reply(f"Benchmarking input {i+1}", mention_author=False)
        out = await run_image(msg, input)
        if not out:
            return
        #await status.delete()

        result: ResultDict = {}
        for line in out.splitlines():
            if line.startswith("FERRIS_ELF_ANSWER "):
                result["answer"] = str(line[18:]).strip()
            if line.startswith("FERRIS_ELF_MEDIAN "):
                result["median"] = int(line[18:])
            if line.startswith("FERRIS_ELF_AVERAGE "):
                result["average"] = int(line[19:])
            if line.startswith("FERRIS_ELF_MAX "):
                result["max"] = int(line[15:])
            if line.startswith("FERRIS_ELF_MIN "):
                result["min"] = int(line[15:])
            # Total Memory Accesses...4,790,804,439
            # FERRIS_ELF_MIN A
            # 
            # Total L1 I-Cache Misses...13,367 (0%)
            # Total LL I-Cache Misses...64 (0%)
            # Total L1 D-Cache Misses...19,345,778 (0%)
            # Total LL D-Cache Misses...555 (0%)
            # 
            #  Ir  I1mr ILmr  Dr  D1mr DLmr  Dw  D1mw DLmw
            # 0.96 1.00 0.83 0.94 0.99 0.00 0.79 0.11 0.01 ???:ferris_elf
            # -----------------------------------------------------------------------
            # 0.02 0.00 0.11 0.06 0.01 1.00 0.10 0.44 0.52 memcpy.S:__GI_memcpy
            # -----------------------------------------------------------------------
            # 0.02 0.00 0.06 0.00 0.00 0.00 0.12 0.45 0.47 memset.S:__GI_memset
            # -----------------------------------------------------------------------
            if "Total Memory Accesses" in line:
                result["total_memory_accesses"] = int(line[33:].replace(",", "").split()[0])
            if "Total L1 I-Cache Misses" in line:
                result["total_l1_icache_misses"] = int(line[35:].replace(",", "").split()[0])
            if "Total LL I-Cache Misses" in line:
                result["total_ll_icache_misses"] = int(line[35:].replace(",", "").split()[0])
            if "Total L1 D-Cache Misses" in line:
                result["total_l1_dcache_misses"] = int(line[35:].replace(",", "").split()[0])
            if "Total LL D-Cache Misses" in line:
                result["total_ll_dcache_misses"] = int(line[35:].replace(",", "").split()[0])

        if verify:
            if not result["answer"] == verify:
                await msg.reply(f"Error: Benchmark returned wrong answer for input {i + 1}")
                return
            verified = True
        else:
            print("Cannot verify run", result["answer"])

        results.append(result)

    for result in results:
        cur.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)", (str(msg.author.id), code, day, part, result["median"], result["answer"], result["answer"]))

    median = avg([int(r["median"]) for r in results])
    average = avg([int(r["average"]) for r in results])
    total_memory_accesses = avg([int(r["total_memory_accesses"]) for r in results])
    total_l1_icache_misses = avg([int(r["total_l1_icache_misses"]) for r in results])
    total_ll_icache_misses = avg([int(r["total_ll_icache_misses"]) for r in results])
    total_l1_dcache_misses = avg([int(r["total_l1_dcache_misses"]) for r in results])
    total_ll_dcache_misses = avg([int(r["total_ll_dcache_misses"]) for r in results])

    if verified:
        await msg.reply(embed=discord.Embed(title="Benchmark complete", description=f"Median: **{ns(median)}**\nAverage: **{ns(average)}**\nTotal Memory Accesses: **{total_memory_accesses}**\nTotal L1 I-Cache Misses: **{total_l1_icache_misses}**\nTotal LL I-Cache Misses: **{total_ll_icache_misses}**\nTotal L1 D-Cache Misses: **{total_l1_dcache_misses}**\nTotal LL D-Cache Misses: **{total_ll_dcache_misses}**"))
    else:
        await msg.reply(embed=discord.Embed(title="Benchmark complete (Unverified)", description=f"Median: **{ns(median)}**\nAverage: **{ns(average)}**\nTotal Memory Accesses: **{total_memory_accesses}**\nTotal L1 I-Cache Misses: **{total_l1_icache_misses}**\nTotal LL I-Cache Misses: **{total_ll_icache_misses}**\nTotal L1 D-Cache Misses: **{total_l1_dcache_misses}**\nTotal LL D-Cache Misses: **{total_ll_dcache_misses}**"))

    db.commit()
    print("Inserted results into DB")


def get_scores_lb(cur: sqlite3.Cursor, day: int, part: int) -> Iterator[tuple[Optional[str], Optional[int]]]:
    return cur.execute("""SELECT user, MIN(time) FROM runs
        WHERE day = ? AND part = ?
        GROUP BY user ORDER BY time""",
        (day, part)
    )

async def formatted_scores_for(author: Union[discord.User, discord.Member], bot: discord.Client, cur: sqlite3.Cursor, day: int, part: int) -> str:
    builder = io.StringIO()

    # If the message was not sent in a DM, get the author's guild.
    if isinstance(author, discord.Member):
        # FIXME [NP]: Is this redundant because we have the `author.guild` already?
        guild = bot.get_guild(author.guild.id)
    else:
        guild = None

    for (opt_user, bench_time) in get_scores_lb(cur, day, part):
        if opt_user is None or bench_time is None:
            continue

        user = int(opt_user)

        # if the aoc command was sent in a guild that isnt the guild of the user we have here, then using <@id>
        # will render as <@id>, instead of as @person, so we have to fallback to using the name directly
        if guild is None or guild.get_member(user) is None:
            userobj = bot.get_user(user) or await bot.fetch_user(user)
            if userobj:
                builder.write(f"\t{userobj.name}: **{ns(bench_time)}**\n")
            continue
        builder.write(f"\t<@{user}>: **{ns(bench_time)}**\n")

    return builder.getvalue()


# print(benchmark(1234, code))
class MyBot(discord.Client):
    queue = asyncio.Queue[discord.Message]()

    async def on_ready(self) -> None:
        print("Logged in as", self.user)

        while True:
            try:
                msg = await self.queue.get()
                print(f"Processing request for {msg.author.name}")
                code = await msg.attachments[0].read()
                parts = [p for p in msg.content.split(" ") if p]
                day = int((parts[0:1] or (today(), ))[0])
                part = int((parts[1:2] or (1, ))[0])

                await benchmark(msg, code, day, part)

                self.queue.task_done()
            except Exception as err:
                print("Queue loop exception!", err)

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot:
            return

        if msg.content.startswith("aoc"):

            timeit = monotonic_ns()

            parts = msg.content.split(" ")

            try:
                day = int(parts[1])
            except IndexError:
                day = today()
            except ValueError: 
                if len(parts) > 2:
                    # if there were more words passed just skip it
                    # it probably wasn't for us
                    return
                    
                if parts[1] == "help":
                    await msg.reply("(For helptext, Direct Message me `help`)")
                    return

                await msg.reply("ERR: Passed invalid integer for day")
                return

            if not (1 <= day <= 25):
                await msg.reply("ERR: Day not in range (1..=25)")
                return

            print(f"Best for d {day}")

            cur = db.cursor()

            part1 = await formatted_scores_for(msg.author, self, cur, day, 1)
            part2 = await formatted_scores_for(msg.author, self, cur, day, 2)
            
            embed = discord.Embed(title=f"Top 10 fastest toboggans for day {day}", color=0xE84611)

            if part1:
                embed.add_field(name="Part 1", value=part1, inline=True)
            if part2:
                embed.add_field(name="Part 2", value=part2, inline=True)

            end = ns(monotonic_ns() - timeit)

            embed.set_footer(text=f"Computed in {end}")

            await msg.reply(embed=embed)
            return

        if not isinstance(msg.channel, discord.DMChannel):
            return
        
        if msg.content == "help":
            await msg.reply(embed=discord.Embed(title="Ferris Elf help page", color=0xE84611, description="""
**help** - Send this message
**info** - Some useful information about benchmarking
**aoc _[day]_** - Best times so far
**_[day]_ _[part]_ <attachment>** - Benchmark attached code

If [_day_] and/or [_part_] is ommited, they are assumed to be today and part 1

Message <@117530756263182344> for any questions"""))
            return

        if msg.content == "info":
            await msg.reply(embed=discord.Embed(title="Benchmark information", color=0xE84611, description="""
When sending code for a benchmark, you should make sure it looks like.
```rs
pub fn run(input: &str) -> i64 {
    0
}
```

Input can be either a &str or a &[u8], which ever you prefer. The return should \
be the solution to the day and part. Output can be `impl std::fmt::Display`.

Note that ferris-elf includes a **trailing newline** in the input.

Rust version is latest Docker nightly
**Available dependencies**
```toml
ahash = "0.8"
arrayvec = "0.7"
atoi = "2"
atoi_radix10 = { git = "https://github.com/gilescope/atoi_radix10" }
atoi_simd = "0.16"
bitvec = "1"
bit-set = "0.8"
bstr = "1"
btoi = "0.4"
bytemuck = { version = "1", features = ["derive"] }
core_simd = { git = "https://github.com/rust-lang/portable-simd" }
dashmap = "6"
fancy-regex = "0.14"
flume = "0.11"
itertools = "0.13"
foldhash = "0.1"
memchr = "2"
mimalloc = { version = "0.1", default-features = false }
nom = "7"
num = "0.4"
num-traits = "0.2"
parse-display = "0.10"
pathfinding = "4"
pollster = "0.4"
radsort = "0.1"
rangemap = "1"
rayon = "1"
regex = "1"
roots = "0.0.8"
rustc-hash = { version = "2.1", features = ["nightly"] }
smallvec = "1"
t1ha = "0.1"
#wgpu = "0.18"
```
If you'd like a dependency be added, please send a message to <@117530756263182344>. Check back often as the available dependencies are bound to change over the course of AOC

**Hardware**
Benchmarks are run on dedicated hardware in my basement. The hardware \
consists of a desktop with a Ryzen 5950X processor, for a \
total of 32 threads. There is 128 gigabytes of DDR4 available to your benchmark.
You benchmark is first ran for 5 seconds to warm up the cores, and then \
benchmarked for another 5. Please do not memoize any values in global state, a \
call to `run` should always perform all of the work.


Be kind and do not abuse :)"""))
            return

        if len(msg.attachments) == 0:
            await msg.reply("Please provide the code as a file attachment")
            return

        if not self.queue.empty():
            await msg.reply("Benchmark queued...", mention_author=False)
        else:
            await msg.reply("Benchmark running...", mention_author=False)

        print("Queued for", msg.author, "(Queue length)", self.queue.qsize())
        self.queue.put_nowait(msg)        

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

token = os.getenv("DISCORD_TOKEN")

assert token is not None, "No discord token passed"

bot = MyBot(intents=intents)
bot.run(token)
