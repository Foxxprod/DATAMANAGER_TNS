# Tableau des scores facon habillage TV, partage par la fiche du match
# (admin.build_match_profile) et l'interface d'arbitrage (umpire.py) : une
# ligne par equipe (service, drapeaux, noms), une colonne par set possible
# selon le format, puis les points du jeu en cours.

from nicegui import ui

from layout import LIST_FLAG_SIZE, flag
from models import Match, Player
from scoring import ScoreState


def team_label(team: list[Player], short: bool = True) -> str:
    names = [player.short_name if short else player.long_name for player in team]
    return " / ".join(names) if names else "A definir"


#jeux d'un set pour l'equipe `team` (colonne `index`), et points de
#tie-break a mettre en exposant (score du perdant du tie-break, convention TV)
def _set_cell(state: ScoreState | None, index: int, team: int) -> tuple[str, str, bool]:
    if state is None:
        return "-", "", False
    if index < len(state.sets):
        tiebreak = state.tiebreaks[index]
        if state.super_tiebreak_sets[index]:
            return str(tiebreak[team]), "", False
        games = state.sets[index]
        exponent = ""
        if tiebreak is not None and games[team] < games[1 - team]:
            exponent = str(tiebreak[team])
        return str(games[team]), exponent, False
    if index == len(state.sets) and not state.finished:
        if state.super_tiebreak:
            return str(state.points[team]), "", True
        return str(state.games[team]), "", True
    return "", "", False


#`state` None : match pas encore debute (cases "-"). `big` : version grand
#format de l'ecran d'arbitrage.
def scoreboard(match: Match, state: ScoreState | None, big: bool = False) -> None:
    set_count = match.format.sets_to_win * 2 - 1
    cell = "5.5rem" if big else "4.5rem"
    #colonne des noms : prend la place restante sans jamais pousser les
    #colonnes de score, qui ont une largeur fixe (minmax(0, 1fr) : une grille
    #elargit sinon la colonne a la largeur d'un nom long)
    columns = f"grid-template-columns: minmax(0, 1fr) repeat({set_count}, {cell}) {'7rem' if big else '5.5rem'};"
    value_size = "text-5xl" if big else "text-2xl"
    name_size = "text-3xl" if big else "text-lg"
    live = state is not None and not state.finished
    server_team = state.server[0] if live else None
    #super tie-break : ses points sont affiches dans la colonne du set
    labels = state.point_labels(match.format.no_ad) if live and not state.super_tiebreak else ["", ""]

    #shrink-0 : jamais comprime par une colonne parente qui manque de place
    #(sinon, en overflow-hidden, il peut disparaitre a une hauteur nulle)
    with ui.column().classes("w-full shrink-0 gap-0 rounded-xl overflow-hidden bg-slate-900 text-white shadow-lg"):
        #w-full sur chaque ligne : sans lui, chaque ligne prend la largeur de son
        #contenu (colonne NiceGUI alignee a gauche) et les colonnes de score ne
        #tombent plus sous leurs titres des qu'un nom est plus long
        with ui.element("div").classes("w-full grid items-center px-4 py-2 bg-slate-800").style(columns):
            ui.label("")
            for number in range(1, set_count + 1):
                ui.label(f"SET {number}").classes("text-xs font-bold tracking-wide text-slate-400 text-center")
            ui.label("PTS").classes("text-xs font-bold tracking-wide text-amber-400 text-center")
        for team_index, team in enumerate((match.team1, match.team2)):
            border = " border-t border-slate-700" if team_index else ""
            winner = state is not None and state.winner == team_index
            with ui.element("div").classes("w-full grid items-center px-4 " + ("py-5" if big else "py-3") + border).style(columns):
                with ui.row(wrap=False).classes("items-center gap-2 min-w-0 overflow-hidden"):
                    #service : balle jaune devant l'equipe au service ; vainqueur : coche
                    if winner:
                        ui.icon("check_circle").classes("text-green-400 " + ("text-3xl" if big else "text-xl"))
                    elif server_team == team_index:
                        ui.element("span").classes(
                            "rounded-full bg-yellow-300 shrink-0 " + ("w-4 h-4" if big else "w-3 h-3")
                        ).tooltip("Au service")
                    else:
                        ui.element("span").classes("shrink-0 " + ("w-4 h-4" if big else "w-3 h-3"))
                    #drapeaux + noms : compresses en X s'ils sont trop longs (.fit-x, voir layout.py)
                    with ui.element("div").classes("fit-x flex-1 min-w-0"):
                        with ui.element("div").classes("items-center gap-2"):
                            if not team:
                                ui.label("A definir").classes(f"{name_size} italic text-slate-500")
                            for position, player in enumerate(team):
                                if position:
                                    ui.label("/").classes(f"{name_size} text-slate-500")
                                flag(player.country, "h-6 w-8" if big else LIST_FLAG_SIZE)
                                ui.label(player.short_name).classes(f"{name_size} font-bold")
                for index in range(set_count):
                    text, exponent, current = _set_cell(state, index, team_index)
                    #case de largeur fixe : le chiffre reste centre, l'exposant du
                    #tie-break est superpose (position absolue) sans le decaler
                    with ui.element("div").classes("relative w-full text-center"):
                        ui.label(text or "").classes(
                            f"{value_size} font-mono font-bold tabular-nums "
                            + ("text-white" if current else "text-slate-300" if text else "text-slate-600")
                        )
                        if exponent:
                            ui.label(exponent).classes(
                                "absolute top-0 right-1 text-sm font-mono font-bold text-slate-400"
                            )
                ui.label(labels[team_index] if live else ("-" if state is None else "")).classes(
                    f"w-full {value_size} font-mono font-bold tabular-nums text-center "
                    + ("text-amber-400" if live else "text-amber-400/60")
                )
