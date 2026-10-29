# API WebSocket pour les systemes graphiques (habillage TV...) :
#
#   ws://<adresse-du-poste>:8080/ws
#
# Protocole (messages JSON, voir docs/websocket.md et docs/websocket_exemple.json) :
#   serveur -> client
#     {"type": "snapshot", "matches": [match, ...]}   a la connexion et sur demande
#     {"type": "match", "match": match}                un match a change (etat complet)
#     {"type": "match_deleted", "id": 12}              un match a ete supprime
#   client -> serveur
#     {"type": "snapshot"}                             renvoyer l'instantane complet
#     {"type": "subscribe", "match_id": 12}            ne recevoir que ce match
#     {"type": "subscribe", "match_id": null}          recevoir de nouveau tous les matchs
#
# Chaque message "match" contient l'etat COMPLET du match (pas une
# difference) : le client remplace simplement ce qu'il avait pour ce match.
# Arborescence simple : le match (infos + etat du jeu) et ses 2 equipes, dont
# chaque ligne est prete a afficher (service, jeux de chaque set, petit chiffre
# du tie-break, points 15/30/40/AD, balles de break/set/match) : aucun calcul
# de tennis cote graphiques.

import asyncio
import json
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect
from nicegui import app

import database
from countries import country_name, flag_iso
from events import match_scored, players_changed, tournaments_changed
from layout import FLAGS_URL
from logos import LOGOS
from models import (
    BACKHANDS,
    CATEGORY_LABELS,
    DISPLAY_STATUSES,
    FINAL_SET_RULES,
    GENDERS,
    HANDS,
    Match,
    Player,
    Tournament,
)
from photos import PHOTOS
from scoring import STAT_KEYS, ScoreState, is_changeover, match_state, match_stats, point_flags

WEBSOCKET_PATH = "/ws"
#verification du statut "A VENIR" (depend de l'heure, pas d'une action)
STATUS_CHECK_INTERVAL = 15.0


# ---------------------------------------------------------------------------
# Mise en forme JSON
# ---------------------------------------------------------------------------

def _url(base_url: str, path: str) -> str | None:
    return f"{base_url}{path}" if path else None


def _flag_url(base_url: str, country: str) -> str | None:
    iso = flag_iso(country)
    return f"{base_url}{FLAGS_URL}/{iso}.svg" if iso else None


def serialize_player(player: Player, base_url: str) -> dict:
    return {
        "id": player.id,
        "first_name": player.first_name,
        "last_name": player.last_name,
        "tv_long_name": player.long_name,
        "tv_short_name": player.short_name,
        "country": player.country,
        "country_name": country_name(player.country) if player.country else "",
        "flag_url": _flag_url(base_url, player.country),
        "photo_url": _url(base_url, PHOTOS.file_url(player.photo, player.updated_at)) if player.photo else None,
        "best_ranking": player.best_ranking,
        "gender": player.gender,
        "gender_label": GENDERS.get(player.gender, ""),
        "birth_date": player.birth_date or None,
        "age": player.age,
        "hand": player.hand or None,
        "hand_label": HANDS.get(player.hand, ""),
        "backhand": player.backhand or None,
        "backhand_label": BACKHANDS.get(player.backhand, ""),
        "height_cm": player.height_cm,
        "weight_kg": player.weight_kg,
        "turned_pro": player.turned_pro,
    }


def serialize_tournament(tournament: Tournament | None, base_url: str) -> dict | None:
    if tournament is None:
        return None
    return {
        "id": tournament.id,
        "name": tournament.name,
        "level": tournament.level,
        "surface": tournament.surface,
        "venue": tournament.venue,
        "city": tournament.city,
        "country": tournament.country,
        "country_name": country_name(tournament.country) if tournament.country else "",
        "flag_url": _flag_url(base_url, tournament.country),
        "logo_url": _url(base_url, LOGOS.file_url(tournament.logo, tournament.updated_at)) if tournament.logo else None,
        "start_date": tournament.start_date or None,
        "end_date": tournament.end_date or None,
        "courts": tournament.courts,
        "is_current": tournament.is_current,
    }


def _duration_seconds(match: Match, now: datetime) -> int | None:
    try:
        start = datetime.fromisoformat(match.started_at)
    except ValueError:
        return None
    try:
        end = datetime.fromisoformat(match.finished_at) if match.finished_at else now
    except ValueError:
        end = now
    return max(0, int((end - start).total_seconds()))


#ligne d'une equipe, prete pour un graphique : identite, service, et une
#case par set (`games`, `tiebreak_small`...) sur toute la longueur du match
def _percent(won: int, played: int) -> int | None:
    return round(100 * won / played) if played else None


#statistiques d'une equipe pour un graphique "face a face" : compteurs +
#pourcentages deja calcules (voir scoring.compute_stats)
def _serialize_stats(stats: dict[str, int]) -> dict:
    return {
        **stats,
        "service_points_won_pct": _percent(stats["service_points_won"], stats["service_points_played"]),
        "return_points_won_pct": _percent(stats["return_points_won"], stats["return_points_played"]),
        "break_points_won_pct": _percent(stats["break_points_won"], stats["break_points_played"]),
        "break_points_saved_pct": _percent(stats["break_points_saved"], stats["break_points_faced"]),
        "service_games_won_pct": _percent(stats["service_games_won"], stats["service_games_played"]),
    }


def _serialize_team(
    match: Match, index: int, state: ScoreState | None, points: list, base_url: str, stats: dict[str, int]
) -> dict:
    team = (match.team1, match.team2)[index]
    set_count = match.format.sets_to_win * 2 - 1
    live = state is not None and not state.finished
    server_team, server_player = state.server if live else (None, None)
    serving = server_team == index

    games: list[int | None] = [None] * set_count
    tiebreak_points: list[int | None] = [None] * set_count
    tiebreak_small: list[int | None] = [None] * set_count
    points_label = points_raw = None
    flags = {"break": False, "set": False, "match": False}
    if state is not None:
        for number, set_games in enumerate(state.sets):
            tiebreak = state.tiebreaks[number]
            if state.super_tiebreak_sets[number]:
                #super tie-break : la case du set affiche ses points (ex: 10 / 8)
                games[number] = tiebreak[index]
            else:
                games[number] = set_games[index]
                if tiebreak is not None:
                    tiebreak_points[number] = tiebreak[index]
                    #convention TV : petit chiffre = points du PERDANT du tie-break
                    if set_games[index] < set_games[1 - index]:
                        tiebreak_small[number] = tiebreak[index]
        if live:
            if not state.super_tiebreak:
                games[len(state.sets)] = state.games[index]
            labels = state.point_labels(match.format.no_ad)
            points_label, points_raw = labels[index], state.points[index]
            flags = point_flags(match.format, match.first_server, (match.first_server_1, match.first_server_2),
                                points, index)

    winner = state.winner if state is not None else None
    return {
        "index": index,
        "tv_long_name": " / ".join(player.long_name for player in team),
        "tv_short_name": " / ".join(player.short_name for player in team),
        "tricodes": [player.country for player in team],
        "flag_urls": [_flag_url(base_url, player.country) for player in team],
        "serving": serving,
        "serving_player": server_player if serving else None,
        #cote du court vu depuis la chaise d'arbitre ("left" / "right"), mis a
        #jour a chaque changement de cote ; null avant le debut du match
        "side": (None if state is None
                 else "left" if state.left_team(match.first_left or 0) == index else "right"),
        "is_winner": winner == index,
        "retired": bool(match.end_reason == "RET" and winner is not None and winner != index),
        "sets_won": state.sets_won[index] if state is not None else 0,
        "games": games,
        "tiebreak_small": tiebreak_small,
        "tiebreak_points": tiebreak_points,
        "points": points_label,
        "points_raw": points_raw,
        "break_point": flags["break"],
        "set_point": flags["set"],
        "match_point": flags["match"],
        "stats": _serialize_stats(stats),
        "players": [
            dict(serialize_player(player, base_url), serving=serving and server_player == position)
            for position, player in enumerate(team)
        ],
    }


#objet "match" envoye aux graphiques : arborescence simple a 2 niveaux - le
#match (infos generales + etat du jeu) et ses 2 equipes `teams` (tout ce qui
#s'affiche sur la ligne d'un joueur), voir docs/websocket.md
def serialize_match(match: Match, base_url: str, now: datetime | None = None) -> dict:
    now = now or datetime.now()
    status = match.display_status(now)
    started = match.first_server is not None
    points = database.get_points(match.id) if started else []
    state = match_state(match, points) if started else None
    stats = (match_stats(match, points, database.get_natures(match.id)) if started
             else [{key: 0 for key in STAT_KEYS} for _ in range(2)])
    live = state is not None and not state.finished
    played = [event for event in points if not isinstance(event, tuple)]
    match_format = match.format
    return {
        "id": match.id,
        "status": status,
        "status_label": DISPLAY_STATUSES.get(status, (status, ""))[0],
        "category": match.category,
        "category_label": CATEGORY_LABELS.get(match.category, match.category),
        "is_double": match.is_double,
        "round": match.round or None,
        "court": match.court or None,
        "scheduled_date": match.scheduled_date or None,
        "scheduled_time": match.scheduled_time or None,
        "started_at": match.started_at or None,
        "finished_at": match.finished_at or None,
        "duration_seconds": _duration_seconds(match, now),
        #etat du jeu (null / false tant que le match n'a pas debute)
        "set_count": match_format.sets_to_win * 2 - 1,
        "active_set": state.set_number if live else None,
        "in_tiebreak": bool(live and state.in_tiebreak),
        "super_tiebreak": bool(live and state.super_tiebreak),
        "tiebreak_target": state.tiebreak_target if live and state.in_tiebreak else None,
        "deciding_point": bool(live and match_format.no_ad and not state.in_tiebreak and state.points == [3, 3]),
        "changeover": bool(state is not None and is_changeover(state, points)),
        "last_point_winner": played[-1] if played else None,
        "total_points": len(played),
        "winner": state.winner if state is not None else None,
        "end_reason": match.end_reason or None,
        "tournament": serialize_tournament(match.tournament, base_url),
        "format": {
            "best_of": match_format.sets_to_win * 2 - 1,
            "sets_to_win": match_format.sets_to_win,
            "games_per_set": match_format.games_per_set,
            "tiebreak_enabled": match_format.tiebreak_enabled,
            "tiebreak_points": match_format.tiebreak_points,
            "final_set_rule": match_format.final_set_rule,
            "final_set_rule_label": FINAL_SET_RULES.get(match_format.final_set_rule, ""),
            "no_ad": match_format.no_ad,
            "summary": match_format.summary,
        },
        "teams": [_serialize_team(match, index, state, points, base_url, stats[index]) for index in (0, 1)],
        "updated_at": match.updated_at,
    }


# ---------------------------------------------------------------------------
# Connexions WebSocket
# ---------------------------------------------------------------------------

class _Connection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        #URLs absolues (drapeaux, photos, logos) avec l'adresse utilisee par le client
        host = websocket.headers.get("host", "localhost:8080")
        self.base_url = f"http://{host}"
        self.match_id: int | None = None      #filtre "subscribe" (None = tous)
        self.lock = asyncio.Lock()            #un seul envoi a la fois par connexion

    def wants(self, match_id: int) -> bool:
        return self.match_id is None or self.match_id == match_id

    async def send(self, message: dict) -> None:
        async with self.lock:
            await self.websocket.send_text(json.dumps(message, ensure_ascii=False))

    def snapshot(self) -> dict:
        now = datetime.now()
        #ordre chronologique, matchs sans date en dernier
        matches = sorted(
            (m for m in database.list_matches() if self.wants(m.id)),
            key=lambda m: (not m.scheduled_date, m.scheduled_date, m.scheduled_time, m.id),
        )
        return {"type": "snapshot", "matches": [serialize_match(m, self.base_url, now) for m in matches]}


_connections: set[_Connection] = set()


#nombre de clients WebSocket connectes (page ADMINISTRATION)
def connection_count() -> int:
    return len(_connections)


@app.websocket(WEBSOCKET_PATH)
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    connection = _Connection(websocket)
    _connections.add(connection)
    try:
        await connection.send(connection.snapshot())
        while True:
            text = await websocket.receive_text()
            try:
                request = json.loads(text)
            except ValueError:
                await connection.send({"type": "error", "message": "JSON invalide"})
                continue
            kind = request.get("type") if isinstance(request, dict) else None
            if kind == "snapshot":
                await connection.send(connection.snapshot())
            elif kind == "subscribe":
                match_id = request.get("match_id")
                connection.match_id = int(match_id) if match_id is not None else None
                await connection.send(connection.snapshot())
            else:
                await connection.send({"type": "error", "message": f"type de message inconnu : {kind}"})
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(connection)


async def _send_all(build, match_id: int | None = None) -> None:
    for connection in list(_connections):
        if match_id is not None and not connection.wants(match_id):
            continue
        try:
            await connection.send(build(connection))
        except Exception:
            #client deconnecte entre-temps : retire, il sera recree a sa reconnexion
            _connections.discard(connection)


#un match a change (point, debut, fin, modification, suppression)
async def _on_match_scored(match_id: int) -> None:
    if not _connections:
        return
    match = database.get_match(match_id)
    if match is None:
        await _send_all(lambda c: {"type": "match_deleted", "id": match_id}, match_id)
    else:
        await _send_all(lambda c: {"type": "match", "match": serialize_match(match, c.base_url)}, match_id)


#joueur ou tournoi modifie : plusieurs matchs peuvent etre concernes (noms,
#photos, logos...) -> instantane complet
async def _on_global_change() -> None:
    if _connections:
        await _send_all(lambda c: c.snapshot())


match_scored.subscribe(_on_match_scored)
tournaments_changed.subscribe(_on_global_change)
players_changed.subscribe(_on_global_change)


#statut "A VENIR" (10 min avant le debut) : change avec l'heure, sans action
#de l'operateur -> verification reguliere, seuls les matchs changes sont envoyes
async def _watch_statuses() -> None:
    previous: dict[int, str] = {}
    while True:
        await asyncio.sleep(STATUS_CHECK_INTERVAL)
        now = datetime.now()
        current = {m.id: m.display_status(now) for m in database.list_matches()}
        changed = [match_id for match_id, status in current.items()
                   if match_id in previous and previous[match_id] != status]
        previous = current
        for match_id in changed:
            await _on_match_scored(match_id)


app.on_startup(_watch_statuses)
