from sessions import session, neighbors, neighbor_session
from engine import timestamp_now, reset_stuff

def get_player_info(USERID, neighbor_ids=()):
    # Update last logged in
    ts_now = timestamp_now()
    session(USERID)["playerInfo"]["last_logged_in"] = ts_now
    # Reset things as some things are taken care of by the server side
    reset_stuff(session(USERID))
    # player
    player_info = {
        "result": "ok",
        "processed_errors": 0,
        "timestamp": ts_now,
        "playerInfo": session(USERID)["playerInfo"],
        "map": session(USERID)["maps"][0],
        "privateState": session(USERID)["privateState"],
        "neighbors": neighbors(USERID, neighbor_ids)
    }
    
    return player_info

def get_neighbor_info(userid, map_number):
    _session = neighbor_session(userid)
    if not _session:
        print(f"USERID {userid} not found.")
        return ""
    if "playerInfo" not in _session or "maps" not in _session or "privateState" not in _session:
        print(f"USERID {userid} not found.")
        return ""
    maps = _session["maps"]
    _map_number = 0 if map_number is None else int(map_number)
    if not 0 <= _map_number < len(maps):
        return ""
    neighbor_info = {
        "result": "ok",
        "processed_errors": 0,
        "timestamp": timestamp_now(),
        "playerInfo": _session["playerInfo"],
        "map": maps[_map_number],
        "privateState": {} if session(userid) is not None else _session["privateState"]
    }
    return neighbor_info
