#!/usr/bin/env python3
"""Flask app that lists student names from Postgres."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from flask import Flask, render_template

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

app = Flask(__name__)


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
        raise RuntimeError(
            "Missing database URL. Put DATABASE_PUBLIC_URL (or DATABASE_URL) "
            f"in {ENV_PATH}."
        )
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def fetch_student_names() -> list[str]:
    with psycopg.connect(database_url(), connect_timeout=20) as conn:
        rows = conn.execute(
            "SELECT name FROM students ORDER BY name"
        ).fetchall()
    return [row[0] for row in rows]


@app.route("/")
def index():
    students = fetch_student_names()
    return render_template("index.html", students=students)


if __name__ == "__main__":
    app.run(debug=True)
