import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BOOKS_URL = "https://books.toscrape.com/catalogue/page-1.html"
GAARAAS_URL = "https://www.gaaraas.com/fr/users/dakar-auto"
MOTOS_URL = "https://dakar-auto.com/senegal/motos-and-scooters-3"


def _check_pages(max_pages):
    pages = int(max_pages)
    if pages < 1 or pages > 100:
        raise ValueError("Le nombre de pages doit être compris entre 1 et 100.")
    return pages


def _read_page(url):
    for attempt in range(3):
        response = requests.get(url, timeout=30)
        if response.status_code not in (502, 503, 504):
            response.raise_for_status()
            return BeautifulSoup(response.text, "html.parser")
        if attempt < 2:
            time.sleep(attempt + 1)

    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _text(parent, selector):
    element = parent.select_one(selector)
    return element.get_text(" ", strip=True) if element else ""


def _vehicle_parts(title):
    year = title[:4] if title[:4].isdigit() else ""
    vehicle = title[5:] if year else title
    parts = vehicle.split(" ", 1)
    brand = parts[0] if parts else ""
    model = parts[1] if len(parts) > 1 else ""
    return brand, model, year


def scrape_books(max_pages=1):
    max_pages = _check_pages(max_pages)
    page_url = BOOKS_URL
    records = []

    for _ in range(max_pages):
        soup = _read_page(page_url)
        books = soup.select("article.product_pod")

        for book in books:
            link = book.select_one("h3 a")
            if not link:
                continue

            detail_url = urljoin(page_url, link.get("href", ""))
            details = _read_page(detail_url)
            table_values = {}
            for row in details.select("table tr"):
                heading = row.select_one("th")
                value = row.select_one("td")
                if heading and value:
                    table_values[heading.get_text(" ", strip=True)] = value.get_text(
                        " ", strip=True
                    )

            categories = details.select("ul.breadcrumb li a")
            rating = book.select_one(".star-rating")
            records.append({
                "Titre": link.get("title", link.get_text(" ", strip=True)),
                "Prix": _text(book, ".price_color"),
                "Disponibilité": _text(book, ".availability"),
                "Produits sur la page": len(books),
                "Note": rating.get("class", [])[-1] if rating and rating.get("class") else "",
                "Nombre de reviews": table_values.get("Number of reviews", ""),
                "Description": _text(details, "#product_description + p"),
                "Catégorie": categories[-1].get_text(" ", strip=True) if len(categories) > 1 else "",
                "Tax": table_values.get("Tax", ""),
                "Page source": page_url,
                "URL produit": detail_url,
            })
            time.sleep(0.1)

        next_link = soup.select_one("li.next a")
        if not books or not next_link:
            break
        page_url = urljoin(page_url, next_link.get("href", ""))

    return records


def scrape_gaaraas(max_pages=1):
    max_pages = _check_pages(max_pages)
    records = []

    for page_number in range(1, max_pages + 1):
        page_url = f"{GAARAAS_URL}?page={page_number}"
        soup = _read_page(page_url)
        cards = soup.select(".common-ad-card")

        for card in cards:
            title = _text(card, ".ad-specification h4")
            brand, model, year = _vehicle_parts(title)
            records.append({
                "Marque": brand,
                "Modèle": model,
                "Année": year,
                "Prix": _text(card, ".ad-vehicle-price .price"),
                "Kilométrage": _text(card, ".ad-vehicle-mileage .value"),
                "Boîte de vitesses": _text(card, ".transmission"),
                "Région": _text(card, ".location"),
                "URL annonce": card.get("href", ""),
                "Page source": page_url,
            })

        has_next_page = any(
            link.get_text(" ", strip=True).casefold() == "suivant"
            for link in soup.select("a[href*='page='], a[rel='next']")
        )
        if not cards or not has_next_page:
            break
        time.sleep(0.5)

    return records


def scrape_motos(max_pages=1):
    max_pages = _check_pages(max_pages)
    records = []

    for page_number in range(1, max_pages + 1):
        page_url = MOTOS_URL if page_number == 1 else f"{MOTOS_URL}?&page={page_number}"
        soup = _read_page(page_url)
        cards = soup.select(".listing-card")

        for card in cards:
            title_link = card.select_one(".listing-card__header__title a")
            if not title_link:
                continue

            image = card.select_one(".listing-card__aside img")
            location = ", ".join(
                value for value in (
                    _text(card, ".town-suburb"),
                    _text(card, ".province"),
                ) if value
            )
            records.append({
                "Titre": title_link.get("title", title_link.get_text(" ", strip=True)),
                "Prix": _text(card, ".listing-card__header__price"),
                "Catégorie": _text(card, ".listing-card__header__category"),
                "Kilométrage": _text(card, ".listing-card__attribute-list"),
                "Localisation": location,
                "Image": urljoin(page_url, image.get("src", "")) if image else "",
                "URL annonce": urljoin(page_url, title_link.get("href", "")),
                "Page source": page_url,
            })

        has_next_page = any(
            link.get_text(" ", strip=True).casefold() == "suivant"
            for link in soup.select("a[href*='page=']")
        )
        if not cards or not has_next_page:
            break
        time.sleep(0.5)

    return records
