# Modele de donnees d'un match de tennis (independant de la base SQLite et
# de l'interface) : dataclasses Match/Player/MatchFormat et listes de
# valeurs proposees dans les formulaires.
#
# Un match oppose 2 equipes (team 1 / team 2) de 1 joueur (simple) ou 2
# joueurs (double), choisis dans l'annuaire des joueurs (Player). Le format (nombre de sets, tie-break, point decisif...)
# est stocke AVEC le match : il conditionnera plus tard le moteur de score
# de l'interface d'arbitrage.

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

#categories de match : (cle stockee en base, libelle affiche, nb joueurs par equipe)
CATEGORIES: list[tuple[str, str, int]] = [
    ("MS", "Simple Messieurs", 1),
    ("WS", "Simple Dames", 1),
    ("MD", "Double Messieurs", 2),
    ("WD", "Double Dames", 2),
    ("XD", "Double Mixte", 2),
]
CATEGORY_LABELS = {key: label for key, label, _ in CATEGORIES}
PLAYERS_PER_TEAM = {key: count for key, _, count in CATEGORIES}

ROUNDS = [
    "Qualifications",
    "1er tour",
    "2e tour",
    "3e tour",
    "Huitiemes de finale",
    "Quarts de finale",
    "Demi-finales",
    "Finale",
    "Match de poules",
    "Exhibition",
]

SURFACES = ["Dur", "Terre battue", "Gazon", "Dur (indoor)", "Terre battue (indoor)", "Moquette"]

#niveaux de tournoi proposes (saisie libre possible)
TOURNAMENT_LEVELS = [
    "Grand Chelem", "ATP 1000", "ATP 500", "ATP 250", "WTA 1000", "WTA 500", "WTA 250",
    "Challenger", "ITF", "Tournoi national", "Tournoi regional", "Exhibition",
]

#regle appliquee dans le set decisif (dernier set possible du match)
FINAL_SET_RULES: dict[str, str] = {
    "tiebreak": "Tie-break classique (comme les autres sets)",
    "tiebreak_10": "Tie-break en 10 points a egalite de jeux",
    "super_tiebreak": "Super tie-break en 10 points a la place du set",
    "advantage": "Sans tie-break (2 jeux d'ecart)",
}

#version courte, pour la colonne "SET DECISIF" de la liste des matchs
FINAL_SET_SHORT: dict[str, str] = {
    "tiebreak": "TB classique",
    "tiebreak_10": "TB 10 pts",
    "super_tiebreak": "Super TB",
    "advantage": "Avantage",
}

#dates : stockees en ISO (AAAA-MM-JJ, tri correct et format d'echange de
#la future API), affichees et saisies en JJ/MM/AAAA dans l'interface
DISPLAY_DATE_FORMAT = "%d/%m/%Y"


def format_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime(DISPLAY_DATE_FORMAT)
    except (TypeError, ValueError):
        return ""


#noms francais (sans dependre de la locale du systeme, souvent anglaise)
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = [
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
]


#"Samedi 08/11/2026" (titres des jours de la liste des matchs)
def format_day(iso: str) -> str:
    try:
        day = date.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    return f"{DAYS[day.weekday()].capitalize()} {day.strftime(DISPLAY_DATE_FORMAT)}"


#JJ/MM/AAAA -> ISO ; None si le texte n'est pas une date complete valide
def parse_date(text: str) -> str | None:
    try:
        return datetime.strptime((text or "").strip(), DISPLAY_DATE_FORMAT).date().isoformat()
    except ValueError:
        return None


#statuts d'un match enregistres en base : (cle, libelle, couleur
#tailwind de la puce)
STATUSES: dict[str, tuple[str, str]] = {
    "scheduled": ("PROGRAMME", "slate"),
    "live": ("EN COURS", "red"),
    "finished": ("TERMINE", "green"),
}

#statuts AFFICHES : en plus des statuts enregistres, "A VENIR" est calcule
#a la volee (voir Match.display_status), jamais stocke - il depend de
#l'heure courante. Ordre = ordre des filtres de la liste des matchs.
UPCOMING_WINDOW = timedelta(minutes=10)
DISPLAY_STATUSES: dict[str, tuple[str, str]] = {
    "scheduled": STATUSES["scheduled"],
    "upcoming": ("A VENIR", "orange"),
    "live": STATUSES["live"],
    "finished": STATUSES["finished"],
}


@dataclass
class MatchFormat:
    sets_to_win: int = 2              #2 = 3 sets gagnants max, 3 = 5 sets
    games_per_set: int = 6            #6 standard, 4 pour le format Fast4
    tiebreak_enabled: bool = True     #tie-break a egalite de jeux (6-6)
    tiebreak_points: int = 7
    final_set_rule: str = "tiebreak"  #voir FINAL_SET_RULES
    no_ad: bool = False               #point decisif a 40-40

    #resume court affiche dans la liste des matchs et le formulaire
    @property
    def summary(self) -> str:
        parts = [
            f"{self.sets_to_win * 2 - 1} sets",
            f"{self.games_per_set} jeux",
            f"TB {self.tiebreak_points} pts" if self.tiebreak_enabled else "sans TB",
        ]
        final_set = {
            "tiebreak_10": "dernier set : TB 10 pts",
            "super_tiebreak": "dernier set : super TB",
            "advantage": "dernier set a l'avantage",
        }.get(self.final_set_rule)
        if final_set:
            parts.append(final_set)
        if self.no_ad:
            parts.append("point decisif")
        return " · ".join(parts)


#formats predefinis proposes en un clic dans le formulaire de creation
FORMAT_PRESETS: dict[str, MatchFormat] = {
    "Standard (3 sets)": MatchFormat(),
    "Grand Chelem (5 sets)": MatchFormat(sets_to_win=3, final_set_rule="tiebreak_10"),
    "Grand Chelem dames (3 sets)": MatchFormat(final_set_rule="tiebreak_10"),
    "Double ATP/WTA (point decisif + super TB)": MatchFormat(final_set_rule="super_tiebreak", no_ad=True),
    "Fast4": MatchFormat(games_per_set=4, tiebreak_points=5, no_ad=True),
}


GENDERS = {"M": "Homme", "F": "Femme"}
HANDS = {"R": "Droitier", "L": "Gaucher"}
BACKHANDS = {"2": "Revers a deux mains", "1": "Revers a une main"}


#joueur de l'annuaire, reutilisable dans plusieurs matchs (voir
#database.py : table athletes, liee aux matchs par match_players)
@dataclass
class Player:
    first_name: str = ""
    last_name: str = ""
    #noms pour l'habillage TV, TOUJOURS remplis en base (lus tels quels par
    #la future API) ; *_auto : nom recalcule depuis prenom/nom a chaque
    #enregistrement (voir fill_tv_names), sinon saisi a la main
    tv_long_name: str = ""
    tv_short_name: str = ""
    tv_long_auto: bool = True
    tv_short_auto: bool = True
    gender: str = "M"               #voir GENDERS
    country: str = ""               #code a 3 lettres, voir countries.py
    birth_date: str = ""            #AAAA-MM-JJ
    best_ranking: int | None = None
    hand: str = ""                  #voir HANDS
    backhand: str = ""              #voir BACKHANDS
    height_cm: int | None = None
    weight_kg: int | None = None
    turned_pro: int | None = None   #annee
    notes: str = ""
    wikidata_id: str = ""           #fiche importee depuis Wikidata (voir wikidata.py)
    photo: str = ""                 #fichier PNG 3000x3000 dans photos/ (voir photos.py)
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name.upper()}".strip()

    #TV LONG NAME automatique : "Prenom NOM"
    @property
    def auto_long_name(self) -> str:
        return self.display_name

    #TV SHORT NAME automatique : "P. NOM"
    @property
    def auto_short_name(self) -> str:
        initial = f"{self.first_name[0].upper()}. " if self.first_name else ""
        return f"{initial}{self.last_name.upper()}".strip()

    @property
    def long_name(self) -> str:
        return self.auto_long_name if self.tv_long_auto else (self.tv_long_name or self.auto_long_name)

    @property
    def short_name(self) -> str:
        return self.auto_short_name if self.tv_short_auto else (self.tv_short_name or self.auto_short_name)

    #ecrit les noms TV effectifs dans tv_long_name/tv_short_name (appele
    #avant chaque enregistrement : la base contient toujours les vrais noms)
    def fill_tv_names(self) -> None:
        self.tv_long_name = self.long_name
        self.tv_short_name = self.short_name

    @property
    def age(self) -> int | None:
        try:
            birth = date.fromisoformat(self.birth_date)
        except ValueError:
            return None
        today = date.today()
        return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


#tournoi cree a l'avance (page TOURNOIS) puis simplement selectionne dans
#chaque match : la surface et la liste des courts viennent du tournoi
@dataclass
class Tournament:
    name: str = ""
    level: str = ""                 #voir TOURNAMENT_LEVELS
    surface: str = ""               #voir SURFACES
    venue: str = ""                 #site / club
    city: str = ""
    country: str = ""               #code a 3 lettres, voir countries.py
    start_date: str = ""            #AAAA-MM-JJ
    end_date: str = ""
    courts: list[str] = field(default_factory=list)
    #marque a la main comme "tournoi en cours" (un seul a la fois), prioritaire
    #sur la detection par les dates - voir database.current_tournaments
    is_current: bool = False
    logo: str = ""                  #fichier PNG redimensionne dans logos/ (voir logos.py)
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    @property
    def dates(self) -> str:
        if self.start_date and self.end_date and self.start_date != self.end_date:
            return f"{format_date(self.start_date)} > {format_date(self.end_date)}"
        return format_date(self.start_date or self.end_date)


@dataclass
class Match:
    tournament_id: int | None = None
    #tournoi charge avec le match (lecture seule, voir database.py)
    tournament: Tournament | None = None
    category: str = "MS"            #voir CATEGORIES
    round: str = ""
    court: str = ""
    scheduled_date: str = ""        #AAAA-MM-JJ
    scheduled_time: str = ""        #HH:MM
    status: str = "scheduled"       #voir STATUSES
    format: MatchFormat = field(default_factory=MatchFormat)
    #team1/team2 : 1 joueur en simple, 2 en double (voir PLAYERS_PER_TEAM)
    team1: list[Player] = field(default_factory=list)
    team2: list[Player] = field(default_factory=list)
    #arbitrage (voir umpire.py / scoring.py) : equipe qui sert le premier jeu
    #(0 = equipe 1, 1 = equipe 2 ; None = match pas encore debute) et, pour
    #chaque equipe, joueur (0/1) qui sert en premier (double)
    first_server: int | None = None
    first_server_1: int = 0
    first_server_2: int = 0
    #equipe a gauche au debut du match, vu depuis la chaise d'arbitre (None =
    #pas encore debute ; les cotes suivent ensuite les changements, voir
    #scoring.ScoreState.left_team)
    first_left: int | None = None
    started_at: str = ""
    finished_at: str = ""
    winner: int | None = None       #0 = equipe 1, 1 = equipe 2
    end_reason: str = ""            #"" fin normale, "RET" abandon
    id: int | None = None
    created_at: str = ""
    updated_at: str = ""

    #debut prevu (date + heure, minuit si l'heure n'est pas saisie), None
    #sans date valide
    @property
    def scheduled_start(self) -> datetime | None:
        try:
            return datetime.fromisoformat(f"{self.scheduled_date}T{self.scheduled_time or '00:00'}")
        except ValueError:
            return None

    #statut a afficher : un match programme (pas encore lance) dont le
    #debut est passe ou dans moins de UPCOMING_WINDOW passe "A VENIR"
    def display_status(self, now: datetime) -> str:
        if self.status != "scheduled":
            return self.status
        start = self.scheduled_start
        if start is not None and now >= start - UPCOMING_WINDOW:
            return "upcoming"
        return "scheduled"

    @property
    def is_double(self) -> bool:
        return PLAYERS_PER_TEAM.get(self.category, 1) == 2

    @staticmethod
    def team_name(team: list[Player]) -> str:
        names = [player.last_name.upper() for player in team if player.last_name]
        return " / ".join(names) if names else "A definir"
