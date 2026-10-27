# Crawler de catalogue produits

Collecte automatisée de fiches produits (titre, prix, note, disponibilité)
sur un catalogue en ligne paginé, avec contrôle qualité des données collectées.

Site cible : books.toscrape.com, bac à sable public conçu pour l'apprentissage
du scraping — la collecte y est explicitement autorisée.

## Ce que fait le script

- Parcourt automatiquement la pagination en suivant le lien « next »
- Extrait les fiches produits de chaque page (requests + BeautifulSoup)
- Relance les requêtes échouées avec un délai croissant (1s, 2s, 4s)
- Respecte un délai d'une seconde entre les requêtes
- Contrôle la qualité des données et émet des alertes
- Exporte en CSV et en JSON

## Contrôles qualité

| Dimension | Contrôle |
|---|---|
| Taux de réussite | Part des pages récupérées sans erreur |
| Complétude | Fiches sans titre, sans prix ou sans note |
| Unicité | Doublons sur l'URL produit |
| Validité | Prix nuls ou négatifs |

Un champ soudainement vide sur de nombreuses fiches signale en général un
changement de structure du site : c'est ce que le monitoring doit détecter
avant que les données ne soient exploitées.

## Installation

pip install requests beautifulsoup4

## Utilisation

python scraper.py              # catalogue complet (50 pages, 1000 fiches)
python scraper.py --pages 3    # les 3 premières pages

## Choix techniques

**Suivre le lien « next » plutôt que construire les URLs.** Si la pagination
change, le crawler s'arrête proprement au lieu de produire des erreurs 404.

**Convertir les types dès la collecte.** Un prix stocké en texte est
inexploitable pour toute analyse ultérieure.

**Séparer réseau, extraction et contrôle.** Chaque couche peut être testée
isolément, et une évolution du site n'impacte que la couche d'extraction.
