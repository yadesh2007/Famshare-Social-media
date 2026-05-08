import sqlite3
from flask import session
from db import get_db

def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None

    try:
        db = get_db()
        return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.OperationalError:
        return None

def is_following(follower_id, following_id):
    try:
        db = get_db()
        row = db.execute(
            "SELECT id FROM follows WHERE follower_id = ? AND following_id = ?",
            (follower_id, following_id)
        ).fetchone()
        return row is not None
    except sqlite3.OperationalError:
        return False
