# Couche de persistance SQLite (module standard sqlite3, pas d'ORM).
#
# Une seule connexion partagee par tout le processus (check_same_thread=
# False) : NiceGUI execute les handlers dans une seule boucle asyncio, et
# les futures couches API HTTP/WebSocket tourneront dans le meme processus
# et liront la meme base. Les requetes sont courtes, pas besoin de pool.
#
# Schema (version 11) :
#   - athletes      : annuaire des joueurs, reutilisables d'un match a l'autre
#   - tournaments   : tournois crees a l'avance (surface, lieu, courts...),
#                     dont au plus un marque "en cours" (is_current) ;
#                     un tournoi encore utilise par un match ne peut pas etre
#                     supprime (ON DELETE RESTRICT)
#   - matches       : tournoi, infos generales + format du match
#   - match_players : composition des equipes (team 1/2, position 1/2),
#                     supprimee en cascade avec le match ; un joueur encore
#                     engage dans un match ne peut pas etre supprime
#                     (ON DELETE RESTRICT)
#   - match_points  : evenements d'un match dans l'ordre : points joues
#                     (kind "point", equipe gagnante) et changements de
#                     serveur manuels (kind "server", equipe + joueur) et
#                     inversions manuelles des cotes (kind "sides") - le
#                     score est recalcule a partir d'eux (scoring.py)
#
# Les modifications de schema se font via SCHEMA_VERSION/_migrate() pour
# ne jamais perdre les donnees deja saisies lors d'une mise a jour.

import json
import sqlite3
import unicodedata
from datetime import date, datetime

from models import Match, MatchFormat, Player, Tournament
from paths import user_data_path

DB_PATH = user_data_path("tennis.db")

SCHEMA_VERSION = 12

#version 1 : joueurs saisis directement dans chaque match (table players)
SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS matches (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament        TEXT    NOT NULL DEFAULT '',
    category          TEXT    NOT NULL DEFAULT 'MS',
    round             TEXT    NOT NULL DEFAULT '',
    court             TEXT    NOT NULL DEFAULT '',
    surface           TEXT    NOT NULL DEFAULT '',
    scheduled_date    TEXT    NOT NULL DEFAULT '',
    scheduled_time    TEXT    NOT NULL DEFAULT '',
    umpire            TEXT    NOT NULL DEFAULT '',
    status            TEXT    NOT NULL DEFAULT 'scheduled',
    sets_to_win       INTEGER NOT NULL DEFAULT 2,
    games_per_set     INTEGER NOT NULL DEFAULT 6,
    tiebreak_enabled  INTEGER NOT NULL DEFAULT 1,
    tiebreak_points   INTEGER NOT NULL DEFAULT 7,
    final_set_rule    TEXT    NOT NULL DEFAULT 'tiebreak',
    no_ad             INTEGER NOT NULL DEFAULT 0,
    team1_seed        INTEGER,
    team2_seed        INTEGER,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team        INTEGER NOT NULL CHECK (team IN (1, 2)),
    position    INTEGER NOT NULL CHECK (position IN (1, 2)),
    first_name  TEXT    NOT NULL DEFAULT '',
    last_name   TEXT    NOT NULL DEFAULT '',
    country     TEXT    NOT NULL DEFAULT '',
    ranking     INTEGER,
    UNIQUE (match_id, team, position)
);
"""

#version 2 : annuaire des joueurs (athletes) + liaison match_players
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS athletes (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name       TEXT    NOT NULL DEFAULT '',
    last_name        TEXT    NOT NULL DEFAULT '',
    tv_name          TEXT    NOT NULL DEFAULT '',
    gender           TEXT    NOT NULL DEFAULT 'M',
    country          TEXT    NOT NULL DEFAULT '',
    birth_date       TEXT    NOT NULL DEFAULT '',
    birthplace       TEXT    NOT NULL DEFAULT '',
    residence        TEXT    NOT NULL DEFAULT '',
    ranking_singles  INTEGER,
    ranking_doubles  INTEGER,
    best_ranking     INTEGER,
    hand             TEXT    NOT NULL DEFAULT '',
    backhand         TEXT    NOT NULL DEFAULT '',
    height_cm        INTEGER,
    weight_kg        INTEGER,
    turned_pro       INTEGER,
    coach            TEXT    NOT NULL DEFAULT '',
    notes            TEXT    NOT NULL DEFAULT '',
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS match_players (
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team        INTEGER NOT NULL CHECK (team IN (1, 2)),
    position    INTEGER NOT NULL CHECK (position IN (1, 2)),
    athlete_id  INTEGER NOT NULL REFERENCES athletes(id) ON DELETE RESTRICT,
    PRIMARY KEY (match_id, team, position)
);

CREATE INDEX IF NOT EXISTS idx_match_players_athlete ON match_players(athlete_id);
"""

#version 3 : noms TV long/court (tv_name -> tv_short_name + tv_long_name),
#identifiant Wikidata ; un seul classement (le meilleur) ; suppression des
#champs entraineur/lieu de naissance/residence (joueurs), juge de chaise et
#tetes de serie (matchs)
MIGRATION_V3 = [
    "ALTER TABLE athletes RENAME COLUMN tv_name TO tv_short_name",
    "ALTER TABLE athletes ADD COLUMN tv_long_name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE athletes ADD COLUMN wikidata_id TEXT NOT NULL DEFAULT ''",
    "UPDATE athletes SET best_ranking = COALESCE(best_ranking, ranking_singles)",
    "ALTER TABLE athletes DROP COLUMN ranking_singles",
    "ALTER TABLE athletes DROP COLUMN ranking_doubles",
    "ALTER TABLE athletes DROP COLUMN coach",
    "ALTER TABLE athletes DROP COLUMN birthplace",
    "ALTER TABLE athletes DROP COLUMN residence",
    "ALTER TABLE matches DROP COLUMN umpire",
    "ALTER TABLE matches DROP COLUMN team1_seed",
    "ALTER TABLE matches DROP COLUMN team2_seed",
]

#version 4 : tournois crees a l'avance ; matches.tournament (texte) et
#matches.surface remplaces par matches.tournament_id (voir _migrate)
SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS tournaments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL DEFAULT '',
    level       TEXT    NOT NULL DEFAULT '',
    surface     TEXT    NOT NULL DEFAULT '',
    venue       TEXT    NOT NULL DEFAULT '',
    city        TEXT    NOT NULL DEFAULT '',
    country     TEXT    NOT NULL DEFAULT '',
    start_date  TEXT    NOT NULL DEFAULT '',
    end_date    TEXT    NOT NULL DEFAULT '',
    courts      TEXT    NOT NULL DEFAULT '[]',
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
"""

#colonnes de tournaments modifiables depuis l'interface (courts : liste
#serialisee en JSON)
TOURNAMENT_FIELDS = [
    "name", "level", "surface", "venue", "city", "country", "start_date", "end_date", "courts",
    "is_current", "logo",
]

MIGRATION_V9 = [
    "ALTER TABLE matches ADD COLUMN first_server INTEGER",
    "ALTER TABLE matches ADD COLUMN first_server_1 INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN first_server_2 INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE matches ADD COLUMN started_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE matches ADD COLUMN finished_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE matches ADD COLUMN winner INTEGER",
    "ALTER TABLE matches ADD COLUMN end_reason TEXT NOT NULL DEFAULT ''",
    """CREATE TABLE IF NOT EXISTS match_points (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
        team        INTEGER NOT NULL CHECK (team IN (0, 1)),
        created_at  TEXT    NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_match_points_match ON match_points(match_id)",
]

#colonnes de athletes modifiables depuis l'interface (tout sauf id/dates)
ATHLETE_FIELDS = [
    "first_name", "last_name", "tv_long_name", "tv_short_name", "gender", "country",
    "birth_date", "best_ranking", "hand", "backhand", "height_cm", "weight_kg",
    "turned_pro", "notes", "wikidata_id", "photo", "tv_long_auto", "tv_short_auto",
]

_connection: sqlite3.Connection | None = None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    global _connection

    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        #indispensable pour ON DELETE CASCADE/RESTRICT (desactive par defaut en SQLite)
        _connection.execute("PRAGMA foreign_keys = ON")
        #WAL : lectures concurrentes possibles pendant une ecriture (futurs
        #lecteurs API/fichiers pendant que l'operateur saisit les points)
        _connection.execute("PRAGMA journal_mode = WAL")
        _migrate(_connection)

    return _connection


def _migrate(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]

    if current < 1:
        conn.executescript(SCHEMA_V1)

    if current < 2:
        conn.executescript(SCHEMA_V2)
        #chaque joueur saisi dans un match v1 devient une fiche de l'annuaire
        now = _now()
        for row in conn.execute("SELECT * FROM players ORDER BY id").fetchall():
            if not (row["first_name"] or row["last_name"]):
                continue
            cursor = conn.execute(
                "INSERT INTO athletes (first_name, last_name, country, ranking_singles, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row["first_name"], row["last_name"], row["country"], row["ranking"], now, now),
            )
            conn.execute(
                "INSERT INTO match_players (match_id, team, position, athlete_id) VALUES (?, ?, ?, ?)",
                (row["match_id"], row["team"], row["position"], cursor.lastrowid),
            )
        conn.execute("DROP TABLE players")

    if current < 3:
        for statement in MIGRATION_V3:
            conn.execute(statement)

    if current < 4:
        conn.executescript(SCHEMA_V4)
        conn.execute(
            "ALTER TABLE matches ADD COLUMN tournament_id INTEGER REFERENCES tournaments(id) ON DELETE RESTRICT"
        )
        #un tournoi par couple (nom, surface) deja saisi dans les matchs,
        #avec les courts utilises
        now = _now()
        groups: dict[tuple[str, str], list] = {}
        for row in conn.execute("SELECT id, tournament, surface, court FROM matches").fetchall():
            if row["tournament"].strip():
                groups.setdefault((row["tournament"].strip(), row["surface"]), []).append(row)
        for (name, surface), rows in groups.items():
            courts = sorted({row["court"] for row in rows if row["court"]})
            cursor = conn.execute(
                "INSERT INTO tournaments (name, surface, courts, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, surface, json.dumps(courts, ensure_ascii=False), now, now),
            )
            for row in rows:
                conn.execute("UPDATE matches SET tournament_id = ? WHERE id = ?", (cursor.lastrowid, row["id"]))
        conn.execute("ALTER TABLE matches DROP COLUMN tournament")
        conn.execute("ALTER TABLE matches DROP COLUMN surface")

    #version 5 : tournoi en cours choisi a la main
    if current < 5:
        conn.execute("ALTER TABLE tournaments ADD COLUMN is_current INTEGER NOT NULL DEFAULT 0")

    #version 6 : photo des joueurs (nom du fichier, voir photos.py)
    if current < 6:
        conn.execute("ALTER TABLE athletes ADD COLUMN photo TEXT NOT NULL DEFAULT ''")

    #version 7 : noms TV toujours remplis en base + indicateur auto/manuel
    #(avant : nom vide = automatique). Les noms vides deviennent "auto" et
    #sont calcules tout de suite, les noms deja saisis restent manuels.
    if current < 7:
        conn.execute("ALTER TABLE athletes ADD COLUMN tv_long_auto INTEGER NOT NULL DEFAULT 1")
        conn.execute("ALTER TABLE athletes ADD COLUMN tv_short_auto INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE athletes SET tv_long_auto = (tv_long_name = ''), tv_short_auto = (tv_short_name = '')")
        for row in conn.execute("SELECT * FROM athletes").fetchall():
            player = _row_to_player(row)
            player.fill_tv_names()
            conn.execute(
                "UPDATE athletes SET tv_long_name = ?, tv_short_name = ? WHERE id = ?",
                (player.tv_long_name, player.tv_short_name, player.id),
            )

    #version 8 : logo des tournois (nom du fichier, voir logos.py)
    if current < 8:
        conn.execute("ALTER TABLE tournaments ADD COLUMN logo TEXT NOT NULL DEFAULT ''")

    #version 9 : arbitrage (debut du match, service, points, resultat)
    if current < 9:
        for statement in MIGRATION_V9:
            conn.execute(statement)

    #version 10 : changements de serveur manuels dans les evenements du match
    if current < 10:
        conn.execute("ALTER TABLE match_points ADD COLUMN kind TEXT NOT NULL DEFAULT 'point'")
        conn.execute("ALTER TABLE match_points ADD COLUMN player INTEGER NOT NULL DEFAULT 0")

    #version 11 : nature des points (ace, double faute...) pour les statistiques
    if current < 11:
        conn.execute("ALTER TABLE match_points ADD COLUMN nature TEXT NOT NULL DEFAULT ''")

    #version 12 : cote de depart des equipes (realite augmentee, graphiques au sol)
    if current < 12:
        conn.execute("ALTER TABLE matches ADD COLUMN first_left INTEGER")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


# ---------------------------------------------------------------------------
# Joueurs (annuaire)
# ---------------------------------------------------------------------------

def _row_to_player(row: sqlite3.Row) -> Player:
    values = {name: row[name] for name in ATHLETE_FIELDS}
    for name in ("tv_long_auto", "tv_short_auto"):
        values[name] = bool(values[name])
    return Player(id=row["id"], created_at=row["created_at"], updated_at=row["updated_at"], **values)


#cle de comparaison d'un nom : sans accents, sans casse, espaces reduits
#("Dušan  Lajović" == "dusan lajovic")
def _name_key(first_name: str, last_name: str) -> str:
    text = unicodedata.normalize("NFKD", f"{first_name} {last_name}")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


#joueur deja present dans l'annuaire avec le meme prenom + nom, ou la meme
#fiche Wikidata (hors le joueur lui-meme, en modification), None sinon
def find_duplicate_player(player: Player) -> Player | None:
    key = _name_key(player.first_name, player.last_name)
    for other in list_players():
        if other.id == player.id:
            continue
        if _name_key(other.first_name, other.last_name) == key:
            return other
        if player.wikidata_id and other.wikidata_id == player.wikidata_id:
            return other
    return None


def list_players() -> list[Player]:
    rows = connect().execute(
        "SELECT * FROM athletes ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE"
    ).fetchall()
    return [_row_to_player(row) for row in rows]


def get_player(player_id: int) -> Player | None:
    row = connect().execute("SELECT * FROM athletes WHERE id = ?", (player_id,)).fetchone()
    return _row_to_player(row) if row else None


def save_player(player: Player) -> int:
    conn = connect()
    player.fill_tv_names()
    values = {name: getattr(player, name) for name in ATHLETE_FIELDS}
    values["updated_at"] = _now()

    with conn:
        if player.id is None:
            values["created_at"] = values["updated_at"]
            columns = ", ".join(values)
            placeholders = ", ".join(f":{key}" for key in values)
            cursor = conn.execute(f"INSERT INTO athletes ({columns}) VALUES ({placeholders})", values)
            player.id = cursor.lastrowid
        else:
            assignments = ", ".join(f"{key} = :{key}" for key in values)
            conn.execute(f"UPDATE athletes SET {assignments} WHERE id = :id", {**values, "id": player.id})

    return player.id


#nombre de matchs dans lesquels chaque joueur est engage {player_id: n}
def player_match_counts() -> dict[int, int]:
    rows = connect().execute(
        "SELECT athlete_id, COUNT(DISTINCT match_id) AS n FROM match_players GROUP BY athlete_id"
    )
    return {row["athlete_id"]: row["n"] for row in rows}


#met a jour uniquement le fichier photo du joueur ("" = pas de photo)
def set_player_photo(player_id: int, photo: str) -> None:
    conn = connect()
    with conn:
        conn.execute("UPDATE athletes SET photo = ?, updated_at = ? WHERE id = ?", (photo, _now(), player_id))


#renvoie False (sans rien supprimer) si le joueur est encore engage dans un match
def delete_player(player_id: int) -> bool:
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM athletes WHERE id = ?", (player_id,))
    except sqlite3.IntegrityError:
        return False
    return True


# ---------------------------------------------------------------------------
# Tournois
# ---------------------------------------------------------------------------

def _row_to_tournament(row: sqlite3.Row) -> Tournament:
    values = {name: row[name] for name in TOURNAMENT_FIELDS}
    values["courts"] = json.loads(values["courts"] or "[]")
    values["is_current"] = bool(values["is_current"])
    return Tournament(id=row["id"], created_at=row["created_at"], updated_at=row["updated_at"], **values)


#tournois les plus recents en premier (date de debut decroissante)
def list_tournaments() -> list[Tournament]:
    rows = connect().execute(
        "SELECT * FROM tournaments ORDER BY start_date DESC, name COLLATE NOCASE"
    ).fetchall()
    return [_row_to_tournament(row) for row in rows]


def get_tournament(tournament_id: int) -> Tournament | None:
    row = connect().execute("SELECT * FROM tournaments WHERE id = ?", (tournament_id,)).fetchone()
    return _row_to_tournament(row) if row else None


def save_tournament(tournament: Tournament) -> int:
    conn = connect()
    values = {name: getattr(tournament, name) for name in TOURNAMENT_FIELDS}
    values["courts"] = json.dumps(tournament.courts, ensure_ascii=False)
    values["is_current"] = int(tournament.is_current)
    values["updated_at"] = _now()

    with conn:
        #un seul tournoi en cours : marquer celui-ci demarque les autres
        if tournament.is_current:
            conn.execute("UPDATE tournaments SET is_current = 0 WHERE is_current = 1")
        if tournament.id is None:
            values["created_at"] = values["updated_at"]
            columns = ", ".join(values)
            placeholders = ", ".join(f":{key}" for key in values)
            cursor = conn.execute(f"INSERT INTO tournaments ({columns}) VALUES ({placeholders})", values)
            tournament.id = cursor.lastrowid
        else:
            assignments = ", ".join(f"{key} = :{key}" for key in values)
            conn.execute(f"UPDATE tournaments SET {assignments} WHERE id = :id", {**values, "id": tournament.id})

    return tournament.id


#marque (current True) ou demarque le tournoi en cours, en une transaction
#(un seul tournoi en cours a la fois)
def set_current_tournament(tournament_id: int, current: bool) -> None:
    conn = connect()
    with conn:
        if current:
            conn.execute("UPDATE tournaments SET is_current = 0 WHERE is_current = 1")
        conn.execute(
            "UPDATE tournaments SET is_current = ?, updated_at = ? WHERE id = ?",
            (int(current), _now(), tournament_id),
        )


#tournoi(s) en cours : celui marque a la main s'il y en a un, sinon ceux
#dont la periode contient `today` (date de fin absente = un seul jour)
def current_tournaments(today: date) -> list[Tournament]:
    tournaments = list_tournaments()
    marked = [tournament for tournament in tournaments if tournament.is_current]
    if marked:
        return marked
    iso = today.isoformat()
    return [
        tournament for tournament in tournaments
        if tournament.start_date and tournament.start_date <= iso <= (tournament.end_date or tournament.start_date)
    ]


#met a jour uniquement le fichier logo du tournoi ("" = pas de logo)
def set_tournament_logo(tournament_id: int, logo: str) -> None:
    conn = connect()
    with conn:
        conn.execute("UPDATE tournaments SET logo = ?, updated_at = ? WHERE id = ?", (logo, _now(), tournament_id))


#nombre de matchs par tournoi {tournament_id: n}
def tournament_match_counts() -> dict[int, int]:
    rows = connect().execute(
        "SELECT tournament_id, COUNT(*) AS n FROM matches WHERE tournament_id IS NOT NULL GROUP BY tournament_id"
    )
    return {row["tournament_id"]: row["n"] for row in rows}


#renvoie False (sans rien supprimer) si le tournoi a encore des matchs
def delete_tournament(tournament_id: int) -> bool:
    conn = connect()
    try:
        with conn:
            conn.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
    except sqlite3.IntegrityError:
        return False
    return True


# ---------------------------------------------------------------------------
# Matchs
# ---------------------------------------------------------------------------

#lignes match_players jointes a athletes (une ligne par joueur engage)
_MATCH_PLAYERS_QUERY = (
    "SELECT mp.match_id, mp.team, mp.position, a.* "
    "FROM match_players mp JOIN athletes a ON a.id = mp.athlete_id"
)


def _row_to_match(
    row: sqlite3.Row, player_rows: list[sqlite3.Row], tournaments: dict[int, Tournament]
) -> Match:
    match = Match(
        id=row["id"],
        tournament_id=row["tournament_id"],
        tournament=tournaments.get(row["tournament_id"]),
        category=row["category"],
        round=row["round"],
        court=row["court"],
        scheduled_date=row["scheduled_date"],
        scheduled_time=row["scheduled_time"],
        status=row["status"],
        format=MatchFormat(
            sets_to_win=row["sets_to_win"],
            games_per_set=row["games_per_set"],
            tiebreak_enabled=bool(row["tiebreak_enabled"]),
            tiebreak_points=row["tiebreak_points"],
            final_set_rule=row["final_set_rule"],
            no_ad=bool(row["no_ad"]),
        ),
        first_server=row["first_server"],
        first_server_1=row["first_server_1"],
        first_server_2=row["first_server_2"],
        first_left=row["first_left"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        winner=row["winner"],
        end_reason=row["end_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

    for player_row in sorted(player_rows, key=lambda r: r["position"]):
        (match.team1 if player_row["team"] == 1 else match.team2).append(_row_to_player(player_row))

    return match


def list_matches() -> list[Match]:
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM matches ORDER BY scheduled_date, scheduled_time, id"
    ).fetchall()

    players_by_match: dict[int, list[sqlite3.Row]] = {}
    for player_row in conn.execute(_MATCH_PLAYERS_QUERY):
        players_by_match.setdefault(player_row["match_id"], []).append(player_row)

    tournaments = {tournament.id: tournament for tournament in list_tournaments()}
    return [_row_to_match(row, players_by_match.get(row["id"], []), tournaments) for row in rows]


def get_match(match_id: int) -> Match | None:
    conn = connect()
    row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    if row is None:
        return None

    player_rows = conn.execute(_MATCH_PLAYERS_QUERY + " WHERE mp.match_id = ?", (match_id,)).fetchall()
    tournament = get_tournament(row["tournament_id"]) if row["tournament_id"] else None
    return _row_to_match(row, player_rows, {tournament.id: tournament} if tournament else {})


#cree (match.id None) ou met a jour le match et la composition des
#equipes (joueurs de l'annuaire, Player.id obligatoire) dans une seule
#transaction. Renvoie l'id du match.
def save_match(match: Match) -> int:
    conn = connect()
    now = _now()
    values = {
        "tournament_id": match.tournament_id,
        "category": match.category,
        "round": match.round,
        "court": match.court,
        "scheduled_date": match.scheduled_date,
        "scheduled_time": match.scheduled_time,
        "status": match.status,
        "sets_to_win": match.format.sets_to_win,
        "games_per_set": match.format.games_per_set,
        "tiebreak_enabled": int(match.format.tiebreak_enabled),
        "tiebreak_points": match.format.tiebreak_points,
        "final_set_rule": match.format.final_set_rule,
        "no_ad": int(match.format.no_ad),
        "updated_at": now,
    }

    with conn:
        if match.id is None:
            values["created_at"] = now
            columns = ", ".join(values)
            placeholders = ", ".join(f":{key}" for key in values)
            cursor = conn.execute(f"INSERT INTO matches ({columns}) VALUES ({placeholders})", values)
            match.id = cursor.lastrowid
        else:
            assignments = ", ".join(f"{key} = :{key}" for key in values)
            conn.execute(f"UPDATE matches SET {assignments} WHERE id = :id", {**values, "id": match.id})
            conn.execute("DELETE FROM match_players WHERE match_id = ?", (match.id,))

        for team_number, team in ((1, match.team1), (2, match.team2)):
            for position, player in enumerate(team, start=1):
                conn.execute(
                    "INSERT INTO match_players (match_id, team, position, athlete_id) VALUES (?, ?, ?, ?)",
                    (match.id, team_number, position, player.id),
                )

    return match.id


# ---------------------------------------------------------------------------
# Arbitrage (points d'un match)
# ---------------------------------------------------------------------------
#Les champs d'arbitrage ne sont jamais touches par save_match (fenetre
#d'administration) : seulement par les fonctions ci-dessous.

#equipes gagnantes des points joues, dans l'ordre
#evenements du match dans l'ordre (format attendu par scoring.compute_state) :
#equipe gagnante (entier) pour un point, ("server", equipe, joueur) pour un
#changement de serveur manuel, ("sides",) pour une inversion des cotes
def get_points(match_id: int) -> list:
    rows = connect().execute(
        "SELECT kind, team, player FROM match_points WHERE match_id = ? ORDER BY id", (match_id,)
    )
    events = []
    for row in rows:
        if row["kind"] == "server":
            events.append(("server", row["team"], row["player"]))
        elif row["kind"] == "sides":
            events.append(("sides",))
        else:
            events.append(row["team"])
    return events


#debut du match : service, cote de depart (`first_left` : equipe a gauche vu
#depuis la chaise d'arbitre), statut "en cours" (repart de zero si des points
#existaient deja)
def start_match(match_id: int, first_server: int, first_server_1: int, first_server_2: int,
                first_left: int = 0) -> None:
    conn = connect()
    now = _now()
    with conn:
        conn.execute("DELETE FROM match_points WHERE match_id = ?", (match_id,))
        conn.execute(
            "UPDATE matches SET first_server = ?, first_server_1 = ?, first_server_2 = ?, first_left = ?, "
            "status = 'live', started_at = ?, finished_at = '', winner = NULL, end_reason = '', updated_at = ? "
            "WHERE id = ?",
            (first_server, first_server_1, first_server_2, first_left, now, now, match_id),
        )


#annule le debut du match (aucun point joue) : retour a "programme"
def reset_match(match_id: int) -> None:
    conn = connect()
    with conn:
        conn.execute("DELETE FROM match_points WHERE match_id = ?", (match_id,))
        conn.execute(
            "UPDATE matches SET first_server = NULL, first_left = NULL, status = 'scheduled', started_at = '', "
            "finished_at = '', winner = NULL, end_reason = '', updated_at = ? WHERE id = ?",
            (_now(), match_id),
        )


#nature de chaque evenement du match, dans le meme ordre que get_points ("" si
#non precisee ou changement de serveur) - voir scoring.POINT_NATURES
def get_natures(match_id: int) -> list[str]:
    rows = connect().execute("SELECT nature FROM match_points WHERE match_id = ? ORDER BY id", (match_id,))
    return [row["nature"] for row in rows]


#nature du DERNIER point joue ("" pour l'effacer) ; sans effet si le dernier
#evenement n'est pas un point (changement de serveur)
def set_last_point_nature(match_id: int, nature: str) -> None:
    conn = connect()
    with conn:
        row = conn.execute(
            "SELECT id, kind FROM match_points WHERE match_id = ? ORDER BY id DESC LIMIT 1", (match_id,)
        ).fetchone()
        if row is None or row["kind"] != "point":
            return
        conn.execute("UPDATE match_points SET nature = ? WHERE id = ?", (nature, row["id"]))
        conn.execute("UPDATE matches SET updated_at = ? WHERE id = ?", (_now(), match_id))


def add_point(match_id: int, team: int) -> None:
    conn = connect()
    now = _now()
    with conn:
        conn.execute("INSERT INTO match_points (match_id, team, created_at) VALUES (?, ?, ?)", (match_id, team, now))
        conn.execute("UPDATE matches SET updated_at = ? WHERE id = ?", (now, match_id))


#changement de serveur manuel : `player` de l'equipe `team` sert le prochain
#point (annulable comme un point, voir remove_last_point)
def add_server_change(match_id: int, team: int, player: int) -> None:
    conn = connect()
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO match_points (match_id, kind, team, player, created_at) VALUES (?, 'server', ?, ?, ?)",
            (match_id, team, player, now),
        )
        conn.execute("UPDATE matches SET updated_at = ? WHERE id = ?", (now, match_id))


#inversion manuelle des cotes (correction, annulable comme un point) : les
#changements automatiques reprennent ensuite normalement
def add_side_swap(match_id: int) -> None:
    conn = connect()
    now = _now()
    with conn:
        conn.execute(
            "INSERT INTO match_points (match_id, kind, team, created_at) VALUES (?, 'sides', 0, ?)",
            (match_id, now),
        )
        conn.execute("UPDATE matches SET updated_at = ? WHERE id = ?", (now, match_id))


#retire le dernier evenement (point, serveur, cotes) ; False s'il
#n'y en avait aucun
def remove_last_point(match_id: int) -> bool:
    conn = connect()
    with conn:
        row = conn.execute("SELECT MAX(id) AS id FROM match_points WHERE match_id = ?", (match_id,)).fetchone()
        if row["id"] is None:
            return False
        conn.execute("DELETE FROM match_points WHERE id = ?", (row["id"],))
        conn.execute("UPDATE matches SET updated_at = ? WHERE id = ?", (_now(), match_id))
    return True


#resultat du match : vainqueur (0/1) -> termine ; None -> de nouveau en cours
def set_match_result(match_id: int, winner: int | None, end_reason: str = "") -> None:
    conn = connect()
    now = _now()
    with conn:
        if winner is None:
            conn.execute(
                "UPDATE matches SET status = 'live', winner = NULL, end_reason = '', finished_at = '', "
                "updated_at = ? WHERE id = ?",
                (now, match_id),
            )
        else:
            conn.execute(
                "UPDATE matches SET status = 'finished', winner = ?, end_reason = ?, finished_at = ?, "
                "updated_at = ? WHERE id = ?",
                (winner, end_reason, now, now, match_id),
            )


def delete_match(match_id: int) -> None:
    conn = connect()
    with conn:
        conn.execute("DELETE FROM matches WHERE id = ?", (match_id,))
