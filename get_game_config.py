import json
import os
import jsonpatch
import time
import datetime
import re

from bundle import MODS_DIR, CONFIG_DIR, CONFIG_PATCH_DIR

__game_config = json.load(open(os.path.join(CONFIG_DIR, "main.json"), 'r', encoding='utf-8'))

def remove_duplicate_items():
    indexes = {}
    items = __game_config["items"]
    num_duplicate = 0

    while True:
        index = 0
        duplicate = False
        for item in items:
            if item["id"] in indexes:
                del items[indexes[item["id"]]]
                indexes.clear()
                duplicate = True
                num_duplicate += 1
                break

            indexes[item["id"]] = index
            index += 1

        if duplicate:
            continue

        print(f" * Removed {num_duplicate} duplicate items.")
        break

def apply_config_patch(filename):
    patch = json.load(open(filename, 'r'))
    jsonpatch.apply_patch(__game_config, patch, in_place=True)

def patch_game_config():

    if os.path.exists(os.path.join(CONFIG_PATCH_DIR, "patches.txt")):
        with open(os.path.join(CONFIG_PATCH_DIR, "patches.txt"), "r") as f:
            lines = f.readlines()
            f.close()

        for line in lines:
            patch = line.strip()
            if patch.startswith("#"):
                continue
            if patch != "":
                patch = patch.replace(".json", "")
                patch_path = f"{CONFIG_PATCH_DIR}/{patch}.json"
                if os.path.exists(patch_path):
                    apply_config_patch(patch_path)
                    print(" * Patch applied:", patch)
                else:
                    print(" * Patch ERROR: Could not find", patch)

def modify_game_config():

    if os.path.exists(os.path.join(MODS_DIR, "mods.txt")):
        with open(os.path.join(MODS_DIR, "mods.txt"), "r") as f:
            lines = f.readlines()
            f.close()

        for line in lines:
            mod = line.strip()
            if mod.startswith("#"):
                continue
            if mod != "":
                mod = mod.replace(".json", "")
                mod_path = f"{MODS_DIR}/{mod}.json"
                if os.path.exists(mod_path):
                    apply_config_patch(mod_path)
                    print(" * Mod applied:", mod)
                else:
                    print(" * Mod ERROR: Could not find", mod)

print (" [+] Applying config patches...")
patch_game_config()

print (" [+] Applying config mods...")
modify_game_config()

print (" [+] Cleaning config duplicates...")
remove_duplicate_items()


# Spanish text for the localized player-facing config values. Asset identifiers and
# numeric/game-state fields are intentionally left untouched.
_SPANISH_PHRASES = [
    ("Rocket Fortress", "Fortaleza de cohetes"), ("Grape Field", "Campo de uvas"),
    ("Corn Field", "Campo de maíz"), ("Field Hospital", "Hospital de campaña"),
    ("Tank wheels", "Ruedas de tanque"), ("Rocket launcher", "Lanzacohetes"),
    ("Stealth Fighter", "Caza furtivo"), ("Treasure Chest", "Cofre del tesoro"),
    ("Lost Rocket", "Cohete perdido"), ("Destroyed Tank", "Tanque destruido"),
    ("Dominion Tank", "Tanque del dominio"), ("Demolition Tank", "Tanque de demolición"),
    ("Crusader Tank", "Tanque cruzado"), ("Missile Tank", "Tanque lanzamisiles"),
    ("Red Mercury Dragon", "Dragón de mercurio rojo"), ("Forge Dragon", "Dragón de la forja"),
    ("Viking Airship", "Dirigible vikingo"), ("Nebular Dragon Rider", "Jinete de dragón nebular"),
    ("Nebular Dragon Knight", "Caballero dragón nebular"), ("Nebular Bicopter", "Bicóptero nebular"),
    ("Andromeda Spaceship", "Nave espacial Andrómeda"), ("Elven Cruiser", "Crucero élfico"),
    ("Space Elf", "Elfo espacial"), ("Elf Airship", "Dirigible élfico"),
    ("Power Bot Chest", "Cofre de robot de poder"), ("Mecha Dragons Chest", "Cofre de dragones mecánicos"),
    ("Chained", "Oferta"), ("Play Dragon City", "Juega a Dragon City"),
    ("Command Center", "Centro de mando"), ("Helicopter Hangar", "Hangar de helicópteros"),
    ("Bazooka Academy", "Academia de bazucas"), ("Tank Academy", "Academia de tanques"),
    ("Wood Factory", "Fábrica de madera"), ("Oil Factory", "Fábrica de petróleo"),
    ("Steel Factory", "Fábrica de acero"), ("Gold Factory", "Fábrica de oro"),
    ("Jeep garage", "Garaje de jeeps"), ("Orc Headquarters", "Cuartel general orco"),
    ("Limited Edition", "Edición limitada"), ("Exclusive", "Exclusivo"),
    ("Aircrafts", "Aeronaves"), ("Aircraft", "Aeronave"),
    ("Village", "Aldea"), ("Defense", "Defensa"), ("Army", "Ejército"),
    ("Decorations", "Decoraciones"), ("Wonders", "Maravillas"),
    ("Fortress", "Fortaleza"), ("Bunker", "Búnker"), ("Turret", "Torreta"),
    ("Barracks", "Cuartel"), ("Academy", "Academia"), ("Hangar", "Hangar"),
    ("Factory", "Fábrica"), ("Market", "Mercado"), ("Garage", "Garaje"),
    ("Headquarters", "Cuartel general"), ("Soldiers", "Soldados"),
    ("Soldier", "Soldado"), ("Vehicles", "Vehículos"), ("Vehicle", "Vehículo"),
    ("Specials", "Especiales"), ("Special", "Especial"), ("Siege", "Asedio"),
    ("Trees", "Árboles"), ("Tree", "Árbol"), ("Flowers", "Flores"),
    ("Flower", "Flor"), ("Statues", "Estatuas"), ("Statue", "Estatua"),
    ("House", "Casa"), ("Wall", "Muralla"), ("Silo", "Silo"),
    ("Tank", "Tanque"), ("Field", "Campo"), ("Rocket", "Cohete"),
    ("Fighter", "Caza"), ("Wheels", "Ruedas"), ("Launcher", "Lanzador"),
    ("Grape", "Uva"), ("Corn", "Maíz"), ("Treasure", "Tesoro"),
    ("Chest", "Cofre"), ("Lost", "Perdido"), ("Destroyed", "Destruido"),
    ("Metallic", "Metálico"), ("Magic", "Mágico"), ("Black", "Negro"),
    ("Electric", "Eléctrico"), ("Red", "Rojo"), ("Blue", "Azul"),
    ("Bonus", "Bono"), ("Power", "Poder"), ("Advanced", "Avanzado"),
    ("Professional", "Profesional"), ("Supreme", "Supremo"),
    ("Ambush", "Emboscada"), ("Combat", "Combate"), ("Killer", "Destructor"),
    ("Bot", "Robot"), ("Ship", "Barco"), ("Airship", "Dirigible"),
    ("Viking", "Vikingo"), ("Rider", "Jinete"), ("Knight", "Caballero"),
    ("Spaceship", "Nave espacial"), ("Space", "Espacial"),
    ("Elven", "Élfico"), ("Elf", "Elfo"), ("Cruiser", "Crucero"),
    ("Scouter", "Explorador"), ("Andromeda", "Andrómeda"),
    ("Basic", "Básico"), ("Ork", "Orco"), ("Wood", "Madera"), ("Oil", "Petróleo"), ("Steel", "Acero"),
    ("Gold", "Oro"), ("Coins", "Monedas"), ("Cash", "Efectivo"),
    ("Warrior", "Guerrero"), ("Orc", "Orco"), ("Alien", "Alienígena"),
    ("Gorilla", "Gorila"), ("Elephant", "Elefante"), ("Wild", "Salvaje"),
    ("Small", "Pequeño"), ("Large", "Grande"), ("Big", "Grande"),
    ("New", "Nuevo"), ("Level", "Nivel"), ("Upgrade", "Mejora"),
    ("Build", "Construir"), ("Building", "Edificio"), ("Unit", "Unidad"),
    ("Units", "Unidades"), ("Attack", "Ataque"), ("Defense", "Defensa"),
    ("Health", "Salud"), ("Speed", "Velocidad"), ("Damage", "Daño"),
    ("Mission", "Misión"), ("Missions", "Misiones"), ("Reward", "Recompensa"),
    ("Complete", "Completar"), ("Collect", "Recolectar"), ("Collection", "Colección"),
    ("Collections", "Colecciones"), ("Research", "Investigación"),
    ("Energy", "Energía"), ("Time", "Tiempo"), ("Free", "Gratis"),
    ("Friends", "Amigos"), ("Friend", "Amigo"), ("Help", "Ayuda"),
    ("Yes", "Sí"), ("No", "No"), ("Cancel", "Cancelar"), ("Back", "Volver"),
    ("Start", "Iniciar"), ("Continue", "Continuar"), ("Buy", "Comprar"),
    ("Sell", "Vender"), ("Storage", "Almacén"), ("Warehouse", "Depósito"),
    ("Harbour", "Puerto"), ("Port", "Puerto"), ("Farm", "Granja"),
    ("Factory", "Fábrica"), ("War", "Guerra"), ("Battle", "Batalla"),
    ("Complete your collection", "Completa tu colección"),
    ("Collect your reward", "Recoge tu recompensa"),
    ("Tap to collect", "Toca para recoger"), ("Tap to build", "Toca para construir"),
    ("Resource storage", "Almacén de recursos"), ("Resource production", "Producción de recursos"),
    ("Mission accomplished", "Misión cumplida"), ("Mission failed", "Misión fallida"),
    ("Attack failed", "Ataque fallido"), ("Attack successful", "Ataque exitoso"),
    ("Find an opponent", "Buscar rival"), ("Search opponent", "Buscar rival"),
    ("Your opponent", "Tu rival"), ("Enemy village", "Aldea enemiga"),
    ("Training time", "Tiempo de entrenamiento"), ("Build time", "Tiempo de construcción"),
    ("Upgrade time", "Tiempo de mejora"), ("Not enough", "No tienes suficiente"),
    ("Not enough resources", "No tienes recursos suficientes"),
    ("Army capacity", "Capacidad del ejército"), ("Population limit", "Límite de población"),
    ("Daily bonus", "Bono diario"), ("Weekly reward", "Recompensa semanal"),
    ("Collection prize", "Premio de colección"), ("Unit collection", "Colección de unidades"),
    ("Battle result", "Resultado del combate"), ("Victory", "Victoria"), ("Defeat", "Derrota"),
    ("Loading", "Cargando"), ("Please wait", "Espera un momento"),
    ("Select", "Seleccionar"), ("Close", "Cerrar"), ("Open", "Abrir"),
    ("Upgrade building", "Mejorar edificio"), ("Train units", "Entrenar unidades"),
    ("Send troops", "Enviar tropas"), ("Mission map", "Mapa de misión"),
    ("Attack map", "Mapa de ataque"), ("Wood storage", "Almacén de madera"),
    ("Oil storage", "Almacén de petróleo"), ("Steel storage", "Almacén de acero"),
]
_SPANISH_TEXT_KEYS = {"name", "title", "description", "hint", "text", "label", "message", "achievement_desc", "goalDescription"}

def _translate_spanish_text(value):
    for english, spanish in _SPANISH_PHRASES:
        value = re.sub(r"(?<!\w)" + re.escape(english) + r"(?!\w)", spanish, value, flags=re.IGNORECASE)
    return value

def _localize_config_node(node):
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key in _SPANISH_TEXT_KEYS and isinstance(value, str):
                node[key] = _translate_spanish_text(value)
            elif isinstance(value, (dict, list)):
                _localize_config_node(value)
    elif isinstance(node, list):
        for value in node:
            _localize_config_node(value)

_localize_config_node(__game_config)

def get_game_config() -> dict:
    make_dynamic(__game_config)
    return __game_config

def game_config() -> dict:
    return get_game_config()

##########
# PLAYER #
##########

def get_xp_from_level(level: int) -> int:
    return __game_config["levels"][int(level)]["exp_required"]

def get_level_from_xp(xp: int) -> int:
    i = 0
    for lvl in __game_config["levels"]:
        if lvl["exp_required"] > int(xp):
            return i
        i += 1
    # Cap over-threshold XP at the final configured level instead of wrapping to 0.
    return max(0, len(__game_config["levels"]) - 1)

#########
# ITEMS #
#########

# ID

items_dict_id_to_items_index = {int(item["id"]): i for i, item in enumerate(__game_config["items"])}

def get_item_from_id(id: int) -> dict:
    items_index = items_dict_id_to_items_index[int(id)] if int(id) in items_dict_id_to_items_index else None
    return __game_config["items"][items_index] if items_index is not None else None

def get_attribute_from_item_id(id: int, attribute_name: str) -> str:
    item = get_item_from_id(id)
    return item[attribute_name] if item and attribute_name in item else None

def get_name_from_item_id(id: int) -> str:
    return get_attribute_from_item_id(id, "name")

# subcat_functional

items_dict_subcat_functional_to_items_index = {int(item["subcat_functional"]): i for i, item in enumerate(__game_config["items"])}

def get_item_from_subcat_functional(subcat_functional: int) -> dict:
    items_index = items_dict_subcat_functional_to_items_index[int(subcat_functional)] if int(subcat_functional) in items_dict_subcat_functional_to_items_index else None
    return __game_config["items"][items_index] if items_index is not None else None

#########
# GOALS #
#########

goals_id_to_goals_index = {int(item["id"]): i for i, item in enumerate(__game_config["goals"])}

def get_goal_from_id(id: int) -> dict:
    items_index = goals_id_to_goals_index[int(id)] if int(id) in goals_id_to_goals_index else None
    return __game_config["goals"][items_index] if items_index is not None else None

def get_attribute_from_goal_id(id: int, attribute_name: str) -> str:
    goal = get_goal_from_id(id)
    return goal[attribute_name] if goal and attribute_name in goal else None

###################
# INVENTORY ITEMS #
###################

def get_inventory_item_name(item: int):
    itemstr = str(item)
    items = __game_config["inventory_items"]
    if itemstr in items:
        return items[itemstr]["name"]
    return None

def get_collection_name(collection: int):
    index = max(0, collection - 1)
    collections = __game_config["collections"]
    if index < len(collections):
        return collections[index]["name"]
    return None

def get_collection_prize(collection: int):
    index = max(0, collection - 1)
    collections = __game_config["collections"]
    if index < len(collections):
        return json.loads(collections[index]["prize"])
    return None

###################
# PREMIUM ACCOUNT #
###################

def get_premium_days(package_index: int):
    packages = __game_config["globals"]["PREMIUM_ACCOUNTS"]
    index = package_index
    if index >= len(packages):
        index = len(packages) - 1
    package = packages[index]
    if "time" in package:
        return package["time"]
    return 0

################################
# WEEKLY REWARD (MONDAY BONUS) #
################################

def get_weekly_reward_length() -> int:
    # This would be better if it was called at the start, instead of being calculated every time
    rewards = __game_config["globals"]["MONDAY_BONUS_REWARDS"]
    length = 1
    for reward in rewards:
        value = reward["value"]
        if type(value) == list:
            length = max(length, len(value))

    return length

#######################
# MAKE CONFIG DYNAMIC #
#######################

def timestamp_now():
    return int(time.time())

def make_dynamic(config):
    # darts
    if "darts_items" in config:
        # 0 no debug
        # 1 debug wrap dates
        # 2 debug all start dates and prizes
        # 3 debug everything
        debug = 0

        # grab start date of last item as it is used as the wrap point
        darts_items = config["darts_items"]
        last_game = darts_items[-1]
        ts_last = time.mktime(datetime.datetime.strptime(last_game["start_date"], "%Y-%m-%d %H:%M:%S").timetuple())
        ts_now = timestamp_now()

        # this has to be a loop because working with dates is stupid, and this ensures correct wrapping
        last_ts = ts_last
        wraps = 0
        while ts_now >= last_ts:
            last_ts = update_darts(darts_items, last_ts, 0, ts_now, debug - 1)
            wraps += 1
            if debug > 0:
                next_wrap = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M:%S")
                print(f"[DEBUG] Next darts date wrap is on {next_wrap}")

        if wraps > 0:
            print(f"[CONFIG] Darts minigame is now dynamic again! - Wrapped {wraps} time(s)!")

# updates darts start dates
def update_darts(darts_items, ts_first, seconds, ts_now, debug = 0):
    week_length = 604800
    shift = seconds
    last_ts = 0
    for game in darts_items:
        # we ignore the date in config and just rebuild dates based on first date in config starting on monday
        ts = time.mktime(datetime.datetime.strptime(game["start_date"], "%Y-%m-%d %H:%M:%S").timetuple())
        new_date = datetime.datetime.fromtimestamp(ts_first + shift)

        # account for daylight savings
        if new_date.hour == 23:
            shift += 3600
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif new_date.hour == 1:
            shift -= 3600
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
            
        # fix to nearest monday
        weekday = new_date.isoweekday()
        if weekday == 2:
            shift -= 86400
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif weekday == 3:
            shift -= 86400 * 2
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif weekday == 4:
            shift -= 86400 * 3
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif weekday == 5:
            shift += 86400 * 3
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif weekday == 6:
            shift += 86400 * 2
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)
        elif weekday == 7:
            shift += 86400
            new_date = datetime.datetime.fromtimestamp(ts_first + shift)

        weekday = new_date.isoweekday()
        new_date = new_date.strftime("%Y-%m-%d %H:%M:%S")
        if debug >= 1:
            test = game["start_date"]
            
            # output minor prizes
            if debug >= 2:
                game_id = game["id"]
                print(f"Darts minigame ID: {game_id}")

                idx = 1
                for unit in game["items"]:
                    item_id = int(unit)
                    item = get_item_from_id(item_id)
                    if item:
                        item_name = item["name"]
                    else:
                        item_name = "INVALID UNIT"

                    print(f"[DEBUG] Minor Prize {idx} = ({item_id}) {item_name}")
                    idx += 1

            # output major prize and date change
            major_prize = int(game["extra_item"])
            item = get_item_from_id(major_prize)
            item_name = "INVALID MAJOR PRIZE"
            if item:
                item_name = item["name"]

            print(f"[DEBUG] {test} -> {new_date} (weekday = {weekday}) -> ({major_prize}) {item_name}")

        game["start_date"] = new_date

        # make sure each one lasts exactly 7 days from first one
        last_ts = ts_first + shift
        shift += week_length

    return last_ts

make_dynamic(__game_config)
