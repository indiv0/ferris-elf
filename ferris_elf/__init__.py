import docker
import discord
import asyncio
import io
import os
import functools
from typing import Optional, Union, TypedDict, cast
from time import monotonic_ns
from os import listdir
from os.path import isfile, join
from discord.utils import escape_markdown
from statistics import median, stdev
from itertools import chain
from datetime import datetime, timezone
from blake3 import blake3

from . import fetch

from .fetch import today

from .database import Database

doc = docker.from_env()


async def build_image(msg: discord.Message, solution: bytes) -> bool:
    print(f"Building for {msg.author.name}")
    # status = await msg.reply("Building...", mention_author=False)
    with open("runner/src/code.rs", "wb+") as f:
        f.write(solution)

    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(
            None,
            functools.partial(
                doc.images.build, path="runner", tag=f"ferris-elf-{msg.author.id}"
            ),
        )
        return True
    except docker.errors.BuildError as err:
        print(f"Build error: {err}")
        e = ""
        for chunk in err.build_log:
            e += chunk.get("stream") or ""
        if "Compiling[0m ferris-elf" in e:
            e = e[e.index("Compiling[0m ferris-elf") - 18 :]
            if len(e) < 2000:
                await msg.reply(f"Error building benchmark: ```ansi{e}\n```")
                return False
        from strip_ansi import strip_ansi

        e = strip_ansi(e)
        await msg.reply(
            f"Error building benchmark: {err}",
            file=discord.File(io.BytesIO(e.encode("utf-8")), "build_log.txt"),
        )
        return False
    # finally:
    #    await status.delete()


async def run_image(msg: discord.Message, input: str) -> Optional[str]:
    print(f"Running for {msg.author.name}")
    # input = ','.join([str(int(x)) for x in input])
    # status = await msg.reply("Running benchmark...", mention_author=False)
    loop = asyncio.get_event_loop()
    try:
        # os.environ['NVIDIA_VISIBLE_DEVICES']='all'
        # os.environ['NVIDIA_DRIVER_CAPABILITIES']='compute,utility'
        # out = await loop.run_in_executor(None, functools.partial(doc.containers.run, f"ferris-elf-{msg.author.id}", f"timeout 180 ./target/release/ferris-elf", environment=dict(INPUT=input), remove=True, stdout=True, mem_limit="120g", network_mode="none", runtime="nvidia"))
        out = await loop.run_in_executor(
            None,
            functools.partial(
                doc.containers.run,
                f"ferris-elf-{msg.author.id}",
                "timeout 180 ./profile.sh",
                environment=dict(INPUT=input),
                remove=True,
                stdout=True,
                mem_limit="120g",
                network_mode="none",
                cpuset_cpus="0-7,16-23",
            ),
        )
        out = out.decode("utf-8")
        print(out)
        return str(out)
    except docker.errors.ContainerError as err:
        print(f"Run error: {err}")
        await msg.reply(
            f"Error running benchmark: {err}",
            file=discord.File(io.BytesIO(err.stderr), "stderr.txt"),
        )
        return None
    # finally:
    #    await status.delete()


def ns(v: float) -> str:
    if v > 1e9:
        return f"{v / 1e9:.2f}s"
    if v > 1e6:
        return f"{v / 1e6:.2f}ms"
    if v > 1e3:
        return f"{v / 1e3:.2f}µs"
    # dont push padding zeroes because resolution is 1 ns
    return f"{v:.0f}ns"


class ResultDict(TypedDict):
    answer: str
    average: int
    median: int
    max: int
    min: int


class CacheGrindResult(ResultDict, total=False):
    total_memory_accesses: int
    total_l1_icache_misses: int
    total_ll_icache_misses: int
    total_l1_dcache_misses: int
    total_ll_dcache_misses: int


def formatted_solutions_for(db: Database, day: int, part: int) -> str:
    builder = io.StringIO()

    for answer, count in db.solutions_for(day, part):
        if answer is None or count is None:
            continue

        builder.write(f"\t{answer}: **{count}**\n")

        if len(builder.getvalue()) > 800:
            break

    return builder.getvalue()


async def benchmark(
    msg: discord.Message,
    db: Database,
    code: bytes,
    day: int,
    part: int,
    rerun: bool,
) -> None:
    build = await build_image(msg, code)
    if not build:
        return

    day_path = fetch.get_day_input_dir(fetch.year, day)
    try:
        onlyfiles = fetch.get_input_filenames(fetch.year, day)
    except Exception:
        # FIXME(ultrabear): excepting on Exception instead of BaseException means things like KeyboardInterrupt
        # wont be caught, but there is probably a more specific exception to catch here
        await msg.reply(f"Failed to read input files for day {day}, part {part}")
        return

    verified = False
    results = []
    previous_best = db.get_best(day, part, msg.author.id)
    size = 0
    for i, file in enumerate(onlyfiles):
        verify = db.get_answer(file, day, part)

        if verify is not None:
            print("Verify", verify, "file", file)

        with open(join(day_path, file), "r") as f:
            input = f.read()
        size = max(len(input), size)

        # status = await msg.reply(f"Benchmarking input {i+1}", mention_author=False)
        out = await run_image(msg, input)
        if not out:
            return
        # await status.delete()

        result = cast(CacheGrindResult, {})
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
                result["total_memory_accesses"] = int(
                    line[33:].replace(",", "").split()[0]
                )
            if "Total L1 I-Cache Misses" in line:
                result["total_l1_icache_misses"] = int(
                    line[35:].replace(",", "").split()[0]
                )
            if "Total LL I-Cache Misses" in line:
                result["total_ll_icache_misses"] = int(
                    line[35:].replace(",", "").split()[0]
                )
            if "Total L1 D-Cache Misses" in line:
                result["total_l1_dcache_misses"] = int(
                    line[35:].replace(",", "").split()[0]
                )
            if "Total LL D-Cache Misses" in line:
                result["total_ll_dcache_misses"] = int(
                    line[35:].replace(",", "").split()[0]
                )

        if verify:
            if not result["answer"] == verify:
                await msg.reply(
                    f"Error: Benchmark returned wrong answer for input {i + 1}"
                )
                return
            verified = True
        else:
            print("Cannot verify run", result["answer"])

        results.append(result)

    now = int(datetime.now(timezone.utc).timestamp())
    code_hash = blake3(code).hexdigest()
    for result in results:
        if rerun:
            db.update_runs(day, part, result["median"], result["answer"], code_hash)
        else:
            db.insert_run(
                msg.author.id,
                code,
                day,
                part,
                result["median"],
                result["answer"],
                now,
                code_hash,
            )

    best = min([int(r["median"]) for r in results])
    med = median([int(r["median"]) for r in results])
    dev = stdev(
        chain([int(r["min"]) for r in results], [int(r["max"]) for r in results])
    )
    # total_memory_accesses = mean([int(r["total_memory_accesses"]) for r in results])
    # total_l1_icache_misses = mean([int(r["total_l1_icache_misses"]) for r in results])
    # total_ll_icache_misses = mean([int(r["total_ll_icache_misses"]) for r in results])
    # total_l1_dcache_misses = mean([int(r["total_l1_dcache_misses"]) for r in results])
    # total_ll_dcache_misses = mean([int(r["total_ll_dcache_misses"]) for r in results])

    title = "Benchmark complete" if verified else "Benchmark complete (Unverified)"
    text = f"Median: **{ns(med)} ±{ns(dev)}**\nThroughput: **{size * 1000 / (med + 1):.2f}MB/s**"
    if previous_best is not None:
        if (
            not (abs(previous_best - best) < 100)
            if best > 1000
            else (abs(previous_best - best) < 5)
        ):
            direction = "+" if previous_best < best else "-"
            text += f"\nChange: **{direction}{ns(abs(previous_best - best))} {abs(((previous_best - best) / (previous_best + 1)) * 100):.2f}%**"
    # await msg.reply(embed=discord.Embed(title="Benchmark complete", description=f"Median: **{ns(median)}**\nAverage: **{ns(average)}**\nTotal Memory Accesses: **{total_memory_accesses:,.2f}**\nTotal L1 I-Cache Misses: **{total_l1_icache_misses:,.2f}**\nTotal LL I-Cache Misses: **{total_ll_icache_misses:,.2f}**\nTotal L1 D-Cache Misses: **{total_l1_dcache_misses:,.2f}**\nTotal LL D-Cache Misses: **{total_ll_dcache_misses:,.2f}**"))
    await msg.reply(
        embed=discord.Embed(
            title=title,
            description=text,
            color=0xE43A25
            if previous_best is not None and previous_best < best
            else 0x41E425,
        )
    )

    db.commit()
    print("Inserted results into DB")


async def formatted_scores_for(
    author: Union[discord.User, discord.Member],
    bot: discord.Client,
    db: Database,
    day: int,
    part: int,
) -> str:
    builder = io.StringIO()

    # If the message was not sent in a DM, get the author's guild.
    if isinstance(author, discord.Member):
        # FIXME [NP]: Is this redundant because we have the `author.guild` already?
        guild = bot.get_guild(author.guild.id)
    else:
        guild = None

    for opt_user, bench_time in db.get_scores_lb(day, part):
        if opt_user is None or bench_time is None:
            continue

        user = int(opt_user)

        # if the aoc command was sent in a guild that isnt the guild of the user we have here, then using <@id>
        # will render as <@id>, instead of as @person, so we have to fallback to using the name directly
        if guild is None or guild.get_member(user) is None:
            userobj = bot.get_user(user) or await bot.fetch_user(user)
            if userobj:
                builder.write(
                    f"\t{escape_markdown(userobj.name)}: **{ns(bench_time)}**\n"
                )
            continue
        builder.write(f"\t<@{user}>: **{ns(bench_time)}**\n")

        if len(builder.getvalue()) > 800:
            break

    return builder.getvalue()


async def formatted_best(
    author: Union[discord.User, discord.Member],
    bot: discord.Client,
    db: Database,
    part: int,
) -> str:
    builder = io.StringIO()

    # If the message was not sent in a DM, get the author's guild.
    if isinstance(author, discord.Member):
        # FIXME [NP]: Is this redundant because we have the `author.guild` already?
        guild = bot.get_guild(author.guild.id)
    else:
        guild = None

    for opt_day, _opt_part, opt_user, opt_bench_time in db.get_best_lb(part):
        if (
            opt_day is None
            or _opt_part is None
            or opt_user is None
            or opt_bench_time is None
        ):
            continue

        user = int(opt_user)

        # if the aoc command was sent in a guild that isnt the guild of the user we have here, then using <@id>
        # will render as <@id>, instead of as @person, so we have to fallback to using the name directly
        if guild is None or guild.get_member(user) is None:
            userobj = bot.get_user(user) or await bot.fetch_user(user)
            if userobj:
                builder.write(
                    f"\td{opt_day}: {escape_markdown(userobj.name)} - **{ns(opt_bench_time)}**\n"
                )
            continue
        builder.write(f"\td{opt_day}: <@{user}> - **{ns(opt_bench_time)}**\n")

        if len(builder.getvalue()) > 800:
            break

    return builder.getvalue()


async def leaderboard_cmd(
    client: discord.Client, db: Database, msg: discord.Message
) -> None:
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

    part1 = await formatted_scores_for(msg.author, client, db, day, 1)
    part2 = await formatted_scores_for(msg.author, client, db, day, 2)

    embed = discord.Embed(
        title=f"Top 10 fastest toboggans for day {day}", color=0xE84611
    )

    if part1:
        embed.add_field(name="Part 1", value=part1, inline=True)
    if part2:
        embed.add_field(name="Part 2", value=part2, inline=True)

    end = ns(monotonic_ns() - timeit)

    embed.set_footer(text=f"Computed in {end}")

    await msg.reply(embed=embed)
    return


async def best_cmd(client: discord.Client, db: Database, msg: discord.Message) -> None:
    timeit = monotonic_ns()

    parts = msg.content.split(" ")

    if len(parts) > 2:
        # if there were more words passed just skip it
        # it probably wasn't for us
        return

    if len(parts) == 2 and parts[1] == "help":
        await msg.reply("(For helptext, Direct Message me `help`)")
        return

    print("Best overall")

    best1 = await formatted_best(msg.author, client, db, 1)
    best2 = await formatted_best(msg.author, client, db, 2)

    embed = discord.Embed(title="Top fastest toboggans for all days", color=0xE84611)

    if best1:
        embed.add_field(name="Part 1", value=best1, inline=True)
    if best2:
        embed.add_field(name="Part 2", value=best2, inline=True)

    end = ns(monotonic_ns() - timeit)

    embed.set_footer(text=f"Computed in {end}")

    await msg.reply(embed=embed)
    return


async def migrate_hash_cmd(
    client: discord.Client, db: Database, msg: discord.Message
) -> None:
    authorized = [
        117530756263182344,  # iwearapot
    ]
    if msg.author.id not in authorized:
        await msg.reply("(For helptext, Direct Message me `help`)")
        return

    for row_id, opt_code in db.get_runs_without_hash():
        if opt_code is None:
            continue

        code_hash = blake3(opt_code).hexdigest()
        print(f"Setting hash of row {row_id} to {code_hash}")
        db.update_code_hash(row_id, code_hash)
    db.commit()


async def rerun_cmd(client: discord.Client, db: Database, msg: discord.Message) -> None:
    authorized = [
        117530756263182344,  # iwearapot
    ]
    if msg.author.id not in authorized:
        await msg.reply("(For helptext, Direct Message me `help`)")
        return

    while True:
        try:
            opt_invalid_run = db.get_next_invalid_run()
            if opt_invalid_run is None:
                await msg.reply("No targets to re-run.")
                return

            (opt_day, opt_part, opt_answer, opt_code, opt_code_hash) = opt_invalid_run
            if (
                opt_day is None
                or opt_part is None
                or opt_answer is None
                or opt_code is None
                or opt_code_hash is None
            ):
                await msg.reply("Invalid re-run target.")
                return

            await msg.reply(
                f"Re-running d{opt_day}p{opt_part} for code {opt_code_hash}"
            )

            await benchmark(msg, db, opt_code, opt_day, opt_part, True)
        except Exception as err:
            print("Rerun loop exception!", err)


async def handle_dm_commands(client: "MyBot", msg: discord.Message) -> None:
    if msg.content == "help":
        await msg.reply(
            embed=discord.Embed(
                title="Ferris Elf help page",
                color=0xE84611,
                description="""
**help** - Send this message
**info** - Some useful information about benchmarking
**aoc _[day]_** - Best times so far
**best** - Best times for all days and parts
**_[day]_ _[part]_ <attachment>** - Benchmark attached code

If [_day_] and/or [_part_] is omitted, they are assumed to be today and part 1

Message <@117530756263182344> for any questions""",
            )
        )
        return

    if msg.content == "info":
        await msg.reply(
            embed=discord.Embed(
                title="Benchmark information",
                color=0xE84611,
                description="""
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
bytemuck = { version = "1", features = ["must_cast", "nightly_portable_simd", "derive"] }
car = "0.1"
core_simd = { git = "https://github.com/rust-lang/portable-simd" }
dashmap = "6"
fancy-regex = "0.14"
flume = "0.11"
glam = { version = "0.29", features = ["approx", "bytemuck", "rand", "serde", "mint"] }
itertools = "0.13"
foldhash = "0.1"
memchr = "2"
mimalloc = { version = "0.1", default-features = false }
ndarray = "0.16"
nom = "7"
nom_locate = "4.2"
num = "0.4"
num-traits = "0.2"
parse-display = "0.10"
paste = "1.0.15"
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


Be kind and do not abuse :)""",
            )
        )
        return

    if msg.content.startswith("inputs"):
        authorized = [
            117530756263182344,  # iwearapot
            696196765564534825,  # bendn
            249215681093042186,  # alion02
            673675955616874518,  # yuyuko
            512328264543371274,  # danielrab
            88225219411443712,  # giooschi
            711617112669683784,  # starfish
            395782478192836608,  # doge
            829024113296539658,  # max397
            1308148297843605504,  # mrpink
            804940746591174656,  # oklyth
            1312479736748048424,  # __main_character__
        ]
        if msg.author.id not in authorized:
            await msg.reply("(For helptext, Direct Message me `help`)")
            return

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

            await msg.reply("ERR: Passed invalid integer for day")
            return

        if not (1 <= day <= 25):
            await msg.reply("ERR: Day not in range (1..=25)")
            return

        print(f"Inputs for d {day}")

        day_path = fetch.get_day_input_dir(fetch.year, day)
        try:
            onlyfiles = [f for f in listdir(day_path) if isfile(join(day_path, f))]
        except Exception:
            # FIXME(ultrabear): excepting on Exception instead of BaseException means things like KeyboardInterrupt
            # wont be caught, but there is probably a more specific exception to catch here
            await msg.reply(f"Failed to read input files for day {day}")
            return

        for file in onlyfiles:
            with open(join(day_path, file), "rb") as f:
                # input = f.read()
                await msg.reply(f"Input {file}", file=discord.File(f))
        return

    if msg.content.startswith("solutions"):
        authorized = [
            117530756263182344,  # iwearapot
            696196765564534825,  # bendn
            249215681093042186,  # alion02
            673675955616874518,  # yuyuko
            512328264543371274,  # danielrab
            88225219411443712,  # giooschi
            711617112669683784,  # starfish
            395782478192836608,  # doge
            829024113296539658,  # max397
            1308148297843605504,  # mrpink
            804940746591174656,  # oklyth
            1312479736748048424,  # __main_character__
        ]
        if msg.author.id not in authorized:
            await msg.reply("(For helptext, Direct Message me `help`)")
            return

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

            await msg.reply("ERR: Passed invalid integer for day")
            return

        if not (1 <= day <= 25):
            await msg.reply("ERR: Day not in range (1..=25)")
            return

        print(f"Solutions for d {day}")

        part1 = formatted_solutions_for(client.db, day, 1)
        part2 = formatted_solutions_for(client.db, day, 2)

        embed = discord.Embed(title=f"Submitted answers for day {day}", color=0xE84611)

        if part1:
            embed.add_field(name="Part 1", value=part1, inline=True)
        if part2:
            embed.add_field(name="Part 2", value=part2, inline=True)

        end = ns(monotonic_ns() - timeit)

        embed.set_footer(text=f"Computed in {end}")

        await msg.reply(embed=embed)
        return

    if msg.content.startswith("approve"):
        # iwearapot + bendn
        if (
            not msg.author.id == 117530756263182344
            and not msg.author.id == 696196765564534825
        ):
            await msg.reply("(For helptext, Direct Message me `help`)")
            return

        parts = msg.content.split(" ")

        try:
            day = int(parts[1])
        except IndexError:
            await msg.reply("First parameter must be the day as an integer")
            return
        except ValueError:
            await msg.reply("ERR: Passed invalid integer for day")
            return

        if not (1 <= day <= 25):
            await msg.reply("ERR: Day not in range (1..=25)")
            return

        try:
            part = int(parts[2])
        except IndexError:
            await msg.reply("Second parameter must be the part as an integer")
            return
        except ValueError:
            await msg.reply("ERR: Passed invalid integer for part")
            return

        if not (1 <= part <= 2):
            await msg.reply("ERR: Part not in range (1..=2)")
            return

        try:
            input_id = str(parts[3])
        except IndexError:
            await msg.reply("Third parameter must be the input ID as an string")
            return
        except ValueError:
            await msg.reply("ERR: Passed invalid string for input ID")
            return

        try:
            answer = int(parts[4])
        except IndexError:
            await msg.reply("Fourth parameter must be the answer as an integer")
            return
        except ValueError:
            await msg.reply("ERR: Passed invalid integer for answer")
            return

        print(f"Approving for d {day}")
        # cur.execute("INSERT INTO solutions VALUES (?, ?, ?, ?, ?)", (input_id, day, part, answer, answer))

        # FIXME(ultrabear): part has been replaced with a quoted string because it is not init as a variable
        # this entire section of code is a deletion candidate too, assess after ruff check pass is completed
        await msg.reply(
            f"Submitted answer {answer} for day {day} part {'part'} input {input_id}"
        )
        return

    if len(msg.attachments) == 0:
        await msg.reply("Please provide the code as a file attachment")
        return

    if not client.queue.empty():
        await msg.reply("Benchmark queued...", mention_author=False)
    else:
        await msg.reply("Benchmark running...", mention_author=False)

    print("Queued for", msg.author, "(Queue length)", client.queue.qsize())
    client.queue.put_nowait(msg)


# print(benchmark(1234, code))
class MyBot(discord.Client):
    queue = asyncio.Queue[discord.Message]()
    db: Database

    async def on_ready(self) -> None:
        print("Logged in as", self.user)

        while True:
            try:
                msg = await self.queue.get()
                print(f"Processing request for {msg.author.name}")
                code = await msg.attachments[0].read()
                parts = [p for p in msg.content.split(" ") if p]

                if len(parts) < 2:
                    await msg.reply(
                        "Looks like you forgot to specify `<day> <part>`. Submit again, with a message like `4 2` if your code is for day 4 part 2."
                    )
                    continue

                day = int((parts[0:1] or (today(),))[0])
                part = int((parts[1:2] or (1,))[0])

                await benchmark(msg, self.db, code, day, part, False)

                self.queue.task_done()
            except Exception as err:
                print("Queue loop exception!", err)

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author.bot:
            return

        if msg.content.startswith("aoc"):
            return await leaderboard_cmd(self, self.db, msg)

        if msg.content.startswith("best"):
            return await best_cmd(self, self.db, msg)

        if msg.content.startswith("migrate-hash"):
            return await migrate_hash_cmd(self, self.db, msg)

        if msg.content.startswith("rerun"):
            return await rerun_cmd(self, self.db, msg)

        if not isinstance(msg.channel, discord.DMChannel):
            return

        return await handle_dm_commands(self, msg)


def main():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    token = os.getenv("DISCORD_TOKEN")

    assert token is not None, "No discord token passed"

    bot = MyBot(intents=intents)
    bot.db = Database("database.db")
    bot.run(token)


if __name__ == "__main__":
    main()
