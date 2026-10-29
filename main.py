import asyncio

from nicegui import app, ui

import api  # noqa: F401  (enregistre le WebSocket /ws, voir api.py)
import database
from logos import LOGOS
from photos import PHOTOS
from admin import build_match_list
from app_config import SERVER_PORT, load_config
from layout import BACKGROUND_PATH, BACKGROUND_URL, FLAGS_DIR, FLAGS_URL, build_header
from paths import resource_path
from home import build_home
from players import build_player_list
from tournaments import build_tournament_list
from system_page import build_system_page
from umpire import build_umpire_match, build_umpire_selection

#icone de l'onglet du navigateur : symbole du logo du Pole superieur
#audiovisuel de Villefontaine (assets/psav_logo.png), recadre en carre
ICON_PATH = resource_path("assets", "favicon.png")

#dict partage par reference avec build_header (boite de dialogue
#Parametres), voir app_config.py
config = load_config()


#drapeaux des pays (assets/flags, voir countries.py) et photo de fond des
#pages (voir layout.apply_theme)
app.add_static_files(FLAGS_URL, FLAGS_DIR)
app.add_static_file(local_file=BACKGROUND_PATH, url_path=BACKGROUND_URL)

#photos des joueurs et logos des tournois (dossiers utilisateur, voir
#media.py) : apercu dans l'interface et future API
for store in (PHOTOS, LOGOS):
    store.ensure_dirs()
    app.add_static_files(store.url, store.dir)


#la creation/edition d'un match, d'un joueur ou d'un tournoi s'ouvre en fenetre
#par-dessus la liste (voir admin.build_match_dialog, players.build_player_dialog,
#tournaments.build_tournament_dialog)
#accueil : logo, acces arbitrage / administration (pas de header)
@ui.page("/")
def index() -> None:
    build_home(config)


#interface d'arbitrage : choix du match, puis saisie des points (umpire.py)
@ui.page("/umpire")
def umpire_page() -> None:
    build_umpire_selection(config)


@ui.page("/umpire/{match_id}")
def umpire_match_page(match_id: int) -> None:
    build_umpire_match(config, match_id)


#administration : adresses du serveur, etat du serveur, constantes du PC
@ui.page("/admin")
def admin_page() -> None:
    build_system_page(config)


@ui.page("/matches")
def matches_page() -> None:
    open_match_dialog = build_match_list()
    build_header(config, "matches", ("NOUVEAU MATCH", open_match_dialog))


@ui.page("/players")
def players_page() -> None:
    open_player_dialog = build_player_list()
    build_header(config, "players", ("NOUVEAU JOUEUR", open_player_dialog))


@ui.page("/tournaments")
def tournaments_page() -> None:
    open_tournament_dialog = build_tournament_list()
    build_header(config, "tournaments", ("NOUVEAU TOURNOI", open_tournament_dialog))


#ouverture (et creation/migration si besoin) de la base au demarrage,
#pour qu'une erreur de fichier soit visible tout de suite dans la console
@app.on_startup
async def startup() -> None:
    database.connect()
    print(f"Base SQLite -> {database.DB_PATH}")
    PHOTOS.cleanup_pending()
    LOGOS.cleanup_pending()
    asyncio.get_running_loop().set_exception_handler(_ignore_connection_reset)


#Windows (boucle Proactor) affiche une trace "ConnectionResetError
#[WinError 10054]" chaque fois qu'un navigateur coupe brutalement une
#connexion (onglet recharge/ferme) : sans consequence, mais elle noyait la
#console. Seule cette erreur est ignoree, les autres restent affichees.
def _ignore_connection_reset(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    if isinstance(context.get("exception"), ConnectionResetError):
        return
    loop.default_exception_handler(context)


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Tennis Data Manager",
        port=SERVER_PORT,
        reload=False,
        favicon=ICON_PATH if ICON_PATH.exists() else None,
    )
