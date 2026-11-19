"""Requests and community parts shared by accepted neighbors."""

from datetime import datetime, timedelta, timezone
import re
import time
import uuid

from flask import jsonify, request

from piece_queue import DDL as PIECE_DDL, ITEMS, pending_deliveries, queue_piece


DDL = (
    """CREATE TABLE IF NOT EXISTS neighbor_aid_requests (
        id TEXT PRIMARY KEY,
        sender TEXT NOT NULL REFERENCES accounts(username),
        recipient TEXT NOT NULL REFERENCES accounts(username),
        kind TEXT NOT NULL CHECK (kind IN ('piece', 'help')),
        item TEXT NOT NULL,
        note TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('pending', 'fulfilled', 'rejected', 'canceled')),
        created BIGINT NOT NULL,
        updated BIGINT NOT NULL,
        nonce TEXT NOT NULL,
        UNIQUE (sender, nonce),
        CHECK (sender <> recipient)
    )""",
    "CREATE INDEX IF NOT EXISTS aid_sender_created ON neighbor_aid_requests(sender, created)",
    "CREATE INDEX IF NOT EXISTS aid_recipient_completed ON neighbor_aid_requests(recipient, kind, status, updated)",
    """CREATE UNIQUE INDEX IF NOT EXISTS aid_pending_request
       ON neighbor_aid_requests(sender, recipient, kind, item) WHERE status='pending'""",
    """CREATE TABLE IF NOT EXISTS neighbor_aid_inventory (
        username TEXT NOT NULL REFERENCES accounts(username),
        item TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity >= 0),
        PRIMARY KEY (username, item)
    )""",
)

CATALOGS = {
    "wars": {
        "frame": "Placa de blindaje",
        "wiring": "Cable de radio",
        "fastener": "Engranaje mecánico",
    },
    "empires": {
        "frame": "Viga de roble",
        "wiring": "Cuerda trenzada",
        "fastener": "Remache de forja",
    },
    "city": {
        "frame": "Perfil de acero",
        "wiring": "Cable eléctrico",
        "fastener": "Perno de obra",
    },
}
REDEEM_POINTS = 4
HELP_POINTS = 5
USERNAME = re.compile(r"[a-z0-9_.-]{3,32}")
NONCE = re.compile(r"[A-Za-z0-9_-]{16,64}")
REQUEST_ID = re.compile(r"[a-f0-9]{32}")
BOGOTA = timezone(timedelta(hours=-5))


def _error(message, status):
    return jsonify(error=message), status


def _day_start(now):
    day = datetime.fromtimestamp(now / 1000, BOGOTA).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int(day.timestamp()) * 1000


def _are_neighbors(db, first, second):
    return db.execute(
        "SELECT 1 FROM friendships WHERE first=? AND second=? AND accepted=1",
        tuple(sorted((first, second))),
    ).fetchone() is not None


def _credit(db, player, kind, reference, points, now):
    db.execute(
        """INSERT INTO community_ledger (username, kind, reference, amount, created)
           VALUES (?, ?, ?, ?, ?)""",
        (player, kind, reference, points, now // 1000),
    )


def _inbox(db, player, catalog, native_available):
    neighbors = [
        row["neighbor"]
        for row in db.execute(
            """SELECT second AS neighbor FROM friendships WHERE first=? AND accepted=1
               UNION ALL
               SELECT first AS neighbor FROM friendships WHERE second=? AND accepted=1
               ORDER BY neighbor""",
            (player, player),
        ).fetchall()
    ]
    active_neighbors = set(neighbors)
    rows = db.execute(
        """SELECT id, sender, recipient, kind, item, note, status, created, updated
           FROM neighbor_aid_requests WHERE sender=? OR recipient=?
           ORDER BY CASE WHEN status='pending' THEN 0 ELSE 1 END, updated DESC, id DESC
           LIMIT 60""",
        (player, player),
    ).fetchall()
    history = []
    for row in rows:
        incoming = row["recipient"] == player
        other = row["sender"] if incoming else row["recipient"]
        history.append(dict(row, incoming=incoming, active=other in active_neighbors))
    inventory = {
        row["item"]: row["quantity"]
        for row in db.execute(
            "SELECT item, quantity FROM neighbor_aid_inventory WHERE username=? AND quantity>0",
            (player,),
        ).fetchall()
    }
    return jsonify(
        neighbors=neighbors,
        catalog=[{"id": item, "label": label} for item, label in catalog.items()],
        requests=history,
        inventory=inventory,
        redeem_points=REDEEM_POINTS,
        native_available=native_available,
        pending_delivery=pending_deliveries(db, player) if native_available else 0,
    )


def _create(db, player, catalog, now):
    recipient = request.form.get("username", "").lower().strip()
    kind = request.form.get("kind", "")
    item = request.form.get("item", "") if kind == "piece" else ""
    note = " ".join(request.form.get("note", "").split())
    nonce = request.form.get("nonce") or uuid.uuid4().hex
    if (
        not USERNAME.fullmatch(recipient)
        or recipient == player
        or kind not in ("piece", "help")
        or (kind == "piece" and item not in catalog)
        or len(note) > 160
        or not NONCE.fullmatch(nonce)
    ):
        return _error("Revisa el vecino, la pieza y la nota de la solicitud.", 400)
    prior = db.execute(
        """SELECT id, recipient, kind, item, note FROM neighbor_aid_requests
           WHERE sender=? AND nonce=?""",
        (player, nonce),
    ).fetchone()
    if prior:
        if (prior["recipient"], prior["kind"], prior["item"], prior["note"]) != (recipient, kind, item, note):
            return _error("Repite el envío con una nueva solicitud.", 409)
        return jsonify(ok=True, id=prior["id"])
    if not _are_neighbors(db, player, recipient):
        return _error("Solo puedes pedir a vecinos que hayan aceptado tu amistad.", 403)
    existing = db.execute(
        """SELECT id FROM neighbor_aid_requests
           WHERE sender=? AND recipient=? AND kind=? AND item=? AND status='pending'""",
        (player, recipient, kind, item),
    ).fetchone()
    if existing:
        return _error("Ya tienes una solicitud pendiente de este tipo con ese vecino.", 409)
    count = db.execute(
        "SELECT COUNT(*) AS total FROM neighbor_aid_requests WHERE sender=? AND created>=?",
        (player, _day_start(now)),
    ).fetchone()["total"]
    if count >= 12:
        return _error("Ya enviaste las 12 solicitudes disponibles para hoy.", 409)
    rid = uuid.uuid4().hex
    db.execute(
        """INSERT INTO neighbor_aid_requests
           (id, sender, recipient, kind, item, note, status, created, updated, nonce)
           VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
        (rid, player, recipient, kind, item, note, now, now, nonce),
    )
    return jsonify(ok=True, id=rid), 201


def _fulfillment_allowed(db, entry, player, now):
    day = _day_start(now)
    sent = db.execute(
        """SELECT COUNT(*) AS total FROM neighbor_aid_requests
           WHERE recipient=? AND status='fulfilled' AND updated>=?""",
        (player, day),
    ).fetchone()["total"]
    if sent >= 12:
        return "Ya respondiste a 12 solicitudes hoy."
    if entry["kind"] == "help":
        received = db.execute(
            """SELECT COUNT(*) AS total FROM neighbor_aid_requests
               WHERE sender=? AND kind='help' AND status='fulfilled' AND updated>=?""",
            (entry["sender"], day),
        ).fetchone()["total"]
        if received >= 3:
            return "El vecino ya recibió las 3 ayudas con recompensa de hoy."
    return ""


def _resolve(db, player, action, now, native_available):
    rid = request.form.get("id", "")
    if not REQUEST_ID.fullmatch(rid):
        return _error("Solicitud no encontrada.", 404)
    entry = db.execute(
        """SELECT sender, recipient, kind, item, status FROM neighbor_aid_requests
           WHERE id=?""",
        (rid,),
    ).fetchone()
    owner_field = "sender" if action == "cancel" else "recipient"
    if not entry or entry[owner_field] != player:
        return _error("Solicitud no encontrada.", 404)
    status = {"fulfill": "fulfilled", "reject": "rejected", "cancel": "canceled"}[action]
    if entry["status"] == status:
        return jsonify(ok=True, id=rid)
    if entry["status"] != "pending":
        return _error("La solicitud ya fue resuelta.", 409)
    if action == "fulfill":
        if not _are_neighbors(db, entry["sender"], player):
            return _error("La amistad ya no está activa.", 403)
        reason = _fulfillment_allowed(db, entry, player, now)
        if reason:
            return _error(reason, 409)
    db.execute(
        "UPDATE neighbor_aid_requests SET status=?, updated=? WHERE id=?",
        (status, now, rid),
    )
    if action == "fulfill":
        if entry["kind"] == "piece":
            db.execute(
                """INSERT INTO neighbor_aid_inventory (username, item, quantity)
                   VALUES (?, ?, 1) ON CONFLICT (username, item) DO UPDATE SET
                   quantity=neighbor_aid_inventory.quantity+1""",
                (entry["sender"], entry["item"]),
            )
        else:
            _credit(db, entry["sender"], "aid-help", rid, HELP_POINTS, now)
            if native_available:
                db.execute(
                    "INSERT INTO neighbor_piece_claims VALUES (?, ?, 'support', ?, ?, 0)",
                    (rid, entry["sender"], "help-" + rid, now),
                )
    return jsonify(ok=True, id=rid)


def _redeem(db, player, catalog, now):
    item = request.form.get("item", "")
    nonce = request.form.get("nonce", "")
    if item not in catalog or not NONCE.fullmatch(nonce):
        return _error("Selecciona una pieza e inténtalo de nuevo.", 400)
    reference = f"{item}:{nonce}"
    if db.execute(
        """SELECT 1 FROM community_ledger
           WHERE username=? AND kind='aid-redeem' AND reference=?""",
        (player, reference),
    ).fetchone():
        return jsonify(ok=True)
    result = db.execute(
        """UPDATE neighbor_aid_inventory SET quantity=quantity-1
           WHERE username=? AND item=? AND quantity>0""",
        (player, item),
    )
    if not result.rowcount:
        return _error("No tienes esa pieza en el inventario.", 409)
    _credit(db, player, "aid-redeem", reference, REDEEM_POINTS, now)
    return jsonify(ok=True)


def install_neighbor_aid(app, connect, username, verify_csrf, persistent, limit, *, theme=None, native_available=False):
    """Register the neighbor inbox, aid actions and community part redemption."""
    key = theme or app.config.get("COMMUNITY_THEME")
    catalog = ITEMS[key] if native_available else CATALOGS.get(key, CATALOGS["city"])
    statements = DDL + (PIECE_DDL if native_available else ())
    if not persistent:
        with connect() as db:
            for statement in statements:
                db.execute(statement)

    @app.route("/social/aid", methods=["GET", "POST"])
    def social_neighbor_aid():
        player = username()
        if request.method == "GET":
            with connect() as db:
                return _inbox(db, player, catalog, native_available)
        verify_csrf()
        limit("aid:" + player)
        action = request.form.get("action", "")
        now = time.time_ns() // 1_000_000
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if action == "request":
                return _create(db, player, catalog, now)
            if action in ("fulfill", "reject", "cancel"):
                return _resolve(db, player, action, now, native_available)
            if action == "redeem":
                return _redeem(db, player, catalog, now)
            if action == "deliver" and native_available:
                item = request.form.get("item", "")
                nonce = request.form.get("nonce", "")
                if item not in catalog or not NONCE.fullmatch(nonce):
                    return _error("Selecciona una pieza e inténtalo de nuevo.", 400)
                return queue_piece(db, player, item, nonce, now)
        return _error("Acción desconocida.", 400)
