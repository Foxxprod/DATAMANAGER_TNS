# Page d'accueil (sans header) : photo de court floutee + masque de
# couleur en fond, tournoi en cours (nom, ville, dates) + date/heure en haut, logo et 2 gros
# boutons ARBITRAGE / GESTION DES DONNEES centres en hauteur, credits en bas.
#
# Texte toujours clair sur cette page (fond photo assombri, commun a toutes
# les pages - voir layout.apply_theme), quel que soit le theme clair/sombre
# choisi dans Parametres.

from datetime import date, datetime

from nicegui import ui

import database
from events import tournaments_changed
from layout import apply_theme, flag, logo, tournament_logo
from models import DAYS, MONTHS

CREDITS = "Foxx Production"


def format_long_date(day: date) -> str:
    return f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} {day.year}"


#vrai bouton (focus clavier, clic sur tout son contenu) habille en tuile
#semi-transparente sur la photo
def _home_button(title: str, icon: str, color: str, url: str) -> None:
    with ui.button(color=None, on_click=lambda: ui.navigate.to(url)).props("no-caps unelevated").classes(
        f"w-96 h-52 rounded-3xl bg-slate-900/70 backdrop-blur-sm border-2 border-{color}-500 shadow-2xl "
        f"hover:bg-slate-900/90 hover:scale-[1.03] transition-transform"
    ):
        with ui.column().classes("items-center gap-4"):
            ui.icon(icon).classes(f"text-7xl text-{color}-400")
            ui.label(title).classes("text-2xl font-bold tracking-widest text-white text-center leading-tight")


def build_home(config: dict) -> None:
    apply_theme(config)
    #page fixe a la hauteur de l'ecran, sans defilement : la marge par
    #defaut de NiceGUI (.nicegui-content) ajoutee a une colonne h-screen
    #depassait de quelques pixels (pas de header ici, donc pas de decalage
    #du contenu a preserver, contrairement aux pages d'administration)
    ui.query(".nicegui-content").style("padding: 0;")
    ui.query("body").style("overflow: hidden;")

    with ui.column().classes("relative z-10 w-full h-screen overflow-hidden px-8 py-6 gap-0 items-stretch"):
        # --- tournoi en cours / date et heure ---------------------------
        with ui.row(wrap=False).classes("w-full items-start justify-between gap-6"):
            tournament_box = ui.column().classes("gap-1 min-w-0")
            with ui.column().classes("gap-0 items-end shrink-0"):
                clock_label = ui.label().classes("text-5xl font-mono font-bold leading-none text-white")
                date_label = ui.label().classes("text-lg font-bold text-slate-300 mt-1")

        #espace entre le bandeau du haut et les credits (les boutons sont
        #positionnes par-dessus, voir ci-dessous)
        ui.element("div").classes("flex-1")

        # --- credits ----------------------------------------------------
        ui.label(CREDITS).classes(
            "w-full text-center text-sm font-bold tracking-widest text-slate-300 "
            "border-t border-white/20 pt-4"
        )

    # --- boutons centres en hauteur sur l'ecran, logo accroche au-dessus ----
    #couche plein ecran : ce sont les BOUTONS qui sont au centre exact de la
    #fenetre ; le logo est en position absolue juste au-dessus d'eux et
    #n'entre donc pas dans le calcul du centrage. pointer-events : la couche
    #ne bloque pas les clics, seuls les boutons restent cliquables.
    with ui.element("div").classes(
        "fixed inset-0 z-10 flex items-center justify-center pointer-events-none"
    ):
        with ui.element("div").classes("relative pointer-events-auto"):
            #au-dessus des boutons : logo, puis titre entre 2 traits fins aussi
            #larges que la rangee des boutons (meme conteneur)
            with ui.column().classes("absolute bottom-full left-0 right-0 mb-14 items-center gap-5"):
                logo("7.5rem").classes("drop-shadow-2xl mb-5")
                ui.element("div").classes("w-full h-px bg-white/50")
                ui.label("TENNIS DATA MANAGER").classes(
                    "text-5xl font-black tracking-[0.18em] text-white text-center drop-shadow-lg"
                )
                ui.element("div").classes("w-full h-px bg-white/50")
            with ui.row(wrap=False).classes("gap-10 justify-center"):
                _home_button("ARBITRAGE", "scoreboard", "green", "/umpire")
                _home_button("GESTION DES DONNEES", "storage", "sky", "/matches")

    state = {"day": None, "tournaments": None}

    def refresh_tournament(today: date) -> None:
        tournament_box.clear()
        tournaments = database.current_tournaments(today)
        with tournament_box:
            if not tournaments:
                ui.label("Aucun tournoi en cours").classes("text-2xl font-bold text-slate-400")
            #logo du tournoi a gauche du texte (nom, puis ville et dates)
            for tournament in tournaments:
                with ui.row(wrap=False).classes("items-center gap-4 min-w-0"):
                    tournament_logo(tournament, "h-20 w-20", placeholder=False)
                    with ui.column().classes("gap-1 min-w-0"):
                        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
                            flag(tournament.country, "h-6 w-8")
                            ui.label(tournament.name).classes("text-3xl font-bold text-white truncate")
                        details = " · ".join(
                            part for part in (tournament.city, tournament.dates) if part
                        )
                        if details:
                            ui.label(details).classes("text-base text-slate-300")

    #horloge chaque seconde ; date au changement de jour ; tournoi en cours
    #relu toutes les 5 s (choix manuel possible depuis un autre poste), la
    #zone n'etant redessinee que s'il a change
    def tick() -> None:
        now = datetime.now()
        clock_label.text = now.strftime("%H:%M:%S")
        if state["day"] != now.date():
            state["day"] = now.date()
            date_label.text = format_long_date(now.date()).capitalize()
        if now.second % 5 == 0 or state["tournaments"] is None:
            current = [(t.id, t.updated_at) for t in database.current_tournaments(now.date())]
            if current != state["tournaments"]:
                state["tournaments"] = current
                refresh_tournament(now.date())

    #tournoi actif change (header, page TOURNOIS, autre poste) : affiche
    #immediatement, sans attendre la verification periodique
    def on_tournaments_changed() -> None:
        state["tournaments"] = None

    tournaments_changed.subscribe(on_tournaments_changed)
    tick()
    ui.timer(1.0, tick)
