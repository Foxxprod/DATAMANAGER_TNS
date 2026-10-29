# Page d'administration des matchs : liste (build_match_list) et fenetre
# de creation/edition ouverte par-dessus la liste (build_match_dialog).
# Aucune requete SQL ici, uniquement de l'affichage et des appels a
# database.py.
#
# Le formulaire travaille sur un objet Match en memoire, lie aux champs
# via bind_value : rien n'est ecrit en base avant "Enregistrer". Le tournoi
# et les joueurs sont choisis dans leurs listes (pages TOURNOIS/JOUEURS),
# chacune avec un premier choix "Ajouter..." pour creer l'element manquant
# sans quitter la fenetre. 4 emplacements joueurs (equipe 1/2, position
# 1/2) toujours presents en memoire, le 2e de chaque equipe masque en
# simple, pour pouvoir basculer simple <-> double sans perdre la
# selection ; le surplus est ignore a la sauvegarde.

import dataclasses
from datetime import date, datetime
from itertools import groupby

from nicegui import ui

import database
from events import match_scored, subscribe_for
from forms import FIELD_PROPS, add_option_button, date_input, form_dialog, optional_select, time_input
from layout import (
    FIELD_LABEL_CLASSES,
    LIST_FLAG_SIZE,
    LIST_GRID_CLASSES_BASE,
    LIST_ROW_CLASSES,
    LIST_STRONG_CLASSES,
    ROUND_BUTTON_CLASSES,
    flag,
    list_card,
    list_cell,
    list_header,
    page_body,
    section_card,
    tournament_logo,
)
from models import (
    CATEGORIES,
    CATEGORY_LABELS,
    DISPLAY_STATUSES,
    FINAL_SET_RULES,
    FINAL_SET_SHORT,
    FORMAT_PRESETS,
    PLAYERS_PER_TEAM,
    ROUNDS,
    STATUSES,
    Match,
    Player,
    Tournament,
    format_date,
    format_day,
)
from players import build_player_dialog, info_tile, player_summary
from scoreboard import scoreboard
from scoring import match_state, match_stats
from tournaments import build_tournament_dialog

#intervalle (secondes) de verification des changements de la liste des
#matchs, voir build_match_list.check_updates
CHECK_INTERVAL = 5.0

#sexe propose par defaut pour un joueur cree depuis la fenetre match,
#deduit de la categorie (rien d'impose pour le double mixte)
CATEGORY_GENDER = {"MS": "M", "MD": "M", "WS": "F", "WD": "F"}


def _status_chip(status: str) -> None:
    label, color = DISPLAY_STATUSES.get(status, (status.upper(), "slate"))
    ui.label(label).classes(
        f"text-sm font-bold tracking-wide rounded-full px-4 py-1.5 text-center whitespace-nowrap "
        f"border border-{color}-500 bg-{color}-600/20 text-{color}-500"
    )


#une equipe de la colonne JOUEURS : drapeau + nom de chaque joueur (nom
#long en simple, nom court en double pour tenir sur la ligne)
def _team(team: list[Player], is_double: bool) -> None:
    with ui.row(wrap=False).classes("items-center gap-2 min-w-0"):
        if not team:
            ui.label("A definir").classes("text-base italic text-slate-400")
            return
        for index, player in enumerate(team):
            if index:
                ui.label("/").classes("text-slate-400")
            flag(player.country, LIST_FLAG_SIZE)
            ui.label(player.short_name if is_double else player.long_name).classes(LIST_STRONG_CLASSES)


# ---------------------------------------------------------------------------
# Liste des matchs
# ---------------------------------------------------------------------------

#colonnes de la liste (entete + lignes partagent la meme grille CSS pour
#rester alignees) : une information par colonne. Pas de colonnes masquees
#selon la largeur d'ecran : la classe `hidden` de Quasar est en !important
#et l'emporte sur les variantes Tailwind md:block - la liste defile plutot
#horizontalement sur un ecran etroit (min-w sur la grille).
#largeur minimale commune aux lignes et aux titres de jour (meme largeur
#de defilement horizontal)
LIST_MIN_WIDTH = "min-w-[110rem]"
LIST_GRID_CLASSES = LIST_GRID_CLASSES_BASE + LIST_MIN_WIDTH + (
    " grid-cols-[8.5rem_7rem_4.5rem_minmax(11rem,1fr)_10rem_10rem_8rem_"
    "minmax(24rem,2fr)_3.5rem_3.5rem_5.5rem_7.5rem_6rem_7.5rem]"
)
#(libelle, alignement) - les colonnes de configuration sont centrees
LIST_COLUMNS = [
    ("STATUT", "text-left"),
    ("DATE", "text-left"),
    ("HEURE", "text-left"),
    ("TOURNOI", "text-left"),
    ("TOUR", "text-left"),
    ("CATEGORIE", "text-left"),
    ("COURT", "text-left"),
    ("JOUEURS", "text-left"),
    ("SETS", "text-center"),
    ("JEUX", "text-center"),
    ("TIE-BREAK", "text-center"),
    ("SET DECISIF", "text-center"),
    ("PT DECISIF", "text-center"),
    ("", "text-right"),
]


#construit la liste et renvoie la fonction d'ouverture de la fenetre
#match (match_id None = creation), utilisee aussi par le bouton
#NOUVEAU MATCH du header
def build_match_list():
    #signature : etat de la liste au dernier affichage, voir check_updates
    state = {"filter": "all", "signature": None}

    with ui.dialog() as delete_dialog, ui.card().classes("gap-3 w-[26rem]"):
        ui.label("Supprimer ce match ?").classes("text-base font-bold")
        delete_text = ui.label().classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=lambda: delete_dialog.submit(False)).props("flat")
            ui.button(
                "Supprimer", color=None, on_click=lambda: delete_dialog.submit(True)
            ).classes("bg-red-600 text-white")

    with ui.dialog() as reset_dialog, ui.card().classes("gap-3 w-[28rem]"):
        ui.label("Remettre ce match a zero ?").classes("text-base font-bold")
        reset_text = ui.label().classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=lambda: reset_dialog.submit(False)).props("flat")
            ui.button(
                "Remettre a zero", color=None, on_click=lambda: reset_dialog.submit(True)
            ).classes("bg-red-600 text-white")

    #remise a zero d'un match commence/termine : points effaces, statut
    #"programme", service a rechoisir (meme action que dans l'arbitrage)
    async def on_reset_click(match: Match) -> None:
        reset_text.text = (
            f"{Match.team_name(match.team1)} vs {Match.team_name(match.team2)} - tous les points saisis "
            "seront effaces et le match repassera en 'programme'. Cette action ne peut pas etre annulee."
        )
        if await reset_dialog:
            database.reset_match(match.id)
            ui.notify("Match remis a zero", type="info")
            match_list.refresh()
            match_scored.emit(match.id)

    async def on_delete_click(match: Match) -> None:
        delete_text.text = (
            f"{Match.team_name(match.team1)} vs {Match.team_name(match.team2)} - "
            "toutes les donnees du match seront definitivement perdues "
            "(les joueurs et le tournoi sont conserves)."
        )
        if await delete_dialog:
            database.delete_match(match.id)
            ui.notify("Match supprime", type="info")
            match_list.refresh()
            match_scored.emit(match.id)

    #la fenetre est reconstruite a chaque ouverture (match recharge depuis
    #la base) puis supprimee a la fermeture : pas d'etat residuel d'une
    #saisie precedente. Construite dans `page` (conteneur stable) et NON
    #dans le contexte du bouton clique : un bouton de la liste (ex: "Creer
    #un match" de la liste vide) est detruit par match_list.refresh(), il
    #ne doit pas emporter la fenetre avec lui.
    async def open_match_dialog(match_id: int | None = None) -> None:
        match = None
        if match_id is not None:
            match = database.get_match(match_id)
            if match is None:
                ui.notify(f"Match #{match_id} introuvable", type="negative")
                match_list.refresh()
                return

        with page:
            dialog = build_match_dialog(match)
        saved = await dialog
        dialog.delete()
        if saved:
            match_list.refresh()

    #fiche du match (clic sur sa ligne) ; son bouton Modifier ferme la fiche
    #et ouvre la fenetre d'edition
    async def open_match_profile(match: Match) -> None:
        with page:
            dialog = build_match_profile(match)
        result = await dialog
        dialog.delete()
        if result == "edit":
            await open_match_dialog(match.id)

    #ce qui est visible dans la liste : un changement (statut "A VENIR"
    #atteint avec l'heure, match cree/modifie/supprime, y compris depuis un
    #autre poste) declenche un rafraichissement
    def signature(matches: list[Match], now: datetime) -> tuple:
        return tuple((match.id, match.updated_at, match.display_status(now)) for match in matches)

    @ui.refreshable
    def match_list() -> None:
        now = datetime.now()
        all_matches = database.list_matches()
        state["signature"] = signature(all_matches, now)
        matches = all_matches
        if state["filter"] != "all":
            matches = [match for match in matches if match.display_status(now) == state["filter"]]

        if not matches:
            with ui.column().classes("w-full items-center gap-3 py-12"):
                ui.icon("sports_tennis").classes("text-5xl text-slate-300")
                ui.label(
                    "Aucun match pour ce filtre" if all_matches else "Aucun match pour le moment"
                ).classes("text-slate-500")
                ui.button("Creer un match", icon="add", on_click=lambda: open_match_dialog())
            return

        #matchs regroupes par jour (titre + separation entre les jours), les
        #matchs sans date en dernier ; dans un jour, tries par heure
        matches = sorted(matches, key=lambda m: (not m.scheduled_date, m.scheduled_date, m.scheduled_time, m.id))
        with ui.element("div").classes("w-full overflow-x-auto"):
            list_header(LIST_GRID_CLASSES, LIST_COLUMNS)
            for index, (day, day_matches) in enumerate(groupby(matches, key=lambda m: m.scheduled_date)):
                day_matches = list(day_matches)
                _day_header(day, len(day_matches), now.date(), first=index == 0)
                for match in day_matches:
                    _match_row(match, now, open_match_dialog, on_delete_click, open_match_profile, on_reset_click)

    #mise a jour automatique sans recharger la page : relecture de la base
    #toutes les CHECK_INTERVAL secondes, la liste n'est redessinee que si
    #quelque chose de visible a change (evite de reconstruire la liste pour
    #rien - et de faire sauter le defilement horizontal)
    def check_updates() -> None:
        if signature(database.list_matches(), datetime.now()) != state["signature"]:
            match_list.refresh()

    ui.timer(CHECK_INTERVAL, check_updates)

    with page_body() as page:
        card, tools = list_card("MATCHS")
        with tools:
            def on_filter_change(event) -> None:
                state["filter"] = event.value
                match_list.refresh()

            ui.toggle(
                {"all": "Tous", **{key: label.capitalize() for key, (label, _) in DISPLAY_STATUSES.items()}},
                value="all",
                on_change=on_filter_change,
            ).props("dense no-caps rounded")

        with card:
            match_list()

    #point marque dans l'interface d'arbitrage : liste a jour tout de suite,
    #sans attendre la verification periodique
    subscribe_for(match_scored, page, check_updates)

    return open_match_dialog


#bandeau de titre d'un jour dans la liste des matchs. La bordure epaisse
#du haut separe les jours (sauf le premier, colle a l'entete des colonnes).
def _day_header(day: str, count: int, today: date, first: bool) -> None:
    separation = "" if first else " border-t-4 border-slate-300 dark:border-slate-600"
    with ui.row(wrap=False).classes(
        f"w-full {LIST_MIN_WIDTH} items-center gap-3 px-4 py-2 "
        "bg-slate-200/70 dark:bg-slate-700/60 border-b border-slate-300 dark:border-slate-600" + separation
    ):
        ui.icon("event").classes("text-xl text-slate-500")
        ui.label(format_day(day) if day else "Date non programmee").classes(
            "text-lg font-bold tracking-wide text-slate-800 dark:text-slate-100"
        )
        if day == today.isoformat():
            ui.label("AUJOURD'HUI").classes(
                "text-xs font-bold tracking-wide rounded-full px-3 py-0.5 "
                "border border-sky-500 bg-sky-600/20 text-sky-600 dark:text-sky-400"
            )
        ui.label(f"{count} match{'s' if count > 1 else ''}").classes("text-sm text-slate-500")


#case de configuration centree (colonnes SETS, JEUX...). `muted` : valeur
#"par defaut/desactivee", affichee en gris pour faire ressortir le reste
def _config_cell(text: str, muted: bool = False) -> None:
    color = "text-slate-400" if muted else "text-slate-900 dark:text-slate-100"
    ui.label(text).classes(f"text-base font-bold text-center {color}")


#ligne cliquable : ouvre la fiche du match (sauf les boutons d'action, dont
#le clic ne remonte pas a la ligne - modificateur .stop)
def _match_row(match: Match, now: datetime, on_edit_click, on_delete_click, on_row_click, on_reset_click) -> None:
    match_format = match.format
    with ui.element("div").classes(LIST_GRID_CLASSES + LIST_ROW_CLASSES + " cursor-pointer").on(
        "click", lambda m=match: on_row_click(m)
    ):
        with ui.row().classes("items-center"):
            _status_chip(match.display_status(now))
        list_cell(format_date(match.scheduled_date), strong=True)
        ui.label(match.scheduled_time or "--:--").classes(
            "text-lg font-mono font-bold text-slate-900 dark:text-slate-100"
        )
        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            tournament_logo(match.tournament)
            list_cell(match.tournament.name if match.tournament else "", strong=True)
        list_cell(match.round)
        list_cell(CATEGORY_LABELS.get(match.category, match.category))
        list_cell(match.court)

        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            _team(match.team1, match.is_double)
            ui.label("vs").classes("text-sm font-bold text-slate-400 shrink-0")
            _team(match.team2, match.is_double)

        _config_cell(str(match_format.sets_to_win * 2 - 1))
        _config_cell(str(match_format.games_per_set))
        _config_cell(
            f"{match_format.tiebreak_points} pts" if match_format.tiebreak_enabled else "Non",
            muted=not match_format.tiebreak_enabled,
        )
        _config_cell(
            FINAL_SET_SHORT.get(match_format.final_set_rule, match_format.final_set_rule),
            muted=match_format.final_set_rule == "tiebreak",
        )
        _config_cell("Oui" if match_format.no_ad else "Non", muted=not match_format.no_ad)

        with ui.row(wrap=False).classes("gap-0 justify-end").on("click.stop", lambda: None):
            ui.button(
                icon="edit", on_click=lambda m=match: on_edit_click(m.id)
            ).props("flat round").tooltip("Modifier")
            #remise a zero : seulement pour un match deja commence ou termine
            if match.first_server is not None:
                ui.button(
                    icon="restart_alt", color="orange", on_click=lambda m=match: on_reset_click(m)
                ).props("flat round").tooltip("Remettre le match a zero")
            ui.button(
                icon="delete", color="red", on_click=lambda m=match: on_delete_click(m)
            ).props("flat round").tooltip("Supprimer")


# ---------------------------------------------------------------------------
# Fiche du match (consultation)
# ---------------------------------------------------------------------------

#ligne de statistique "face a face" : valeur equipe 1 | libelle | valeur equipe 2
#(barres proportionnelles de part et d'autre)
STAT_ROWS = [
    ("Points gagnes", "points_won", None),
    ("Aces", "aces", None),
    ("Doubles fautes", "double_faults", None),
    ("Coups gagnants", "winners", None),
    ("Fautes directes", "unforced_errors", None),
    ("Points gagnes au service", "service_points_won", "service_points_played"),
    ("Points gagnes en retour", "return_points_won", "return_points_played"),
    ("Balles de break converties", "break_points_won", "break_points_played"),
    ("Balles de break sauvees", "break_points_saved", "break_points_faced"),
    ("Jeux de service gagnes", "service_games_won", "service_games_played"),
    ("Plus longue serie de points", "max_points_in_row", None),
]


def _stats_table(match: Match, stats: list[dict[str, int]]) -> None:
    def text(team: int, key: str, total_key: str | None) -> str:
        value = stats[team][key]
        if total_key is None:
            return str(value)
        total = stats[team][total_key]
        return f"{value}/{total} ({round(100 * value / total)}%)" if total else "0/0"

    with ui.column().classes("w-full gap-2"):
        ui.label("STATISTIQUES").classes("text-xs font-bold tracking-widest text-slate-500")
        with ui.column().classes("w-full gap-0 rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden"):
            with ui.element("div").classes(
                "w-full grid grid-cols-[1fr_16rem_1fr] items-center px-4 py-2 bg-slate-100 dark:bg-slate-900/60"
            ):
                ui.label(Match.team_name(match.team1)).classes("text-sm font-bold text-right truncate")
                ui.label("")
                ui.label(Match.team_name(match.team2)).classes("text-sm font-bold truncate")
            for label, key, total_key in STAT_ROWS:
                values = [stats[0][key], stats[1][key]]
                share = values[0] / sum(values) if sum(values) else 0.5
                with ui.element("div").classes(
                    "w-full grid grid-cols-[1fr_16rem_1fr] items-center gap-3 px-4 py-1.5 "
                    "border-t border-slate-100 dark:border-slate-700/60"
                ):
                    with ui.row(wrap=False).classes("items-center justify-end gap-2"):
                        ui.label(text(0, key, total_key)).classes("text-base font-bold font-mono")
                        ui.element("div").classes("h-2 rounded-full bg-sky-500").style(f"width: {share * 6}rem")
                    ui.label(label).classes("text-sm text-center text-slate-500")
                    with ui.row(wrap=False).classes("items-center gap-2"):
                        ui.element("div").classes("h-2 rounded-full bg-amber-500").style(
                            f"width: {(1 - share) * 6}rem"
                        )
                        ui.label(text(1, key, total_key)).classes("text-base font-bold font-mono")
        ui.label(
            "Aces, doubles fautes, coups gagnants et fautes directes : selon la nature des points saisie "
            "dans l'arbitrage (facultative)."
        ).classes("text-xs text-slate-400")


#configuration du match : une tuile par parametre du format + categorie
def _match_config(match: Match) -> None:
    match_format = match.format
    with ui.column().classes("w-full gap-2"):
        ui.label("CONFIGURATION DU MATCH").classes("text-xs font-bold tracking-widest text-slate-500")
        with ui.element("div").classes("w-full grid grid-cols-2 md:grid-cols-6 gap-3"):
            info_tile("Categorie", CATEGORY_LABELS.get(match.category, match.category))
            info_tile("Sets", f"{match_format.sets_to_win * 2 - 1} ({match_format.sets_to_win} gagnants)")
            info_tile("Jeux par set", str(match_format.games_per_set))
            info_tile(
                "Tie-break",
                f"{match_format.tiebreak_points} pts" if match_format.tiebreak_enabled else "Non",
            )
            info_tile("Set decisif", FINAL_SET_SHORT.get(match_format.final_set_rule, match_format.final_set_rule))
            info_tile("Point decisif", "Oui (no-ad)" if match_format.no_ad else "Non")
        ui.label(
            "Set decisif : " + FINAL_SET_RULES.get(match_format.final_set_rule, match_format.final_set_rule)
        ).classes("text-sm text-slate-500")


#fiche de consultation : bandeau (tournoi, tour, court, programme, statut),
#tableau des scores, configuration du match, puis les 2 equipes cote a cote (photo + infos de chaque
#joueur). Se ferme au clic a cote, avec Echap ou la croix. A attendre
#(`await dialog`) : renvoie "edit" si le bouton Modifier a ete clique.
def build_match_profile(match: Match) -> ui.dialog:
    tournament = match.tournament

    #score et statut relus en base a chaque point marque dans l'interface
    #d'arbitrage (evenement match_scored) : la fiche ouverte suit le match en
    #direct, sans devoir la fermer/rouvrir
    def current_match() -> Match:
        return database.get_match(match.id) or match

    @ui.refreshable
    def live_status() -> None:
        _status_chip(current_match().display_status(datetime.now()))

    @ui.refreshable
    def live_score() -> None:
        live = current_match()
        if live.first_server is None:
            scoreboard(live, None)
            return
        points = database.get_points(live.id)
        scoreboard(live, match_state(live, points))
        _stats_table(live, match_stats(live, points, database.get_natures(live.id)))

    def on_match_scored(updated_id: int) -> None:
        if updated_id == match.id:
            live_status.refresh()
            live_score.refresh()

    dialog = ui.dialog()
    subscribe_for(match_scored, dialog, on_match_scored, expect_args=True)
    with dialog, ui.card().classes(
        "p-0 gap-0 rounded-2xl overflow-hidden bg-white dark:bg-slate-800"
    ).style("width: 76rem; max-width: 96vw; max-height: 92vh;"):
        with ui.row(wrap=False).classes("w-full items-center justify-between gap-4 bg-slate-900 text-white px-6 py-4"):
            with ui.column().classes("gap-1 min-w-0"):
                with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
                    tournament_logo(tournament, "h-14 w-14", placeholder=False)
                    if tournament:
                        flag(tournament.country, "h-5 w-7")
                    ui.label(tournament.name if tournament else "Tournoi ?").classes("text-2xl font-bold truncate")
                details = [
                    match.round,
                    CATEGORY_LABELS.get(match.category, match.category),
                    match.court,
                ]
                ui.label(" · ".join(part for part in details if part)).classes(
                    "text-sm font-bold uppercase tracking-wide text-slate-300"
                )
                schedule = " ".join(part for part in (format_date(match.scheduled_date), match.scheduled_time) if part)
                ui.label(schedule or "Date non programmee").classes("text-sm font-mono text-slate-400")
            with ui.row(wrap=False).classes("items-center gap-3 shrink-0"):
                live_status()
                ui.button(icon="close", color=None, on_click=lambda: dialog.submit(None)).classes(
                    ROUND_BUTTON_CLASSES
                ).props("round").tooltip("Fermer")

        #[&>*]:shrink-0 : la zone defile quand la fiche depasse l'ecran, au lieu
        #de comprimer ses blocs (le tableau des scores, en overflow-hidden,
        #etait ecrase a une hauteur nulle des que les statistiques s'ajoutaient)
        with ui.column().classes("w-full flex-1 min-h-0 overflow-auto p-6 gap-5 [&>*]:shrink-0"):
            #score reel (points saisis dans l'interface d'arbitrage), cases vides
            #si le match n'a pas encore debute ; mis a jour en direct
            live_score()
            _match_config(match)

            with ui.element("div").classes("w-full grid grid-cols-[1fr_auto_1fr] gap-6 items-start"):
                for index, team in enumerate((match.team1, match.team2)):
                    if index:
                        ui.label("VS").classes("self-center text-2xl font-bold text-slate-400")
                    with ui.column().classes(
                        "w-full gap-4 rounded-xl border border-slate-200 dark:border-slate-700 p-4"
                    ):
                        ui.label(
                            f"EQUIPE {index + 1}" if match.is_double else f"JOUEUR {index + 1}"
                        ).classes("text-xs font-bold tracking-widest text-slate-500")
                        if not team:
                            ui.label("A definir").classes("text-lg italic text-slate-400")
                        for player in team:
                            player_summary(player)

            with ui.row().classes("w-full justify-end"):
                ui.button("Modifier", icon="edit", on_click=lambda: dialog.submit("edit")).props("no-caps")

    return dialog


# ---------------------------------------------------------------------------
# Formulaire de creation / edition
# ---------------------------------------------------------------------------

def _is_double(category: str) -> bool:
    return PLAYERS_PER_TEAM.get(category, 1) == 2


#libelle d'un joueur dans les selects de la fenetre match
def _player_option(player: Player) -> str:
    parts = [f"{player.last_name.upper()} {player.first_name}".strip()]
    if player.country:
        parts.append(player.country)
    if player.best_ranking:
        parts.append(f"#{player.best_ranking}")
    return " · ".join(parts)


def _tournament_option(tournament: Tournament) -> str:
    return " · ".join(part for part in (tournament.name, tournament.city, tournament.dates) if part)


#cle d'un emplacement joueur : "equipe-position" (ex: "2-1")
SLOT_KEYS = ["1-1", "1-2", "2-1", "2-2"]


#compose les equipes a partir des emplacements choisis et verifie la
#saisie. Renvoie la liste des erreurs bloquantes (vide si tout est valide).
def _normalize(match: Match, slots: dict[str, int | None], players_by_id: dict[int, Player]) -> list[str]:
    errors = []
    count = PLAYERS_PER_TEAM.get(match.category, 1)

    chosen = []
    for team_number in (1, 2):
        team = []
        for position in range(1, count + 1):
            player_id = slots[f"{team_number}-{position}"]
            if player_id is not None and player_id in players_by_id:
                team.append(players_by_id[player_id])
                chosen.append(player_id)
        setattr(match, f"team{team_number}", team)

    if len(chosen) != len(set(chosen)):
        errors.append("Un meme joueur ne peut pas apparaitre deux fois dans le match")
    if match.tournament_id is None:
        errors.append("Choisissez le tournoi du match")
    match.court = (match.court or "").strip()

    return errors


#fenetre de creation (match None) / edition. A attendre (`await dialog`) :
#renvoie True si le match a ete enregistre, None si la fenetre a ete
#fermee sans enregistrer.
def build_match_dialog(match: Match | None) -> ui.dialog:
    is_new = match is None
    #copie de travail : le match charge n'est jamais modifie directement
    working = dataclasses.replace(match) if match else Match()
    working.format = dataclasses.replace(working.format)
    #nouveau match : tournoi en cours preselectionne (voir database.current_tournaments)
    if is_new:
        current = database.current_tournaments(date.today())
        if current:
            working.tournament_id = current[0].id

    slots: dict[str, int | None] = {key: None for key in SLOT_KEYS}
    for team_number, team in ((1, working.team1), (2, working.team2)):
        for position, player in enumerate(team[:2], start=1):
            slots[f"{team_number}-{position}"] = player.id

    players_by_id: dict[int, Player] = {}
    tournaments_by_id: dict[int, Tournament] = {}
    selects: dict[str, ui.select] = {}
    flag_boxes: dict[str, ui.row] = {}

    def player_options() -> dict[int, str]:
        return {player.id: _player_option(player) for player in players_by_id.values()}

    def tournament_options() -> dict[int, str]:
        return {tournament.id: _tournament_option(tournament) for tournament in tournaments_by_id.values()}

    def reload_players() -> None:
        players_by_id.clear()
        players_by_id.update({player.id: player for player in database.list_players()})

    def reload_tournaments() -> None:
        tournaments_by_id.clear()
        tournaments_by_id.update({tournament.id: tournament for tournament in database.list_tournaments()})

    def refresh_flag(key: str) -> None:
        box = flag_boxes[key]
        box.clear()
        player = players_by_id.get(slots[key])
        with box:
            flag(player.country if player else "")

    reload_players()
    reload_tournaments()

    title = "NOUVEAU MATCH" if is_new else "MODIFIER LE MATCH"
    dialog, body, footer = form_dialog(title)

    def on_save() -> None:
        errors = _normalize(working, slots, players_by_id)
        if errors:
            for error in errors:
                ui.notify(error, type="negative")
            return

        match_id = database.save_match(working)
        ui.notify(f"Match #{match_id} {'cree' if is_new else 'mis a jour'}", type="positive")
        #autres postes (listes, fiches, arbitrage) a jour immediatement
        match_scored.emit(match_id)
        dialog.submit(True)

    #tournoi choisi : courts proposes, surface/lieu affiches, et date du
    #match pre-remplie avec la date de debut du tournoi si elle est vide
    def on_tournament_change() -> None:
        tournament = tournaments_by_id.get(working.tournament_id)
        courts = list(tournament.courts) if tournament else []
        #court deja saisi hors liste du tournoi : conserve tel quel
        if working.court and working.court not in courts:
            courts.append(working.court)
        court_select.set_options(courts, value=working.court or None)
        if tournament and tournament.start_date and not working.scheduled_date:
            working.scheduled_date = tournament.start_date
        details = [part for part in (tournament.surface, tournament.venue, tournament.city) if part] if tournament else []
        tournament_info.text = " · ".join(details)

    #element absent de sa liste : fenetre de creation ouverte PAR-DESSUS la
    #fenetre match (la meme que sur la page TOURNOIS/JOUEURS), puis
    #l'element cree est selectionne
    async def create_tournament() -> None:
        with body:
            tournament_dialog = build_tournament_dialog(None)
        new_id = await tournament_dialog
        tournament_dialog.delete()
        if not new_id:
            return
        reload_tournaments()
        tournament_select.set_options(tournament_options(), value=new_id)

    async def create_player(key: str) -> None:
        defaults = {"gender": CATEGORY_GENDER[working.category]} if working.category in CATEGORY_GENDER else {}
        with body:
            player_dialog = build_player_dialog(None, defaults)
        new_id = await player_dialog
        player_dialog.delete()
        if not new_id:
            return
        reload_players()
        options = player_options()
        for slot_key, select in selects.items():
            select.set_options(options, value=new_id if slot_key == key else slots[slot_key])

    def apply_preset(event) -> None:
        preset = FORMAT_PRESETS.get(event.value)
        if preset is None:
            return
        #attribut par attribut (pas de remplacement de working.format) :
        #les champs sont lies a CET objet
        for format_field in dataclasses.fields(preset):
            setattr(working.format, format_field.name, getattr(preset, format_field.name))

    #drapeau affiche DANS le champ (slot prepend) : une case a cote du champ
    #le decalait vers la droite par rapport au titre de l'equipe
    def player_slot(key: str, label: str) -> ui.select:
        select = ui.select(
            player_options(), label=label, with_input=True, clearable=True,
        ).bind_value(slots, key).props(FIELD_PROPS).classes("w-full")
        with select.add_slot("prepend"):
            flag_boxes[key] = ui.row().classes("w-6 justify-center")
        add_option_button(select, "Ajouter un joueur", lambda k=key: create_player(k))
        selects[key] = select
        refresh_flag(key)
        #branche apres refresh_flag : bind_value declenche deja un changement
        #a la creation, avant que flag_boxes[key] n'existe
        select.on_value_change(lambda _, k=key: refresh_flag(k))
        return select

    with body:
        # --- Informations generales -------------------------------------
        with section_card("INFORMATIONS DU MATCH", "info"):
            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-4 gap-2"):
                with ui.column().classes("gap-0 md:col-span-2"):
                    tournament_select = ui.select(
                        tournament_options(), label="Tournoi *", with_input=True,
                    ).bind_value(working, "tournament_id").props(FIELD_PROPS).classes("w-full")
                    add_option_button(tournament_select, "Ajouter un tournoi", create_tournament)
                    tournament_info = ui.label().classes("text-xs text-slate-500 pl-1")
                ui.select(
                    {key: label for key, label, _ in CATEGORIES}, label="Categorie"
                ).bind_value(working, "category").props(FIELD_PROPS)
                optional_select(ROUNDS, "Tour", working, "round", allow_new=True)

                court_select = optional_select([], "Court", working, "court", allow_new=True, with_input=True)
                date_input(working, "scheduled_date", "Date")
                time_input(working, "scheduled_time", "Heure prevue")
                if not is_new:
                    ui.select(
                        {key: label.capitalize() for key, (label, _) in STATUSES.items()},
                        label="Statut",
                    ).bind_value(working, "status").props(FIELD_PROPS)

        # --- Joueurs ------------------------------------------------------
        with section_card("JOUEURS", "groups"):
            ui.label(
                "Choisissez les joueurs dans la liste (tapez pour rechercher). "
                "Absent de la liste ? Premier choix : Ajouter un joueur."
            ).classes("text-xs text-slate-500 -mt-1")
            with ui.element("div").classes("w-full grid grid-cols-1 lg:grid-cols-2 gap-4"):
                for number in (1, 2):
                    with ui.column().classes(
                        "w-full gap-3 rounded-xl border border-slate-200 dark:border-slate-700 p-3"
                    ):
                        ui.label().classes(
                            "text-sm font-bold text-slate-700 dark:text-slate-200"
                        ).bind_text_from(
                            working,
                            "category",
                            backward=lambda c, n=number: f"EQUIPE {n}" if _is_double(c) else f"JOUEUR {n}",
                        )
                        player_slot(f"{number}-1", "Joueur")
                        player_slot(f"{number}-2", "Partenaire").bind_visibility_from(
                            working, "category", backward=_is_double
                        )

        # --- Format -------------------------------------------------------
        with section_card("FORMAT DU MATCH", "rule"):
            ui.select(
                list(FORMAT_PRESETS), label="Appliquer un format predefini", on_change=apply_preset
            ).props(FIELD_PROPS).classes("w-full md:w-96")

            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3"):
                with ui.column().classes("gap-1"):
                    ui.label("Nombre de sets").classes(FIELD_LABEL_CLASSES)
                    ui.toggle({2: "3 sets (2 gagnants)", 3: "5 sets (3 gagnants)"}).bind_value(
                        working.format, "sets_to_win"
                    ).props("no-caps")

                with ui.column().classes("gap-1"):
                    ui.label("Jeux par set").classes(FIELD_LABEL_CLASSES)
                    ui.toggle({6: "6 jeux", 4: "4 jeux (Fast4)"}).bind_value(
                        working.format, "games_per_set"
                    ).props("no-caps")

                with ui.column().classes("gap-1"):
                    ui.label("Tie-break").classes(FIELD_LABEL_CLASSES)
                    with ui.row().classes("items-center gap-4"):
                        ui.switch("A egalite de jeux").bind_value(working.format, "tiebreak_enabled")
                        ui.toggle({5: "5 pts", 7: "7 pts", 10: "10 pts"}).bind_value(
                            working.format, "tiebreak_points"
                        ).bind_enabled_from(working.format, "tiebreak_enabled").props("no-caps")

                with ui.column().classes("gap-1"):
                    ui.label("Jeu").classes(FIELD_LABEL_CLASSES)
                    ui.switch("Point decisif a 40-40 (no-ad)").bind_value(working.format, "no_ad")

                with ui.column().classes("gap-1 md:col-span-2"):
                    ui.label("Set decisif").classes(FIELD_LABEL_CLASSES)
                    ui.select(FINAL_SET_RULES).bind_value(working.format, "final_set_rule").props(
                        FIELD_PROPS
                    ).classes("w-full md:w-[28rem]")

            with ui.row().classes(
                "w-full items-center gap-2 rounded-xl bg-slate-50 dark:bg-slate-900/60 px-3 py-2"
            ):
                ui.icon("summarize").classes("text-slate-500")
                ui.label().classes("text-sm font-bold text-slate-700 dark:text-slate-200").bind_text_from(
                    working.format, "summary"
                )

    #branche APRES la construction : bind_value declenche deja un changement
    #de valeur a la creation du select (edition d'un match existant), avant
    #que court_select/tournament_info n'existent
    tournament_select.on_value_change(lambda _: on_tournament_change())
    on_tournament_change()

    with footer:
        ui.button("Annuler", on_click=lambda: dialog.submit(None)).props("flat")
        ui.button(
            "Creer le match" if is_new else "Enregistrer", icon="save", on_click=on_save
        ).classes("px-6")

    return dialog
