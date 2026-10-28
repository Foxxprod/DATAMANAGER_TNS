# Page TOURNOIS : tournois crees a l'avance (build_tournament_list) et
# fenetre de creation/edition (build_tournament_dialog), egalement ouverte
# depuis la fenetre match pour creer un tournoi absent de la liste sans
# quitter la saisie du match.

import dataclasses

from nicegui import ui

import database
from countries import COUNTRY_OPTIONS, country_name
from forms import FIELD_PROPS, ImageField, date_input, form_dialog, optional_select
from layout import (
    LIST_FLAG_SIZE,
    LIST_GRID_CLASSES_BASE,
    LIST_ROW_CLASSES,
    LIST_TEXT_CLASSES,
    flag,
    list_card,
    list_cell,
    list_header,
    page_body,
    section_card,
    tournament_logo,
)
from events import subscribe_for, tournaments_changed
from logos import ACCEPTED_TYPES, LOGO_MAX_SIZE, LOGOS
from models import SURFACES, TOURNAMENT_LEVELS, Tournament, format_date

#colonnes de la liste (meme principe que la liste des matchs, voir
#admin.LIST_GRID_CLASSES : une information par colonne)
LIST_GRID_CLASSES = LIST_GRID_CLASSES_BASE + (
    "min-w-[106rem] grid-cols-[6rem_minmax(14rem,1.3fr)_9rem_minmax(10rem,1fr)_minmax(9rem,1fr)_"
    "minmax(10rem,1fr)_10rem_7rem_7rem_minmax(10rem,1fr)_5rem_5rem]"
)
LIST_COLUMNS = [
    ("EN COURS", "text-center"),
    ("TOURNOI", "text-left"),
    ("NIVEAU", "text-left"),
    ("SITE / CLUB", "text-left"),
    ("VILLE", "text-left"),
    ("PAYS", "text-left"),
    ("SURFACE", "text-left"),
    ("DEBUT", "text-left"),
    ("FIN", "text-left"),
    ("COURTS", "text-left"),
    ("MATCHS", "text-center"),
    ("", "text-right"),
]


# ---------------------------------------------------------------------------
# Liste des tournois
# ---------------------------------------------------------------------------

#construit la liste et renvoie la fonction d'ouverture de la fenetre
#tournoi (tournament_id None = creation), utilisee par le bouton NOUVEAU
#TOURNOI du header
def build_tournament_list():
    state = {"search": ""}

    with ui.dialog() as delete_dialog, ui.card().classes("gap-3 w-[26rem]"):
        ui.label("Supprimer ce tournoi ?").classes("text-base font-bold")
        delete_text = ui.label().classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=lambda: delete_dialog.submit(False)).props("flat")
            ui.button(
                "Supprimer", color=None, on_click=lambda: delete_dialog.submit(True)
            ).classes("bg-red-600 text-white")

    async def on_delete_click(tournament: Tournament, match_count: int) -> None:
        if match_count:
            ui.notify(
                f"{tournament.name} contient {match_count} match(s) : supprimez-les d'abord",
                type="warning",
            )
            return
        delete_text.text = f"{tournament.name} sera definitivement supprime."
        if await delete_dialog:
            if database.delete_tournament(tournament.id):
                ui.notify("Tournoi supprime", type="info")
                tournaments_changed.emit()
            else:
                ui.notify("Tournoi utilise par un match, suppression impossible", type="negative")

    #meme principe que admin.open_match_dialog : fenetre reconstruite a
    #chaque ouverture, dans le conteneur stable de la page
    async def open_tournament_dialog(tournament_id: int | None = None) -> None:
        tournament = None
        if tournament_id is not None:
            tournament = database.get_tournament(tournament_id)
            if tournament is None:
                ui.notify(f"Tournoi #{tournament_id} introuvable", type="negative")
                tournament_list.refresh()
                return

        with page:
            dialog = build_tournament_dialog(tournament)
        #liste rafraichie par l'evenement tournaments_changed (emis a
        #l'enregistrement, voir build_tournament_dialog)
        await dialog
        dialog.delete()

    #etoile de la colonne EN COURS : marque ce tournoi comme tournoi en cours
    #(demarque le precedent) ou le demarque
    def on_current_click(tournament: Tournament) -> None:
        database.set_current_tournament(tournament.id, not tournament.is_current)
        if tournament.is_current:
            ui.notify(f"{tournament.name} n'est plus le tournoi en cours", type="info")
        else:
            ui.notify(f"{tournament.name} est le tournoi en cours", type="positive")
        tournaments_changed.emit()

    @ui.refreshable
    def tournament_list() -> None:
        all_tournaments = database.list_tournaments()
        search = state["search"].strip().lower()
        tournaments = [
            tournament for tournament in all_tournaments
            if not search or search in " ".join(
                (tournament.name, tournament.level, tournament.venue, tournament.city)
            ).lower()
        ]
        match_counts = database.tournament_match_counts()

        if not tournaments:
            with ui.column().classes("w-full items-center gap-3 py-12"):
                ui.icon("emoji_events").classes("text-5xl text-slate-300")
                ui.label(
                    "Aucun tournoi ne correspond a la recherche" if all_tournaments else "Aucun tournoi pour le moment"
                ).classes("text-slate-500")
                ui.button("Creer un tournoi", icon="add", on_click=lambda: open_tournament_dialog())
            return

        with ui.element("div").classes("w-full overflow-x-auto"):
            list_header(LIST_GRID_CLASSES, LIST_COLUMNS)
            for tournament in tournaments:
                _tournament_row(
                    tournament, match_counts.get(tournament.id, 0),
                    open_tournament_dialog, on_delete_click, on_current_click,
                )

    with page_body() as page:
        card, tools = list_card("TOURNOIS")
        with tools:
            def on_search(event) -> None:
                state["search"] = event.value or ""
                tournament_list.refresh()

            ui.input(placeholder="Rechercher (nom, ville...)", on_change=on_search).props(
                "outlined dense clearable debounce=250"
            ).classes("w-72").add_slot("prepend", '<q-icon name="search" />')

        with card:
            tournament_list()

    #toute modification de tournoi (ici, dans le header, depuis la fenetre
    #match ou un autre poste) rafraichit la liste
    subscribe_for(tournaments_changed, card, tournament_list.refresh)

    return open_tournament_dialog


def _tournament_row(
    tournament: Tournament, match_count: int, on_edit_click, on_delete_click, on_current_click
) -> None:
    highlight = " bg-amber-400/10" if tournament.is_current else ""
    with ui.element("div").classes(LIST_GRID_CLASSES + LIST_ROW_CLASSES + highlight):
        with ui.row().classes("justify-center"):
            ui.button(
                icon="star" if tournament.is_current else "star_border",
                color="amber" if tournament.is_current else "grey",
                on_click=lambda t=tournament: on_current_click(t),
            ).props("flat round").tooltip(
                "Tournoi en cours - cliquer pour le retirer" if tournament.is_current
                else "Definir comme tournoi en cours"
            )
        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            tournament_logo(tournament)
            list_cell(tournament.name, strong=True)
        list_cell(tournament.level)
        list_cell(tournament.venue)
        list_cell(tournament.city)
        with ui.row(wrap=False).classes("items-center gap-2 min-w-0"):
            flag(tournament.country, LIST_FLAG_SIZE)
            ui.label(country_name(tournament.country) if tournament.country else "-").classes(LIST_TEXT_CLASSES)
        list_cell(tournament.surface)
        list_cell(format_date(tournament.start_date))
        list_cell(format_date(tournament.end_date))
        list_cell(", ".join(tournament.courts)).tooltip(", ".join(tournament.courts))
        list_cell(str(match_count) if match_count else "", strong=True, align="text-center")

        with ui.row(wrap=False).classes("gap-0 justify-end"):
            ui.button(
                icon="edit", on_click=lambda t=tournament: on_edit_click(t.id)
            ).props("flat round").tooltip("Modifier")
            ui.button(
                icon="delete", color="red", on_click=lambda t=tournament: on_delete_click(t, match_count)
            ).props("flat round").tooltip("Supprimer")


# ---------------------------------------------------------------------------
# Fenetre de creation / edition
# ---------------------------------------------------------------------------

#fenetre de creation (tournament None) / edition. A attendre (`await
#dialog`) : renvoie l'id du tournoi enregistre, None si fermee sans
#enregistrer.
def build_tournament_dialog(tournament: Tournament | None) -> ui.dialog:
    is_new = tournament is None
    working = dataclasses.replace(tournament) if tournament else Tournament()
    working.courts = list(working.courts)

    title = "NOUVEAU TOURNOI" if is_new else f"MODIFIER {tournament.name}"
    dialog, body, footer = form_dialog(title, width="52rem")

    def on_save() -> None:
        for name in ("name", "venue", "city"):
            setattr(working, name, (getattr(working, name) or "").strip())
        working.courts = [court.strip() for court in working.courts if court.strip()]
        if not working.name:
            ui.notify("Le nom du tournoi est obligatoire", type="negative")
            return
        if working.start_date and working.end_date and working.end_date < working.start_date:
            ui.notify("La date de fin est avant la date de debut", type="negative")
            return
        tournament_id = database.save_tournament(working)
        #logo rattache apres l'enregistrement : l'id du tournoi (nom du
        #fichier) n'existe pas avant pour un nouveau tournoi
        logo = logo_field.commit(tournament_id)
        if logo is not None:
            working.logo = logo
            database.set_tournament_logo(tournament_id, logo)
        state["saved"] = True
        ui.notify(f"{working.name} {'cree' if is_new else 'mis a jour'}", type="positive")
        tournaments_changed.emit()
        dialog.submit(tournament_id)

    #fenetre fermee sans enregistrer : le logo en attente est supprime
    state = {"saved": False}

    def on_dialog_close(event) -> None:
        if not event.value and not state["saved"]:
            logo_field.discard()

    dialog.on_value_change(on_dialog_close)

    def refresh_flag() -> None:
        flag_box.clear()
        with flag_box:
            flag(working.country, "h-6 w-8")

    with body:
        with section_card("INFORMATIONS", "emoji_events"):
            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-4 gap-2"):
                ui.input("Nom du tournoi *").bind_value(working, "name").props(FIELD_PROPS).classes("md:col-span-2")
                optional_select(TOURNAMENT_LEVELS, "Niveau", working, "level", allow_new=True)
                optional_select(SURFACES, "Surface", working, "surface", allow_new=True)
                date_input(working, "start_date", "Date de debut").classes("md:col-span-2")
                date_input(working, "end_date", "Date de fin").classes("md:col-span-2")
            ui.switch(
                "Tournoi en cours (affiche sur l'accueil et propose par defaut dans les nouveaux matchs, "
                "quelles que soient les dates)"
            ).bind_value(working, "is_current")

        with section_card("LIEU", "place"):
            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-2 gap-2"):
                ui.input("Site / club").bind_value(working, "venue").props(FIELD_PROPS)
                ui.input("Ville").bind_value(working, "city").props(FIELD_PROPS)
                with ui.row(wrap=False).classes("items-center gap-2 md:col-span-2"):
                    optional_select(COUNTRY_OPTIONS, "Pays", working, "country", with_input=True).classes(
                        "flex-1"
                    ).on_value_change(lambda _: refresh_flag())
                    flag_box = ui.row().classes("w-8 justify-center")

        with section_card("LOGO", "image"):
            logo_field = ImageField(
                LOGOS, working.logo, working.updated_at,
                upload_label="Choisir le logo du tournoi",
                accept=ACCEPTED_TYPES,
                hint=f"PNG, JPEG, WEBP... : redimensionne automatiquement (max {LOGO_MAX_SIZE[0]} x "
                     f"{LOGO_MAX_SIZE[1]} px, proportions conservees). Enregistre avec le tournoi.",
                placeholder_icon="emoji_events",
                fit="contain",
            )

        with section_card("COURTS", "grid_view"):
            ui.input_chips("Courts du tournoi", new_value_mode="add-unique").bind_value(
                working, "courts"
            ).props(FIELD_PROPS).classes("w-full")
            ui.label(
                "Tapez le nom d'un court puis Entree pour l'ajouter (ex: Central, Court 1...). "
                "Ils seront proposes a la creation des matchs."
            ).classes("text-xs text-slate-500")

    refresh_flag()

    with footer:
        ui.button("Annuler", on_click=lambda: dialog.submit(None)).props("flat")
        ui.button(
            "Creer le tournoi" if is_new else "Enregistrer", icon="save", on_click=on_save
        ).classes("px-6")

    return dialog
