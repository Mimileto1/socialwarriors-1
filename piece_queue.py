"""Queues transfers from the community piece inventory to a game save."""
import uuid

from flask import jsonify

DDL = (
    """CREATE TABLE IF NOT EXISTS neighbor_piece_claims (
        id TEXT PRIMARY KEY, username TEXT NOT NULL REFERENCES accounts(username),
        item TEXT NOT NULL, nonce TEXT NOT NULL, created BIGINT NOT NULL,
        delivered INTEGER NOT NULL DEFAULT 0 CHECK (delivered IN (0,1)),
        UNIQUE(username, nonce)
    )""",
    "CREATE INDEX IF NOT EXISTS pending_piece_claims ON neighbor_piece_claims(username, delivered, created)",
)

ITEMS = {
    "wars": {"frame": "Cemento", "wiring": "Cable", "fastener": "Tabla"},
    "empires": {"frame": "Madera ×25", "wiring": "Piedra ×25", "fastener": "Comida ×25"},
    "city": {"frame": "Ladrillo", "wiring": "Mármol", "fastener": "Cinta"},
}


def pending_deliveries(db, player):
    return db.execute(
        "SELECT COUNT(*) AS total FROM neighbor_piece_claims WHERE username=? AND delivered=0",
        (player,),
    ).fetchone()["total"]


def queue_piece(db, player, item, nonce, now):
    existing = db.execute(
        "SELECT item FROM neighbor_piece_claims WHERE username=? AND nonce=?", (player, nonce)
    ).fetchone()
    if existing:
        if existing["item"] != item:
            return jsonify(error="Vuelve a seleccionar la pieza."), 409
        return jsonify(ok=True)
    if pending_deliveries(db, player) >= 30:
        return jsonify(error="Vuelve a abrir tu partida para recibir tus piezas pendientes."), 409
    changed = db.execute(
        """UPDATE neighbor_aid_inventory SET quantity=quantity-1
           WHERE username=? AND item=? AND quantity>0""",
        (player, item),
    )
    if changed.rowcount != 1:
        return jsonify(error="No tienes esa pieza en el inventario."), 409
    db.execute(
        "INSERT INTO neighbor_piece_claims VALUES (?, ?, ?, ?, ?, 0)",
        (uuid.uuid4().hex, player, item, nonce, now),
    )
    return jsonify(ok=True)
