"""Deliver reserved neighbor pieces to the game's existing save format."""

from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile


_WARS_ITEMS = {"frame": "1", "wiring": "21", "fastener": "17"}
_CITY_ITEMS = {"frame": "material_brick", "wiring": "material_marble", "fastener": "material_ribbon"}
_EMPIRES_RESOURCES = {"frame": "wood", "wiring": "stone", "fastener": "food"}
_LOCAL_RECEIPTS = "_neighbor_piece_receipts"


def _increase(values, key, quantity):
    values[key] = int(values.get(key, 0)) + quantity


def _grant(save, theme, counts):
    support = counts.pop("support", 0)
    if theme in {"wars", "social-wars"}:
        items = save["privateState"].setdefault("inventoryItems", {})
        for piece, quantity in counts.items():
            _increase(items, _WARS_ITEMS[piece], quantity)
        if support:
            _increase(save["maps"][0], "wood", support * 25)
    elif theme in {"city", "cityville"}:
        inventory = save["userInfo"]["player"].setdefault("inventory", {})
        items = inventory.setdefault("items", {})
        if "count" not in inventory:
            inventory["count"] = sum(int(quantity) for quantity in items.values())
        for piece, quantity in counts.items():
            _increase(items, _CITY_ITEMS[piece], quantity)
            _increase(inventory, "count", quantity)
        if support:
            _increase(save["userInfo"]["player"], "gold", support * 25)
    elif theme in {"empires", "social-empires"}:
        resources = save["maps"][0]
        for piece, quantity in counts.items():
            _increase(resources, _EMPIRES_RESOURCES[piece], quantity * 25)
        if support:
            _increase(resources, "food", support * 25)
    else:
        raise ValueError("Unsupported theme for native piece delivery")


def _replace_json(target, data):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(
            dir=target.parent, mode="w", encoding="utf-8", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _deliver_local(save, local_root, relative_path, theme, claims):
    root = Path(local_root).resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Invalid native save path")
    try:
        with target.open(encoding="utf-8-sig") as handle:
            updated = json.load(handle)
    except FileNotFoundError:
        updated = deepcopy(save)
    prior = set(updated.get(_LOCAL_RECEIPTS, ()))
    counts = Counter(claim["item"] for claim in claims if str(claim["id"]) not in prior)
    if counts:
        _grant(updated, theme, counts)
        # The receipt travels with the save across a process crash before the
        # separate SQLite transaction can acknowledge this batch.
        updated[_LOCAL_RECEIPTS] = [str(claim["id"]) for claim in claims]
        _replace_json(target, updated)
    return updated


def deliver_native_pieces(connect, player, save, relative_path, local_root, theme, *, persistent=False):
    """Run under the game's state lock before exposing or modifying the save."""
    with connect() as db:
        if not db.execute(
            "SELECT 1 FROM neighbor_piece_claims WHERE username=? AND delivered=0 LIMIT 1",
            (player,),
        ).fetchone():
            return 0
        db.execute("BEGIN IMMEDIATE")
        claims = db.execute(
            """SELECT id,item FROM neighbor_piece_claims
               WHERE username=? AND delivered=0 ORDER BY created,id""",
            (player,),
        ).fetchall()
        if not claims:
            return 0
        if persistent:
            row = db.execute(
                "SELECT data FROM game_files WHERE path=? FOR UPDATE", (relative_path,),
            ).fetchone()
            if not row:
                return 0
            updated = deepcopy(row["data"])
            _grant(updated, theme, Counter(claim["item"] for claim in claims))
            db.execute(
                "UPDATE game_files SET data=CAST(? AS JSONB) WHERE path=?",
                (json.dumps(updated, ensure_ascii=False), relative_path),
            )
        else:
            updated = _deliver_local(save, local_root, relative_path, theme, claims)
            # Once the file is durable, mirror its receipts even if acknowledging
            # the claim in SQLite fails. A later game save must retain them.
            save.clear()
            save.update(updated)
        for claim in claims:
            db.execute(
                "UPDATE neighbor_piece_claims SET delivered=1 WHERE id=? AND username=?",
                (claim["id"], player),
            )
    if persistent:
        # The database save and claim receipt share one commit.
        save.clear()
        save.update(updated)
    return len(claims)
