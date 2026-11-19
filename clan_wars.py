"""Tactical alliance wars with locked rosters and durable deployments."""

from collections import defaultdict
import re
import time
from uuid import uuid4

from flask import jsonify, request


ROUND_SECONDS = 24 * 60 * 60
ROUNDS = 3
CHALLENGE_SECONDS = 2 * ROUND_SECONDS
DEPLOYMENT_COST = 2
SECTORS = ("north", "center", "south")
SIDES = ("attacker", "defender")

DDL = (
    """CREATE TABLE IF NOT EXISTS clan_wars (
        id TEXT PRIMARY KEY,
        attacker_id TEXT NOT NULL,
        defender_id TEXT NOT NULL,
        attacker_name TEXT NOT NULL,
        defender_name TEXT NOT NULL,
        state TEXT NOT NULL CHECK (state IN ('pending','accepted','declined','canceled')),
        requested_at BIGINT NOT NULL,
        expires_at BIGINT NOT NULL,
        starts_at BIGINT,
        ends_at BIGINT,
        deployment_cap INTEGER,
        CHECK (attacker_id <> defender_id)
    )""",
    "CREATE INDEX IF NOT EXISTS clan_wars_attacker ON clan_wars(attacker_id, state, ends_at)",
    "CREATE INDEX IF NOT EXISTS clan_wars_defender ON clan_wars(defender_id, state, ends_at)",
    """CREATE TABLE IF NOT EXISTS clan_war_roster (
        war_id TEXT NOT NULL REFERENCES clan_wars(id) ON DELETE CASCADE,
        username TEXT NOT NULL,
        side TEXT NOT NULL CHECK (side IN ('attacker','defender')),
        PRIMARY KEY(war_id, username)
    )""",
    """CREATE TABLE IF NOT EXISTS clan_war_deployments (
        war_id TEXT NOT NULL,
        username TEXT NOT NULL,
        round_number INTEGER NOT NULL CHECK (round_number BETWEEN 1 AND 3),
        side TEXT NOT NULL CHECK (side IN ('attacker','defender')),
        sector TEXT NOT NULL CHECK (sector IN ('north','center','south')),
        PRIMARY KEY(war_id, username, round_number),
        FOREIGN KEY(war_id,username) REFERENCES clan_war_roster(war_id,username) ON DELETE CASCADE
    )""",
    "CREATE INDEX IF NOT EXISTS clan_war_deployment_order ON clan_war_deployments(war_id, round_number, side)",
)


def _error(message, status=409):
    return jsonify(error=message), status


def _valid_id(value):
    return bool(re.fullmatch(r"[a-f0-9]{32}", value))


def _wallet(db, player):
    row = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS points FROM community_ledger WHERE username=?",
        (player,),
    ).fetchone()
    return row["points"]


def _member(db, player):
    return db.execute(
        """SELECT a.id, a.name, a.leader FROM alliances a JOIN alliance_members m
           ON a.id=m.alliance_id WHERE m.username=?""",
        (player,),
    ).fetchone()


def _ongoing(db, alliance_id, now):
    return db.execute(
        """SELECT * FROM clan_wars WHERE state='accepted' AND ends_at>?
           AND (attacker_id=? OR defender_id=?) ORDER BY ends_at LIMIT 1""",
        (now, alliance_id, alliance_id),
    ).fetchone()


def _names(war):
    return {"id": war["id"], "attacker": war["attacker_name"], "defender": war["defender_name"]}


def _result(war, now, counts):
    all_rounds = []
    score = dict.fromkeys(SIDES, 0)
    completed_rounds = max(0, min(ROUNDS, (now - war["starts_at"]) // ROUND_SECONDS))
    for round_number in range(1, completed_rounds + 1):
        side_totals = {
            side: {sector: counts.get((round_number, side, sector), 0) for sector in SECTORS}
            for side in SIDES
        }
        for sector in SECTORS:
            attackers, defenders = (side_totals[side][sector] for side in SIDES)
            if attackers > defenders:
                score["attacker"] += 1
            elif defenders > attackers:
                score["defender"] += 1
        all_rounds.append({"round": round_number, **side_totals})
    return score, all_rounds


def _counts_for(db, wars):
    counts = defaultdict(dict)
    if wars:
        placeholders = ",".join("?" for _ in wars)
        for row in db.execute(
            f"""SELECT war_id, round_number, side, sector, COUNT(*) AS total
                FROM clan_war_deployments WHERE war_id IN ({placeholders})
                GROUP BY war_id, round_number, side, sector""",
            tuple(war["id"] for war in wars),
        ).fetchall():
            counts[row["war_id"]][(row["round_number"], row["side"], row["sector"])] = row["total"]
    return counts


def _panel(db, player, member, now, points):
    alliance_id = member["id"]
    leader = member["leader"] == player
    ongoing = _ongoing(db, alliance_id, now)
    finished = db.execute(
        """SELECT * FROM clan_wars WHERE state='accepted' AND ends_at<=?
           AND (attacker_id=? OR defender_id=?) ORDER BY ends_at DESC, id DESC LIMIT 10""",
        (now, alliance_id, alliance_id),
    ).fetchall()
    counts = _counts_for(db, [*finished, *([ongoing] if ongoing else [])])
    history = []
    for war in finished:
        score, _ = _result(war, now, counts[war["id"]])
        winner = "draw" if score["attacker"] == score["defender"] else max(score, key=score.get)
        history.append({**_names(war), "ends_at": war["ends_at"], "score": score, "winner": winner})

    challenges = db.execute(
        """SELECT w.* FROM clan_wars w JOIN alliances a ON w.attacker_id=a.id
           JOIN alliances d ON w.defender_id=d.id
           WHERE w.state='pending' AND w.expires_at>? AND (w.attacker_id=? OR w.defender_id=?)
           ORDER BY w.expires_at, w.id""",
        (now, alliance_id, alliance_id),
    ).fetchall()
    targets = []
    if leader and not ongoing and not any(war["attacker_id"] == alliance_id for war in challenges):
        targets = db.execute(
            """SELECT a.id, a.name FROM alliances a WHERE a.id<>? AND NOT EXISTS (
                 SELECT 1 FROM clan_wars w WHERE w.state='accepted' AND w.ends_at>?
                 AND (w.attacker_id=a.id OR w.defender_id=a.id)
               ) ORDER BY a.slug, a.id LIMIT 40""",
            (alliance_id, now),
        ).fetchall()

    active = None
    if ongoing:
        war_id = ongoing["id"]
        round_number = (now - ongoing["starts_at"]) // ROUND_SECONDS + 1
        side = "attacker" if ongoing["attacker_id"] == alliance_id else "defender"
        selected = db.execute(
            "SELECT sector FROM clan_war_deployments WHERE war_id=? AND username=? AND round_number=?",
            (war_id, player, round_number),
        ).fetchone()
        roster = db.execute(
            "SELECT 1 FROM clan_war_roster WHERE war_id=? AND username=? AND side=?",
            (war_id, player, side),
        ).fetchone()
        war_counts = counts[war_id]
        score, rounds = _result(ongoing, now, war_counts)
        own_allocations = {sector: war_counts.get((round_number, side, sector), 0) for sector in SECTORS}
        can_deploy = (
            roster is not None and selected is None and points >= DEPLOYMENT_COST
            and sum(own_allocations.values()) < ongoing["deployment_cap"]
        )
        active = {
            **_names(ongoing), "starts_at": ongoing["starts_at"], "ends_at": ongoing["ends_at"],
            "round": round_number, "own_side": side, "can_deploy": can_deploy,
            "selected": selected["sector"] if selected else None, "own_allocations": own_allocations,
            "deployment_cap": ongoing["deployment_cap"], "score": score, "rounds": rounds,
        }
    return {
        "alliance": {"id": alliance_id, "name": member["name"], "leader": leader},
        "targets": [dict(target) for target in targets],
        "challenges": [
            {**_names(challenge), "incoming": challenge["defender_id"] == alliance_id,
             "expires_at": challenge["expires_at"]}
            for challenge in challenges
        ],
        "war": active, "history": history,
    }


def _challenge(db, member, target_id, now):
    alliance_id = member["id"]
    if not _valid_id(target_id) or alliance_id == target_id:
        return _error("Elige otra alianza.", 400)
    target = db.execute("SELECT id,name FROM alliances WHERE id=?", (target_id,)).fetchone()
    if not target:
        return _error("Esa alianza ya no está disponible.", 404)
    existing = db.execute(
        """SELECT id,defender_id FROM clan_wars WHERE attacker_id=? AND state='pending'
           AND expires_at>? ORDER BY expires_at DESC LIMIT 1""",
        (alliance_id, now),
    ).fetchone()
    if existing:
        if existing["defender_id"] == target_id:
            return jsonify(ok=True, war_id=existing["id"])
        return _error("Tu alianza ya tiene un desafío enviado.")
    if _ongoing(db, alliance_id, now) or _ongoing(db, target_id, now):
        return _error("Una de las alianzas está en guerra.")
    if db.execute(
        """SELECT 1 FROM clan_wars WHERE attacker_id=? AND defender_id=?
           AND state='pending' AND expires_at>?""", (target_id, alliance_id, now),
    ).fetchone():
        return _error("Esa alianza ya les envió un desafío. Acéptalo en la lista.")
    incoming = db.execute(
        """SELECT COUNT(*) AS total FROM clan_wars
           WHERE defender_id=? AND state='pending' AND expires_at>?""", (target_id, now),
    ).fetchone()["total"]
    if incoming >= 5:
        return _error("Esa alianza ya tiene cinco desafíos pendientes.")
    war_id = uuid4().hex
    db.execute(
        """INSERT INTO clan_wars
           (id,attacker_id,defender_id,attacker_name,defender_name,state,requested_at,expires_at)
           VALUES (?,?,?,?,?,'pending',?,?)""",
        (war_id, alliance_id, target_id, member["name"], target["name"], now, now + CHALLENGE_SECONDS),
    )
    return jsonify(ok=True, war_id=war_id), 201


def _activate_war(db, war, now):
    attack_id, defend_id = war["attacker_id"], war["defender_id"]
    if _ongoing(db, attack_id, now) or _ongoing(db, defend_id, now):
        return _error("Una de las alianzas está en guerra.")
    counts = {
        row["alliance_id"]: row["total"]
        for row in db.execute(
            """SELECT alliance_id,COUNT(*) AS total FROM alliance_members
               WHERE alliance_id IN (?,?) GROUP BY alliance_id""",
            (attack_id, defend_id),
        ).fetchall()
    }
    cap = min(20, counts.get(attack_id, 0), counts.get(defend_id, 0))
    if not cap:
        return _error("Una de las alianzas ya no está disponible.")
    db.execute(
        """UPDATE clan_wars SET state='accepted',starts_at=?,ends_at=?,deployment_cap=? WHERE id=?""",
        (now, now + ROUNDS * ROUND_SECONDS, cap, war["id"]),
    )
    db.execute(
        """INSERT INTO clan_war_roster(war_id,username,side)
           SELECT ?,username,CASE WHEN alliance_id=? THEN 'attacker' ELSE 'defender' END
           FROM alliance_members WHERE alliance_id IN (?,?)""",
        (war["id"], attack_id, attack_id, defend_id),
    )
    # Once either clan is occupied, its remaining invitations cannot be accepted.
    db.execute(
        """UPDATE clan_wars SET state='canceled' WHERE id<>? AND state='pending'
           AND (attacker_id IN (?,?) OR defender_id IN (?,?))""",
        (war["id"], attack_id, defend_id, attack_id, defend_id),
    )
    return jsonify(ok=True)


def _deploy(db, war, player, side, now):
    raw_round, sector = request.form.get("round", ""), request.form.get("sector", "")
    if raw_round not in {"1", "2", "3"} or sector not in SECTORS:
        return _error("Elige un sector y una ronda válidos.", 400)
    round_number = int(raw_round)
    roster = db.execute(
        "SELECT 1 FROM clan_war_roster WHERE war_id=? AND username=? AND side=?",
        (war["id"], player, side),
    ).fetchone()
    if not roster:
        return _error("Solo pueden desplegar quienes ya pertenecían a la alianza al iniciar la guerra.", 403)
    previous = db.execute(
        "SELECT sector FROM clan_war_deployments WHERE war_id=? AND username=? AND round_number=?",
        (war["id"], player, round_number),
    ).fetchone()
    if previous:
        if previous["sector"] == sector:
            return jsonify(ok=True)
        return _error("Ya desplegaste en otro sector de esta ronda.")
    if (
        war["state"] != "accepted" or now >= war["ends_at"]
        or (now - war["starts_at"]) // ROUND_SECONDS + 1 != round_number
    ):
        return _error("Esta ronda ya no está disponible. Actualiza la lista.")
    deployments = db.execute(
        """SELECT COUNT(*) AS total FROM clan_war_deployments
           WHERE war_id=? AND round_number=? AND side=?""",
        (war["id"], round_number, side),
    ).fetchone()["total"]
    if deployments >= war["deployment_cap"]:
        return _error("Tu alianza ya cubrió su cupo de despliegues de esta ronda.")
    if _wallet(db, player) < DEPLOYMENT_COST:
        return _error("Te faltan 2 puntos de comunidad para desplegar.")
    db.execute(
        """INSERT INTO community_ledger(username,kind,reference,amount,created)
           VALUES (?,'clan_war',?,?,?)""",
        (player, f"{war['id']}:{round_number}", -DEPLOYMENT_COST, now),
    )
    db.execute(
        """INSERT INTO clan_war_deployments(war_id,username,round_number,side,sector)
           VALUES (?,?,?,?,?)""",
        (war["id"], player, round_number, side, sector),
    )
    return jsonify(ok=True)


def install_clan_wars(app, connect, username, verify_csrf, persistent, limit):
    if not persistent:
        with connect() as db:
            for statement in DDL:
                db.execute(statement)

    @app.route("/social/clan-wars", methods=["GET", "POST"])
    def clan_wars():
        player = username()
        if request.method == "POST":
            verify_csrf()
            limit("clan-war:" + player)
        with connect() as db:
            if request.method == "POST":
                db.execute("BEGIN IMMEDIATE")
            now = int(time.time())
            member = _member(db, player)
            if request.method == "GET":
                points = _wallet(db, player)
                panel = _panel(db, player, member, now, points) if member else {
                    "alliance": None, "targets": [], "challenges": [], "war": None, "history": [],
                }
                return jsonify(now=now, deployment_cost=DEPLOYMENT_COST, points_balance=points, **panel)

            if not member:
                return _error("Necesitas pertenecer a una alianza.", 403)
            action = request.form.get("action", "")
            if action not in {"challenge", "accept", "decline", "cancel", "deploy"}:
                return _error("La acción no es válida.", 400)
            if action != "deploy" and member["leader"] != player:
                return _error("Solo quien lidera la alianza puede gestionar desafíos.", 403)
            if action == "challenge":
                return _challenge(db, member, request.form.get("alliance_id", ""), now)
            war_id = request.form.get("war_id", "")
            if not _valid_id(war_id):
                return _error("Ese desafío no está disponible.", 404)
            war = db.execute(
                """SELECT * FROM clan_wars WHERE id=? AND (attacker_id=? OR defender_id=?)""",
                (war_id, member["id"], member["id"]),
            ).fetchone()
            if not war:
                return _error("Ese desafío no está disponible.", 404)
            side = "attacker" if war["attacker_id"] == member["id"] else "defender"
            if action == "deploy":
                return _deploy(db, war, player, side, now)
            authorized_side = "attacker" if action == "cancel" else "defender"
            if side != authorized_side:
                return _error("La otra alianza debe decidir sobre esta solicitud.", 403)
            next_state = {"accept": "accepted", "decline": "declined", "cancel": "canceled"}[action]
            if war["state"] == next_state:
                return jsonify(ok=True)
            if war["state"] != "pending" or war["expires_at"] <= now:
                return _error("El desafío ya no está pendiente.")
            if action == "accept":
                return _activate_war(db, war, now)
            db.execute("UPDATE clan_wars SET state=? WHERE id=?", (next_state, war_id))
            return jsonify(ok=True)
