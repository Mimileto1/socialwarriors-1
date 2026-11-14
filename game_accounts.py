"""Local account and session storage for the Flask game server."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import os
import re
import secrets
import sqlite3
import sys
import time
from threading import RLock

import durable

from flask import abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

SESSION_SECONDS = 30 * 86400
USERNAME = re.compile(r"[a-zA-Z0-9_.-]{3,32}")


class PostgresAccounts:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        if statement == "BEGIN IMMEDIATE":
            # Serialize account creation and migration across connections.
            return self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema()))")
        if statement.startswith("DELETE FROM auth_attempts"):
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtext(current_schema() || ':rate'))")
        return self.connection.execute(statement.replace("?", "%s"), parameters)


def install_accounts(app, *, data_dir, slug, title, theme, play, create_save, save_exists, legacy_accounts=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    database = data_dir / "accounts.sqlite3"
    cookie_name = f"{slug}_account"
    secure = os.environ.get("GAME_HTTPS") == "1" or os.environ.get("RENDER") == "true"
    if os.environ.get("RENDER") == "true" and not durable.DATABASE_URL and not os.environ.get("GAME_DATA_DIR"):
        raise RuntimeError("Configure GAME_DATABASE_URL or a persistent GAME_DATA_DIR before starting this service.")
    app.config.update(
        SECRET_KEY=secrets.token_hex(32),
        SESSION_COOKIE_NAME=f"{slug}_form",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=secure,
    )
    # The original game engines keep active saves in process memory.
    game_lock = RLock()

    @contextmanager
    def connect():
        if durable.DATABASE_URL:
            with durable.connect() as db:
                yield PostgresAccounts(db)
            return
        db = sqlite3.connect(database, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    if not durable.DATABASE_URL:
        with connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    password TEXT NOT NULL,
                    save_id TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL REFERENCES accounts(username),
                    expires INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    kind TEXT NOT NULL, address TEXT NOT NULL, attempted INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS auth_attempt_time ON auth_attempts(attempted);
            """)

    dummy_hash = generate_password_hash(secrets.token_urlsafe())

    def token_hash():
        token = request.cookies.get(cookie_name, "")
        if re.fullmatch(r"[\w-]{43}", token, re.ASCII):
            return sha256(token.encode("ascii")).hexdigest()
        return None

    def current_save():
        if "account" not in g:
            g.account = None
            key = token_hash()
            if key:
                with connect() as db:
                    g.account = db.execute(
                        "SELECT save_id FROM accounts JOIN sessions USING(username)"
                        " WHERE token_hash=? AND expires>?",
                        (key, int(time.time())),
                    ).fetchone()
        return g.account["save_id"] if g.account else None

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    def verify_csrf():
        expected = session.get("csrf")
        submitted = request.form.get("csrf", "")
        if not expected or not secrets.compare_digest(expected.encode(), submitted.encode()):
            abort(403)

    def sign_in(username):
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE expires<=? OR token_hash=?", (now, token_hash()))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (sha256(token.encode()).hexdigest(), username, now + SESSION_SECONDS))
        session.clear()
        response = redirect(play, code=303)
        response.set_cookie(cookie_name, token, max_age=SESSION_SECONDS, httponly=True, samesite="Lax", secure=secure)
        return response

    def limited(kind):
        now = int(time.time())
        address = request.remote_addr or ""
        with connect() as db:
            db.execute("DELETE FROM auth_attempts WHERE attempted<=?", (now - 300,))
            count = db.execute("SELECT COUNT(*) AS total FROM auth_attempts WHERE kind=? AND address=?", (kind, address)).fetchone()["total"]
            if count >= 20:
                return True
            db.execute("INSERT INTO auth_attempts VALUES (?,?,?)", (kind, address, now))
        return False

    def validate(username, password):
        if not USERNAME.fullmatch(username):
            raise ValueError("Usa entre 3 y 32 letras, números, puntos, guiones o guiones bajos.")
        if not 8 <= len(password) <= 128:
            raise ValueError("La contraseña debe tener entre 8 y 128 caracteres.")

    def register_account(username, password, save_factory, *, link=False):
        validate(username, password)
        password_hash = generate_password_hash(password)
        with game_lock, connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM accounts WHERE username=?", (username,)).fetchone():
                raise ValueError("Ese nombre de usuario ya está registrado.")
            if legacy_accounts and legacy_accounts.exists(username):
                raise ValueError("Ese nombre de usuario ya está registrado.")
            save_id = save_factory()
            if link and legacy_accounts and legacy_accounts.owns_save(save_id):
                raise ValueError("Esa partida ya está vinculada.")
            if db.execute("SELECT 1 FROM accounts WHERE save_id=?", (save_id,)).fetchone():
                raise ValueError("Esa partida ya está vinculada.")
            db.execute("INSERT INTO accounts VALUES (?,?,?)", (username, password_hash, save_id))

    def page(mode, error=None, status=200):
        return render_template("account.html", title=title, theme=theme, mode=mode, error=error), status

    app.jinja_env.globals["account_csrf"] = csrf_token

    @app.after_request
    def no_store(response):
        if request.endpoint in {"account_login", "account_register", "account_logout", "play", "ruffle", "hello"} or current_save_cached():
            response.headers["Cache-Control"] = "no-store"
        return response

    def current_save_cached():
        return g.get("account") is not None

    @app.route("/", methods=["GET", "POST"])
    @app.route("/login", methods=["GET", "POST"])
    def account_login():
        if request.method == "GET":
            return redirect(play) if current_save() else page("login")
        verify_csrf()
        if limited("login"):
            return page("login", "Demasiados intentos. Espera unos minutos.", 429)
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        with connect() as db:
            account = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone() if USERNAME.fullmatch(username) else None
        if len(password) > 128:
            return page("login", "Usuario o contraseña incorrectos.", 401)
        if account and check_password_hash(account["password"], password):
            return sign_in(account["username"])
        if not account and legacy_accounts and USERNAME.fullmatch(username):
            existing_id = legacy_accounts.verify_user(username, password)
            if existing_id and save_exists(existing_id):
                with game_lock, connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
                    if row is None:
                        owner = db.execute("SELECT 1 FROM accounts WHERE save_id=?", (existing_id,)).fetchone()
                        if not owner:
                            db.execute("INSERT INTO accounts VALUES (?,?,?)", (username, generate_password_hash(password), existing_id))
                    row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
                if row and check_password_hash(row["password"], password):
                    return sign_in(row["username"])
        if not account:
            check_password_hash(dummy_hash, password)
        return page("login", "Usuario o contraseña incorrectos.", 401)


    @app.route("/new.html", methods=["GET", "POST"])
    @app.route("/signup", methods=["GET", "POST"])
    @app.route("/register", methods=["GET", "POST"])
    def account_register():
        if request.method == "GET":
            return redirect(play) if current_save() else page("register")
        verify_csrf()
        if limited("register"):
            return page("register", "Demasiados intentos. Espera unos minutos.", 429)
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        if password != request.form.get("confirm"):
            return page("register", "Las contraseñas no coinciden.", 400)
        try:
            register_account(username, password, lambda: create_save(username))
        except ValueError as error:
            return page("register", str(error), 400)
        return sign_in(username)

    @app.route("/logout", methods=["POST"])
    def account_logout():
        verify_csrf()
        with game_lock, connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(),))
        session.clear()
        response = redirect(url_for("account_login"), code=303)
        response.delete_cookie(cookie_name, httponly=True, samesite="Lax", secure=secure)
        return response

    @app.cli.command("link-save")
    def link_save():
        """Create an account for an existing, unassigned save."""
        import click
        save_id = click.prompt("ID de la partida")
        if not save_exists(save_id):
            raise click.ClickException("No se encontró la partida.")
        username = click.prompt("Usuario").strip().lower()
        password = click.prompt("Contraseña", hide_input=True, confirmation_prompt=True)
        try:
            register_account(username, password, lambda: save_id, link=True)
        except ValueError as error:
            raise click.ClickException(str(error)) from error
        click.echo("Partida vinculada.")

    def protect_payload(supplied):
        # A stale tab must not be able to play the account now signed in.
        save_id = current_save()
        if not save_id:
            abort(401)
        if supplied is not None and str(supplied) != save_id:
            abort(403)
        return save_id

    return current_save, protect_payload, game_lock
