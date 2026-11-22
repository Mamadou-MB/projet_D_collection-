import unittest
from unittest.mock import patch

import scraping_beautifulsoup as scrapers


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise scrapers.requests.HTTPError(f"HTTP {self.status_code}")


class BeautifulSoupScraperTests(unittest.TestCase):
    def test_books_include_requested_detail_fields(self):
        page_url = scrapers.BOOKS_URL
        product_url = "https://books.toscrape.com/catalogue/a-book_1/index.html"
        listing = """
        <article class="product_pod">
          <p class="star-rating Five"></p>
          <h3><a href="a-book_1/index.html" title="A Book"></a></h3>
          <p class="price_color">£12.50</p>
          <p class="availability">In stock</p>
        </article>
        """
        details = """
        <ul class="breadcrumb"><li><a>Home</a></li><li><a>Books</a></li></ul>
        <div id="product_description"></div><p>A short description.</p>
        <table>
          <tr><th>Number of reviews</th><td>7</td></tr>
          <tr><th>Tax</th><td>£2.50</td></tr>
        </table>
        """
        pages = {page_url: listing, product_url: details}
        with patch.object(
            scrapers.requests,
            "get",
            side_effect=lambda url, timeout: FakeResponse(pages[url]),
        ), patch.object(scrapers.time, "sleep"):
            records = scrapers.scrape_books(1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Note"], "Five")
        self.assertEqual(records[0]["Nombre de reviews"], "7")
        self.assertEqual(records[0]["Tax"], "£2.50")
        self.assertEqual(records[0]["Catégorie"], "Books")

    def test_gaaraas_reads_vehicle_fields_and_next_page(self):
        first_url = "https://www.gaaraas.com/fr/users/dakar-auto?page=1"
        second_url = "https://www.gaaraas.com/fr/users/dakar-auto?page=2"
        card = """
        <a class="common-ad-card" href="/fr/vehicle_listings/car-1">
          <div class="ad-specification">
            <h4>2004 Mercedes‒Benz 190</h4>
            <div class="location">Dakar</div>
            <div class="ad-vehicle-price"><span class="price">2 200 000</span></div>
            <div class="ad-vehicle-mileage"><div class="value">140 000 km</div></div>
            <div class="transmission">Manuelle</div>
          </div>
        </a>
        """
        requested = []
        pages = {
            first_url: card + '<a href="?page=2">Suivant</a>',
            second_url: card,
        }

        def fake_get(url, timeout):
            requested.append(url)
            return FakeResponse(pages[url])

        with patch.object(scrapers.requests, "get", side_effect=fake_get), patch.object(
            scrapers.time, "sleep"
        ):
            records = scrapers.scrape_gaaraas(2)

        self.assertEqual(requested, [first_url, second_url])
        self.assertEqual(records[0]["Marque"], "Mercedes‒Benz")
        self.assertEqual(records[0]["Modèle"], "190")
        self.assertEqual(records[0]["Année"], "2004")
        self.assertEqual(records[0]["Boîte de vitesses"], "Manuelle")

    def test_motos_reads_cards_without_normalizing_source_fields(self):
        page_url = scrapers.MOTOS_URL
        listing = """
        <div class="listing-card">
          <div class="listing-card__header__category">Motos Occasion</div>
          <h2 class="listing-card__header__title">
            <a href="/annonce-1" title="Honda CBF 2010">Honda CBF 2010</a>
          </h2>
          <div class="listing-card__header__price">450&nbsp;000 CFA</div>
          <div class="town-suburb">Dakar,</div><div class="province">Dakar</div>
          <ul class="listing-card__attribute-list"><li>1 000 km</li></ul>
          <div class="listing-card__aside"><img src="/images/moto.jpg"></div>
        </div>
        """
        with patch.object(
            scrapers.requests,
            "get",
            return_value=FakeResponse(listing),
        ):
            records = scrapers.scrape_motos(1)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["Catégorie"], "Motos Occasion")
        self.assertEqual(records[0]["Kilométrage"], "1 000 km")
        self.assertEqual(records[0]["URL annonce"], "https://dakar-auto.com/annonce-1")

    def test_page_limit_must_stay_between_one_and_one_hundred(self):
        with self.assertRaises(ValueError):
            scrapers.scrape_motos(0)

        with self.assertRaises(ValueError):
            scrapers.scrape_motos(101)

    def test_temporary_server_error_is_retried(self):
        responses = [FakeResponse("", 502), FakeResponse("<html></html>")]
        with patch.object(
            scrapers.requests,
            "get",
            side_effect=responses,
        ) as get_page, patch.object(scrapers.time, "sleep"):
            soup = scrapers._read_page("https://example.test")

        self.assertEqual(get_page.call_count, 2)
        self.assertEqual(soup.title, None)


if __name__ == "__main__":
    unittest.main()
