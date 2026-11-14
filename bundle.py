import sys
import os

# Bundled data (extracted to a temp dir)

TMP_BUNDLED_DIR = sys._MEIPASS if getattr(sys, 'frozen', None) else os.path.dirname(os.path.abspath(__file__))

ASSETS_DIR = os.path.join(TMP_BUNDLED_DIR, "assets")
STUB_DIR = os.path.join(TMP_BUNDLED_DIR, "stub")
TEMPLATES_DIR = os.path.join(TMP_BUNDLED_DIR, "templates")
VILLAGES_DIR = os.path.join(TMP_BUNDLED_DIR, "villages")
QUESTS_DIR = os.path.join(VILLAGES_DIR, "quest")
CONFIG_DIR = os.path.join(TMP_BUNDLED_DIR, "config")
CONFIG_PATCH_DIR = os.path.join(CONFIG_DIR, "patch")

# Not bundled data (next to server EXE)

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else TMP_BUNDLED_DIR

# ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MODS_DIR = os.path.join(BASE_DIR, "mods")
DATA_DIR = os.environ.get("GAME_DATA_DIR") or BASE_DIR
SAVES_DIR = os.path.join(DATA_DIR, "saves")
AUCTIONS_DIR = os.path.join(BASE_DIR, "auctions")