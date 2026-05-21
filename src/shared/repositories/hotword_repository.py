"""CRUD for hotword_groups table."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from shared.db import utc_now_iso


class DuplicateNameError(Exception):
    pass


class GroupNotFoundError(Exception):
    pass


@dataclass
class HotwordGroup:
    id: int
    name: str
    words: list[str]
    created_at: str
    updated_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> HotwordGroup:
        return cls(
            id=row["id"], name=row["name"],
            words=_deserialize_words(row["words_csv"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


def _serialize_words(words: list[str]) -> str:
    for w in words:
        if "," in w:
            raise ValueError(f"hotword may not contain ',' : {w!r}")
    return ",".join(words)


def _deserialize_words(csv: str) -> list[str]:
    if not csv:
        return []
    return csv.split(",")


def create_group(conn: sqlite3.Connection, *, name: str, words: list[str]) -> int:
    words_csv = _serialize_words(words)
    now = utc_now_iso()
    try:
        cur = conn.execute(
            "INSERT INTO hotword_groups "
            "(name, words_csv, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (name, words_csv, now, now),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise DuplicateNameError(name) from e
        raise


def get_group(conn: sqlite3.Connection, group_id: int) -> HotwordGroup | None:
    row = conn.execute(
        "SELECT * FROM hotword_groups WHERE id=?", (group_id,)
    ).fetchone()
    if not row:
        return None
    return HotwordGroup.from_row(row)


def get_group_words(conn: sqlite3.Connection, group_ids: list[int]) -> list[str]:
    if not group_ids:
        return []
    placeholders = ",".join("?" * len(group_ids))
    rows = conn.execute(
        f"SELECT words_csv FROM hotword_groups WHERE id IN ({placeholders})",
        group_ids,
    ).fetchall()
    out: list[str] = []
    for r in rows:
        out.extend(_deserialize_words(r["words_csv"]))
    return out


def list_groups(conn: sqlite3.Connection) -> list[HotwordGroup]:
    rows = conn.execute("SELECT * FROM hotword_groups ORDER BY name").fetchall()
    return [HotwordGroup.from_row(r) for r in rows]


def update_group(conn: sqlite3.Connection, group_id: int, *,
                 name: str | None = None, words: list[str] | None = None) -> None:
    existing = get_group(conn, group_id)
    if not existing:
        raise GroupNotFoundError(group_id)
    new_name = name if name is not None else existing.name
    new_words = words if words is not None else existing.words
    try:
        conn.execute(
            "UPDATE hotword_groups SET name=?, words_csv=?, updated_at=? WHERE id=?",
            (new_name, _serialize_words(new_words), utc_now_iso(), group_id),
        )
        conn.commit()
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed" in str(e):
            raise DuplicateNameError(new_name) from e
        raise


def delete_group(conn: sqlite3.Connection, group_id: int) -> None:
    cur = conn.execute("DELETE FROM hotword_groups WHERE id=?", (group_id,))
    conn.commit()
    if cur.rowcount == 0:
        raise GroupNotFoundError(group_id)
