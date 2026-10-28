# Briques communes aux fenetres de saisie (match, joueur, tournoi) :
# squelette de fenetre, champs date/heure avec selecteur, select facultatif,
# champ image (photo, logo), conversion des nombres saisis.

from typing import Callable

from nicegui import ui

from layout import ROUND_BUTTON_CLASSES
from media import MediaError, MediaStore
from models import format_date, parse_date

FIELD_PROPS = "outlined dense"


#squelette d'une fenetre de saisie : bandeau titre sombre + croix, corps
#qui defile, pied (boutons) toujours visible. Renvoie (dialog, body,
#footer) a remplir par l'appelant. La fenetre est a attendre (`await
#dialog`) ; la croix la ferme avec le resultat None.
#
#persistent : un clic a cote de la fenetre ne doit pas faire perdre la
#saisie en cours (fermeture uniquement via Annuler / la croix). La
#largeur inline remplace le max-width de 560px impose par Quasar.
def form_dialog(title: str, width: str = "72rem") -> tuple[ui.dialog, ui.column, ui.row]:
    dialog = ui.dialog().props("persistent")
    with dialog, ui.card().classes(
        "p-0 gap-0 rounded-2xl overflow-hidden bg-slate-50 dark:bg-slate-900"
    ).style(f"width: {width}; max-width: 95vw; max-height: 92vh;"):
        with ui.row(wrap=False).classes(
            "w-full items-center justify-between bg-slate-900 text-white px-4 py-3"
        ):
            ui.label(title).classes("text-base font-bold tracking-wide")
            ui.button(icon="close", color=None, on_click=lambda: dialog.submit(None)).classes(
                ROUND_BUTTON_CLASSES
            ).props("round dense").tooltip("Fermer sans enregistrer")

        body = ui.column().classes("w-full flex-1 min-h-0 overflow-auto p-4 gap-3")

        footer = ui.row().classes(
            "w-full justify-end gap-2 px-4 py-3 border-t border-slate-200 dark:border-slate-700"
        )

    return dialog, body, footer


#champ date saisi/affiche en JJ/MM/AAAA, attribut `attr` de `obj` en ISO
#(voir models.format_date/parse_date). Liaison en 2 temps plutot qu'un
#bind_value avec conversion : un texte incomplet en cours de frappe
#("12/0") ne doit ni effacer la date enregistree ni etre reecrit par elle.
#  - objet -> champ : bind_value_from (date modifiee ailleurs : import
#    Wikidata, date du tournoi reprise dans le match...)
#  - champ -> objet : uniquement une date complete valide, ou champ vide
def date_input(obj, attr: str, label: str) -> ui.input:
    def on_change(event) -> None:
        text = (event.value or "").strip()
        if not text:
            setattr(obj, attr, "")
        elif (iso := parse_date(text)) is not None:
            setattr(obj, attr, iso)

    with ui.input(label, placeholder="JJ/MM/AAAA", on_change=on_change).bind_value_from(
        obj, attr, backward=format_date
    ).props(FIELD_PROPS + " mask=##/##/####") as field:
        with ui.menu().props("no-parent-event") as menu:
            with ui.date(mask="DD/MM/YYYY").bind_value(field):
                with ui.row().classes("justify-end"):
                    ui.button("Fermer", on_click=menu.close).props("flat")
        with field.add_slot("append"):
            ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
    return field


def time_input(obj, attr: str, label: str) -> ui.input:
    with ui.input(label).bind_value(obj, attr).props(FIELD_PROPS) as field:
        with ui.menu().props("no-parent-event") as menu:
            with ui.time(mask="HH:mm").props("format24h").bind_value(field):
                with ui.row().classes("justify-end"):
                    ui.button("Fermer", on_click=menu.close).props("flat")
        with field.add_slot("append"):
            ui.icon("schedule").on("click", menu.open).classes("cursor-pointer")
    return field


#select facultatif lie a un attribut texte : "" en base <-> None dans le
#select (ui.select refuse une valeur absente de ses options). Une valeur
#deja saisie hors liste (tour personnalise) est ajoutee aux options.
def optional_select(
    options: list[str] | dict[str, str],
    label: str,
    obj,
    attr: str,
    allow_new: bool = False,
    with_input: bool = False,
) -> ui.select:
    current = getattr(obj, attr)
    if isinstance(options, dict):
        options = dict(options)
        if current and current not in options:
            options[current] = current
    else:
        options = options + [current] if current and current not in options else list(options)
    return ui.select(
        options,
        label=label,
        clearable=True,
        with_input=with_input,
        new_value_mode="add-unique" if allow_new else None,
    ).bind_value(
        obj, attr, forward=lambda value: value or "", backward=lambda value: value or None
    ).props(FIELD_PROPS)


#premier choix de la liste deroulante d'un select : bouton "Ajouter..."
#qui reste visible en haut de la liste meme quand on la fait defiler
#(sticky dans le slot before-options de QSelect). Le slot no-option est
#indispensable : sans lui, Quasar n'ouvre pas du tout la liste quand
#aucune option ne correspond a la saisie, et le bouton serait inaccessible
#precisement quand on en a besoin (element absent de la liste).
def add_option_button(select: ui.select, label: str, on_click: Callable) -> None:
    def on_button_click():
        select.run_method("hidePopup")
        return on_click()

    with select.add_slot("before-options"):
        with ui.element("div").classes(
            "sticky top-0 z-10 bg-white dark:bg-[var(--q-dark)] "
            "border-b border-slate-200 dark:border-slate-700"
        ):
            ui.button(label, icon="add_circle", color=None, on_click=on_button_click).props(
                "flat no-caps align=left"
            ).classes("w-full font-bold text-green-600")
    with select.add_slot("no-option"):
        ui.label("Aucun resultat").classes("px-4 py-2 text-sm text-slate-500")


def to_int(value) -> int | None:
    return int(value) if value not in (None, "") else None


#champ image d'une fenetre de saisie (photo d'un joueur, logo d'un tournoi) :
#apercu, envoi de fichier, bouton Retirer. L'image choisie reste en attente
#(voir media.py) jusqu'a commit(), appele apres l'enregistrement de
#l'element (son id donne le nom du fichier) ; discard() la supprime si la
#fenetre est fermee sans enregistrer.
class ImageField:
    def __init__(
        self,
        store: MediaStore,
        current: str,
        version: str,
        *,
        upload_label: str,
        accept: str,
        hint: str,
        placeholder_icon: str,
        box_classes: str = "w-40 h-40",
        fit: str = "cover",
    ) -> None:
        self.store = store
        self.current = current
        self.version = version
        self.fit = fit
        self.placeholder_icon = placeholder_icon
        self.pending: str | None = None
        self.remove = False

        with ui.row(wrap=False).classes("w-full items-start gap-4") as self.container:
            self.box = ui.element("div").classes(
                f"{box_classes} shrink-0 rounded-xl overflow-hidden flex items-center justify-center "
                "border border-slate-300 dark:border-slate-600 bg-slate-100 dark:bg-slate-900"
            )
            with ui.column().classes("flex-1 gap-2"):
                self.upload = ui.upload(
                    label=upload_label,
                    auto_upload=True,
                    max_file_size=store.max_upload_bytes,
                    on_upload=self._on_upload,
                    on_rejected=lambda: ui.notify(
                        f"Fichier refuse ({store.max_upload_bytes // (1024 * 1024)} Mo maximum)", type="negative"
                    ),
                ).props(f'accept="{accept}" flat bordered').classes("w-full")
                ui.label(hint).classes("text-xs text-slate-500")
                self.remove_button = ui.button(
                    "Retirer", icon="delete", color="red", on_click=self._on_remove
                ).props("flat dense no-caps")
        self._refresh()

    def _refresh(self) -> None:
        self.box.clear()
        with self.box:
            if self.pending:
                url = self.store.pending_url(self.pending)
            elif self.current and not self.remove:
                url = self.store.file_url(self.current, self.version)
            else:
                url = None
            if url:
                ui.image(url).classes("w-full h-full").props(f"fit={self.fit}")
            else:
                ui.icon(self.placeholder_icon).classes("text-6xl text-slate-400")
        self.remove_button.set_visibility(url is not None)

    async def _on_upload(self, event) -> None:
        data = await event.file.read()
        #contexte explicite : le handler s'execute dans celui de l'upload,
        #que reset() reinitialise
        with self.container:
            try:
                name = self.store.save_pending(data)
            except MediaError as error:
                ui.notify(str(error), type="negative")
            else:
                self.discard()
                self.pending = name
                self.remove = False
                self._refresh()
                ui.notify("Image prete : elle sera enregistree avec la fiche", type="positive")
            self.upload.reset()

    def _on_remove(self) -> None:
        self.discard()
        self.remove = bool(self.current)
        self._refresh()

    #supprime l'image en attente (fenetre fermee sans enregistrer)
    def discard(self) -> None:
        if self.pending:
            self.store.delete_pending(self.pending)
            self.pending = None

    #apres enregistrement de l'element `owner_id` : nouveau nom de fichier a
    #enregistrer en base ("" = image retiree), ou None si rien n'a change
    def commit(self, owner_id: int) -> str | None:
        if self.pending:
            name = self.store.commit_pending(self.pending, owner_id)
            self.pending = None
            return name
        if self.remove and self.current:
            self.store.delete(self.current)
            return ""
        return None
