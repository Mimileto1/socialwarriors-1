"""Authenticated chat and friendship requests for one game."""
import time
import uuid
from collections import defaultdict, deque
from threading import Lock

from flask import abort, jsonify, request


DDL = (
    """CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY, author TEXT NOT NULL REFERENCES accounts(username),
        body TEXT NOT NULL, created BIGINT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS chat_created ON chat_messages(created, id)",
    """CREATE TABLE IF NOT EXISTS friendships (
        first TEXT NOT NULL REFERENCES accounts(username),
        second TEXT NOT NULL REFERENCES accounts(username),
        sender TEXT NOT NULL REFERENCES accounts(username),
        accepted INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(first, second)
    )""",
)


def install_social(app, connect, current_account, verify_csrf, username_pattern, persistent):
    if not persistent:
        with connect() as db:
            for statement in DDL:
                db.execute(statement)

    write_times = defaultdict(deque)
    lock = Lock()

    def identity():
        account = current_account()
        if not account:
            abort(401)
        return account["username"]

    def limit(username):
        now = time.monotonic()
        with lock:
            for key in list(write_times):
                if now - write_times[key][-1] >= 10:
                    del write_times[key]
            times = write_times[username]
            while times and now - times[0] >= 10:
                times.popleft()
            if len(times) >= 5:
                abort(429)
            times.append(now)

    @app.route("/social/chat", methods=["GET", "POST"])
    def social_chat():
        username = identity()
        if request.method == "POST":
            verify_csrf()
            limit(username)
            message = request.form.get("message", "").strip()
            if not 1 <= len(message) <= 300:
                return jsonify(error="Escribe un mensaje de 1 a 300 caracteres."), 400
            with connect() as db:
                db.execute("INSERT INTO chat_messages VALUES (?, ?, ?, ?)",
                           (uuid.uuid4().hex, username, message, time.time_ns() // 1_000_000))
            return jsonify(ok=True), 201
        with connect() as db:
            rows = db.execute(
                "SELECT author, body, created FROM chat_messages ORDER BY created DESC, id DESC LIMIT 50"
            ).fetchall()
        return jsonify(messages=[dict(row) for row in reversed(rows)])

    @app.route("/social/friends", methods=["GET", "POST"])
    def social_friends():
        username = identity()
        if request.method == "GET":
            with connect() as db:
                rows = db.execute(
                    """SELECT first, second, sender, accepted FROM friendships
                       WHERE first=? OR second=? ORDER BY first, second""", (username, username)
                ).fetchall()
            return jsonify(friends=[
                {"username": row["second"] if row["first"] == username else row["first"],
                 "status": "accepted" if row["accepted"] else "outgoing" if row["sender"] == username else "incoming"}
                for row in rows
            ])
        verify_csrf()
        limit(username)
        other = request.form.get("username", "").strip().lower()
        action = request.form.get("action")
        if not username_pattern.fullmatch(other) or other == username or action not in {"request", "accept", "remove"}:
            return jsonify(error="Solicitud de amistad inválida."), 400
        first, second = sorted((username, other))
        with connect() as db:
            if action == "request":
                if not db.execute("SELECT 1 FROM accounts WHERE username=?", (other,)).fetchone():
                    return jsonify(error="No encontré esa cuenta."), 404
                db.execute(
                    """INSERT INTO friendships(first, second, sender) VALUES (?, ?, ?)
                       ON CONFLICT(first, second) DO NOTHING""", (first, second, username)
                )
            elif action == "accept":
                changed = db.execute(
                    "UPDATE friendships SET accepted=1 WHERE first=? AND second=? AND sender<>?",
                    (first, second, username)
                )
                if not changed.rowcount:
                    return jsonify(error="No tienes una solicitud pendiente de ese jugador."), 409
            else:
                db.execute("DELETE FROM friendships WHERE first=? AND second=?", (first, second))
        return jsonify(ok=True)
