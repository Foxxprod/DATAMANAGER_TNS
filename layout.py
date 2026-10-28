# Elements communs a toutes les pages d'administration : barre d'outils du
# haut (meme style que Biath Control Center : bandeau bg-slate-900 arrondi,
# logo, case titre blanche, boutons ronds, horloge), theme clair/sombre et
# boite de dialogue Parametres, plus quelques helpers de style partages.
#
# Theme : ui.dark_mode() pose la classe body--dark, a laquelle NiceGUI
# rattache la variante Tailwind `dark:` (voir templates/index.html de
# NiceGUI). Les classes "xxx dark:yyy" suffisent donc, sans avoir a
# reappliquer les classes a la main a chaque bascule.

from datetime import datetime
from typing import Callable

from nicegui import ui

import database
from app_config import save_config
from countries import country_name, flag_iso
from events import subscribe_for, tournaments_changed
from logos import LOGOS
from models import Tournament
from paths import resource_path
from photos import png_size

#logo complet du Pole superieur audiovisuel de Villefontaine (header et
#accueil), planete en balle de tennis, version blanche sur fond transparent
#derivee de assets/psav_logo_tennis.png (noir sur fond blanc opaque) :
#header et accueil sont sur fond sombre. L'icone d'onglet n'en garde que le symbole (favicon.png).
LOGO_PATH = resource_path("assets", "psav_logo_white.png")


#largeur/hauteur d'un PNG, lues dans son entete : permet d'afficher le
#logo dans ses proportions d'origine quel que soit le fichier fourni
def _png_ratio(path) -> float:
    with open(path, "rb") as file:
        width, height = png_size(file.read(24))
    return width / height


#logo a la hauteur `height` (unite CSS), largeur deduite de ses proportions
#d'origine : q-img a besoin d'une taille explicite, et une case aux
#mauvaises proportions rognait le logo (fit=cover par defaut de Quasar)
def logo(height: str, path=LOGO_PATH) -> ui.image:
    return ui.image(path).props("fit=contain no-spinner").style(
        f"height: {height}; width: calc({height} * {_png_ratio(path):.4f});"
    )

#photo de fond de toutes les pages (court floute + masque, voir
#apply_theme et assets/CREDITS.txt), servie par main.py
BACKGROUND_PATH = resource_path("assets", "home_background.jpg")
BACKGROUND_URL = "/background.jpg"

#fond pose sur des pseudo-elements de <body> en z-index negatif : toujours
#DERRIERE tout le contenu de la page, sans avoir a toucher au z-index des
#elements de chaque page. Photo agrandie (scale) pour que le flou ne
#laisse pas de bord clair, masque de couleur semi-transparent par-dessus.
BACKGROUND_CSS = f"""
body::before {{
    content: ""; position: fixed; inset: 0; z-index: -2;
    background: url('{BACKGROUND_URL}') center / cover no-repeat;
    filter: blur(8px); transform: scale(1.1);
}}
body::after {{
    content: ""; position: fixed; inset: 0; z-index: -1;
    background: linear-gradient(to bottom, rgba(2, 6, 23, 0.85), rgba(15, 23, 42, 0.65), rgba(2, 6, 23, 0.9));
}}
"""

#drapeaux servis en fichiers statiques (voir main.py / countries.py)
FLAGS_DIR = resource_path("assets", "flags")
FLAGS_URL = "/flags"

#onglets de navigation du header : (cle, libelle, icone, url)
#pages de gestion des donnees
NAV_ITEMS = [
    ("home", "ACCUEIL", "home", "/"),
    ("matches", "MATCHS", "sports_tennis", "/matches"),
    ("players", "JOUEURS", "groups", "/players"),
    ("tournaments", "TOURNOIS", "emoji_events", "/tournaments"),
]
#pages d'arbitrage
UMPIRE_NAV_ITEMS = [
    ("home", "ACCUEIL", "home", "/"),
    ("umpire", "MATCHS A ARBITRER", "scoreboard", "/umpire"),
]

ROUND_BUTTON_CLASSES = (
    "border border-slate-600 bg-slate-700/40 hover:bg-slate-700/60 "
    "text-slate-300 rounded-full"
)
PILL_BUTTON_CLASSES = (
    "border border-slate-600 bg-slate-700/40 hover:bg-slate-700/60 "
    "text-slate-300 font-bold rounded-full px-4"
)
ACTIVE_PILL_CLASSES = (
    "border border-slate-300 bg-slate-600/60 hover:bg-slate-600/80 "
    "text-white font-bold rounded-full px-4"
)
PRIMARY_PILL_CLASSES = (
    "border border-green-500 bg-green-600/20 hover:bg-green-600/30 "
    "text-green-400 font-bold rounded-full px-4"
)

CARD_CLASSES = (
    "w-full border border-slate-200 dark:border-slate-700 rounded-2xl "
    "bg-white dark:bg-slate-800 p-4 gap-3"
)
SECTION_TITLE_CLASSES = "text-sm font-bold tracking-wide text-slate-500"
FIELD_LABEL_CLASSES = "text-xs font-bold uppercase tracking-wide text-slate-500"

#textes des listes (matchs, joueurs, tournois) : une seule definition pour
#garder les 3 onglets homogenes
#debut commun des grilles de liste (chaque page ajoute min-w et grid-cols)
LIST_GRID_CLASSES_BASE = "grid items-center gap-x-4 px-4 "
LIST_HEADER_CLASSES = "text-sm font-bold uppercase tracking-wide text-slate-500"
LIST_TEXT_CLASSES = "text-base text-slate-800 dark:text-slate-100 truncate"
LIST_STRONG_CLASSES = "text-base font-bold text-slate-900 dark:text-slate-100 truncate"
LIST_MUTED_CLASSES = "text-base text-slate-400 truncate"
LIST_HEADER_ROW_CLASSES = (
    " w-full py-3 bg-slate-100 dark:bg-slate-900/60 border-b border-slate-200 dark:border-slate-700"
)
LIST_ROW_CLASSES = (
    " w-full py-3 border-b border-slate-100 dark:border-slate-700/60 "
    "last:border-b-0 hover:bg-slate-50 dark:hover:bg-slate-700/40"
)
#drapeau un peu plus grand dans les listes que dans les champs
LIST_FLAG_SIZE = "h-[1.1rem] w-[1.5rem]"


#texte d'une cellule de liste : `text` vide -> "-" grise. `align` :
#classe Tailwind d'alignement (text-left/text-center)
def list_cell(text: str, strong: bool = False, align: str = "text-left") -> ui.label:
    if not text:
        return ui.label("-").classes(f"{LIST_MUTED_CLASSES} {align}")
    return ui.label(text).classes(f"{LIST_STRONG_CLASSES if strong else LIST_TEXT_CLASSES} {align}")


#ligne d'entete d'une liste : columns = [(libelle, alignement)]
def list_header(grid_classes: str, columns: list[tuple[str, str]]) -> None:
    with ui.element("div").classes(grid_classes + LIST_HEADER_ROW_CLASSES):
        for text, align in columns:
            ui.label(text).classes(f"{LIST_HEADER_CLASSES} {align}")


#carte de section (equivalent des cartes PRE RACE/RACE/POST RACE de Biath
#Control Center) : titre en haut, contenu libre dans le `with`
def section_card(title: str, icon: str | None = None) -> ui.column:
    card = ui.column().classes(CARD_CLASSES)
    with card:
        with ui.row().classes("items-center gap-2"):
            if icon:
                ui.icon(icon).classes("text-lg text-slate-500")
            ui.label(title).classes(SECTION_TITLE_CLASSES)
    return card


#carte d'une liste (matchs, joueurs, tournois) : titre et filtres DANS la carte, sur
#le meme retrait (px-4) que les colonnes du tableau, pour que leurs bords
#soient alignes. Renvoie (carte, zone des filtres) ; le tableau est ajoute
#ensuite dans la carte par l'appelant.
def list_card(title: str) -> tuple[ui.column, ui.row]:
    card = ui.column().classes(CARD_CLASSES + " p-0 gap-0 overflow-hidden")
    with card:
        with ui.row(wrap=False).classes(
            "w-full items-center justify-between gap-3 px-4 py-3 "
            "border-b border-slate-200 dark:border-slate-700"
        ):
            ui.label(title).classes("text-xl font-bold tracking-wide text-slate-800 dark:text-slate-100")
            tools = ui.row(wrap=False).classes("items-center gap-3")
    return card, tools


#conteneur du corps de page, aligne sur l'inset de 12px du header (m-3)
def page_body() -> ui.column:
    return ui.column().classes("w-full px-3 pb-3 gap-3")


#drapeau du pays (code a 3 lettres, voir countries.py). Sans drapeau
#connu (pays vide, "NEU"...), une case vide de meme taille garde
#l'alignement des noms dans les listes.
def flag(country: str, size: str = "h-3.5 w-[1.2rem]") -> ui.element:
    iso = flag_iso(country)
    classes = f"{size} shrink-0 rounded-[2px]"
    if not iso:
        return ui.element("span").classes(classes)
    image = ui.element("img").props(f'src="{FLAGS_URL}/{iso}.svg" alt="{country}"').classes(
        classes + " object-cover shadow-sm ring-1 ring-slate-300/60"
    )
    image.tooltip(country_name(country))
    return image


#logo du tournoi sur une tuile blanche arrondie (lisible sur fond clair
#comme sur fond sombre : bandeau de la fiche match, accueil). Sans logo,
#case vide de meme taille si `placeholder` (alignement dans les listes).
#Utilise aussi par admin.py et home.py.
def tournament_logo(tournament: Tournament | None, size: str = "h-10 w-10", placeholder: bool = True) -> None:
    if tournament is not None and tournament.logo:
        with ui.element("div").classes(
            f"{size} shrink-0 rounded-lg bg-white p-1 flex items-center justify-center "
            "border border-slate-200 shadow-sm"
        ):
            ui.image(LOGOS.file_url(tournament.logo, tournament.updated_at)).classes("w-full h-full").props(
                "fit=contain no-spinner"
            )
    elif placeholder:
        ui.element("div").classes(f"{size} shrink-0")


#selecteur du tournoi actif dans le header : choisir un tournoi le marque
#comme tournoi en cours (comme l'etoile de la page TOURNOIS), l'effacer
#revient a la detection par les dates. Synchronise avec les autres vues et
#postes par l'evenement tournaments_changed.
def _build_tournament_selector() -> None:
    def marked_id() -> int | None:
        return next((t.id for t in database.list_tournaments() if t.is_current), None)

    def options() -> dict[int, str]:
        return {t.id: t.name for t in database.list_tournaments()}

    with ui.row(wrap=False).classes("items-center gap-2"):
        logo_box = ui.row().classes("shrink-0")
        select = ui.select(
            options(), value=marked_id(), label="Tournoi actif", with_input=True, clearable=True
        ).props("dark dense outlined options-dense").classes("w-64").tooltip(
            "Tournoi en cours (accueil, nouveaux matchs). Vide : determine par les dates."
        )

    def refresh_logo() -> None:
        logo_box.clear()
        with logo_box:
            tournament_logo(database.get_tournament(select.value) if select.value else None, placeholder=False)

    def on_change(event) -> None:
        current = marked_id()
        #valeur deja enregistree (mise a jour venue de l'evenement) : rien a faire
        if event.value == current:
            refresh_logo()
            return
        if event.value is None:
            database.set_current_tournament(current, False)
            ui.notify("Plus de tournoi actif : determine par les dates", type="info")
        else:
            database.set_current_tournament(event.value, True)
            ui.notify(f"{options().get(event.value, 'Tournoi')} est le tournoi actif", type="positive")
        tournaments_changed.emit()

    def on_tournaments_changed() -> None:
        select.set_options(options(), value=marked_id())
        refresh_logo()

    select.on_value_change(on_change)
    subscribe_for(tournaments_changed, select, on_tournaments_changed)
    refresh_logo()


def _build_clock_box() -> ui.label:
    with ui.column().classes("h-full justify-center items-center px-4 gap-0"):
        ui.label("HEURE").classes(
            "text-[10px] font-bold tracking-wide text-slate-500 whitespace-nowrap"
        )
        return ui.label().classes(
            "text-2xl font-mono font-bold leading-none text-slate-900 whitespace-nowrap"
        )


#texte compresse horizontalement pour tenir dans sa case (noms du tableau
#des scores) : un element .fit-x contient UN enfant (le texte) ; si celui-ci
#est plus large que la case, il est reduit en X (scaleX) au lieu d'agrandir
#la case ou d'etre coupe. Le CSS seul ne sait pas le faire : le script
#remesure a chaque changement de la page et au redimensionnement.
FIT_X_CSS = """
.fit-x { overflow: hidden; white-space: nowrap; }
.fit-x > * { display: inline-flex; transform-origin: left center; white-space: nowrap; }
"""
FIT_X_SCRIPT = """
<script>
(() => {
    const fit = (box) => {
        const inner = box.firstElementChild;
        if (!inner) return;
        inner.style.transform = "none";
        const available = box.clientWidth, needed = inner.scrollWidth;
        inner.style.transform = available > 0 && needed > available ? `scaleX(${available / needed})` : "none";
    };
    const fitAll = () => document.querySelectorAll(".fit-x").forEach(fit);
    let pending = false;
    const schedule = () => {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; fitAll(); });
    };
    new MutationObserver(schedule).observe(document.body, {childList: true, subtree: true, characterData: true});
    window.addEventListener("resize", schedule);
    schedule();
})();
</script>
"""


#theme clair/sombre + fond de page (photo floutee, voir BACKGROUND_CSS),
#commun a toutes les pages (y compris l'accueil, qui n'a pas de header).
#Renvoie le ui.dark_mode pour pouvoir le basculer en direct (boite de
#dialogue Parametres). Les cartes restent opaques (blanches/sombres selon
#le theme) par-dessus la photo.
def apply_theme(config: dict) -> ui.dark_mode:
    dark_mode = ui.dark_mode(config["dark_mode"])
    ui.query("body").classes("bg-slate-900")
    ui.add_css(BACKGROUND_CSS + FIT_X_CSS)
    ui.add_body_html(FIT_X_SCRIPT)
    #meme reset que Biath Control Center : padding gauche/droite seulement,
    #Quasar calcule lui-meme le padding-top qui pousse le contenu sous le
    #header (position fixed)
    ui.query(".nicegui-content").style("padding-left: 0; padding-right: 0;")
    return dark_mode


#construit la barre d'outils du haut (gestion des donnees et arbitrage) :
#logo (retour a l'accueil), titre du logiciel et onglets a gauche ; bouton
#d'action, Parametres et horloge a droite. `active` : cle de l'onglet
#courant (voir NAV_ITEMS / UMPIRE_NAV_ITEMS, None = aucun). `primary_action` :
#(libelle, action) du bouton vert de la page (ex: NOUVEAU MATCH -> ouverture
#de la fenetre de creation), masque si None. `tournament_selector` : selecteur
#du tournoi actif (pages de gestion des donnees uniquement).
def build_header(
    config: dict,
    active: str | None,
    primary_action: tuple[str, Callable] | None = None,
    nav_items: list[tuple[str, str, str, str]] = NAV_ITEMS,
    tournament_selector: bool = True,
) -> None:
    dark_mode = apply_theme(config)

    with ui.dialog() as settings_dialog, ui.card().classes("gap-3 w-[28rem] max-w-[95vw]"):
        ui.label("Parametres").classes("text-lg font-bold")
        dark_switch = ui.switch("Mode sombre", value=config["dark_mode"])
        title_input = ui.input("Titre du logiciel", value=config["software_title"]).classes("w-full")

        def on_settings_save() -> None:
            config["dark_mode"] = dark_switch.value
            config["software_title"] = title_input.value.strip() or config["software_title"]
            save_config(config)
            dark_mode.set_value(config["dark_mode"])
            software_title_label.text = config["software_title"]
            settings_dialog.close()
            ui.notify("Parametres enregistres", type="positive")

        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=settings_dialog.close).props("flat")
            ui.button("Enregistrer", on_click=on_settings_save)

    with ui.header(wrap=False).classes(
        "items-stretch justify-between bg-slate-900 text-white p-0 "
        "m-3 rounded-2xl overflow-hidden"
    ):
        with ui.row(wrap=False).classes("items-stretch gap-0 min-w-0"):
            with ui.row().classes("items-center px-4 py-3 cursor-pointer").on(
                "click", lambda: ui.navigate.to("/")
            ).tooltip("Accueil"):
                logo("3rem")

            with ui.row().classes("h-full items-center bg-white px-4 min-w-0 flex-1"):
                software_title_label = ui.label(config["software_title"]).classes(
                    "font-bold text-slate-900 truncate min-w-0"
                ).style("font-size: clamp(0.7rem, 1.4vw, 1.125rem);")

            with ui.row(wrap=False).classes("items-center gap-2 px-4 py-3").style("flex-shrink: 0;"):
                for key, label, icon, url in nav_items:
                    ui.button(
                        label, icon=icon, color=None, on_click=lambda u=url: ui.navigate.to(u)
                    ).classes(ACTIVE_PILL_CLASSES if key == active else PILL_BUTTON_CLASSES)

        with ui.row(wrap=False).classes("items-stretch gap-0").style("flex-shrink: 0;"):
            with ui.row(wrap=False).classes("items-center gap-2 px-4 py-3"):
                if tournament_selector:
                    _build_tournament_selector()
                if primary_action is not None:
                    action_label, action = primary_action
                    ui.button(
                        action_label, icon="add", color=None, on_click=lambda: action()
                    ).classes(PRIMARY_PILL_CLASSES)
                ui.button(
                    icon="settings", color=None, on_click=settings_dialog.open
                ).classes(ROUND_BUTTON_CLASSES).props("round").tooltip("Parametres")

            with ui.row(wrap=False).classes("h-full items-stretch border-l border-slate-700 bg-white gap-0"):
                clock_label = _build_clock_box()

    def update_clock() -> None:
        clock_label.text = datetime.now().strftime("%H:%M:%S")

    update_clock()
    ui.timer(1.0, update_clock)
