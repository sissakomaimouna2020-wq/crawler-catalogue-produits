"""
Crawler de catalogue produits — books.toscrape.com

Collecte les fiches produits d'un catalogue en ligne (titre, prix, note,
disponibilité, URL) en parcourant automatiquement la pagination.

Le script est conçu autour de trois exigences d'une collecte en production :
  1. Robustesse  : relance automatique en cas d'échec réseau.
  2. Politesse   : délai entre les requêtes pour ne pas surcharger le serveur.
  3. Monitoring  : suivi du taux de réussite et détection des anomalies.

Site cible : books.toscrape.com, bac à sable public conçu pour
l'apprentissage du scraping (collecte explicitement autorisée).

Usage :
    python scraper.py              # collecte tout le catalogue
    python scraper.py --pages 3    # collecte les 3 premières pages
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

BASE_URL = "https://books.toscrape.com/catalogue/page-1.html"
DELAY_SECONDS = 1.0          # pause entre deux requêtes
MAX_RETRIES = 3              # tentatives par page avant abandon
TIMEOUT_SECONDS = 10         # délai d'attente maximal d'une réponse
MIN_SUCCESS_RATE = 0.95      # seuil d'alerte du monitoring

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PortfolioScraper/1.0; +educational use)"
}

# Conversion des notes : le site les exprime en toutes lettres dans une classe CSS
RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Modèle de donnée
# --------------------------------------------------------------------------

@dataclass
class Book:
    """Une fiche produit collectée.

    Utiliser une dataclass plutôt qu'un dictionnaire libre fixe le schéma :
    tout champ manquant devient visible immédiatement, ce qui est la base
    d'une collecte fiable.
    """
    title: str
    price_gbp: float | None
    rating: int | None
    availability: str
    url: str


# --------------------------------------------------------------------------
# Couche réseau
# --------------------------------------------------------------------------

def fetch_page(url: str, session: requests.Session) -> str | None:
    """Télécharge une page HTML, avec relances en cas d'échec.

    Renvoie le HTML, ou None si la page reste inaccessible après
    MAX_RETRIES tentatives. Le délai entre les relances augmente
    progressivement (1s, 2s, 4s) pour laisser au serveur le temps de
    se rétablir plutôt que de l'assaillir.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()

            # Le site déclare l'UTF-8 dans son HTML mais pas toujours dans ses
            # en-têtes HTTP : sans cette ligne, requests retombe sur Latin-1 et
            # le symbole « £ » arrive sous la forme « Â£ ».
            response.encoding = response.apparent_encoding or "utf-8"
            return response.text

        except requests.RequestException as exc:
            wait = 2 ** (attempt - 1)
            logger.warning(
                "Échec (%s/%s) sur %s : %s — nouvelle tentative dans %ss",
                attempt, MAX_RETRIES, url, exc, wait,
            )
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    logger.error("Page abandonnée après %s tentatives : %s", MAX_RETRIES, url)
    return None


# --------------------------------------------------------------------------
# Couche extraction (parsing)
# --------------------------------------------------------------------------

def parse_price(raw: str) -> float | None:
    """Convertit '£51.77' en 51.77.

    La valeur numérique est extraite par expression régulière plutôt qu'en
    retirant un symbole précis : le texte collecté peut contenir une devise
    différente, une espace insécable ou un symbole mal décodé selon
    l'encodage de la réponse. On isole donc les chiffres, ce qui reste
    valable dans tous ces cas.

    Le prix est converti en nombre dès la collecte : une donnée stockée en
    texte devient inexploitable pour toute analyse ultérieure.
    """
    if not raw:
        return None

    match = re.search(r"\d+(?:[.,]\d+)?", raw)
    if not match:
        return None

    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def parse_books(html: str, page_url: str) -> list[Book]:
    """Extrait toutes les fiches produits présentes sur une page."""
    soup = BeautifulSoup(html, "html.parser")
    books: list[Book] = []

    for article in soup.select("article.product_pod"):
        link = article.select_one("h3 a")
        price_tag = article.select_one("p.price_color")
        rating_tag = article.select_one("p.star-rating")
        stock_tag = article.select_one("p.instock.availability")

        # Le titre complet est dans l'attribut title ; le texte visible est tronqué.
        title = link.get("title", "").strip() if link else ""

        # La note est encodée dans la classe CSS, ex. : class="star-rating Three"
        rating = None
        if rating_tag:
            classes = [c for c in rating_tag.get("class", []) if c in RATING_MAP]
            rating = RATING_MAP[classes[0]] if classes else None

        books.append(
            Book(
                title=title,
                price_gbp=parse_price(price_tag.text) if price_tag else None,
                rating=rating,
                availability=stock_tag.text.strip() if stock_tag else "",
                url=urljoin(page_url, link["href"]) if link else "",
            )
        )

    return books


def find_next_page(html: str, current_url: str) -> str | None:
    """Renvoie l'URL de la page suivante, ou None sur la dernière page.

    Suivre le lien « next » présent dans la page est plus robuste que
    construire les URLs à la main : si la pagination change, le crawler
    s'arrête proprement au lieu de produire des erreurs 404 en série.
    """
    soup = BeautifulSoup(html, "html.parser")
    next_link = soup.select_one("li.next a")
    return urljoin(current_url, next_link["href"]) if next_link else None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def crawl(start_url: str = BASE_URL, max_pages: int | None = None) -> tuple[list[Book], dict]:
    """Parcourt la pagination et collecte toutes les fiches produits.

    Renvoie les livres collectés et un rapport de collecte permettant
    de vérifier que la campagne s'est déroulée correctement.
    """
    books: list[Book] = []
    url: str | None = start_url
    pages_ok, pages_failed = 0, 0
    started_at = time.time()

    with requests.Session() as session:
        while url and (max_pages is None or pages_ok + pages_failed < max_pages):
            logger.info("Collecte de %s", url)
            html = fetch_page(url, session)

            if html is None:
                pages_failed += 1
                break  # pagination interrompue : inutile de continuer à l'aveugle

            page_books = parse_books(html, url)
            books.extend(page_books)
            pages_ok += 1
            logger.info("  → %s fiches extraites", len(page_books))

            url = find_next_page(html, url)
            if url:
                time.sleep(DELAY_SECONDS)  # politesse : on n'enchaîne pas les requêtes

    total_pages = pages_ok + pages_failed
    report = {
        "pages_reussies": pages_ok,
        "pages_echouees": pages_failed,
        "taux_reussite": round(pages_ok / total_pages, 3) if total_pages else 0.0,
        "fiches_collectees": len(books),
        "duree_secondes": round(time.time() - started_at, 1),
    }
    return books, report


# --------------------------------------------------------------------------
# Contrôle qualité (monitoring)
# --------------------------------------------------------------------------

def check_quality(books: list[Book], report: dict) -> list[str]:
    """Contrôle la qualité des données et renvoie la liste des alertes.

    Une collecte peut « réussir » techniquement tout en ramenant des
    données inutilisables : c'est ce que ces contrôles détectent.
    """
    alerts: list[str] = []

    if not books:
        alerts.append("CRITIQUE : aucune fiche collectée.")
        return alerts

    if report["taux_reussite"] < MIN_SUCCESS_RATE:
        alerts.append(
            f"Taux de réussite de {report['taux_reussite']:.0%}, "
            f"sous le seuil de {MIN_SUCCESS_RATE:.0%}."
        )

    # Complétude : des champs vides signalent souvent un changement de structure du site
    missing_price = sum(1 for b in books if b.price_gbp is None)
    missing_title = sum(1 for b in books if not b.title)
    missing_rating = sum(1 for b in books if b.rating is None)

    for label, count in [
        ("prix", missing_price),
        ("titre", missing_title),
        ("note", missing_rating),
    ]:
        if count:
            alerts.append(f"{count} fiche(s) sans {label} ({count / len(books):.1%}).")

    # Unicité : un taux de doublons élevé trahit une pagination qui boucle
    duplicates = len(books) - len({b.url for b in books})
    if duplicates:
        alerts.append(f"{duplicates} doublon(s) détecté(s) sur l'URL produit.")

    # Validité : un prix négatif ou nul est une valeur aberrante
    invalid = [b for b in books if b.price_gbp is not None and b.price_gbp <= 0]
    if invalid:
        alerts.append(f"{len(invalid)} prix invalide(s) (valeur nulle ou négative).")

    return alerts


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------

def save(books: list[Book], report: dict, prefix: str = "books") -> None:
    """Écrit les données en CSV (analyse) et en JSON (rapport complet)."""
    rows = [asdict(b) for b in books]

    with open(f"{prefix}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(Book.__annotations__))
        writer.writeheader()
        writer.writerows(rows)

    with open(f"{prefix}.json", "w", encoding="utf-8") as f:
        json.dump({"rapport": report, "donnees": rows}, f, ensure_ascii=False, indent=2)

    logger.info("Fichiers écrits : %s.csv et %s.json", prefix, prefix)


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Crawler de catalogue produits.")
    parser.add_argument("--pages", type=int, default=None, help="nombre de pages à collecter")
    args = parser.parse_args()

    books, report = crawl(max_pages=args.pages)

    logger.info("--- Rapport de collecte ---")
    for key, value in report.items():
        logger.info("%-18s : %s", key, value)

    alerts = check_quality(books, report)
    if alerts:
        logger.warning("--- Alertes qualité ---")
        for alert in alerts:
            logger.warning("  %s", alert)
    else:
        logger.info("Contrôles qualité : aucune anomalie détectée.")

    if books:
        save(books, report)


if __name__ == "__main__":
    main()
