# Tennis Data Manager

Logiciel de gestion des données de matchs de tennis pour l'habillage TV en
direct. Il centralise les tournois, les joueurs et les matchs. Les arbitres
saisissent les points en direct depuis une tablette. Le score complet est
diffusé en temps réel par WebSocket aux systèmes graphiques : CasparCG pour
la 2D, Unreal Engine pour la réalité augmentée.

Le logiciel s'utilise entièrement depuis un navigateur web, sur le PC
serveur ou sur n'importe quel poste ou tablette du réseau local. Plusieurs
matchs peuvent être arbitrés en parallèle.

> Projet Foxx Production · Pôle supérieur audiovisuel de Villefontaine

---

## Sommaire

- [Fonctionnalités](#fonctionnalités)
- [Architecture](#architecture)
- [Installation](#installation)
- [Lancement](#lancement)
- [Utilisation](#utilisation)
- [Diffusion des données (WebSocket)](#diffusion-des-données-websocket)
- [Intégration graphique : CasparCG et Unreal Engine](#intégration-graphique--casparcg-et-unreal-engine)
- [Données et fichiers](#données-et-fichiers)
- [Structure du code](#structure-du-code)
- [Développement](#développement)
- [Crédits](#crédits)

---

## Fonctionnalités

### Gestion des données
- **Tournois** : nom, niveau, surface, lieu, dates, liste des courts, logo
  (redimensionné automatiquement). Le **tournoi actif** se choisit depuis le
  header ou la liste des tournois.
- **Joueurs** :
  - annuaire avec **import depuis Wikidata** (identité, pays, classement,
    main…) ;
  - photo PNG 3000×3000 ;
  - noms TV long et court, calculés automatiquement ou saisis à la main ;
  - détection des doublons.
- **Matchs** :
  - simple ou double, tour, court, date et heure ;
  - format complet : nombre de sets, jeux par set, tie-break, règle du set
    décisif (tie-break, tie-break en 10, avantage, super tie-break), point
    décisif (no-ad).
- **Listes groupées par jour**, filtres par statut, fiches en pop-up (fiche
  joueur, fiche match avec score et statistiques en direct).
- **Statuts automatiques** : PROGRAMMÉ, À VENIR, EN COURS, TERMINÉ.

### Arbitrage (pensé pour un opérateur novice, sur tablette)
- Choix du match à arbitrer, groupé par jour et filtrable (Tous / À arbitrer
  / Terminés).
- Avant le match : **premier service** (et premier serveur de chaque équipe
  en double) et **côté de départ** (joueur à gauche, vu depuis la chaise
  d'arbitre).
- Deux gros boutons **POINT**, placés comme les joueurs sur le court. Ils
  s'échangent automatiquement à chaque changement de côté.
- Score calculé automatiquement selon les règles du tennis : jeux, sets,
  tie-breaks, alternance du service, changements de côté.
- Indications en direct : balle de break, de set et de match, tie-break,
  point décisif, changement de côté.
- **Nature du point** (facultative) : ace, double faute, coup gagnant,
  faute directe, pour les statistiques.
- Corrections : annuler le dernier point (avec confirmation), changer le
  serveur, inverser les côtés, abandon, remise à zéro.
- Raccourcis clavier : flèche gauche ou droite = point, retour arrière =
  annuler.
- Un poste par match : si le match est déjà ouvert ailleurs, l'opérateur
  peut **prendre la main**.

### Statistiques
Calculées pour chaque joueur ou équipe à partir des points saisis :
- points gagnés, aces, doubles fautes, coups gagnants, fautes directes ;
- points gagnés au service et en retour ;
- balles de break (converties et sauvées) ;
- jeux de service gagnés ;
- plus longue série de points.

### Temps réel
Toute modification (point, début ou fin de match, tournoi actif, joueur…)
est répercutée **immédiatement** sur toutes les pages ouvertes, sur tous les
postes, et envoyée aux graphiques par WebSocket.

### Administration
- Adresses du serveur, avec bouton Copier : adresse IP, interface web,
  WebSocket des graphiques.
- État du serveur : temps en ligne, clients connectés, matchs en cours,
  taille de la base.
- Constantes du PC serveur : processeur, mémoire, disque, température.

### Interface
- Thème clair ou sombre, titre du logiciel personnalisable (Paramètres).
- **Mise à l'échelle automatique** : l'interface se réduit pour toujours
  tenir dans l'écran (tablettes en paysage ou en portrait, petits écrans).
  L'écran d'arbitrage tient sans défilement.

---

## Architecture

```
  Tablettes / postes            PC serveur                    Graphiques
  (navigateur web)
                         ┌──────────────────────────┐
  Arbitrage  ───────────►│   Tennis Data Manager    │
  Gestion    ───────────►│   NiceGUI  :8080         │
  Administration ───────►│   SQLite (tennis.db)     │
                         └────────────┬─────────────┘
                                      │ ws://<ip>:8080/ws  (JSON)
                                      ▼
                         ┌──────────────────────────┐   AMCP      ┌──────────┐
                         │  Application de contrôle │────────────►│ CasparCG │ 2D
                         │  (projet séparé)         │             └──────────┘
                         │                          │ Remote      ┌──────────┐
                         │                          │ Control API │  Unreal  │ AR
                         └──────────────────────────┘────────────►└──────────┘
```

- **Tennis Data Manager** (ce projet) est la source de vérité. Il stocke les
  données, calcule le score et publie l'état complet des matchs.
- L'**application de contrôle** (projet séparé) se connecte au WebSocket.
  Elle associe les champs du JSON aux champs des graphiques et pilote les
  moteurs de rendu. Les graphiques ne se connectent pas directement au
  serveur.

**Technologies** : Python 3.13, [NiceGUI](https://nicegui.io) 3.16 (Vue,
Quasar, Tailwind, FastAPI), SQLite, Pillow, httpx, psutil.

---

## Installation

Prérequis : **Python 3.11 ou plus récent** (développé et testé avec 3.13),
sous Windows.

```bash
git clone https://github.com/Foxxprod/DATAMANAGER_TNS.git
cd DATAMANAGER_TNS

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Lancement

```bash
python main.py
```

L'interface est disponible sur **http://localhost:8080**. Depuis un autre
poste ou une tablette, utilisez l'adresse IP du PC serveur, affichée sur la
page **ADMINISTRATION**.

- Si un autre poste n'arrive pas à se connecter, autorisez le **port 8080**
  dans le pare-feu Windows du PC serveur.
- Le port se change dans `app_config.py` (`SERVER_PORT`).
- La base de données est créée automatiquement au premier lancement, et mise
  à jour automatiquement lors des nouvelles versions sans perte de données.

---

## Utilisation

### Accueil
Deux grandes tuiles :
- **ARBITRAGE** : saisie des points ;
- **GESTION DES DONNÉES** : tournois, joueurs, matchs.

Le petit bouton **ADMINISTRATION** en bas à droite est réservé au
technicien. Le haut de l'écran affiche le tournoi en cours, la date et
l'heure.

### Préparer un tournoi
1. **TOURNOIS** : créer le tournoi (courts, dates, logo) et le marquer comme
   actif (étoile).
2. **JOUEURS** : ajouter les joueurs. La recherche Wikidata remplit la fiche
   automatiquement. Vérifier les noms TV et ajouter les photos.
3. **MATCHS** : créer les matchs (joueurs, court, horaire, format). Un joueur
   manquant peut être créé directement depuis la fenêtre du match.

### Arbitrer un match
1. **ARBITRAGE** : choisir le match.
2. Sélectionner le **premier service** puis le **joueur à gauche** (vu depuis
   la chaise d'arbitre), puis **DÉBUTER LE MATCH**.
3. Appuyer sur **POINT** du côté du joueur qui gagne chaque point.
   Facultatif : préciser la nature du point juste après.
4. En cas d'erreur : **ANNULER LE DERNIER POINT**. Les corrections de
   serveur ou de côté s'annulent de la même façon.
5. En fin de match, le vainqueur s'affiche, puis **RETOUR AUX MATCHS**.

---

## Diffusion des données (WebSocket)

```
ws://<ip-du-serveur>:8080/ws
```

- **À la connexion** : un instantané de tous les matchs, avec le tournoi
  actif.
- **Ensuite** : le **match complet** à chaque changement (point, statut,
  joueur…). Aucun calcul de tennis n'est nécessaire côté graphique.
- **Messages client** : `subscribe` pour ne suivre que certains matchs,
  `snapshot` pour redemander l'état complet.

Arborescence simple à deux niveaux :

```
match
├── id, status, round, court, active_set, in_tiebreak, changeover…
├── tournament { name, logo_url… }
├── format { best_of, no_ad… }
└── teams [2]
    ├── tv_short_name, tricodes, flag_urls, serving, side
    ├── games [6, 2, null], tiebreak_small, points "30"
    ├── break_point, set_point, match_point, is_winner
    ├── stats { aces, double_faults, break_points_won… }
    └── players [1 ou 2] { tv_short_name, country, photo_url… }
```

- Documentation complète : [docs/websocket.md](docs/websocket.md)
- Exemple réel : [docs/websocket_exemple.json](docs/websocket_exemple.json)

---

## Intégration graphique : CasparCG et Unreal Engine

L'architecture prévue passe par l'application de contrôle :

- **CasparCG (2D)** : commandes AMCP (port TCP 5250) et données XML (nom du
  champ et valeur) associées aux chemins du JSON.
- **Unreal Engine (réalité augmentée)** : plugin **Remote Control API** (HTTP
  sur le port 30010, WebSocket sur le port 30020).
  - Caméra PTZ **Panasonic AW-UE160** avec tracking **FreeD** via le plugin
    *Live Link FreeD*.
  - Calibrage du court en cliquant ses 4 coins.
  - Le champ `side` (`left` / `right`, vu depuis la chaise d'arbitre) permet
    de placer les graphiques au sol du côté du bon joueur.

Le moment le plus favorable aux graphiques au sol est quand le terrain est
vide : avant le match, aux changements de côté (champ `changeover`) et entre
les sets.

---

## Données et fichiers

| Élément | En développement | Exécutable installé |
|---|---|---|
| Base de données | `tennis.db` (racine du projet) | `%APPDATA%\DataManagerTNS\tennis.db` |
| Configuration | `config.json` | `%APPDATA%\DataManagerTNS\config.json` |
| Photos des joueurs | `photos/` | `%APPDATA%\DataManagerTNS\photos\` |
| Logos des tournois | `logos/` | `%APPDATA%\DataManagerTNS\logos\` |

Ces données d'instance **ne sont pas versionnées** (voir `.gitignore`). Pour
sauvegarder une installation, copiez la base et les dossiers `photos` et
`logos`, de préférence application arrêtée.

---

## Structure du code

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée : pages, fichiers statiques, démarrage du serveur |
| `home.py` | Page d'accueil |
| `layout.py` | Thème, header, mise à l'échelle, composants communs (drapeaux, logos, listes) |
| `admin.py` | Liste des matchs, fenêtre de création/modification, fiche du match |
| `players.py` | Annuaire des joueurs, fenêtre et fiche joueur |
| `tournaments.py` | Tournois et tournoi actif |
| `umpire.py` | Interface d'arbitrage (sélection, début de match, saisie des points) |
| `scoring.py` | Moteur de score : règles du tennis, service, côtés, statistiques |
| `scoreboard.py` | Tableau des scores (arbitrage et fiche du match) |
| `api.py` | Serveur WebSocket et format JSON des matchs |
| `events.py` | Événements temps réel partagés entre pages et postes |
| `database.py` | Schéma SQLite, migrations, accès aux données |
| `models.py` | Modèle de données (Match, Player, Tournament, MatchFormat) |
| `system_page.py`, `system_info.py` | Page ADMINISTRATION et lecture des informations du PC |
| `forms.py` | Composants des formulaires (dates, images, listes) |
| `media.py`, `photos.py`, `logos.py` | Stockage et traitement des images envoyées |
| `wikidata.py` | Recherche et import de joueurs depuis Wikidata |
| `countries.py` | Codes pays CIO, noms et drapeaux |
| `app_config.py`, `paths.py` | Configuration et chemins (développement ou exécutable) |
| `assets/` | Logos, favicon, fond d'écran, drapeaux SVG |
| `docs/` | Documentation du WebSocket |

---

## Développement

### Moteur de score
Le score n'est jamais stocké : il est **recalculé en rejouant la liste des
événements** du match (`match_points`). Il y a trois types d'événements :
- un point gagné ;
- un changement de serveur manuel ;
- une inversion des côtés.

Annuler revient donc à supprimer le dernier événement, sans état
intermédiaire à défaire. Les statistiques sont calculées de la même façon, en
un seul passage.

### Migrations de la base
Le schéma est versionné avec `PRAGMA user_version` (`SCHEMA_VERSION` dans
`database.py`, actuellement **12**). Pour toute évolution du schéma :
1. incrémenter `SCHEMA_VERSION` ;
2. ajouter un bloc `if current < N:` dans `_migrate()`.

Les bases existantes sont mises à jour au démarrage, sans perte de données.

### Temps réel
Les pages s'abonnent aux événements de `events.py` (`match_scored`,
`tournaments_changed`, `players_changed`) avec `subscribe_for`, qui se
désabonne automatiquement à la fermeture de la page. Le WebSocket
(`api.py`) écoute les mêmes événements.

---

## Crédits

- Développement : **Foxx Production**
- Logo : Pôle supérieur audiovisuel de Villefontaine (Léonard de Vinci)
- Drapeaux : [flag-icons](https://github.com/lipis/flag-icons) 7.2.3, licence
  MIT
- Photo de fond : *The Greenbrier resort's Center tennis court*, Jumpy542,
  Wikimedia Commons, licence CC0
- Détail des ressources tierces : [assets/CREDITS.txt](assets/CREDITS.txt)
