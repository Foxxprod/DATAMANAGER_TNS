# Page JOUEURS : annuaire des joueurs reutilisables dans les matchs
# (build_player_list), fiche de consultation ouverte au clic sur un joueur
# (build_player_profile) et fenetre de creation/edition d'un joueur
# (build_player_dialog), egalement ouverte depuis la fenetre match pour
# creer un joueur absent de la liste sans quitter la saisie du match.
# La fenetre joueur peut pre-remplir la fiche depuis Wikidata (wikidata.py).

import dataclasses
from typing import Callable

from nicegui import ui

import database
import wikidata
from events import players_changed
from countries import COUNTRY_OPTIONS, country_name
from forms import FIELD_PROPS, ImageField, date_input, form_dialog, optional_select, to_int
from layout import (
    FIELD_LABEL_CLASSES,
    LIST_FLAG_SIZE,
    LIST_GRID_CLASSES_BASE,
    LIST_ROW_CLASSES,
    LIST_STRONG_CLASSES,
    flag,
    list_card,
    list_cell,
    list_header,
    page_body,
    section_card,
)
from models import BACKHANDS, GENDERS, HANDS, Player, format_date
from photos import PHOTO_SIZE, PHOTOS

#colonnes de la liste (meme principe que la liste des matchs, voir
#admin.LIST_GRID_CLASSES : une information par colonne, grille partagee
#entete/lignes, defilement horizontal sur ecran etroit)
LIST_GRID_CLASSES = LIST_GRID_CLASSES_BASE + (
    "min-w-[86rem] grid-cols-[minmax(16rem,1.4fr)_minmax(10rem,1fr)_minmax(11rem,1fr)_"
    "4.5rem_6rem_7.5rem_6.5rem_6.5rem_5.5rem_4.5rem_5rem_5rem]"
)
LIST_COLUMNS = [
    ("JOUEUR", "text-left"),
    ("NOM COURT", "text-left"),
    ("PAYS", "text-left"),
    ("SEXE", "text-center"),
    ("AGE", "text-center"),
    ("CLASSEMENT", "text-center"),
    ("MAIN", "text-center"),
    ("REVERS", "text-center"),
    ("TAILLE", "text-center"),
    ("PHOTO", "text-center"),
    ("MATCHS", "text-center"),
    ("", "text-right"),
]
SHORT_BACKHANDS = {"2": "2 mains", "1": "1 main"}


# ---------------------------------------------------------------------------
# Liste des joueurs
# ---------------------------------------------------------------------------

#construit la liste et renvoie la fonction d'ouverture de la fenetre
#joueur (player_id None = creation), utilisee par le bouton NOUVEAU
#JOUEUR du header
def build_player_list():
    state = {"search": "", "gender": "all"}

    with ui.dialog() as delete_dialog, ui.card().classes("gap-3 w-[26rem]"):
        ui.label("Supprimer ce joueur ?").classes("text-base font-bold")
        delete_text = ui.label().classes("text-sm text-slate-500")
        with ui.row().classes("justify-end gap-2 w-full mt-2"):
            ui.button("Annuler", on_click=lambda: delete_dialog.submit(False)).props("flat")
            ui.button(
                "Supprimer", color=None, on_click=lambda: delete_dialog.submit(True)
            ).classes("bg-red-600 text-white")

    async def on_delete_click(player: Player, match_count: int) -> None:
        if match_count:
            ui.notify(
                f"{player.display_name} est engage dans {match_count} match(s) : "
                "retirez-le d'abord de ces matchs",
                type="warning",
            )
            return
        delete_text.text = f"{player.display_name} sera definitivement supprime de l'annuaire."
        if await delete_dialog:
            if database.delete_player(player.id):
                PHOTOS.delete(player.photo)
                ui.notify("Joueur supprime", type="info")
                players_changed.emit()
            else:
                ui.notify("Joueur engage dans un match, suppression impossible", type="negative")
            player_list.refresh()

    #meme principe que admin.open_match_dialog : fenetre reconstruite a
    #chaque ouverture, dans le conteneur stable de la page
    async def open_player_dialog(player_id: int | None = None) -> None:
        player = None
        if player_id is not None:
            player = database.get_player(player_id)
            if player is None:
                ui.notify(f"Joueur #{player_id} introuvable", type="negative")
                player_list.refresh()
                return

        with page:
            dialog = build_player_dialog(player)
        saved_id = await dialog
        dialog.delete()
        if saved_id:
            player_list.refresh()

    #fiche du joueur (clic sur sa ligne) ; son bouton Modifier ferme la fiche
    #et ouvre la fenetre d'edition
    async def open_player_profile(player: Player, match_count: int) -> None:
        with page:
            dialog = build_player_profile(player, match_count)
        result = await dialog
        dialog.delete()
        if result == "edit":
            await open_player_dialog(player.id)

    def matches_filters(player: Player) -> bool:
        if state["gender"] != "all" and player.gender != state["gender"]:
            return False
        search = state["search"].strip().lower()
        if search:
            haystack = " ".join(
                (player.first_name, player.last_name, player.long_name, player.short_name,
                 player.country, country_name(player.country))
            ).lower()
            return search in haystack
        return True

    @ui.refreshable
    def player_list() -> None:
        all_players = database.list_players()
        players = [player for player in all_players if matches_filters(player)]
        match_counts = database.player_match_counts()

        if not players:
            with ui.column().classes("w-full items-center gap-3 py-12"):
                ui.icon("person_search").classes("text-5xl text-slate-300")
                ui.label(
                    "Aucun joueur ne correspond a la recherche" if all_players else "Aucun joueur pour le moment"
                ).classes("text-slate-500")
                ui.button("Creer un joueur", icon="person_add", on_click=lambda: open_player_dialog())
            return

        with ui.element("div").classes("w-full overflow-x-auto"):
            list_header(LIST_GRID_CLASSES, LIST_COLUMNS)
            for player in players:
                _player_row(
                    player, match_counts.get(player.id, 0),
                    open_player_dialog, on_delete_click, open_player_profile,
                )

    with page_body() as page:
        card, tools = list_card("JOUEURS")
        with tools:
            def on_search(event) -> None:
                state["search"] = event.value or ""
                player_list.refresh()

            def on_gender(event) -> None:
                state["gender"] = event.value
                player_list.refresh()

            ui.input(placeholder="Rechercher (nom, pays...)", on_change=on_search).props(
                "outlined dense clearable debounce=250"
            ).classes("w-72").add_slot("prepend", '<q-icon name="search" />')
            ui.toggle(
                {"all": "Tous", "M": "Hommes", "F": "Femmes"}, value="all", on_change=on_gender
            ).props("dense no-caps rounded")

        with card:
            player_list()

    return open_player_dialog


#ligne cliquable : ouvre la fiche du joueur (sauf les boutons d'action, dont
#le clic ne remonte pas a la ligne - modificateur .stop)
def _player_row(player: Player, match_count: int, on_edit_click, on_delete_click, on_row_click) -> None:
    with ui.element("div").classes(LIST_GRID_CLASSES + LIST_ROW_CLASSES + " cursor-pointer").on(
        "click", lambda p=player: on_row_click(p, match_count)
    ):
        with ui.row(wrap=False).classes("items-center gap-3 min-w-0"):
            flag(player.country, LIST_FLAG_SIZE)
            ui.label(player.long_name or "Sans nom").classes(LIST_STRONG_CLASSES)
        list_cell(player.short_name)
        list_cell(f"{country_name(player.country)} ({player.country})" if player.country else "")
        list_cell(player.gender, align="text-center")
        list_cell(f"{player.age} ans" if player.age is not None else "", align="text-center")
        list_cell(f"#{player.best_ranking}" if player.best_ranking else "", strong=True, align="text-center")
        list_cell(HANDS.get(player.hand, ""), align="text-center")
        list_cell(SHORT_BACKHANDS.get(player.backhand, ""), align="text-center")
        list_cell(f"{player.height_cm} cm" if player.height_cm else "", align="text-center")
        if player.photo:
            with ui.row().classes("justify-center"):
                ui.icon("photo_camera").classes("text-xl text-green-500").tooltip(player.photo)
        else:
            list_cell("", align="text-center")
        list_cell(str(match_count) if match_count else "", strong=True, align="text-center")

        with ui.row(wrap=False).classes("gap-0 justify-end").on("click.stop", lambda: None):
            ui.button(
                icon="edit", on_click=lambda p=player: on_edit_click(p.id)
            ).props("flat round").tooltip("Modifier")
            ui.button(
                icon="delete", color="red", on_click=lambda p=player: on_delete_click(p, match_count)
            ).props("flat round").tooltip("Supprimer")


# ---------------------------------------------------------------------------
# Fiche du joueur (consultation)
# ---------------------------------------------------------------------------

#tuile titre/valeur des fiches (joueur, match - voir admin.build_match_profile)
def info_tile(title: str, value: str, highlight: bool = False) -> None:
    with ui.column().classes(
        "gap-0 rounded-xl px-3 py-2 bg-slate-100 dark:bg-slate-900/60 "
        + ("ring-2 ring-amber-400" if highlight else "")
    ):
        ui.label(title).classes("text-xs font-bold uppercase tracking-wide text-slate-500")
        ui.label(value or "-").classes(
            ("text-2xl" if highlight else "text-lg")
            + " font-bold " + ("text-slate-900 dark:text-slate-100" if value else "text-slate-400")
        )


#resume d'un joueur (fiche du match, voir admin.build_match_profile) :
#photo a gauche, identite/noms TV/pays et principales infos a droite
def player_summary(player: Player) -> None:
    with ui.row(wrap=False).classes("w-full items-start gap-4"):
        with ui.element("div").classes(
            "w-36 h-36 shrink-0 rounded-xl overflow-hidden bg-slate-900 flex items-center justify-center"
        ):
            if player.photo:
                ui.image(PHOTOS.file_url(player.photo, player.updated_at)).classes("w-full h-full").props("fit=cover")
            else:
                ui.icon("person").classes("text-6xl text-slate-600")
        with ui.column().classes("flex-1 min-w-0 gap-2"):
            with ui.column().classes("gap-0 min-w-0"):
                ui.label(player.first_name).classes("text-base text-slate-500")
                ui.label(player.last_name.upper() or "Sans nom").classes(
                    "text-2xl font-bold leading-tight text-slate-900 dark:text-slate-100 truncate"
                )
            with ui.row(wrap=False).classes("items-center gap-2"):
                flag(player.country, "h-5 w-7")
                ui.label(player.country or "-").classes(
                    "text-lg font-bold font-mono text-slate-900 dark:text-slate-100"
                ).tooltip("Code pays (NOC)")
                if player.country:
                    ui.label(country_name(player.country)).classes("text-sm text-slate-500 truncate")
            with ui.row(wrap=False).classes("items-center gap-2 min-w-0"):
                ui.label("TV").classes("text-xs font-bold text-slate-400")
                ui.label(player.long_name).classes("text-sm text-slate-700 dark:text-slate-200 truncate")
                ui.label("·").classes("text-slate-400")
                ui.label(player.short_name).classes("text-sm font-bold text-slate-700 dark:text-slate-200 truncate")
            with ui.element("div").classes("w-full grid grid-cols-3 gap-2"):
                info_tile("World rank", f"#{player.best_ranking}" if player.best_ranking else "", highlight=True)
                info_tile("Age", f"{player.age} ans" if player.age is not None else "")
                info_tile("Main", HANDS.get(player.hand, ""))


#fiche de consultation : photo a gauche, infos a droite (identite, noms TV,
#pays, puis statistiques). Se ferme au clic a cote, avec Echap ou la croix.
#A attendre (`await dialog`) : renvoie "edit" si le bouton Modifier a ete
#clique, None sinon.
def build_player_profile(player: Player, match_count: int) -> ui.dialog:
    dialog = ui.dialog()
    with dialog, ui.card().classes(
        "p-0 gap-0 rounded-2xl overflow-hidden bg-white dark:bg-slate-800"
    ).style("width: 60rem; max-width: 95vw;"):
        with ui.row(wrap=False).classes("w-full items-stretch gap-0"):
            # --- photo ------------------------------------------------------
            with ui.element("div").classes(
                "w-80 shrink-0 bg-slate-900 flex items-center justify-center"
            ).style("min-height: 20rem;"):
                if player.photo:
                    ui.image(PHOTOS.file_url(player.photo, player.updated_at)).classes("w-full h-full").props(
                        "fit=cover"
                    )
                else:
                    with ui.column().classes("items-center gap-2"):
                        ui.icon("person").classes("text-8xl text-slate-600")
                        ui.label("Pas de photo").classes("text-sm text-slate-500")

            # --- infos -------------------------------------------------------
            with ui.column().classes("flex-1 min-w-0 p-6 gap-4"):
                with ui.row(wrap=False).classes("w-full items-start justify-between gap-3"):
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(player.first_name).classes("text-xl text-slate-500")
                        ui.label(player.last_name.upper() or "Sans nom").classes(
                            "text-4xl font-bold leading-tight text-slate-900 dark:text-slate-100 truncate"
                        )
                    ui.button(icon="close", on_click=lambda: dialog.submit(None)).props(
                        "flat round"
                    ).tooltip("Fermer")

                with ui.row(wrap=False).classes("items-center gap-3"):
                    flag(player.country, "h-7 w-10")
                    if player.country:
                        ui.label(player.country).classes(
                            "text-2xl font-bold font-mono text-slate-900 dark:text-slate-100"
                        ).tooltip("Code pays (NOC)")
                        ui.label(country_name(player.country)).classes("text-lg text-slate-500")
                    else:
                        ui.label("Pays non renseigne").classes("text-lg text-slate-400")

                with ui.element("div").classes("w-full grid grid-cols-2 gap-3"):
                    info_tile("TV long name", player.long_name)
                    info_tile("TV short name", player.short_name)

                with ui.element("div").classes("w-full grid grid-cols-3 gap-3"):
                    info_tile("World rank (meilleur)", f"#{player.best_ranking}" if player.best_ranking else "",
                                  highlight=True)
                    info_tile(
                        "Age",
                        f"{player.age} ans" if player.age is not None else "",
                    )
                    info_tile("Date de naissance", format_date(player.birth_date))
                    info_tile("Sexe", GENDERS.get(player.gender, ""))
                    info_tile("Main", HANDS.get(player.hand, ""))
                    info_tile("Revers", SHORT_BACKHANDS.get(player.backhand, ""))
                    info_tile("Taille", f"{player.height_cm} cm" if player.height_cm else "")
                    info_tile("Poids", f"{player.weight_kg} kg" if player.weight_kg else "")
                    info_tile("Pro depuis", str(player.turned_pro) if player.turned_pro else "")

                if player.notes:
                    with ui.column().classes("w-full gap-1"):
                        ui.label("NOTES").classes("text-xs font-bold uppercase tracking-wide text-slate-500")
                        ui.label(player.notes).classes(
                            "text-sm text-slate-700 dark:text-slate-200 whitespace-pre-line"
                        )

                with ui.row(wrap=False).classes("w-full items-center justify-between gap-3 mt-auto"):
                    ui.label(
                        f"Engage dans {match_count} match(s)" if match_count else "Engage dans aucun match"
                    ).classes("text-sm text-slate-500")
                    ui.button("Modifier", icon="edit", on_click=lambda: dialog.submit("edit")).props("no-caps")

    return dialog


# ---------------------------------------------------------------------------
# Fenetre de creation / edition
# ---------------------------------------------------------------------------

#nettoie la copie de travail avant sauvegarde. Renvoie la liste des
#erreurs bloquantes (vide si tout est valide).
def _normalize(player: Player) -> list[str]:
    for name in ("first_name", "last_name", "tv_long_name", "tv_short_name", "notes"):
        setattr(player, name, (getattr(player, name) or "").strip())
    for name in ("best_ranking", "height_cm", "weight_kg", "turned_pro"):
        setattr(player, name, to_int(getattr(player, name)))

    errors = []
    if not player.last_name:
        errors.append("Le nom du joueur est obligatoire")
    return errors


#champ de nom TV avec interrupteur "Auto" : en automatique, le champ est
#grise et suit le prenom/nom (valeur `auto_value`) ; decoche, l'operateur
#le saisit a la main (en partant de la valeur automatique). Renvoie la
#fonction de mise a jour a appeler quand le prenom/nom change.
#`attr` : tv_long_name / tv_short_name, `auto_attr` : son indicateur auto.
def _tv_name_field(
    label: str, working: Player, attr: str, auto_attr: str, auto_value: Callable[[], str]
) -> Callable[[], None]:
    with ui.row(wrap=False).classes("items-center gap-2 w-full"):
        field = ui.input(label).props(FIELD_PROPS).classes("flex-1")
        switch = ui.switch("Auto", value=getattr(working, auto_attr))

    def sync() -> None:
        if switch.value:
            field.value = auto_value()
            field.disable()
        else:
            field.enable()

    def on_field_change(event) -> None:
        if not switch.value:
            setattr(working, attr, (event.value or "").strip())

    def on_switch_change(_) -> None:
        setattr(working, auto_attr, switch.value)
        if not switch.value:
            setattr(working, attr, (field.value or "").strip())
        sync()

    field.value = getattr(working, attr) if not switch.value else auto_value()
    field.on_value_change(on_field_change)
    switch.on_value_change(on_switch_change)
    sync()
    return sync


#fenetre de creation (player None) / edition. `defaults` : valeurs de
#depart d'un nouveau joueur (ex: sexe deduit de la categorie du match
#depuis lequel la fenetre est ouverte). A attendre (`await dialog`) :
#renvoie l'id du joueur enregistre, None si fermee sans enregistrer.
def build_player_dialog(player: Player | None, defaults: dict | None = None) -> ui.dialog:
    is_new = player is None
    working = dataclasses.replace(player) if player else Player(**(defaults or {}))

    title = "NOUVEAU JOUEUR" if is_new else f"MODIFIER {player.display_name}"
    dialog, body, footer = form_dialog(title, width="56rem")
    #rafraichissements a declencher quand la fiche change (nom, pays, date...)
    refreshers: list[Callable[[], None]] = []

    def refresh_all() -> None:
        for refresher in refreshers:
            refresher()

    state = {"saved": False}

    def on_save() -> None:
        errors = _normalize(working)
        #pas de doublon dans l'annuaire (meme nom, ou meme fiche Wikidata)
        duplicate = database.find_duplicate_player(working) if not errors else None
        if duplicate is not None:
            errors.append(
                f"Ce joueur existe deja dans l'annuaire : {duplicate.display_name}"
                + (f" ({duplicate.country})" if duplicate.country else "")
            )
        if errors:
            for error in errors:
                ui.notify(error, type="negative")
            return
        player_id = database.save_player(working)
        #photo rattachee apres l'enregistrement : l'id du joueur (nom du
        #fichier) n'existe pas avant pour un nouveau joueur
        photo = photo_field.commit(player_id)
        if photo is not None:
            working.photo = photo
            database.set_player_photo(player_id, photo)
        state["saved"] = True
        ui.notify(f"{working.display_name} {'cree' if is_new else 'mis a jour'}", type="positive")
        players_changed.emit()
        dialog.submit(player_id)

    #fenetre fermee sans enregistrer : la photo en attente est supprimee
    def on_dialog_close(event) -> None:
        if not event.value and not state["saved"]:
            photo_field.discard()

    dialog.on_value_change(on_dialog_close)

    # --- Recherche Wikidata ---------------------------------------------
    async def on_search() -> None:
        query = (search_input.value or "").strip()
        if len(query) < 2:
            ui.notify("Tapez au moins 2 lettres du nom", type="warning")
            return
        results_box.clear()
        with results_box:
            ui.spinner(size="md")
        try:
            results = await wikidata.search_players(query)
        except wikidata.WikidataError as error:
            results = None
            message = str(error)
        results_box.clear()
        with results_box:
            if results is None:
                ui.label(f"{message} - verifiez la connexion internet").classes("text-sm text-red-500")
            elif not results:
                ui.label("Aucun joueur de tennis trouve").classes("text-sm text-slate-500")
            for result in results or []:
                with ui.row(wrap=False).classes(
                    "w-full items-center justify-between gap-3 rounded-lg px-3 py-1 "
                    "hover:bg-slate-100 dark:hover:bg-slate-700/40"
                ):
                    with ui.column().classes("gap-0 min-w-0"):
                        ui.label(result["label"]).classes("text-sm font-bold truncate")
                        ui.label(result["description"]).classes("text-xs text-slate-500 truncate")
                    ui.button(
                        "Importer", icon="download",
                        on_click=lambda r=result: on_import(r),
                    ).props("flat dense no-caps")

    async def on_import(result: dict) -> None:
        try:
            fields = await wikidata.fetch_player(result["id"])
        except wikidata.WikidataError as error:
            ui.notify(str(error), type="negative")
            return
        #seuls les champs trouves sur Wikidata sont remplaces, le reste de
        #la saisie est conserve
        for name, value in fields.items():
            setattr(working, name, value)
        #`with body` : le handler s'execute dans le contexte du bouton
        #"Importer", que results_box.clear() supprime - sans contexte
        #explicite, ui.notify plantait ("parent element ... deleted")
        with body:
            refresh_all()
            ui.notify(
                f"{result['label']} importe ({len(fields) - 1} infos) - verifiez avant d'enregistrer",
                type="positive",
            )
            results_box.clear()

    with body:
        with section_card("RECHERCHE EN LIGNE (WIKIDATA)", "travel_explore"):
            with ui.row(wrap=False).classes("w-full items-center gap-2"):
                search_input = ui.input(
                    placeholder="Nom du joueur (ex: Monfils, Swiatek...)", value=working.display_name
                ).props(FIELD_PROPS + " clearable").classes("flex-1").on("keydown.enter", on_search)
                ui.button("Rechercher", icon="search", on_click=on_search).props("no-caps")
            results_box = ui.column().classes("w-full gap-1")
            ui.label(
                "Pre-remplit pays, date de naissance, taille, poids, main, revers, debut de carriere et "
                "meilleur classement en simple. Donnees communautaires : a verifier."
            ).classes("text-xs text-slate-500")

        with section_card("IDENTITE", "badge"):
            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-3 gap-2"):
                ui.input("Prenom").bind_value(working, "first_name").props(FIELD_PROPS).on_value_change(
                    lambda _: refresh_all()
                )
                ui.input("Nom *").bind_value(working, "last_name").props(FIELD_PROPS).on_value_change(
                    lambda _: refresh_all()
                )
                with ui.column().classes("gap-0"):
                    ui.label("Sexe").classes(FIELD_LABEL_CLASSES)
                    ui.toggle(GENDERS).bind_value(working, "gender").props("no-caps dense")

                with ui.row(wrap=False).classes("items-center gap-2 md:col-span-2"):
                    optional_select(COUNTRY_OPTIONS, "Pays", working, "country", with_input=True).classes(
                        "flex-1"
                    ).on_value_change(lambda _: refresh_all())
                    flag_box = ui.row().classes("w-8 justify-center")
                with ui.row(wrap=False).classes("items-center gap-2"):
                    date_input(working, "birth_date", "Date de naissance").classes("flex-1").on_value_change(
                        lambda _: refresh_all()
                    )
                    age_label = ui.label().classes("text-sm font-bold text-slate-500 w-14")

        with section_card("PHOTO", "photo_camera"):
            photo_field = ImageField(
                PHOTOS, working.photo, working.updated_at,
                upload_label="Choisir une photo PNG",
                accept=".png,image/png",
                hint=f"Format attendu : PNG de {PHOTO_SIZE[0]} x {PHOTO_SIZE[1]} px. "
                     "La photo est enregistree avec le joueur (bouton Enregistrer).",
                placeholder_icon="person",
            )

        with section_card("NOMS TV (HABILLAGE)", "tv"):
            refreshers.append(_tv_name_field(
                "TV LONG NAME", working, "tv_long_name", "tv_long_auto", lambda: working.auto_long_name
            ))
            refreshers.append(_tv_name_field(
                "TV SHORT NAME", working, "tv_short_name", "tv_short_auto", lambda: working.auto_short_name
            ))
            ui.label("Auto : TV LONG NAME = Prenom NOM, TV SHORT NAME = P. NOM. Decochez Auto pour saisir a la main.").classes(
                "text-xs text-slate-500"
            )

        with section_card("PROFIL", "sports_tennis"):
            with ui.element("div").classes("w-full grid grid-cols-1 md:grid-cols-3 gap-2"):
                ui.number("Meilleur classement", min=1, precision=0).bind_value(
                    working, "best_ranking"
                ).props(FIELD_PROPS)
                with ui.column().classes("gap-0"):
                    ui.label("Main").classes(FIELD_LABEL_CLASSES)
                    ui.toggle({"": "?", **HANDS}).bind_value(working, "hand").props("no-caps dense")
                with ui.column().classes("gap-0"):
                    ui.label("Revers").classes(FIELD_LABEL_CLASSES)
                    ui.toggle({"": "?", **SHORT_BACKHANDS}).bind_value(working, "backhand").props("no-caps dense")

                ui.number("Taille (cm)", min=100, max=250, precision=0).bind_value(
                    working, "height_cm"
                ).props(FIELD_PROPS)
                ui.number("Poids (kg)", min=30, max=200, precision=0).bind_value(
                    working, "weight_kg"
                ).props(FIELD_PROPS)
                ui.number("Pro depuis (annee)", min=1950, max=2100, precision=0).bind_value(
                    working, "turned_pro"
                ).props(FIELD_PROPS)

                ui.textarea("Notes (anecdotes, palmares...)").bind_value(working, "notes").props(
                    FIELD_PROPS + " autogrow"
                ).classes("md:col-span-3")

    def refresh_flag() -> None:
        flag_box.clear()
        with flag_box:
            flag(working.country, "h-6 w-8")

    def refresh_age() -> None:
        age_label.text = f"{working.age} ans" if working.age is not None else ""

    refreshers.extend([refresh_flag, refresh_age])
    refresh_all()

    with footer:
        ui.button("Annuler", on_click=lambda: dialog.submit(None)).props("flat")
        ui.button(
            "Creer le joueur" if is_new else "Enregistrer", icon="save", on_click=on_save
        ).classes("px-6")

    return dialog
