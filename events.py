# Evenements partages entre toutes les pages et tous les postes connectes
# (nicegui.Event) : une modification faite a un endroit met a jour
# immediatement les autres vues ouvertes, sans attendre de rechargement.

from typing import Any, Callable

from nicegui import Event
from nicegui.element import Element

#un tournoi a ete cree, modifie, supprime, ou le tournoi actif a change :
#selecteur du header, liste des tournois et accueil se rafraichissent
tournaments_changed = Event()

#match modifie - score ou etat d'arbitrage (debut, point, annulation,
#resultat, remise a zero) ou fiche du match (creation, modification,
#suppression depuis la gestion des donnees) : argument = id du match. Listes
#des matchs, fiches ouvertes et ecrans d'arbitrage se rafraichissent.
match_scored = Event[int]()

#joueur cree, modifie ou supprime (noms, photo...) : API WebSocket
players_changed = Event()


#abonnement lie a un element de la page : l'appel est ignore si l'element
#(donc sa page) a deja ete supprime. NiceGUI desabonne normalement a la
#suppression de la page, mais un evenement emis juste avant peut encore
#arriver - sans cette garde : "The client this element belongs to has been
#deleted" dans la console.
#`expect_args` : transmettre au callback les arguments de l'evenement (ex: id
#du match). A preciser : NiceGUI ne peut pas le deduire de `guarded(*args)`.
def subscribe_for(
    event: Event, element: Element, callback: Callable[..., Any], expect_args: bool = False
) -> None:
    def guarded(*args: Any) -> None:
        if _is_alive(element):
            callback(*args)

    event.subscribe(guarded, expect_args=expect_args)


#l'element et sa page existent encore (element.client leve une erreur si
#la page a deja ete supprimee, meme quand l'element n'est pas marque)
def _is_alive(element: Element) -> bool:
    if element.is_deleted:
        return False
    try:
        return not element.client.is_deleted
    except RuntimeError:
        return False
