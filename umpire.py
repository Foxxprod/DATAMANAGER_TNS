# Interface d'arbitrage, pensee pour un operateur novice :
#   - /umpire            : choix du match a arbitrer (grandes cartes)
#   - /umpire/<id>       : avant le match, choix du service puis "DEBUTER LE
#                          MATCH" ; pendant le match, tableau des scores et 2
#                          tres gros boutons POINT, annulation du dernier point
#
# Plusieurs matchs s'arbitrent en parallele, un par poste (onglet). Un match
# ouvert sur un autre poste est signale dans la selection (_controllers) et
# il faut confirmer pour en prendre la main. Chaque changement est enregistre
# point par point (database.add_point) et diffuse (events.match_scored) aux
# autres ecrans ouverts.

from datetime import date, datetime
from itertools import groupby

from nicegui import Client, context, ui

import database
from events import match_scored, subscribe_for
from layout import (HEADER_HEIGHT, UMPIRE_FIT, UMPIRE_MATCH_FIT, UMPIRE_NAV_ITEMS, build_header, flag,
                    full_height, page_body, tournament_logo)
from models import CATEGORY_LABELS, DISPLAY_STATUSES, Match, format_day
from players import player_summary
from scoreboard import scoreboard, team_label
from scoring import ScoreState, is_changeover, match_state, point_stake

#poste (client NiceGUI) qui arbitre chaque match : {match_id: client_id}
_controllers: dict[int, str] = {}

#couleurs des 2 equipes (boutons POINT, choix du service)
TEAM_COLORS = ["sky", "amber"]

STAKE_LABELS = {"match": "BALLE DE MATCH", "set": "BALLE DE SET", "break": "BALLE DE BREAK"}
STATUS_ORDER = {"live": 0, "upcoming": 1, "scheduled": 2, "finished": 3}


#id du poste qui arbitre ce match, s'il est encore connecte
def _controller(match_id: int) -> str | None:
    client_id = _controllers.get(match_id)
    client = Client.instances.get(client_id) if client_id else None
    if client is None or client.is_deleted:
        _controllers.pop(match_id, None)
        return None
    return client_id


def _take_control(match_id: int) -> None:
    client = context.client
    _controllers[match_id] = client.id

    def release() -> None:
        if _controllers.get(match_id) == client.id:
            _controllers.pop(match_id, None)

    client.on_delete(release)


def _status_chip(status: str, big: bool = False) -> None:
    label, color = DISPLAY_STATUSES.get(status, (status.upper(), "slate"))
    ui.label(label).classes(
        ("text-base px-5 py-2" if big else "text-sm px-4 py-1.5")
        + f" font-bold tracking-wide rounded-full text-center whitespace-nowrap "
        f"border border-{color}-500 bg-{color}-600/20 text-{color}-500"
    )


#header des pages d'arbitrage : meme bandeau que la gestion des donnees,
#avec les onglets d'arbitrage et sans selecteur de tournoi
def _umpire_header(config: dict, active: str | None, fit: tuple[int, int] = UMPIRE_FIT) -> None:
    build_header(config, active, nav_items=UMPIRE_NAV_ITEMS, tournament_selector=False, fit=fit)


#score abrege pour les cartes de selection : "6-4 3-2" + points du jeu
def _short_score(match: Match, state: ScoreState) -> str:
    parts = []
    for index, games in enumerate(state.sets):
        tiebreak = state.tiebreaks[index]
        parts.append(f"{tiebreak[0]}-{tiebreak[1]}" if state.super_tiebreak_sets[index] else f"{games[0]}-{games[1]}")
    if not state.finished:
        if state.super_tiebreak:
            parts.append(f"[{state.points[0]}-{state.points[1]}]")
        else:
            parts.append(f"{state.games[0]}-{state.games[1]}")
            labels = state.point_labels(match.format.no_ad)
            parts.append(f"({labels[0]}-{labels[1]})")
    return "  ".join(parts)


# ---------------------------------------------------------------------------
# Selection du match
# ---------------------------------------------------------------------------

def build_umpire_selection(config: dict) -> None:
    _umpire_header(config, "umpire")
    state = {"tab": "all", "signature": None}

    with ui.dialog() as takeover_dialog, ui.card().classes("gap-3 w-[28rem]"):
        ui.label("Match deja arbitre sur un autre poste").classes("text-lg font-bold")
        ui.label(
            "Un autre poste a ce match ouvert. Si vous continuez, vous en prenez la main : "
            "ne saisissez pas les points a deux en meme temps."
        ).classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=lambda: takeover_dialog.submit(False)).props("flat")
            ui.button("Prendre la main", color=None, on_click=lambda: takeover_dialog.submit(True)).classes(
                "bg-amber-600 text-white"
            )

    async def open_match(match: Match) -> None:
        if _controller(match.id) not in (None, context.client.id) and not await takeover_dialog:
            return
        ui.navigate.to(f"/umpire/{match.id}")

    def load() -> list[tuple[Match, ScoreState | None, str]]:
        now = datetime.now()
        rows = []
        for match in database.list_matches():
            score = match_state(match, database.get_points(match.id)) if match.first_server is not None else None
            rows.append((match, score, match.display_status(now)))
        return rows

    def signature(rows) -> tuple:
        return tuple((m.id, m.updated_at, status, _controller(m.id)) for m, _, status in rows)

    @ui.refreshable
    def match_cards() -> None:
        rows = load()
        state["signature"] = signature(rows)
        #filtres : "todo" (a arbitrer), "done" (termines), "all" (tous)
        tab = state["tab"]
        if tab != "all":
            rows = [row for row in rows if (row[2] == "finished") == (tab == "done")]
        #regroupes par jour (sans date en dernier) ; dans un jour, matchs en
        #cours d'abord, puis par heure
        rows.sort(key=lambda r: (not r[0].scheduled_date, r[0].scheduled_date, STATUS_ORDER.get(r[2], 9),
                                 r[0].scheduled_time, r[0].id))
        if not rows:
            with ui.column().classes("w-full items-center gap-3 py-16"):
                ui.icon("sports_tennis").classes("text-6xl text-slate-300")
                empty = {"done": "Aucun match termine", "all": "Aucun match"}.get(tab, "Aucun match a arbitrer")
                ui.label(empty).classes(
                    "text-lg text-slate-300"
                )
            return
        today = date.today().isoformat()
        for day, day_rows in groupby(rows, key=lambda r: r[0].scheduled_date):
            day_rows = list(day_rows)
            with ui.column().classes("w-full gap-4"):
                #titre du jour + trait de separation
                with ui.row(wrap=False).classes("w-full items-center gap-3 pb-2 border-b-2 border-white/25"):
                    ui.icon("event").classes("text-2xl text-slate-300")
                    ui.label(format_day(day) if day else "Date non programmee").classes(
                        "text-2xl font-bold tracking-wide text-white"
                    )
                    if day == today:
                        ui.label("AUJOURD'HUI").classes(
                            "text-xs font-bold tracking-wide rounded-full px-3 py-0.5 "
                            "border border-sky-400 bg-sky-500/30 text-sky-200"
                        )
                    ui.label(f"{len(day_rows)} match{'s' if len(day_rows) > 1 else ''}").classes(
                        "text-base text-slate-300"
                    )
                with ui.element("div").classes("w-full grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4"):
                    for match, score, status in day_rows:
                        _match_card(match, score, status, _controller(match.id) not in (None, context.client.id),
                                    open_match, dimmed=tab == "all" and status == "finished")

    def check_updates() -> None:
        if signature(load()) != state["signature"]:
            match_cards.refresh()

    with page_body().classes("max-w-[110rem] mx-auto"):
        with ui.row(wrap=False).classes("w-full items-center justify-between gap-4 mt-6"):
            ui.label("CHOISISSEZ LE MATCH A ARBITRER").classes("text-2xl font-bold tracking-wide text-white")

            def on_tab(event) -> None:
                state["tab"] = event.value
                match_cards.refresh()

            ui.toggle({"all": "Tous", "todo": "A arbitrer", "done": "Termines"}, value="all",
                      on_change=on_tab).props(
                "no-caps rounded"
            ).classes("bg-white dark:bg-slate-800")
        cards_box = ui.column().classes("w-full gap-8 mt-2")
        with cards_box:
            match_cards()

    subscribe_for(match_scored, cards_box, match_cards.refresh)
    ui.timer(3.0, check_updates)


#`dimmed` : carte legerement grisee (match termine affiche avec le filtre
#"Tous"), redevient nette au survol
def _match_card(match: Match, score: ScoreState | None, status: str, locked: bool, on_open,
                dimmed: bool = False) -> None:
    tournament = match.tournament
    with ui.column().classes(
        "w-full gap-3 rounded-2xl p-5 cursor-pointer bg-white dark:bg-slate-800 shadow-lg "
        "border-2 border-transparent hover:border-sky-500 transition "
        + ("opacity-60 grayscale-[40%] hover:opacity-100 hover:grayscale-0" if dimmed else "")
    ).on("click", lambda m=match: on_open(m)):
        with ui.row(wrap=False).classes("w-full items-center justify-between gap-3"):
            _status_chip(status)
            #le jour est dans le titre du groupe : seulement l'heure ici
            ui.label(match.scheduled_time or "--:--").classes(
                "text-2xl font-mono font-bold text-slate-700 dark:text-slate-200"
            )
        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            tournament_logo(tournament, placeholder=False)
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(tournament.name if tournament else "Tournoi ?").classes(
                    "text-lg font-bold text-slate-900 dark:text-slate-100 truncate"
                )
                details = [match.round, CATEGORY_LABELS.get(match.category, match.category), match.court]
                ui.label(" · ".join(p for p in details if p)).classes("text-sm text-slate-500 truncate")
        with ui.column().classes("w-full gap-1 rounded-xl bg-slate-100 dark:bg-slate-900/60 px-4 py-3"):
            for index, team in enumerate((match.team1, match.team2)):
                with ui.row(wrap=False).classes("w-full items-center gap-2 min-w-0"):
                    if score is not None and score.winner == index:
                        ui.icon("check_circle").classes("text-green-500 text-xl")
                    #drapeaux + noms compresses en X s'ils depassent de la carte (.fit-x)
                    with ui.element("div").classes("fit-x flex-1 min-w-0"):
                        with ui.element("div").classes("items-center gap-2"):
                            for position, player in enumerate(team):
                                if position:
                                    ui.label("/").classes("text-xl text-slate-400")
                                flag(player.country, "h-5 w-7")
                                ui.label(player.long_name if len(team) == 1 else player.short_name).classes(
                                    "text-xl font-bold text-slate-900 dark:text-slate-100"
                                )
                            if not team:
                                ui.label("A definir").classes("text-xl italic text-slate-400")
        if score is not None:
            ui.label(_short_score(match, score)).classes(
                "text-xl font-mono font-bold text-slate-700 dark:text-slate-200"
            )
        if locked:
            ui.label("ARBITRE SUR UN AUTRE POSTE").classes(
                "text-xs font-bold tracking-wide rounded-full px-3 py-1 border border-amber-500 "
                "bg-amber-500/20 text-amber-600 self-start"
            )


# ---------------------------------------------------------------------------
# Arbitrage d'un match
# ---------------------------------------------------------------------------

#boutons POINT : le contenu interne du bouton Quasar (.q-btn__content) ne
#retrecit pas par defaut - un nom long elargissait alors le bouton hors de
#l'ecran au lieu d'etre compresse (.fit-x)
POINT_BUTTON_CSS = ".point-button .q-btn__content { width: 100%; min-width: 0; }"


def build_umpire_match(config: dict, match_id: int) -> None:
    _umpire_header(config, None, UMPIRE_MATCH_FIT)
    ui.add_css(POINT_BUTTON_CSS)
    if database.get_match(match_id) is None:
        with page_body():
            ui.label(f"Match #{match_id} introuvable").classes("text-2xl text-white")
        return
    _take_control(match_id)

    #setup_* : choix en cours avant le debut du match (service, cote de depart)
    #own_updates : evenements match_scored emis par CE poste, a ne pas traiter
    #une 2e fois a leur reception (l'ecran est deja rafraichi directement)
    view = {"setup_server": None, "setup_players": [0, 0], "setup_left": None, "own_updates": 0}

    #match None : supprime entre-temps depuis la gestion des donnees
    def load() -> tuple[Match | None, list, ScoreState | None]:
        match = database.get_match(match_id)
        if match is None:
            return None, [], None
        points = database.get_points(match_id)
        score = match_state(match, points) if match.first_server is not None else None
        return match, points, score

    def changed() -> None:
        view["own_updates"] += 1
        match_scored.emit(match_id)
        content.refresh()

    #point marque depuis un autre poste (prise de main) : mise a jour ici aussi
    def on_match_scored(updated_id: int) -> None:
        if updated_id != match_id:
            return
        if view["own_updates"]:
            view["own_updates"] -= 1
            return
        content.refresh()

    # --- actions -------------------------------------------------------------
    def start_match() -> None:
        if view["setup_server"] is None:
            ui.notify("Selectionnez d'abord le premier service", type="warning")
            return
        if view["setup_left"] is None:
            ui.notify("Selectionnez d'abord le joueur a gauche", type="warning")
            return
        database.start_match(match_id, view["setup_server"], *view["setup_players"], view["setup_left"])
        ui.notify("Match debute", type="positive")
        changed()

    def score_point(team: int) -> None:
        match, points, score = load()
        if score is None or match.status == "finished":
            return
        database.add_point(match_id, team)
        score = match_state(match, points + [team])
        if score.finished:
            database.set_match_result(match_id, score.winner)
            ui.notify(f"Fin du match : victoire de {team_label(match.team1 if score.winner == 0 else match.team2)}",
                      type="positive")
        changed()

    #annulation du dernier evenement, toujours apres confirmation (bouton ou
    #touche retour arriere) : le message precise ce qui va etre annule
    async def undo() -> None:
        match, points, score = load()
        if score is None:
            return
        teams = (match.team1, match.team2)
        if match.end_reason:
            undo_text.text = "L'abandon sera annule et le match reprendra."
        elif points and points[-1] == ("sides",):
            undo_text.text = "La derniere inversion des cotes sera annulee."
        elif points and isinstance(points[-1], tuple):
            undo_text.text = "Le dernier changement de serveur sera annule."
        elif points:
            undo_text.text = f"Le dernier point (gagne par {team_label(teams[points[-1]])}) sera annule."
        if (match.end_reason or points) and not await undo_dialog:
            return
        if match.end_reason:
            database.set_match_result(match_id, None)
            ui.notify("Abandon annule : le match reprend", type="info")
        elif points:
            database.remove_last_point(match_id)
            if match.status == "finished":
                database.set_match_result(match_id, None)
            if points[-1] == ("sides",):
                ui.notify("Inversion des cotes annulee", type="info")
            elif isinstance(points[-1], tuple):
                ui.notify("Changement de serveur annule", type="info")
            else:
                ui.notify("Dernier point annule", type="info")
        else:
            if not await reset_dialog:
                return
            database.reset_match(match_id)
            ui.notify("Debut du match annule", type="info")
        changed()

    #correction manuelle du service : enregistree comme un evenement du match
    #(annulable avec "Annuler le dernier point")
    async def change_server() -> None:
        choice = await server_dialog
        if choice is None:
            return
        team, player = choice
        match, _, _ = load()
        database.add_server_change(match_id, team, player)
        ui.notify(f"Service : {(match.team1, match.team2)[team][player].short_name}", type="info")
        changed()

    #remise a zero complete : tous les points effaces, retour au choix du service
    #nature du dernier point (statistiques) : "" efface la nature
    def set_nature(nature: str) -> None:
        database.set_last_point_nature(match_id, nature)
        changed()

    async def reset_all() -> None:
        if not await reset_all_dialog:
            return
        database.reset_match(match_id)
        view["setup_server"] = view["setup_left"] = None
        ui.notify("Match remis a zero", type="info")
        changed()

    async def retire() -> None:
        retiring = await retire_dialog
        if retiring is None:
            return
        match, _, _ = load()
        database.set_match_result(match_id, 1 - retiring, "RET")
        ui.notify(f"Abandon de {team_label(match.team1 if retiring == 0 else match.team2)}", type="info")
        changed()

    #correction des cotes (les changements automatiques ne correspondent pas
    #au terrain) : enregistree comme un evenement du match, diffusee aux
    #graphiques et annulable avec "Annuler le dernier point"
    def swap() -> None:
        database.add_side_swap(match_id)
        ui.notify("Cotes inverses", type="info")
        changed()

    with ui.dialog() as undo_dialog, ui.card().classes("gap-3 w-[30rem]"):
        ui.label("Annuler le dernier point ?").classes("text-lg font-bold")
        undo_text = ui.label().classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Non", on_click=lambda: undo_dialog.submit(False)).props("flat")
            ui.button("Confirmer l'annulation", color=None, on_click=lambda: undo_dialog.submit(True)).classes(
                "bg-slate-900 text-white"
            )

    with ui.dialog() as reset_dialog, ui.card().classes("gap-3 w-[28rem]"):
        ui.label("Annuler le debut du match ?").classes("text-lg font-bold")
        ui.label("Aucun point n'a ete joue : le match repasse en 'programme' et le service sera a rechoisir.").classes(
            "text-sm text-slate-500"
        )
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Non", on_click=lambda: reset_dialog.submit(False)).props("flat")
            ui.button("Oui, annuler", color=None, on_click=lambda: reset_dialog.submit(True)).classes(
                "bg-red-600 text-white"
            )

    with ui.dialog() as server_dialog, ui.card().classes("gap-4 w-[34rem]"):
        ui.label("Qui sert le prochain point ?").classes("text-lg font-bold")
        ui.label("Correction manuelle : l'alternance normale du service reprend ensuite.").classes(
            "text-sm text-slate-500"
        )
        server_buttons = ui.column().classes("w-full gap-2")
        ui.button("Annuler", on_click=lambda: server_dialog.submit(None)).props("flat").classes("self-end")

    with ui.dialog() as reset_all_dialog, ui.card().classes("gap-3 w-[30rem]"):
        ui.label("Remettre le match a zero ?").classes("text-lg font-bold")
        ui.label(
            "Tous les points saisis seront effaces et le match reviendra au choix du service. "
            "Cette action ne peut pas etre annulee."
        ).classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Non", on_click=lambda: reset_all_dialog.submit(False)).props("flat")
            ui.button("Oui, tout remettre a zero", color=None, on_click=lambda: reset_all_dialog.submit(True)).classes(
                "bg-red-600 text-white"
            )

    with ui.dialog() as retire_dialog, ui.card().classes("gap-4 w-[34rem]"):
        ui.label("Abandon : quel joueur abandonne ?").classes("text-lg font-bold")
        retire_buttons = ui.column().classes("w-full gap-2")
        ui.button("Annuler", on_click=lambda: retire_dialog.submit(None)).props("flat").classes("self-end")

    # --- ecrans --------------------------------------------------------------
    @ui.refreshable
    def content() -> None:
        match, points, score = load()
        if match is None:
            with ui.column().classes("w-full items-center gap-4 rounded-2xl bg-white dark:bg-slate-800 p-10"):
                ui.icon("delete_forever").classes("text-6xl text-slate-400")
                ui.label("Ce match a ete supprime dans la gestion des donnees.").classes("text-xl font-bold")
                ui.button("RETOUR AUX MATCHS", icon="arrow_back", on_click=lambda: ui.navigate.to("/umpire")).props(
                    "no-caps unelevated"
                )
            return
        teams = (match.team1, match.team2)
        retire_buttons.clear()
        with retire_buttons:
            for index, team in enumerate(teams):
                ui.button(team_label(team, short=False), on_click=lambda i=index: retire_dialog.submit(i)).props(
                    "no-caps outline"
                ).classes("w-full text-lg")
        server_buttons.clear()
        current = score.server if score is not None and not score.finished else None
        with server_buttons:
            for index, team in enumerate(teams):
                for position, player in enumerate(team):
                    serving = current == (index, position)
                    ui.button(
                        player.long_name + ("  (au service)" if serving else ""), icon="sports_tennis",
                        on_click=lambda i=index, p=position: server_dialog.submit((i, p)),
                    ).props("no-caps " + ("unelevated" if serving else "outline")).classes("w-full text-lg")

        _match_banner(match)
        if score is None:
            _setup_view(match, view, start_match, content.refresh)
        else:
            _live_view(match, points, score, view, score_point,
                       {"undo": undo, "retire": retire, "swap": swap, "server": change_server, "reset": reset_all,
                        "nature": set_nature},
                       database.get_natures(match_id))

    #page a la hauteur de l'ecran (header et marges de NiceGUI deduits) : les
    #boutons POINT (flex-1) prennent toute la hauteur restante
    with page_body().classes("max-w-[110rem] mx-auto").style(
        f"min-height: {full_height(minus=HEADER_HEIGHT + 32)};"
    ) as body:
        content()

    subscribe_for(match_scored, body, on_match_scored, expect_args=True)

    #raccourcis : fleches gauche/droite = point pour le joueur affiche de ce
    #cote, retour arriere = annuler le dernier point. Actifs meme quand un
    #bouton a le focus (sinon, apres un clic, les touches seraient ignorees).
    def on_key(event) -> None:
        if not event.action.keydown or event.action.repeat:
            return
        match, _, score = load()
        if score is None or score.finished:
            if event.key.backspace and score is not None:
                return undo()
            return
        left = score.left_team(match.first_left or 0)
        right = 1 - left
        if event.key.arrow_left:
            score_point(left)
        elif event.key.arrow_right:
            score_point(right)
        elif event.key.backspace:
            return undo()

    ui.keyboard(on_key=on_key, ignore=["input", "textarea"])


def _match_banner(match: Match) -> None:
    tournament = match.tournament
    with ui.row(wrap=False).classes("w-full items-center justify-between gap-4 rounded-2xl bg-white dark:bg-slate-800 px-5 py-3 shadow"):
        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            tournament_logo(tournament, "h-12 w-12", placeholder=False)
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(tournament.name if tournament else "Tournoi ?").classes(
                    "text-xl font-bold text-slate-900 dark:text-slate-100 truncate"
                )
                details = [match.round, CATEGORY_LABELS.get(match.category, match.category), match.court]
                ui.label(" · ".join(p for p in details if p)).classes("text-sm font-bold uppercase text-slate-500")
        _status_chip(match.display_status(datetime.now()), big=True)


#avant le match : joueurs, choix du service, bouton DEBUTER
def _setup_view(match: Match, view: dict, on_start, refresh) -> None:
    teams = (match.team1, match.team2)
    if not match.team1 or not match.team2:
        with ui.column().classes("w-full items-center gap-3 rounded-2xl bg-white dark:bg-slate-800 p-10"):
            ui.icon("group_off").classes("text-6xl text-slate-400")
            ui.label("Les joueurs de ce match ne sont pas encore definis.").classes("text-xl font-bold")
            ui.label("Completez le match dans GESTION DES DONNEES avant de l'arbitrer.").classes("text-slate-500")
        return

    with ui.element("div").classes("w-full grid grid-cols-[1fr_auto_1fr] gap-6 items-start"):
        for index, team in enumerate(teams):
            if index:
                ui.label("VS").classes("self-center text-3xl font-bold text-white")
            with ui.column().classes("w-full gap-4 rounded-2xl bg-white dark:bg-slate-800 p-5 shadow"):
                for player in team:
                    player_summary(player)

    with ui.column().classes("w-full items-center gap-5 rounded-2xl bg-white dark:bg-slate-800 p-6 shadow"):
        ui.label("SELECTIONNER LE PREMIER SERVICE").classes("text-2xl font-bold tracking-wide")
        with ui.row(wrap=False).classes("w-full gap-6 justify-center"):
            for index, team in enumerate(teams):
                color = TEAM_COLORS[index]
                selected = view["setup_server"] == index

                def choose(i=index) -> None:
                    view["setup_server"] = i
                    refresh()

                with ui.button(color=None, on_click=choose).props("no-caps unelevated").classes(
                    f"flex-1 max-w-[32rem] h-28 rounded-2xl border-4 text-2xl font-bold "
                    + (f"bg-{color}-500 border-{color}-300 text-white" if selected
                       else f"bg-{color}-500/10 border-{color}-500/40 text-{color}-600 dark:text-{color}-300")
                ):
                    with ui.row(wrap=False).classes("items-center gap-3"):
                        if selected:
                            ui.icon("sports_tennis").classes("text-3xl")
                        ui.label(team_label(team, short=len(team) > 1))

        #double : quel joueur de chaque equipe sert en premier pour son equipe
        if match.is_double:
            with ui.row(wrap=False).classes("w-full gap-6 justify-center"):
                for index, team in enumerate(teams):
                    with ui.column().classes("flex-1 max-w-[32rem] items-center gap-1"):
                        ui.label(f"Premier serveur de l'equipe {index + 1}").classes(
                            "text-sm font-bold uppercase text-slate-500"
                        )

                        def choose_player(event, i=index) -> None:
                            view["setup_players"][i] = event.value

                        ui.toggle(
                            {position: player.short_name for position, player in enumerate(team)},
                            value=view["setup_players"][index], on_change=choose_player,
                        ).props("no-caps")

        _side_choice(teams, view, refresh)

        ready = view["setup_server"] is not None and view["setup_left"] is not None
        ui.button("DEBUTER LE MATCH", icon="play_arrow", color=None, on_click=on_start).props(
            "no-caps unelevated"
        ).classes(
            "h-20 px-12 rounded-2xl text-2xl font-bold text-white "
            + ("bg-green-600 hover:bg-green-500" if ready else "bg-slate-400")
        )


#cote de depart : quel joueur est a GAUCHE vu depuis la chaise d'arbitre
#(reference fixe du court, utilisee par les graphiques au sol en realite
#augmentee) ; apercu du court une fois choisi
def _side_choice(teams: tuple, view: dict, refresh) -> None:
    ui.element("div").classes("w-full h-px bg-slate-200 dark:bg-slate-700")
    with ui.column().classes("items-center gap-0"):
        ui.label("SELECTIONNER LE JOUEUR A GAUCHE").classes("text-2xl font-bold tracking-wide")
        ui.label("vu depuis la chaise d'arbitre, au debut du match").classes("text-sm text-slate-500")
    with ui.row(wrap=False).classes("w-full gap-6 justify-center"):
        for index, team in enumerate(teams):
            color = TEAM_COLORS[index]
            selected = view["setup_left"] == index

            def choose(i=index) -> None:
                view["setup_left"] = i
                refresh()

            with ui.button(color=None, on_click=choose).props("no-caps unelevated").classes(
                f"flex-1 max-w-[32rem] h-20 rounded-2xl border-4 text-xl font-bold "
                + (f"bg-{color}-500 border-{color}-300 text-white" if selected
                   else f"bg-{color}-500/10 border-{color}-500/40 text-{color}-600 dark:text-{color}-300")
            ):
                with ui.row(wrap=False).classes("items-center gap-3"):
                    if selected:
                        ui.icon("west").classes("text-3xl")
                    ui.label(team_label(team, short=len(team) > 1))

    if view["setup_left"] is None:
        return
    left = view["setup_left"]
    with ui.row(wrap=False).classes(
        "w-full max-w-[66rem] h-16 items-stretch rounded-xl overflow-hidden border-2 border-white shadow"
    ):
        for position, team_index in enumerate((left, 1 - left)):
            if position:
                ui.element("div").classes("w-1.5 bg-white")
            with ui.row(wrap=False).classes(
                f"flex-1 min-w-0 items-center justify-center gap-2 px-3 bg-{TEAM_COLORS[team_index]}-500 text-white"
            ):
                ui.icon("west" if position == 0 else "east").classes("text-2xl")
                ui.label(team_label(teams[team_index])).classes("text-lg font-bold truncate")


#bandeau d'information du point a venir (balle de break/set/match, tie-break,
#point decisif, changement de cote)
def _situation(match: Match, points: list[int], score: ScoreState) -> list[tuple[str, str]]:
    infos = []
    if score.finished:
        return infos
    teams = (match.team1, match.team2)
    for team in (0, 1):
        stake = point_stake(match.format, match.first_server or 0,
                            (match.first_server_1, match.first_server_2), points, team)
        if stake:
            infos.append((f"{STAKE_LABELS[stake]} pour {team_label(teams[team])}", "amber"))
    if score.super_tiebreak:
        infos.append(("SUPER TIE-BREAK", "violet"))
    elif score.in_tiebreak:
        infos.append(("JEU DECISIF (TIE-BREAK)", "violet"))
    elif match.format.no_ad and score.points == [3, 3]:
        infos.append(("POINT DECISIF", "violet"))
    if is_changeover(score, points):
        infos.append(("CHANGEMENT DE COTE", "sky"))
    return infos


#pendant / apres le match : tableau des scores, situation, boutons POINT, actions
#barre facultative "nature du dernier point" (statistiques : aces, doubles
#fautes, coups gagnants, fautes directes). Seules les natures coherentes sont
#proposees : ace si le gagnant servait, double faute si le perdant servait.
#Un 2e clic sur la nature choisie l'efface.
def _nature_bar(match: Match, points: list, natures: list[str], on_nature) -> None:
    if not points or isinstance(points[-1], tuple) or match.end_reason:
        return
    winner = points[-1]
    server = match_state(match, points[:-1]).server[0]
    current = natures[-1] if natures else ""
    options = [("ace", "ACE")] if winner == server else [("double_fault", "DOUBLE FAUTE")]
    options += [("winner", "COUP GAGNANT"), ("unforced_error", "FAUTE DIRECTE")]
    with ui.row(wrap=False).classes(
        "w-full items-center justify-center gap-3 rounded-2xl bg-slate-900/70 px-4 py-3"
    ):
        with ui.column().classes("gap-0 shrink-0"):
            ui.label("NATURE DU DERNIER POINT (facultatif)").classes(
                "text-xs font-bold tracking-widest text-slate-300"
            )
            ui.label(f"gagne par {team_label((match.team1, match.team2)[winner])}").classes(
                "text-sm font-bold text-white"
            )
        for nature, label in options:
            selected = current == nature
            ui.button(label, color=None, on_click=lambda n=nature, sel=selected: on_nature("" if sel else n)).props(
                "no-caps unelevated"
            ).classes(
                "h-12 px-5 rounded-xl text-base font-bold "
                + ("bg-violet-500 text-white ring-2 ring-white" if selected
                   else "bg-slate-700 text-slate-100 hover:bg-slate-600")
            )
        ui.label("Double faute / faute directe : commise par l'adversaire").classes(
            "text-xs text-slate-400 shrink"
        )


#`actions` : {"undo", "retire", "swap", "server", "reset", "nature"} -> fonction
def _live_view(match: Match, points: list, score: ScoreState, view: dict, on_point, actions: dict,
               natures: list[str]) -> None:
    teams = (match.team1, match.team2)
    scoreboard(match, score, big=True)

    if score.finished:
        winner = teams[score.winner]
        with ui.column().classes("w-full items-center gap-2 rounded-2xl bg-green-600 text-white p-6 shadow-lg"):
            ui.label("MATCH TERMINE" + (" (ABANDON)" if match.end_reason == "RET" else "")).classes(
                "text-lg font-bold tracking-widest"
            )
            ui.label(f"Victoire de {team_label(winner, short=False)}").classes("text-4xl font-bold")
            ui.button("RETOUR AUX MATCHS", icon="arrow_back", color=None,
                      on_click=lambda: ui.navigate.to("/umpire")).props("no-caps unelevated").classes(
                "mt-3 h-14 px-8 rounded-xl text-lg font-bold bg-white text-green-700 hover:bg-green-50"
            )
    else:
        infos = _situation(match, points, score)
        with ui.row(wrap=False).classes("w-full min-h-[3.5rem] items-center justify-center gap-3"):
            for text, color in infos:
                ui.label(text).classes(
                    f"text-xl font-bold tracking-wide rounded-full px-6 py-2 bg-{color}-500 text-white shadow"
                )

        #boutons places comme les joueurs sur le court (vu depuis la chaise
        #d'arbitre) : ils s'echangent a chaque changement de cote
        left = score.left_team(match.first_left or 0)
        order = (left, 1 - left)
        server_team = score.server[0]
        with ui.row(wrap=False).classes("w-full flex-1 min-h-[11rem] max-h-[30rem] items-stretch gap-6"):
            for team in order:
                color = TEAM_COLORS[team]
                with ui.button(color=None, on_click=lambda t=team: on_point(t)).props(
                    "no-caps unelevated"
                ).classes(
                    f"point-button flex-1 min-w-0 rounded-3xl bg-{color}-500 hover:bg-{color}-400 "
                    f"active:scale-[0.98] transition-transform text-white shadow-xl"
                ):
                    with ui.column().classes("w-full items-center gap-2 px-6"):
                        ui.label("POINT").classes("text-5xl font-black tracking-widest")
                        #nom(s) sur une seule ligne, compresses en X si trop longs
                        with ui.element("div").classes("fit-x w-full text-center"):
                            with ui.element("div").classes("items-center gap-3"):
                                for player in teams[team]:
                                    flag(player.country, "h-6 w-8")
                                ui.label(team_label(teams[team])).classes("text-3xl font-bold")
                        if server_team == team:
                            ui.label("AU SERVICE").classes(
                                "text-sm font-bold tracking-widest rounded-full px-3 py-0.5 bg-white/25"
                            )

    _nature_bar(match, points, natures, actions["nature"])

    #barre d'actions : reglages a gauche, ANNULER au centre (l'action la plus
    #utilisee, bien visible), fin de match / remise a zero a droite
    #libelles sur 2 lignes si la place manque (tablette) : hauteur libre
    secondary = "min-h-[3.5rem] px-5 py-1 rounded-xl text-base font-bold leading-tight text-white"
    with ui.element("div").classes("w-full grid grid-cols-[1fr_auto_1fr] items-center gap-4"):
        with ui.row(wrap=False).classes("gap-3 justify-start"):
            if not score.finished:
                ui.button("INVERSER LES COTES", icon="swap_horiz", color=None, on_click=actions["swap"]).props(
                    "no-caps unelevated"
                ).classes(f"{secondary} bg-slate-700 hover:bg-slate-600")
                ui.button("CHANGER LE SERVEUR", icon="sports_tennis", color=None, on_click=actions["server"]).props(
                    "no-caps unelevated"
                ).classes(f"{secondary} bg-slate-700 hover:bg-slate-600")
        ui.button("ANNULER LE DERNIER POINT" if not match.end_reason else "ANNULER L'ABANDON",
                  icon="undo", color=None, on_click=actions["undo"]).props("no-caps unelevated").classes(
            "h-16 px-10 rounded-2xl text-xl font-bold bg-white text-slate-900 hover:bg-slate-200 shadow-lg"
        )
        with ui.row(wrap=False).classes("gap-3 justify-end"):
            if not score.finished:
                ui.button("ABANDON", icon="flag", color=None, on_click=actions["retire"]).props(
                    "no-caps unelevated"
                ).classes(f"{secondary} bg-red-600/90 hover:bg-red-500")
            ui.button("REMETTRE A ZERO", icon="restart_alt", color=None, on_click=actions["reset"]).props(
                "no-caps unelevated"
            ).classes(f"{secondary} bg-slate-700 hover:bg-red-700")
    if not score.finished:
        ui.label(
            "Clavier : fleche gauche / droite = point pour le joueur de ce cote, retour arriere = annuler"
        ).classes("w-full text-center text-sm text-slate-300")
