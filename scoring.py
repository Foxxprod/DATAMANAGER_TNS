# Moteur de score d'un match de tennis, independant de l'interface et de la
# base : le score est RECALCULE en rejouant la liste des points (equipe
# gagnante de chaque point, dans l'ordre). Annuler un point = le retirer de
# la liste et recalculer, sans etat intermediaire a defaire.
#
# Equipes numerotees 0 (equipe/joueur 1) et 1 (equipe/joueur 2). En double,
# chaque equipe a 2 joueurs (index 0/1 dans l'equipe) qui alternent au
# service a chaque fois que leur equipe sert.
#
# Regles appliquees (voir models.MatchFormat) :
#   - jeu : 0/15/30/40, 2 points d'ecart (avantage) ; point decisif a 40-40
#     si no_ad (le premier a 4 points gagne)
#   - set : games_per_set jeux avec 2 jeux d'ecart ; a games_per_set partout,
#     tie-break (si tiebreak_enabled) en tiebreak_points, 2 points d'ecart
#   - set decisif (chaque equipe a sets_to_win - 1 sets) selon final_set_rule :
#     "tiebreak" comme les autres sets, "tiebreak_10" tie-break en 10 points,
#     "advantage" sans tie-break, "super_tiebreak" le set est remplace par un
#     super tie-break en 10 points
#   - service : alterne a chaque jeu ; en tie-break, le premier serveur sert
#     1 point puis alternance tous les 2 points ; l'equipe qui a servi en
#     premier dans le tie-break recoit au premier jeu du set suivant

from dataclasses import dataclass, field

from models import MatchFormat

POINT_LABELS = ["0", "15", "30", "40"]
SUPER_TIEBREAK_POINTS = 10


@dataclass
class ScoreState:
    #sets termines : jeux [equipe 0, equipe 1] ; pour un set conclu par un
    #tie-break, points du tie-break dans `tiebreaks` (None sinon). Un super
    #tie-break est enregistre comme un set 1-0 avec ses points de tie-break.
    sets: list[list[int]] = field(default_factory=list)
    tiebreaks: list[list[int] | None] = field(default_factory=list)
    super_tiebreak_sets: list[bool] = field(default_factory=list)
    games: list[int] = field(default_factory=lambda: [0, 0])
    points: list[int] = field(default_factory=lambda: [0, 0])
    sets_won: list[int] = field(default_factory=lambda: [0, 0])
    in_tiebreak: bool = False
    super_tiebreak: bool = False
    tiebreak_target: int = 7
    #equipe qui sert le prochain jeu (hors tie-break) et, par equipe, joueur
    #qui servira la prochaine fois que l'equipe sert
    game_server: int = 0
    server_player: list[int] = field(default_factory=lambda: [0, 0])
    tiebreak_first_server: int = 0
    #False en simple : un seul joueur par equipe, le serveur est toujours le
    #joueur 0 (la rotation de server_player n'a de sens qu'en double)
    doubles: bool = True
    winner: int | None = None
    total_points: int = 0

    #equipe et joueur au service pour le prochain point
    @property
    def server(self) -> tuple[int, int]:
        team, player = self._server()
        return team, player if self.doubles else 0

    def _server(self) -> tuple[int, int]:
        if not self.in_tiebreak:
            return self.game_server, self.server_player[self.game_server]
        played = sum(self.points)
        turn = 0 if played == 0 else (played + 1) // 2
        first = self.tiebreak_first_server
        team = first if turn % 2 == 0 else 1 - first
        #chaque equipe change de serveur a chacun de ses tours de service
        own_turns = turn // 2
        return team, self.server_player[team] ^ (own_turns % 2)

    @property
    def finished(self) -> bool:
        return self.winner is not None

    @property
    def set_number(self) -> int:
        return len(self.sets) + 1

    #points du jeu en cours tels qu'affiches ("15", "40", "AD"...)
    def point_labels(self, no_ad: bool) -> list[str]:
        if self.in_tiebreak:
            return [str(points) for points in self.points]
        a, b = self.points
        if a >= 3 and b >= 3 and not no_ad:
            if a == b:
                return ["40", "40"]
            return ["AD", "40"] if a > b else ["40", "AD"]
        return [POINT_LABELS[min(a, 3)], POINT_LABELS[min(b, 3)]]


def _is_final_set(state: ScoreState, fmt: MatchFormat) -> bool:
    return state.sets_won == [fmt.sets_to_win - 1] * 2


def _start_tiebreak(state: ScoreState, target: int, super_tiebreak: bool = False) -> None:
    state.in_tiebreak = True
    state.super_tiebreak = super_tiebreak
    state.tiebreak_target = target
    state.tiebreak_first_server = state.game_server


def _end_set(state: ScoreState, fmt: MatchFormat, team: int, tiebreak: list[int] | None) -> None:
    state.sets.append(list(state.games))
    state.tiebreaks.append(tiebreak)
    state.super_tiebreak_sets.append(state.super_tiebreak)
    state.sets_won[team] += 1
    state.games = [0, 0]
    state.points = [0, 0]
    state.in_tiebreak = False
    state.super_tiebreak = False
    if state.sets_won[team] == fmt.sets_to_win:
        state.winner = team
        return
    if _is_final_set(state, fmt) and fmt.final_set_rule == "super_tiebreak":
        _start_tiebreak(state, SUPER_TIEBREAK_POINTS, super_tiebreak=True)


def _end_game(state: ScoreState, fmt: MatchFormat, team: int) -> None:
    state.games[team] += 1
    state.points = [0, 0]
    #service : l'equipe qui vient de servir change de serveur pour son
    #prochain jeu de service, et le service passe a l'autre equipe
    state.server_player[state.game_server] ^= 1
    state.game_server = 1 - state.game_server

    won, lost = state.games[team], state.games[1 - team]
    target = fmt.games_per_set
    if won >= target and won - lost >= 2:
        _end_set(state, fmt, team, None)
        return
    if won == target and lost == target:
        final = _is_final_set(state, fmt)
        rule = fmt.final_set_rule if final else "tiebreak"
        if rule == "tiebreak_10":
            _start_tiebreak(state, 10)
        elif rule == "tiebreak" and fmt.tiebreak_enabled:
            _start_tiebreak(state, fmt.tiebreak_points)
        #sinon ("advantage" ou tie-break desactive) : le set continue jusqu'a 2 jeux d'ecart


def _end_tiebreak(state: ScoreState, fmt: MatchFormat, team: int) -> None:
    tiebreak = list(state.points)
    if state.super_tiebreak:
        state.games = [1, 0] if team == 0 else [0, 1]
    else:
        state.games[team] += 1
    #l'equipe qui a servi en premier dans le tie-break recoit au jeu suivant ;
    #le tie-break compte comme un jeu de service de cette equipe
    first = state.tiebreak_first_server
    state.server_player[first] ^= 1
    state.game_server = 1 - first
    _end_set(state, fmt, team, tiebreak)


def apply_point(state: ScoreState, fmt: MatchFormat, team: int) -> None:
    if state.winner is not None:
        return
    state.total_points += 1
    other = 1 - team
    state.points[team] += 1
    won, lost = state.points[team], state.points[other]
    if state.in_tiebreak:
        if won >= state.tiebreak_target and won - lost >= 2:
            _end_tiebreak(state, fmt, team)
        return
    if (won >= 4 and fmt.no_ad) or (won >= 4 and won - lost >= 2):
        _end_game(state, fmt, team)


#score apres la liste `points` (equipe gagnante de chaque point).
#changement de serveur saisi a la main par l'operateur (correction) :
#`player` (de l'equipe `team`) sert le prochain point ; l'alternance normale
#reprend ensuite a partir de lui
def set_server(state: ScoreState, team: int, player: int) -> None:
    if state.winner is not None:
        return
    if state.in_tiebreak:
        #en tie-break, le serveur du point depend du nombre de points joues :
        #on recale le premier serveur du tie-break pour obtenir `team` ici
        played = sum(state.points)
        turn = 0 if played == 0 else (played + 1) // 2
        state.tiebreak_first_server = team if turn % 2 == 0 else 1 - team
        state.server_player[team] = player ^ ((turn // 2) % 2)
    else:
        state.game_server = team
        state.server_player[team] = player


#Evenements d'un match : un entier = point gagne par cette equipe ; un tuple
#("server", equipe, joueur) = changement de serveur manuel (voir set_server).
#`first_server` : equipe qui sert le premier jeu ; `first_players` : pour
#chaque equipe, joueur (0/1) qui sert en premier quand l'equipe sert.
def compute_state(
    fmt: MatchFormat, first_server: int, first_players: tuple[int, int], points: list
) -> ScoreState:
    state = ScoreState(game_server=first_server, server_player=list(first_players))
    if _is_final_set(state, fmt) and fmt.final_set_rule == "super_tiebreak":
        #cas limite : match en 1 set gagnant joue en super tie-break
        _start_tiebreak(state, SUPER_TIEBREAK_POINTS, super_tiebreak=True)
    for event in points:
        if isinstance(event, tuple):
            _, team, player = event
            set_server(state, team, player)
        else:
            apply_point(state, fmt, event)
    return state


#score d'un match (models.Match) apres la liste de ses points. Un match
#termine par abandon (end_reason) a un vainqueur que les points seuls ne
#donnent pas : il est repris de match.winner.
def match_state(match, points: list[int]) -> ScoreState:
    state = compute_state(
        match.format, match.first_server or 0, (match.first_server_1, match.first_server_2), points
    )
    if match.end_reason and match.winner is not None and state.winner is None:
        state.winner = match.winner
    state.doubles = match.is_double
    return state


#situation du prochain point pour l'equipe `team` s'il le gagne :
#"match", "set", "break" (jeu gagne en relance) ou None
def point_stake(
    fmt: MatchFormat, first_server: int, first_players: tuple[int, int], points: list, team: int
) -> str | None:
    flags = point_flags(fmt, first_server, first_players, points, team)
    for stake in ("match", "set", "break"):
        if flags[stake]:
            return stake
    return None


#enjeux du prochain point pour l'equipe `team` s'il le gagne, SEPARES (ils
#peuvent se cumuler : balle de set ET de break) : {"break", "set", "match"}.
#"set" est faux quand c'est une balle de match (on affiche la plus importante).
def point_flags(
    fmt: MatchFormat, first_server: int, first_players: tuple[int, int], points: list, team: int
) -> dict[str, bool]:
    flags = {"break": False, "set": False, "match": False}
    before = compute_state(fmt, first_server, first_players, points)
    if before.finished:
        return flags
    after = compute_state(fmt, first_server, first_players, points + [team])
    flags["match"] = after.winner == team
    flags["set"] = not flags["match"] and after.sets_won[team] > before.sets_won[team]
    game_won = after.games != before.games or len(after.sets) != len(before.sets)
    flags["break"] = game_won and not before.in_tiebreak and before.server[0] != team
    return flags


#changement de cote a faire maintenant (entre deux points) : apres chaque jeu
#impair du set, a la fin d'un set au total de jeux impair (ex: 6-3, 7-6), et
#tous les 6 points en tie-break
def is_changeover(state: ScoreState, points: list) -> bool:
    if state.finished or not any(not isinstance(event, tuple) for event in points):
        return False
    if state.in_tiebreak:
        played = sum(state.points)
        return played > 0 and played % 6 == 0
    if state.points != [0, 0]:
        return False
    total = sum(state.games)
    return total % 2 == 1 or (total == 0 and bool(state.sets) and sum(state.sets[-1]) % 2 == 1)
