"""Private conditional responses and retry-safe chat writes."""
from hashlib import sha256
import re
import uuid

from flask import jsonify, request


def conditional_json(**fields):
    response = jsonify(**fields)
    response.cache_control.private = True
    response.cache_control.no_store = True
    response.set_etag(sha256(response.get_data()).hexdigest())
    return response.make_conditional(request)


def chat_id(username, room):
    token = request.form.get("message_id", "")
    if re.fullmatch(r"[a-f0-9]{32}", token):
        return sha256(f"{username}|{room}|{token}".encode("utf-8")).hexdigest()[:32]
    return uuid.uuid4().hex
