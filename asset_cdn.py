import json
from pathlib import Path

from flask import redirect


manifest = Path(__file__).with_name("asset_cdn.json")
asset_urls = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}


def asset_redirect(path):
    url = asset_urls.get(path)
    if url is None:
        return None
    response = redirect(url, code=302)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response
