"""Community events, activity rankings, bonuses and profile rewards."""
from datetime import datetime, timedelta, timezone
import re
import time
import uuid

from flask import abort, jsonify, redirect, render_template, request

DDL = (
    """CREATE TABLE IF NOT EXISTS community_events (
        id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
        starts BIGINT NOT NULL, ends BIGINT NOT NULL, points INTEGER NOT NULL,
        author TEXT NOT NULL REFERENCES accounts(username), closed INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS community_event_goals (
        event_id TEXT PRIMARY KEY REFERENCES community_events(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, target INTEGER NOT NULL, closed_at BIGINT
    )""",
    """CREATE TABLE IF NOT EXISTS community_ledger (
        username TEXT NOT NULL REFERENCES accounts(username), kind TEXT NOT NULL,
        reference TEXT NOT NULL, amount INTEGER NOT NULL, created BIGINT NOT NULL,
        PRIMARY KEY(username, kind, reference)
    )""",
    "CREATE INDEX IF NOT EXISTS community_ledger_kind ON community_ledger(kind, reference, username)",
    """CREATE TABLE IF NOT EXISTS community_codes (
        code TEXT PRIMARY KEY, points INTEGER NOT NULL, max_claims INTEGER NOT NULL,
        author TEXT NOT NULL REFERENCES accounts(username), closed INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS community_profiles (
        username TEXT PRIMARY KEY REFERENCES accounts(username), item TEXT NOT NULL
    )""",
)

ITEMS = {
    "vanguard": ("Vanguardia", 30),
    "envoy": ("Embajador", 70),
    "legend": ("Leyenda", 150),
}
BONUSES = {"daily": 10, "weekly": 25}
EVENT_GOALS = {"help", "piece"}

# The same progress calculation drives both the event view and the claim check.
EVENT_PROGRESS = """
    SELECT e.id, e.title, e.description, e.starts, e.ends, e.points, e.closed,
           g.kind, g.target, g.closed_at,
           CASE WHEN EXISTS (
             SELECT 1 FROM community_ledger l
             WHERE l.username=? AND l.kind='event' AND l.reference=e.id
           ) THEN 1 ELSE 0 END AS claimed,
           (SELECT COUNT(DISTINCT r.sender) FROM neighbor_aid_requests r
            WHERE r.recipient=? AND r.kind=g.kind AND r.status='fulfilled'
              AND r.updated >= e.starts * 1000 AND r.updated < e.ends * 1000
              AND r.updated < COALESCE(g.closed_at, e.ends) * 1000
              AND r.updated < ?) AS progress
    FROM community_events e LEFT JOIN community_event_goals g ON g.event_id=e.id
"""


def event_state(row, now):
    event = dict(row)
    kind = event.pop("kind")
    target = event.pop("target") or 1
    progress = event.pop("progress") if kind else int(bool(event["claimed"]))
    event.pop("closed_at")
    until = event["ends"] + (86400 if kind else 0)
    if event["closed"]:
        phase = "closed"
    elif now < event["starts"]:
        phase = "scheduled"
    elif now < event["ends"]:
        phase = "active"
    elif now < until:
        phase = "claim"
    else:
        phase = "finished"
    return {
        **event,
        "goal": {"kind": kind or "checkin", "target": target, "progress": progress},
        "phase": phase,
        "claim_until": until,
        "claimable": phase in {"active", "claim"} and not event["claimed"] and (not kind or progress >= target),
    }


def periods(now):
    date = datetime.fromtimestamp(now, timezone(timedelta(hours=-5))).date()
    return {"daily": date.isoformat(), "weekly": (date - timedelta(days=date.weekday())).isoformat()}


def bounded(form, key, minimum, maximum):
    raw = form.get(key, "")
    if re.fullmatch(r"[0-9]{1,5}", raw):
        value = int(raw)
        if minimum <= value <= maximum:
            return value
    abort(400)


def install_activities(app, connect, username, is_admin, verify_csrf, persistent, limit):
    if not persistent:
        with connect() as db:
            for statement in DDL:
                db.execute(statement)

    def credit(db, player, kind, reference, amount, now):
        result = db.execute(
            "INSERT INTO community_ledger VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            (player, kind, reference, amount, now),
        )
        return result.rowcount == 1

    def balance(db, player):
        return db.execute(
            "SELECT COALESCE(SUM(amount), 0) AS balance FROM community_ledger WHERE username=?",
            (player,),
        ).fetchone()["balance"]

    @app.get("/social/events")
    def community_events():
        player = username()
        now = int(time.time())
        with connect() as db:
            rows = db.execute(
                EVENT_PROGRESS + " ORDER BY e.starts DESC, e.id DESC LIMIT 30",
                (player, player, (now + 1) * 1000),
            ).fetchall()
        return jsonify(events=[event_state(row, now) for row in rows], now=now)

    @app.get("/social/rankings")
    def community_rankings():
        username()
        event = request.args.get("event", "")[:32]
        with connect() as db:
            goal = db.execute(
                """SELECT g.kind, g.closed_at, e.starts, e.ends
                   FROM community_event_goals g JOIN community_events e ON e.id=g.event_id
                   WHERE g.event_id=?""", (event,),
            ).fetchone() if event else None
            if goal:
                upper = min(goal["ends"], goal["closed_at"] or goal["ends"], int(time.time()) + 1)
                ranking = db.execute(
                    """SELECT recipient AS username, COUNT(DISTINCT sender) AS score
                       FROM neighbor_aid_requests WHERE kind=? AND status='fulfilled'
                         AND updated>=? AND updated<?
                       GROUP BY recipient ORDER BY score DESC, MIN(updated), username LIMIT 30""",
                    (goal["kind"], goal["starts"] * 1000, upper * 1000),
                ).fetchall()
            elif event:
                ranking = db.execute(
                    """SELECT username, amount AS score FROM community_ledger
                       WHERE kind='event' AND reference=? ORDER BY amount DESC, created, username LIMIT 30""",
                    (event,),
                ).fetchall()
            else:
                ranking = db.execute(
                    """SELECT username, SUM(amount) AS score FROM community_ledger
                       WHERE amount>0 GROUP BY username ORDER BY score DESC, username LIMIT 30"""
                ).fetchall()
        return jsonify(players=[dict(row) for row in ranking], metric=goal["kind"] if goal else "points")

    @app.get("/social/rewards")
    def community_rewards():
        player = username()
        today = periods(int(time.time()))
        with connect() as db:
            entries = db.execute(
                "SELECT kind, reference FROM community_ledger WHERE username=? AND kind IN ('daily','weekly','shop')",
                (player,),
            ).fetchall()
            claims = {(row["kind"], row["reference"]) for row in entries}
            profile = db.execute("SELECT item FROM community_profiles WHERE username=?", (player,)).fetchone()
            points = balance(db, player)
        return jsonify(points=points, bonuses=[
            {"kind": kind, "points": amount, "claimed": (kind, today[kind]) in claims}
            for kind, amount in BONUSES.items()
        ], items=[
            {"id": key, "title": title, "cost": cost, "owned": ("shop", key) in claims}
            for key, (title, cost) in ITEMS.items()
        ], equipped=profile["item"] if profile else "")

    @app.post("/social/rewards")
    def community_reward_action():
        player = username()
        verify_csrf()
        limit("reward:" + player)
        kind = request.form.get("kind", "")
        reference = request.form.get("reference", "")[:32]
        now = int(time.time())
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if kind in BONUSES:
                applied = credit(db, player, kind, periods(now)[kind], BONUSES[kind], now)
            elif kind == "event":
                row = db.execute(
                    EVENT_PROGRESS + " WHERE e.id=?",
                    (player, player, (now + 1) * 1000, reference),
                ).fetchone()
                if not row:
                    return jsonify(error="No se encontró ese evento."), 404
                event = event_state(row, now)
                if event["claimed"]:
                    return jsonify(error="Ya reclamaste esta recompensa."), 409
                if event["phase"] not in {"active", "claim"}:
                    return jsonify(error="Este evento no está abierto para reclamar."), 409
                if not event["claimable"]:
                    return jsonify(error="Completa el objetivo antes de reclamar el premio."), 409
                applied = credit(db, player, kind, reference, event["points"], now)
            elif kind == "code":
                reference = reference.upper()
                code = db.execute(
                    """SELECT c.points FROM community_codes c WHERE c.code=? AND c.closed=0 AND
                       (SELECT COUNT(*) FROM community_ledger l WHERE l.kind='code' AND l.reference=c.code)<c.max_claims""",
                    (reference,),
                ).fetchone()
                if not code:
                    return jsonify(error="El código no está activo o ya alcanzó su límite."), 409
                applied = credit(db, player, kind, reference, code["points"], now)
            elif kind == "shop":
                if reference not in ITEMS:
                    abort(404)
                cost = ITEMS[reference][1]
                if balance(db, player) < cost:
                    return jsonify(error="Te faltan puntos de comunidad."), 409
                applied = credit(db, player, kind, reference, -cost, now)
            elif kind == "equip":
                if reference and not db.execute(
                    "SELECT 1 FROM community_ledger WHERE username=? AND kind='shop' AND reference=?",
                    (player, reference),
                ).fetchone():
                    abort(403)
                db.execute(
                    """INSERT INTO community_profiles VALUES (?, ?)
                       ON CONFLICT(username) DO UPDATE SET item=excluded.item""", (player, reference),
                )
                applied = True
            else:
                abort(400)
            if not applied:
                return jsonify(error="Ya reclamaste esta recompensa."), 409
        return jsonify(ok=True)

    @app.route("/admin/actividades", methods=["GET", "POST"])
    def community_activity_admin():
        if not is_admin():
            abort(403)
        if request.method == "POST":
            verify_csrf()
            player = username()
            limit("activity-admin:" + player)
            form = request.form
            action = form.get("action")
            now = int(time.time())
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                if action == "event":
                    title, description = form.get("title", "").strip(), form.get("description", "").strip()
                    if not 3 <= len(title) <= 80 or len(description) > 500:
                        abort(400)
                    starts = now + bounded(form, "delay", 0, 720) * 3600
                    ends = starts + bounded(form, "hours", 1, 720) * 3600
                    points = bounded(form, "points", 1, 1000)
                    goal = form.get("goal_kind", "checkin")
                    if goal not in EVENT_GOALS | {"checkin"}:
                        abort(400)
                    event_id = uuid.uuid4().hex
                    db.execute(
                        "INSERT INTO community_events VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                        (event_id, title, description, starts, ends, points, player),
                    )
                    if goal != "checkin":
                        db.execute("INSERT INTO community_event_goals VALUES (?, ?, ?, NULL)",
                                   (event_id, goal, bounded(form, "goal_target", 1, 50)))
                elif action == "close_event":
                    event_id = form.get("id", "")[:32]
                    db.execute("UPDATE community_events SET closed=1 WHERE id=?", (event_id,))
                    db.execute(
                        "UPDATE community_event_goals SET closed_at=? WHERE event_id=? AND closed_at IS NULL",
                        (now + 1, event_id),
                    )
                elif action == "code":
                    code = form.get("code", "").strip().upper()
                    if not re.fullmatch(r"[A-Z0-9_-]{4,24}", code):
                        abort(400)
                    result = db.execute(
                        "INSERT INTO community_codes VALUES (?, ?, ?, ?, 0) ON CONFLICT DO NOTHING",
                        (code, bounded(form, "points", 1, 1000), bounded(form, "uses", 1, 10000), player),
                    )
                    if result.rowcount != 1:
                        abort(409)
                elif action == "gift":
                    recipient = form.get("recipient", "").strip().lower()[:32]
                    if not db.execute("SELECT 1 FROM accounts WHERE username=?", (recipient,)).fetchone():
                        abort(404)
                    reference = player + ":" + uuid.uuid4().hex
                    credit(db, recipient, "gift", reference, bounded(form, "points", 1, 1000), now)
                elif action == "close_code":
                    db.execute("UPDATE community_codes SET closed=1 WHERE code=?", (form.get("code", "")[:24],))
                else:
                    abort(400)
            return redirect("/admin/actividades", code=303)
        query = request.args.get("q", "").strip().lower()[:32]
        prefix = query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        with connect() as db:
            players = db.execute(
                "SELECT username FROM accounts WHERE username LIKE ? ESCAPE '!' ORDER BY username LIMIT 20",
                (prefix,),
            ).fetchall() if query else []
            events = db.execute(
                """SELECT e.id, e.title, e.points, e.closed, g.kind, g.target
                   FROM community_events e LEFT JOIN community_event_goals g ON e.id=g.event_id
                   ORDER BY e.starts DESC LIMIT 50"""
            ).fetchall()
            codes = db.execute("SELECT code, points, max_claims, closed FROM community_codes ORDER BY code LIMIT 50").fetchall()
        return render_template("community_activities_admin.html", events=events, codes=codes, players=players, query=query)

    def profile_title(db, player):
        row = db.execute("SELECT item FROM community_profiles WHERE username=?", (player,)).fetchone()
        return ITEMS.get(row["item"], ("", 0))[0] if row else ""

    return profile_title
