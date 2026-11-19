"""Alliance membership and community moderation."""
import os
import re
import time
import uuid

from flask import abort, jsonify, redirect, render_template, request

DDL = (
    """CREATE TABLE IF NOT EXISTS alliances (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
        leader TEXT NOT NULL UNIQUE REFERENCES accounts(username)
    )""",
    """CREATE TABLE IF NOT EXISTS alliance_members (
        username TEXT PRIMARY KEY REFERENCES accounts(username),
        alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS alliance_members_group ON alliance_members(alliance_id)",
    """CREATE TABLE IF NOT EXISTS alliance_requests (
        username TEXT NOT NULL REFERENCES accounts(username),
        alliance_id TEXT NOT NULL REFERENCES alliances(id) ON DELETE CASCADE,
        PRIMARY KEY(username, alliance_id)
    )""",
    """CREATE TABLE IF NOT EXISTS hidden_chat_messages (
        message_id TEXT PRIMARY KEY REFERENCES chat_messages(id) ON DELETE CASCADE,
        moderator TEXT NOT NULL REFERENCES accounts(username), hidden_at BIGINT NOT NULL
    )""",
)


def install_community_tools(app, connect, current_account, verify_csrf, persistent, limit):
    if not persistent:
        with connect() as db:
            for statement in DDL:
                db.execute(statement)

    admins = {name.strip().lower() for name in os.environ.get("GAME_ADMIN_USERS", "").split(",") if name.strip()}

    def is_admin():
        account = current_account()
        return bool(account and account["username"] in admins)

    app.jinja_env.globals["community_is_admin"] = is_admin

    def username():
        account = current_account()
        if not account:
            abort(401)
        return account["username"]

    @app.route("/social/alliance", methods=["GET", "POST"])
    def social_alliance():
        player = username()
        if request.method == "GET":
            with connect() as db:
                group = db.execute(
                    """SELECT a.id, a.name, a.leader FROM alliances a JOIN alliance_members m
                       ON m.alliance_id=a.id WHERE m.username=?""", (player,)
                ).fetchone()
                members = db.execute(
                    "SELECT username FROM alliance_members WHERE alliance_id=? ORDER BY username",
                    (group["id"],),
                ).fetchall() if group else []
                pending = db.execute(
                    "SELECT username FROM alliance_requests WHERE alliance_id=? ORDER BY username",
                    (group["id"],),
                ).fetchall() if group and group["leader"] == player else []
                directory = db.execute(
                    """SELECT a.id, a.name, CASE WHEN EXISTS (
                       SELECT 1 FROM alliance_requests r WHERE r.alliance_id=a.id AND r.username=?
                       ) THEN 1 ELSE 0 END AS pending FROM alliances a
                       WHERE a.slug LIKE ? ESCAPE '!' ORDER BY a.slug LIMIT 30""",
                    (player, request.args.get("q", "").casefold()[:36].replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"),
                ).fetchall() if not group else []
            return jsonify(alliance=dict(group) if group else None, player=player,
                           members=[r["username"] for r in members], pending=[r["username"] for r in pending],
                           directory=[dict(r) for r in directory])

        verify_csrf()
        limit("alliance:" + player)
        action = request.form.get("action")
        group_id = request.form.get("alliance_id", "")[:40]
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            member = db.execute(
                """SELECT a.id, a.leader FROM alliance_members m JOIN alliances a
                   ON a.id=m.alliance_id WHERE m.username=?""", (player,)
            ).fetchone()
            if action == "create":
                name = " ".join(request.form.get("name", "").split())
                if member or not re.fullmatch(r"[\w -]{3,36}", name):
                    return jsonify(error="Escribe un nombre válido de 3 a 36 caracteres y sal de tu alianza actual si tienes una."), 400
                if db.execute("SELECT 1 FROM alliances WHERE slug=?", (name.casefold(),)).fetchone():
                    return jsonify(error="Ese nombre ya está en uso."), 409
                group_id = uuid.uuid4().hex
                db.execute("INSERT INTO alliances VALUES (?, ?, ?, ?)", (group_id, name, name.casefold(), player))
                db.execute("INSERT INTO alliance_members VALUES (?, ?)", (player, group_id))
                db.execute("DELETE FROM alliance_requests WHERE username=?", (player,))
            elif action in {"request", "cancel"}:
                if member or not db.execute("SELECT 1 FROM alliances WHERE id=?", (group_id,)).fetchone():
                    return jsonify(error="La alianza no está disponible."), 409
                if action == "request":
                    db.execute("INSERT INTO alliance_requests VALUES (?, ?) ON CONFLICT DO NOTHING", (player, group_id))
                else:
                    db.execute("DELETE FROM alliance_requests WHERE username=? AND alliance_id=?", (player, group_id))
            elif action in {"accept", "reject"}:
                candidate = request.form.get("username", "")[:32]
                if not member or member["leader"] != player:
                    abort(403)
                gid = member["id"]
                result = db.execute("DELETE FROM alliance_requests WHERE username=? AND alliance_id=?", (candidate, gid))
                if result.rowcount != 1:
                    return jsonify(error="La solicitud ya no está disponible."), 404
                if action == "accept":
                    db.execute("INSERT INTO alliance_members VALUES (?, ?) ON CONFLICT DO NOTHING", (candidate, gid))
                    db.execute("DELETE FROM alliance_requests WHERE username=?", (candidate,))
            elif action == "leave":
                if not member:
                    return jsonify(error="No perteneces a una alianza."), 409
                if member["leader"] == player:
                    if db.execute("SELECT 1 FROM alliance_members WHERE alliance_id=? AND username<>?", (member["id"], player)).fetchone():
                        return jsonify(error="El líder debe transferir el liderazgo antes de salir."), 409
                    db.execute("DELETE FROM alliances WHERE id=?", (member["id"],))
                else:
                    db.execute("DELETE FROM alliance_members WHERE username=?", (player,))
            elif action == "transfer":
                candidate = request.form.get("username", "")[:32]
                if not member or member["leader"] != player:
                    abort(403)
                if not db.execute("SELECT 1 FROM alliance_members WHERE username=? AND alliance_id=?", (candidate, member["id"])).fetchone():
                    return jsonify(error="Elige a un integrante de la alianza."), 400
                db.execute("UPDATE alliances SET leader=? WHERE id=?", (candidate, member["id"]))
            else:
                abort(400)
        return jsonify(ok=True)

    @app.get("/social/profile")
    def social_profile():
        player = username()
        with connect() as db:
            count = db.execute(
                "SELECT COUNT(*) AS total FROM friendships WHERE accepted=1 AND (first=? OR second=?)",
                (player, player),
            ).fetchone()["total"]
            group = db.execute(
                "SELECT a.name FROM alliances a JOIN alliance_members m ON m.alliance_id=a.id WHERE m.username=?",
                (player,),
            ).fetchone()
        return jsonify(username=player, neighbors=count, alliance=group["name"] if group else None)

    @app.route("/admin", methods=["GET", "POST"])
    def community_admin():
        if not is_admin():
            abort(403)
        if request.method == "POST":
            verify_csrf()
            actor = username()
            limit("mod:" + actor)
            message = request.form.get("message", "")[:32]
            action = request.form.get("action")
            with connect() as db:
                if action == "hide":
                    db.execute(
                        """INSERT INTO hidden_chat_messages SELECT id, ?, ? FROM chat_messages
                           WHERE id=? ON CONFLICT DO NOTHING""",
                        (actor, int(time.time()), message),
                    )
                elif action == "restore":
                    db.execute("DELETE FROM hidden_chat_messages WHERE message_id=?", (message,))
                else:
                    abort(400)
            return redirect("/admin", code=303)
        with connect() as db:
            messages = db.execute(
                """SELECT m.id, m.author, m.body, h.moderator FROM chat_messages m
                   LEFT JOIN hidden_chat_messages h ON h.message_id=m.id
                   ORDER BY m.created DESC, m.id DESC LIMIT 100"""
            ).fetchall()
            players = db.execute("SELECT COUNT(*) AS total FROM accounts").fetchone()["total"]
            alliances = db.execute("SELECT COUNT(*) AS total FROM alliances").fetchone()["total"]
        return render_template("community_admin.html", messages=messages, players=players, alliances=alliances)
