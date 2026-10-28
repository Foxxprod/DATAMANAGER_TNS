# Recherche de joueurs sur Wikidata (API publique, gratuite, sans cle) pour
# pre-remplir la fiche joueur. Aucune ecriture en base ici : la fenetre
# joueur (players.py) applique le resultat sur sa copie de travail, que
# l'operateur verifie avant d'enregistrer.
#
# Proprietes Wikidata utilisees :
#   P21 sexe, P569 date de naissance, P1532 pays sportif (sinon P27
#   nationalite) -> code ISO P297 -> code CIO (countries.py), P2048 taille,
#   P2067 masse, P741/P552 main et revers, P2031 debut de carriere,
#   P1352 classement (meilleur classement en simple : qualificatif P641 =
#   tennis simple), P735/P734 prenom/nom.
#
# Les donnees Wikidata sont communautaires : parfois incompletes ou en
# retard (classement notamment), d'ou la verification par l'operateur.

import httpx

from countries import code_from_iso

API_URL = "https://www.wikidata.org/w/api.php"
#Wikimedia exige un User-Agent avec un moyen de contact (URL), sinon 403
HEADERS = {"User-Agent": "TennisDataManager/0.1 (https://github.com/Foxxprod)"}
TIMEOUT = 10.0

GENDER_ITEMS = {"Q6581097": "M", "Q6581072": "F"}
HAND_ITEMS = {"Q3039938": "R", "Q789447": "L"}
BACKHAND_ITEMS = {"Q14420068": "2", "Q14420039": "1"}
SINGLES_ITEM = "Q18123880"
TENNIS_PLAYER_ITEM = "Q10833314"
CM_UNIT = "Q174728"
METRE_UNIT = "Q11573"


class WikidataError(Exception):
    pass


async def _get(client: httpx.AsyncClient, **params) -> dict:
    try:
        response = await client.get(API_URL, params={**params, "format": "json"})
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise WikidataError(f"Wikidata injoignable ({error.__class__.__name__})") from error


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=TIMEOUT)


#recherche par nom, en 2 temps :
#  1. recherche plein texte filtree sur la profession "joueur de tennis"
#     (P106=Q10833314) : trouve "Sinner" malgre les nombreux homonymes,
#     mais pas les debuts de mot ("Monf") et parfois refusee par Wikidata
#     ("too busy") - erreur alors ignoree
#  2. recherche par libelle (gere les debuts de mot), filtree sur la
#     description ("joueur/joueuse de tennis...", "tennis player"), en
#     complement
#Renvoie [{"id", "label", "description"}], sans doublon.
async def search_players(query: str) -> list[dict]:
    results: dict[str, dict] = {}
    async with _client() as client:
        try:
            data = await _get(
                client, action="query", list="search", srlimit=15,
                srsearch=f"{query} haswbstatement:P106={TENNIS_PLAYER_ITEM}",
            )
            ids = [item["title"] for item in data.get("query", {}).get("search", [])]
            if ids:
                details = await _get(
                    client, action="wbgetentities", ids="|".join(ids), props="labels|descriptions",
                    languages="fr|en",
                )
                for item_id in ids:
                    entity = details.get("entities", {}).get(item_id, {})
                    results[item_id] = {
                        "id": item_id,
                        "label": _localized(entity.get("labels", {})),
                        "description": _localized(entity.get("descriptions", {})),
                    }
        except WikidataError:
            pass

        data = await _get(
            client, action="wbsearchentities", search=query, language="fr", uselang="fr",
            type="item", limit=30,
        )
    for item in data.get("search", []):
        description = item.get("description", "")
        lowered = description.lower()
        is_player = "tennis" in lowered and any(word in lowered for word in ("joueu", "player"))
        if is_player and item["id"] not in results:
            results[item["id"]] = {"id": item["id"], "label": item.get("label", ""), "description": description}
    return list(results.values())


def _localized(values: dict) -> str:
    return (values.get("fr") or values.get("en") or {}).get("value", "")


def _values(claims: dict, prop: str) -> list:
    #statements "preferred" en premier, "deprecated" ignores
    statements = sorted(
        (s for s in claims.get(prop, []) if s.get("rank") != "deprecated"),
        key=lambda s: s.get("rank") != "preferred",
    )
    return [s for s in statements if s["mainsnak"].get("datavalue")]


def _item_ids(claims: dict, prop: str) -> list[str]:
    return [s["mainsnak"]["datavalue"]["value"]["id"] for s in _values(claims, prop)]


def _amount(statement: dict) -> float:
    return float(statement["mainsnak"]["datavalue"]["value"]["amount"])


def _best_singles_ranking(claims: dict) -> int | None:
    singles, unqualified = [], []
    for statement in _values(claims, "P1352"):
        sports = [q["datavalue"]["value"]["id"] for q in statement.get("qualifiers", {}).get("P641", [])
                  if q.get("datavalue")]
        if SINGLES_ITEM in sports:
            singles.append(_amount(statement))
        elif not sports:
            unqualified.append(_amount(statement))
    candidates = singles or unqualified
    return int(min(candidates)) if candidates else None


#fiche complete d'un joueur Wikidata -> dict des champs de models.Player
#trouves (les champs absents sur Wikidata ne figurent pas dans le dict)
async def fetch_player(qid: str) -> dict:
    async with _client() as client:
        data = await _get(client, action="wbgetentities", ids=qid, props="labels|claims", languages="fr|en")
        entity = data.get("entities", {}).get(qid)
        if not entity or "claims" not in entity:
            raise WikidataError("Joueur introuvable sur Wikidata")
        claims = entity["claims"]
        fields: dict = {"wikidata_id": qid}

        #prenom/nom : libelles des items P735/P734, sinon decoupe du libelle
        given_ids = sorted(
            _values(claims, "P735"),
            key=lambda s: int((s.get("qualifiers", {}).get("P1545") or [{"datavalue": {"value": "0"}}])[0]
                              ["datavalue"]["value"] or 0),
        )
        given_ids = [s["mainsnak"]["datavalue"]["value"]["id"] for s in given_ids]
        family_ids = _item_ids(claims, "P734")[:1]
        label_ids = given_ids + family_ids
        labels: dict[str, str] = {}
        if label_ids:
            label_data = await _get(
                client, action="wbgetentities", ids="|".join(label_ids), props="labels", languages="fr|en"
            )
            for item_id, item in label_data.get("entities", {}).items():
                item_labels = item.get("labels", {})
                label = item_labels.get("fr") or item_labels.get("en")
                if label:
                    labels[item_id] = label["value"]

        full_label = _localized(entity.get("labels", {}))
        #premier prenom seulement ("Gael", pas "Gael Sebastien") : c'est
        #celui utilise a l'antenne
        first = next((labels[i] for i in given_ids if i in labels), "")
        last = labels.get(family_ids[0], "") if family_ids else ""
        if not (first and last) and " " in full_label:
            first, last = full_label.split(" ", 1)
        if first:
            fields["first_name"] = first
        if last:
            fields["last_name"] = last

        gender = next((GENDER_ITEMS[i] for i in _item_ids(claims, "P21") if i in GENDER_ITEMS), None)
        if gender:
            fields["gender"] = gender

        birth = _values(claims, "P569")
        if birth:
            value = birth[0]["mainsnak"]["datavalue"]["value"]
            if value.get("precision", 0) >= 11:
                fields["birth_date"] = value["time"][1:11]

        for country_item in _item_ids(claims, "P1532") + _item_ids(claims, "P27"):
            iso_data = await _get(client, action="wbgetclaims", entity=country_item, property="P297")
            iso_values = _values(iso_data.get("claims", {}), "P297")
            code = code_from_iso(iso_values[0]["mainsnak"]["datavalue"]["value"]) if iso_values else ""
            if code:
                fields["country"] = code
                break

    for statement in _values(claims, "P2048"):
        unit = statement["mainsnak"]["datavalue"]["value"].get("unit", "")
        if unit.endswith(CM_UNIT):
            fields["height_cm"] = round(_amount(statement))
        elif unit.endswith(METRE_UNIT):
            fields["height_cm"] = round(_amount(statement) * 100)
        if "height_cm" in fields:
            break

    weight = _values(claims, "P2067")
    if weight:
        fields["weight_kg"] = round(_amount(weight[0]))

    style_items = _item_ids(claims, "P741") + _item_ids(claims, "P552")
    hand = next((HAND_ITEMS[i] for i in style_items if i in HAND_ITEMS), None)
    if hand:
        fields["hand"] = hand
    backhand = next((BACKHAND_ITEMS[i] for i in style_items if i in BACKHAND_ITEMS), None)
    if backhand:
        fields["backhand"] = backhand

    career_start = _values(claims, "P2031")
    if career_start:
        fields["turned_pro"] = int(career_start[0]["mainsnak"]["datavalue"]["value"]["time"][1:5])

    best = _best_singles_ranking(claims)
    if best:
        fields["best_ranking"] = best

    return fields
