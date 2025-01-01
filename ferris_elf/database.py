import sqlite3
from typing import Optional, Iterator, Self


class Database:
    __slots__ = "_db", "_cursor"

    def __init__(self, file: str) -> None:
        db = sqlite3.connect(file)

        cur = db.cursor()
        # Migration: ALTER TABLE runs ADD COLUMN timestamp INTEGER NOT NULL DEFAULT 0;
        # Migration: ALTER TABLE runs ADD COLUMN code_hash TEXT DEFAULT NULL;
        cur.execute("""CREATE TABLE IF NOT EXISTS runs 
            (user TEXT, code TEXT, day INTEGER, part INTEGER, time REAL, answer INTEGER, answer2, timestamp INTEGER NOT NULL DEFAULT 0, code_hash TEXT DEFAULT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS solutions 
            (key TEXT, day INTEGER, part INTEGER, answer INTEGER, answer2)""")

        # Implementation details: https://github.com/indiv0/ferris-elf/issues/7
        cur.execute(
            "CREATE INDEX IF NOT EXISTS runs_index ON runs (day, part, user, time)"
        )

        cur.execute(
            "CREATE INDEX IF NOT EXISTS solutions_idx ON solutions (day, part)"
        )

        # run these on startup to clean up database
        print("Running database maintenance tasks, this may take a while")
        cur.execute("VACUUM")
        cur.execute("ANALYZE")

        db.commit()

        self._db = db
        self._cursor: None | sqlite3.Cursor = None

    def __enter__(self) -> Self:
        self._cursor = self._db.cursor()
        return self

    def __exit__(self, *_) -> None:
        self._cursor = None
        self.commit()

    def commit(self) -> None:
        self._db.commit()

    def _get_cur(self) -> sqlite3.Cursor:
        if self._cursor:
            return self._cursor
        else:
            return self._db.cursor()

    def solutions_for(
        self, day: int, part: int
    ) -> Iterator[tuple[Optional[int], Optional[int]]]:
        return self._get_cur().execute(
            """SELECT answer2, COUNT(*)
            FROM runs
            WHERE day = ? AND part = ?
            GROUP BY answer2""",
            (day, part),
        )

    def get_best(self, day: int, part: int, user: int) -> Optional[int]:
        return next(
            self._get_cur().execute(
                """SELECT MIN(time) FROM runs WHERE day = ? AND part = ? AND user = ? LIMIT 1""",
                (day, part, user),
            )
        )[0]

    def get_scores_lb(
        self, day: int, part: int
    ) -> Iterator[tuple[Optional[str], Optional[int]]]:
        return self._get_cur().execute(
            """SELECT user, MIN(time) FROM runs
            WHERE day = ? AND part = ?
            GROUP BY user ORDER BY time""",
            (day, part),
        )

    def get_best_lb(
        self, part: int
    ) -> Iterator[tuple[Optional[int], Optional[int], Optional[str], Optional[int]]]:
        return self._get_cur().execute(
            "SELECT day, part, user, MIN(time) FROM runs WHERE part=? GROUP BY day, part ORDER BY day, part;",
            (part,),
        )

    def get_answer(self, key: str, day: int, part: int) -> Optional[str]:
        row = (
            self._get_cur()
            .execute(
                "SELECT answer2 FROM solutions WHERE key = ? AND day = ? AND part = ?",
                (key, day, part),
            )
            .fetchone()
        )

        if row:
            return str(row[0]).strip()
        else:
            return None

    def insert_run(
        self,
        author_id: int,
        code: bytes,
        day: int,
        part: int,
        median: float,
        answer: str,
        timestamp: int,
        code_hash: str,
    ):
        self._get_cur().execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                author_id,
                code,
                day,
                part,
                median,
                answer,
                answer,
                timestamp,
                code_hash,
            ),
        )

    def update_runs(
        self,
        day: int,
        part: int,
        median: float,
        answer: str,
        code_hash: str,
    ):
        self._get_cur().execute(
            """UPDATE runs
            SET time = ?, timestamp = 1
            WHERE timestamp = 0 AND day = ? AND part = ? AND answer = ? AND code_hash = ?""",
            (
                median,
                day,
                part,
                answer,
                code_hash,
            ),
        )

    def get_runs_without_hash(self) -> Iterator[tuple[int, Optional[bytes]]]:
        return self._get_cur().execute(
            """SELECT ROWID,code
            FROM runs
            WHERE code_hash IS NULL""",
        )

    def update_code_hash(
        self,
        row_id: int,
        code_hash: str,
    ):
        self._get_cur().execute(
            """UPDATE runs
            SET code_hash = ?
            WHERE ROWID = ?""",
            (code_hash, row_id),
        )

    def get_next_invalid_run(
        self,
    ) -> Optional[
        tuple[
            Optional[int], Optional[int], Optional[str], Optional[bytes], Optional[str]
        ]
    ]:
        try:
            # Order the result by random in case a run
            # with invalid answers is encountered. This
            # prevents it from blocking the rerun
            # process.
            return next(
                self._get_cur().execute(
                    """SELECT day, part, answer, code, code_hash
                FROM (
                    SELECT day, part, answer, code, code_hash
                    FROM runs
                    WHERE timestamp = 0
                    GROUP BY day, part, answer, code_hash
                    ORDER BY ROWID
                )
                ORDER BY RANDOM()
                LIMIT 1""",
                )
            )
        except StopIteration:
            return None
