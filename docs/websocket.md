# API WebSocket — Tennis Data Manager

Flux temps réel de tous les matchs (tournoi, joueurs, score), pour les
systèmes graphiques (habillage TV, CasparCG…).

```
ws://<adresse-du-poste>:8080/ws
```

Exemple complet d'un instantané : [websocket_exemple.json](websocket_exemple.json)
(un match terminé avec un tie-break, un match en cours sur balle de break, un
double programmé).

## Principe

1. À la connexion, le serveur envoie un **instantané** de tous les matchs.
2. Ensuite, à chaque changement (point, début, fin, abandon, modification
   d'un match…), il envoie **le match concerné en entier**.

Chaque message contient l'état **complet** : le client remplace simplement
ce qu'il avait pour ce match, sans calcul ni fusion. Un message manqué n'a
pas de conséquence : le suivant contient de nouveau tout.

Le score est **déjà calculé** et rangé par équipe (service, jeux de chaque
set, petit chiffre du tie-break, points 15/30/40/AD, balles de break/set/
match) : aucune règle de tennis à coder côté graphiques.

## Messages du serveur

| `type` | Contenu | Quand |
|---|---|---|
| `snapshot` | `matches` : liste de tous les matchs (ordre chronologique, sans date en dernier) | à la connexion, sur demande `snapshot` / `subscribe`, et quand un joueur ou un tournoi est modifié |
| `match` | `match` : un match, état complet | à chaque changement de ce match (dont le passage automatique « À VENIR ») |
| `match_deleted` | `id` : identifiant du match supprimé | suppression dans la gestion des données |
| `error` | `message` | message client invalide |

## Messages du client (facultatifs)

```json
{"type": "snapshot"}                    // renvoyer l'instantané complet
{"type": "subscribe", "match_id": 12}   // ne recevoir que le match 12
{"type": "subscribe", "match_id": null} // recevoir de nouveau tous les matchs
```

Un template dédié à un seul match (par ex. le score du court central) peut
s'abonner à ce match : il ne reçoit alors plus rien sur les autres.

## Objet `match`

Arborescence simple à deux niveaux : le **match** (informations générales et
état du jeu), puis ses deux **équipes** `teams[0]` et `teams[1]`, dont chaque
ligne contient tout ce qui s'affiche pour un joueur / une équipe dans un
graphique de score. Les valeurs sont prêtes à afficher : aucun calcul de
tennis à faire côté graphique.

```
match
├── id, status, status_label, round, court, scheduled_date, scheduled_time…
├── set_count, active_set, in_tiebreak, super_tiebreak, deciding_point, changeover…
├── tournament { name, logo_url, flag_url… }
├── format { best_of, no_ad, final_set_rule… }
└── teams [2]
    ├── tv_short_name, tricodes, flag_urls, serving, side
    ├── games [6, 2, null], tiebreak_small [null, null, null], points "30"
    ├── break_point, set_point, match_point, is_winner, retired
    ├── stats { points_won, aces, double_faults, break_points_won… }
    └── players [1 ou 2] { tv_short_name, country, flag_url, photo_url, serving… }
```

### Le match

| Champ | Description |
|---|---|
| `id` | identifiant du match |
| `status` | `scheduled` (programmé), `upcoming` (à venir : début dans moins de 10 min ou passé), `live` (en cours), `finished` (terminé) |
| `status_label` | libellé du statut (« EN COURS »…) |
| `category`, `category_label` | `MS`/`WS`/`MD`/`WD`/`XD`, « Simple Messieurs »… |
| `is_double` | `true` pour un double |
| `round`, `court` | tour (« Finale »…), court (« Central »…) |
| `scheduled_date`, `scheduled_time` | `AAAA-MM-JJ`, `HH:MM` |
| `started_at`, `finished_at` | horodatages ISO du début / de la fin |
| `duration_seconds` | durée du match en secondes (depuis le début, jusqu'à la fin ou maintenant) |
| `set_count` | nombre de sets possibles (3 ou 5) : nombre de colonnes du graphique |
| `active_set` | numéro du set en cours (1, 2, 3…) pour déplier le graphique au fur et à mesure — `null` avant le début et après la fin |
| `in_tiebreak` | un jeu décisif (tie-break) est en cours |
| `super_tiebreak` | le jeu décisif en cours est un super tie-break (remplace le set décisif) |
| `tiebreak_target` | en combien de points se joue le tie-break en cours (7, 10…) |
| `deciding_point` | point décisif en cours (40-40 avec la règle no-ad) |
| `changeover` | changement de côté à faire maintenant (entre deux jeux) : utile pour déclencher un graphique pendant la pause |
| `last_point_winner` | équipe (0/1) qui a gagné le dernier point |
| `total_points` | nombre de points joués |
| `winner` | équipe gagnante (0/1) ou `null` |
| `end_reason` | `"RET"` (abandon) ou `null` |
| `tournament` | voir ci-dessous |
| `format` | `best_of` (3 ou 5), `games_per_set`, `tiebreak_enabled`, `tiebreak_points`, `final_set_rule` (`tiebreak`, `tiebreak_10`, `super_tiebreak`, `advantage`), `no_ad` (point décisif), `summary` |
| `teams` | les 2 équipes (voir ci-dessous) |
| `updated_at` | horodatage ISO de la dernière modification |

### Une équipe (`teams[0]`, `teams[1]`)

En simple, une équipe = un joueur.

| Champ | Description |
|---|---|
| `index` | 0 ou 1 |
| `tv_short_name`, `tv_long_name` | « G. MONFILS » / « Gael MONFILS » (en double : « N. MAHUT / P. HERBERT ») |
| `tricodes` | code(s) pays des joueurs : `["FRA"]` (double : `["ESP", "ARG"]`) |
| `flag_urls` | URL des drapeaux (SVG), dans le même ordre |
| `serving` | `true` si l'équipe est au service : afficher le logo de service |
| `serving_player` | en double, joueur (0/1) de l'équipe qui sert — `null` si l'équipe ne sert pas |
| `side` | côté du court où se trouve l'équipe, **vu depuis la chaise d'arbitre** : `"left"` ou `"right"` (`null` avant le début du match). Choisi par l'arbitre au début du match, puis mis à jour automatiquement à chaque changement de côté (jeux impairs, fin de set au total impair, tous les 6 points en tie-break) et à chaque correction manuelle. C'est une référence fixe du terrain : utile pour placer un graphique au sol (réalité augmentée) du côté du bon joueur |
| `sets_won` | nombre de sets gagnés |
| `games` | jeux de chaque set, une case par set : `[6, 2, null]` = 6 au 1er set, 2 au 2e (en cours), 3e pas joué. Pour un super tie-break terminé, la case contient ses points (ex. 10) |
| `tiebreak_small` | petit chiffre à afficher dans chaque set : points du **perdant** du tie-break (convention TV), sinon `null`. Ex. `[5, null, null]` = set 1 perdu 6-7, 5 points au tie-break |
| `tiebreak_points` | points des deux équipes au tie-break de chaque set (pas seulement le perdant), sinon `null` |
| `points` | points du jeu en cours, prêts à afficher : `"0"`, `"15"`, `"30"`, `"40"`, `"AD"` ; en tie-break et super tie-break, le nombre de points — `null` si le match n'est pas en cours |
| `points_raw` | nombre de points bruts du jeu en cours |
| `break_point` | si l'équipe gagne le prochain point, elle **fait le break** (balle de break) |
| `set_point` | si l'équipe gagne le prochain point, elle **gagne le set** (balle de set) |
| `match_point` | si l'équipe gagne le prochain point, elle **gagne le match** (balle de match) |
| `is_winner` | l'équipe a gagné le match |
| `retired` | l'équipe a abandonné (afficher « RET. ») |
| `stats` | statistiques de l'équipe, pour un graphique « face à face » (voir ci-dessous) |
| `players` | joueurs de l'équipe (voir ci-dessous) |

`break_point` et `set_point` peuvent être vrais en même temps (balle de set
sur le service adverse). `set_point` est faux quand c'est une balle de match
(on affiche la plus importante).

### Statistiques (`teams[i].stats`)

Mêmes champs pour les deux équipes : il suffit d'afficher `teams[0].stats`
contre `teams[1].stats`. Recalculées à chaque point.

| Champ | Description |
|---|---|
| `points_won` | points gagnés |
| `aces` | aces |
| `double_faults` | doubles fautes |
| `winners` | coups gagnants |
| `unforced_errors` | fautes directes |
| `service_points_won` / `service_points_played` / `service_points_won_pct` | points gagnés au service, sur points joués au service, et en % |
| `return_points_won` / `return_points_played` / `return_points_won_pct` | points gagnés en retour, idem |
| `break_points_won` / `break_points_played` / `break_points_won_pct` | balles de break **converties** sur balles de break obtenues (ex. 2/5, 40 %) |
| `break_points_saved` / `break_points_faced` / `break_points_saved_pct` | balles de break **sauvées** sur balles de break concédées au service |
| `service_games_won` / `service_games_played` / `service_games_won_pct` | jeux de service gagnés (hors tie-breaks) |
| `max_points_in_row` | plus longue série de points gagnés d'affilée |

Les pourcentages valent `null` tant qu'il n'y a rien à diviser (ex. aucune
balle de break). Aces, doubles fautes, coups gagnants et fautes directes
dépendent de la **nature du point**, saisie (facultativement) par l'arbitre
après chaque point : ils restent à 0 si elle n'est pas renseignée. Tous les
autres chiffres sont calculés automatiquement à partir des points joués.

### `tournament`

`id`, `name`, `level`, `surface`, `venue`, `city`, `country` (code CIO),
`country_name`, `flag_url`, `logo_url` (PNG, 512 px max), `start_date`,
`end_date`, `courts`, `is_current` (tournoi actif).

### Joueur (`teams[i].players[j]`)

`id`, `first_name`, `last_name`, `tv_long_name` (« Gael MONFILS »),
`tv_short_name` (« G. MONFILS »), `country` (tricode : FRA, ESP…),
`country_name`, `flag_url` (SVG), `photo_url` (PNG 3000×3000 ou `null`),
`serving` (ce joueur sert le prochain point), `best_ranking`, `gender`,
`birth_date`, `age`, `hand` (`R`/`L`), `backhand` (`1`/`2`), `height_cm`,
`weight_kg`, `turned_pro`, et les libellés `gender_label`, `hand_label`,
`backhand_label`.

Les URL sont absolues, avec l'adresse utilisée par le client pour se
connecter : elles fonctionnent directement dans un template HTML.

## Exemple minimal (JavaScript, template HTML)

```js
const matches = new Map();
const ws = new WebSocket("ws://192.168.1.16:8080/ws");

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.type === "snapshot") {
    matches.clear();
    message.matches.forEach((m) => matches.set(m.id, m));
  } else if (message.type === "match") {
    matches.set(message.match.id, message.match);
  } else if (message.type === "match_deleted") {
    matches.delete(message.id);
  }
  render(matches);   // a ecrire : met a jour le graphique
};

// reconnexion automatique (redemarrage du serveur, coupure reseau)
ws.onclose = () => setTimeout(() => location.reload(), 2000);
```
