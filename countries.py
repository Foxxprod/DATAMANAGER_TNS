# Pays des joueurs : code a 3 lettres (codes CIO, ceux utilises par
# l'ATP/WTA/ITF : SUI, GER, NED, CRO...), nom affiche et code ISO 3166
# alpha-2 du drapeau (fichier assets/flags/<iso2>.svg, pack flag-icons -
# licence MIT, voir assets/flags/LICENSE). Drapeaux embarques en local :
# le logiciel doit fonctionner sans acces internet en regie.
#
# "NEU" : joueurs sous banniere neutre (pas de drapeau).

_RAW = """
AFG af Afghanistan
RSA za Afrique du Sud
ALB al Albanie
ALG dz Algerie
GER de Allemagne
AND ad Andorre
ANG ao Angola
ANT ag Antigua-et-Barbuda
KSA sa Arabie saoudite
ARG ar Argentine
ARM am Armenie
ARU aw Aruba
AUS au Australie
AUT at Autriche
AZE az Azerbaidjan
BAH bs Bahamas
BRN bh Bahrein
BAN bd Bangladesh
BAR bb Barbade
BEL be Belgique
BIZ bz Belize
BEN bj Benin
BER bm Bermudes
BHU bt Bhoutan
BLR by Bielorussie
BOL bo Bolivie
BIH ba Bosnie-Herzegovine
BOT bw Botswana
BRA br Bresil
BRU bn Brunei
BUL bg Bulgarie
BUR bf Burkina Faso
BDI bi Burundi
CAM kh Cambodge
CMR cm Cameroun
CAN ca Canada
CPV cv Cap-Vert
CHI cl Chili
CHN cn Chine
CYP cy Chypre
COL co Colombie
COM km Comores
CGO cg Congo
COD cd RD Congo
KOR kr Coree du Sud
PRK kp Coree du Nord
CRC cr Costa Rica
CIV ci Cote d'Ivoire
CRO hr Croatie
CUB cu Cuba
DEN dk Danemark
DJI dj Djibouti
DMA dm Dominique
EGY eg Egypte
UAE ae Emirats arabes unis
ECU ec Equateur
ERI er Erythree
ESP es Espagne
EST ee Estonie
SWZ sz Eswatini
USA us Etats-Unis
ETH et Ethiopie
FIJ fj Fidji
FIN fi Finlande
FRA fr France
GAB ga Gabon
GAM gm Gambie
GEO ge Georgie
GHA gh Ghana
GBR gb Grande-Bretagne
GRE gr Grece
GRN gd Grenade
GUM gu Guam
GUA gt Guatemala
GUI gn Guinee
GEQ gq Guinee equatoriale
GBS gw Guinee-Bissau
GUY gy Guyana
HAI ht Haiti
HON hn Honduras
HKG hk Hong Kong
HUN hu Hongrie
IND in Inde
INA id Indonesie
IRQ iq Irak
IRI ir Iran
IRL ie Irlande
ISL is Islande
ISR il Israel
ITA it Italie
JAM jm Jamaique
JPN jp Japon
JOR jo Jordanie
KAZ kz Kazakhstan
KEN ke Kenya
KGZ kg Kirghizistan
KOS xk Kosovo
KUW kw Koweit
LAO la Laos
LES ls Lesotho
LAT lv Lettonie
LBN lb Liban
LBR lr Liberia
LBA ly Libye
LIE li Liechtenstein
LTU lt Lituanie
LUX lu Luxembourg
MKD mk Macedoine du Nord
MAD mg Madagascar
MAS my Malaisie
MAW mw Malawi
MDV mv Maldives
MLI ml Mali
MLT mt Malte
MAR ma Maroc
MRI mu Maurice
MTN mr Mauritanie
MEX mx Mexique
MDA md Moldavie
MON mc Monaco
MGL mn Mongolie
MNE me Montenegro
MOZ mz Mozambique
MYA mm Myanmar
NAM na Namibie
NEP np Nepal
NCA ni Nicaragua
NIG ne Niger
NGR ng Nigeria
NOR no Norvege
NZL nz Nouvelle-Zelande
OMA om Oman
UGA ug Ouganda
UZB uz Ouzbekistan
PAK pk Pakistan
PLE ps Palestine
PAN pa Panama
PNG pg Papouasie-Nouvelle-Guinee
PAR py Paraguay
NED nl Pays-Bas
PER pe Perou
PHI ph Philippines
POL pl Pologne
PUR pr Porto Rico
POR pt Portugal
QAT qa Qatar
DOM do Republique dominicaine
CZE cz Republique tcheque
ROU ro Roumanie
RUS ru Russie
RWA rw Rwanda
SMR sm Saint-Marin
LCA lc Sainte-Lucie
ESA sv Salvador
SAM ws Samoa
SEN sn Senegal
SRB rs Serbie
SEY sc Seychelles
SLE sl Sierra Leone
SGP sg Singapour
SVK sk Slovaquie
SLO si Slovenie
SOM so Somalie
SUD sd Soudan
SRI lk Sri Lanka
SWE se Suede
SUI ch Suisse
SUR sr Suriname
SYR sy Syrie
TJK tj Tadjikistan
TPE tw Taipei chinois
TAN tz Tanzanie
CHA td Tchad
THA th Thailande
TOG tg Togo
TGA to Tonga
TTO tt Trinite-et-Tobago
TUN tn Tunisie
TKM tm Turkmenistan
TUR tr Turquie
UKR ua Ukraine
URU uy Uruguay
VAN vu Vanuatu
VEN ve Venezuela
VIE vn Viet Nam
YEM ye Yemen
ZAM zm Zambie
ZIM zw Zimbabwe
NEU - Neutre
"""

#code -> (nom, iso2 du drapeau ou "" si aucun)
COUNTRIES: dict[str, tuple[str, str]] = {}
for _line in _RAW.strip().splitlines():
    _code, _iso2, _name = _line.split(" ", 2)
    COUNTRIES[_code] = (_name, "" if _iso2 == "-" else _iso2)

#options du select "Pays" du formulaire joueur, triees par nom
COUNTRY_OPTIONS: dict[str, str] = {
    code: f"{name} ({code})" for code, (name, _) in sorted(COUNTRIES.items(), key=lambda item: item[1][0])
}


def country_name(code: str) -> str:
    return COUNTRIES.get(code, (code, ""))[0]


def flag_iso(code: str) -> str:
    return COUNTRIES.get(code, ("", ""))[1]


_ISO_TO_CODE = {iso: code for code, (_, iso) in COUNTRIES.items() if iso}


#code a 3 lettres depuis un code ISO alpha-2 (ex: "FR" -> "FRA"), "" si inconnu
def code_from_iso(iso2: str) -> str:
    return _ISO_TO_CODE.get(iso2.lower(), "")
