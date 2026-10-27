#!/usr/bin/env python3
"""Apply schema.sql and load class_dataset.csv into Railway Postgres."""

from __future__ import annotations

import csv
import os
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SCHEMA_PATH = ROOT / "schema.sql"
CSV_PATH = ROOT / "class_dataset.csv"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def database_url() -> str:
    load_dotenv(ENV_PATH)
    url = (
        os.environ.get("DATABASE_PUBLIC_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()
    if not url:
        raise SystemExit(
            "Missing database URL. Put DATABASE_PUBLIC_URL (or DATABASE_URL) "
            f"in {ENV_PATH}."
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def split_multi(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def main() -> None:
    url = database_url()
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    uncommented = "\n".join(
        line for line in schema_sql.splitlines() if not line.strip().startswith("--")
    )
    create_statements = [
        stmt.strip() for stmt in uncommented.split(";") if stmt.strip()
    ]

    with CSV_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"No rows found in {CSV_PATH}")

    tools = sorted({name for row in rows for name in split_multi(row["tools"])})
    slots = sorted(
        {name for row in rows for name in split_multi(row["availability"])}
    )

    drop_sql = """
        DROP TABLE IF EXISTS student_availability;
        DROP TABLE IF EXISTS student_tools;
        DROP TABLE IF EXISTS availability_slots;
        DROP TABLE IF EXISTS tools;
        DROP TABLE IF EXISTS students;
    """

    with psycopg.connect(url, connect_timeout=20) as conn:
        conn.execute(drop_sql)
        for statement in create_statements:
            conn.execute(statement)

        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO tools (tool_name) VALUES (%s)",
                [(name,) for name in tools],
            )
            cur.executemany(
                "INSERT INTO availability_slots (slot_name) VALUES (%s)",
                [(name,) for name in slots],
            )

            cur.execute("SELECT tool_id, tool_name FROM tools")
            tool_ids = {name: tool_id for tool_id, name in cur.fetchall()}
            cur.execute("SELECT slot_id, slot_name FROM availability_slots")
            slot_ids = {name: slot_id for slot_id, name in cur.fetchall()}

            cur.executemany(
                """
                INSERT INTO students (
                    netid, name, school_year, intro_programming,
                    skill_programming, skill_data_stats,
                    skill_frontend_design, skill_business_pitch,
                    working_style, interests, semester_goal, submitted_at
                ) VALUES (
                    %(netid)s, %(name)s, %(school_year)s, %(intro_programming)s,
                    %(skill_programming)s, %(skill_data_stats)s,
                    %(skill_frontend_design)s, %(skill_business_pitch)s,
                    %(working_style)s, %(interests)s, %(semester_goal)s,
                    %(submitted_at)s
                )
                """,
                rows,
            )

            student_tools = []
            student_slots = []
            for row in rows:
                netid = row["netid"]
                for name in split_multi(row["tools"]):
                    student_tools.append((netid, tool_ids[name]))
                for name in split_multi(row["availability"]):
                    student_slots.append((netid, slot_ids[name]))

            cur.executemany(
                "INSERT INTO student_tools (netid, tool_id) VALUES (%s, %s)",
                student_tools,
            )
            cur.executemany(
                "INSERT INTO student_availability (netid, slot_id) VALUES (%s, %s)",
                student_slots,
            )

        counts = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM students) AS students,
                (SELECT COUNT(*) FROM tools) AS tools,
                (SELECT COUNT(*) FROM student_tools) AS student_tools,
                (SELECT COUNT(*) FROM availability_slots) AS availability_slots,
                (SELECT COUNT(*) FROM student_availability) AS student_availability
            """
        ).fetchone()

        conn.commit()

    print("Loaded into Railway Postgres:")
    print(f"  students: {counts[0]}")
    print(f"  tools: {counts[1]}")
    print(f"  student_tools: {counts[2]}")
    print(f"  availability_slots: {counts[3]}")
    print(f"  student_availability: {counts[4]}")


if __name__ == "__main__":
    main()
