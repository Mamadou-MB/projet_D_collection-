from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import pymupdf
import requests
import streamlit as st

from scraping_beautifulsoup import scrape_books as scrape_books_bs
from scraping_beautifulsoup import scrape_gaaraas as scrape_gaaraas_bs
from scraping_beautifulsoup import scrape_motos as scrape_motos_bs


PROJECT_DIR = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_DIR / "collecte.db"
MONTH_NAMES = {
    "janvier": "Janvier",
    "fevrier": "Février",
    "mars": "Mars",
    "avril": "Avril",
    "mai": "Mai",
    "juin": "Juin",
    "juillet": "Juillet",
    "aout": "Août",
    "septembre": "Septembre",
    "octobre": "Octobre",
    "novembre": "Novembre",
    "decembre": "Décembre",
}
SOURCES = {
    "Books to Scrape": {
        "key": "books",
        "url": "https://books.toscrape.com/catalogue/page-1.html",
    },
    "Gaaraas - Dakar Auto": {
        "key": "gaaraas",
        "url": "https://www.gaaraas.com/fr/users/dakar-auto?page=1",
    },
    "Dakar-Auto - Motos": {
        "key": "motos",
        "url": "https://dakar-auto.com/senegal/motos-and-scooters-3",
    },
}
SCRAPERS = {
    "books": scrape_books_bs,
    "gaaraas": scrape_gaaraas_bs,
    "motos": scrape_motos_bs,
}

kobo_url = os.getenv("KOBO_FORM_URL", "https://ee.kobotoolbox.org/x/kP4saSrZ")
google_url = os.getenv(
    "GOOGLE_FORM_URL",
    "https://docs.google.com/forms/d/e/1FAIpQLSfoX-FU_YmXEs6zqf41xgrxCTrmEX-mlcHuAXSDsj-Sk0UvVw/viewform?usp=publish-editor",
)


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def clean_dataframe(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    column_names = []
    seen_names: dict[str, int] = {}
    for column in cleaned.columns:
        name = str(column).strip()
        seen_names[name] = seen_names.get(name, 0) + 1
        column_names.append(name if seen_names[name] == 1 else f"{name}_{seen_names[name]}")
    cleaned.columns = column_names
    for column in cleaned.columns:
        if cleaned[column].dtype == "object":
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )
    return cleaned.dropna(how="all").drop_duplicates().reset_index(drop=True)


def initialize_database() -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS no_code_exports (
                filename TEXT PRIMARY KEY,
                contents BLOB NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS code_scrapes (
                id INTEGER PRIMARY KEY,
                source TEXT NOT NULL,
                method TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                clean_json TEXT NOT NULL,
                scraped_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        count = connection.execute("SELECT COUNT(*) FROM code_scrapes").fetchone()[0]
        if count == 0:
            mapping = [
                ("Books to Scrape", PROJECT_DIR / "exports" / "books_beautifulsoup_brut.csv", PROJECT_DIR / "exports" / "books_beautifulsoup_nettoye.csv"),
                ("Gaaraas - Dakar Auto", PROJECT_DIR / "exports" / "gaaraas_beautifulsoup_brut.csv", PROJECT_DIR / "exports" / "gaaraas_beautifulsoup_nettoye.csv"),
                ("Dakar-Auto - Motos", PROJECT_DIR / "exports" / "motos_beautifulsoup_brut.csv", PROJECT_DIR / "exports" / "motos_beautifulsoup_nettoye.csv"),
            ]
            for source, raw_path, clean_path in mapping:
                if raw_path.exists() and clean_path.exists():
                    raw_df = pd.read_csv(raw_path)
                    clean_df = pd.read_csv(clean_path)
                    connection.execute(
                        """
                        INSERT INTO code_scrapes (source, method, raw_json, clean_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            source,
                            "Beautiful Soup",
                            raw_df.to_json(orient="records", force_ascii=False),
                            clean_df.to_json(orient="records", force_ascii=False),
                        ),
                    )


def save_code_scrape(
    source: str,
    method: str,
    raw_data: pd.DataFrame,
    clean_data: pd.DataFrame,
) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO code_scrapes (source, method, raw_json, clean_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                source,
                method,
                raw_data.to_json(orient="records", force_ascii=False),
                clean_data.to_json(orient="records", force_ascii=False),
            ),
        )


def load_code_scrapes() -> list[dict[str, str]]:
    with sqlite3.connect(DATABASE_PATH) as connection:
        rows = connection.execute(
            """
            SELECT source, method, raw_json, clean_json, scraped_at
            FROM code_scrapes
            WHERE method = 'Beautiful Soup'
            ORDER BY id DESC
            """
        ).fetchall()

    latest = {}
    for source, method, raw_json, clean_json, scraped_at in rows:
        latest.setdefault(source, {
            "source": source,
            "method": method,
            "raw_json": raw_json,
            "clean_json": clean_json,
            "scraped_at": scraped_at,
        })
    return list(latest.values())


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def search_roots() -> list[Path]:
    roots = []
    for root in (PROJECT_DIR, Path.cwd()):
        if root not in roots:
            roots.append(root)
    return roots


def all_pdfs() -> list[Path]:
    found = {}
    for root in search_roots():
        for pdf_path in root.rglob("*"):
            if pdf_path.suffix.casefold() == ".pdf" and pdf_path.is_file():
                if not any(part.startswith(".") for part in pdf_path.relative_to(root).parts):
                    found[pdf_path.resolve()] = pdf_path
    return sorted(found.values())


def available_bulletins() -> list[tuple[int, str, Path]]:
    bulletins = []
    for pdf_path in all_pdfs():
        stem = normalize_text(pdf_path.stem)
        month = next((name for key, name in MONTH_NAMES.items() if key in stem), None)
        year_match = re.search(r"(20\d{2}|19\d{2})", " ".join(pdf_path.parts[-3:]))
        if year_match and month:
            bulletins.append((int(year_match.group(1)), month, pdf_path))
    return bulletins


def extract_bulletin_pages(year: int, month: str, pdf_path: Path) -> list[dict]:
    records = []
    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            records.append({
                "Année": year,
                "Mois": month,
                "Fichier source": pdf_path.name,
                "Page": page_number,
                "Texte brut": page.get_text("text"),
            })
    return records


def clean_bulletin_pages(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned["Texte"] = cleaned["Texte brut"].map(
        lambda value: re.sub(r"\s+", " ", value).strip()
        if isinstance(value, str)
        else ""
    )
    return cleaned.loc[cleaned["Texte"].ne("")].drop(columns="Texte brut")


def zip_download(files: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, contents in files:
            archive.writestr(filename, contents)
    return buffer.getvalue()


def valid_form_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


initialize_database()
st.set_page_config(
    page_title="Collecte de données | Sénégal",
    layout="wide",
)

st.markdown(
    """
    <style>
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 1200px; }

    h1 { font-size: 2rem; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 0.25rem; }
    div[data-testid="stCaptionContainer"] { opacity: 0.75; }
    div[data-testid="stHeading"] h3 {
        font-size: 1.35rem;
        font-weight: 650;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.25);
    }

    div[data-baseweb="tab-list"] {
        gap: 0.25rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.25);
        margin-bottom: 1.25rem;
    }
    button[data-baseweb="tab"] { font-size: 0.95rem; font-weight: 600; padding: 0.7rem 1.1rem; }

    div[data-testid="stMetric"] {
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 10px;
        padding: 0.9rem 1.1rem;
    }
    div[data-testid="stMetricLabel"] p { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.7; }
    div[data-testid="stMetricValue"] { font-weight: 700; }

    div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 12px; }
    div[data-testid="stExpander"] { border-radius: 10px; }
    div[data-testid="stDataFrame"] { border: 1px solid rgba(128, 128, 128, 0.25); border-radius: 10px; }
    div[data-testid="stAlert"] { border-radius: 10px; }

    div[data-testid="stDownloadButton"] button,
    div[data-testid="stLinkButton"] a,
    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }

    section[data-testid="stSidebar"] .block-container { padding-top: 2rem; }
    hr { margin: 1.5rem 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Collecte de données — Sénégal")
st.caption(
    "Collecte, nettoyage et analyse de données : scraping avec code, tableau de bord, "
    "bulletins météo et formulaires d’évaluation."
)

with st.sidebar:
    st.header("Navigation")
    st.markdown(
        "- **Données brutes et CSV** : CSV bruts des collectes\n"
        "- **Scraping avec code** : lancer une collecte\n"
        "- **Tableau de bord** : graphiques et analyse\n"
        "- **Base SQL** : état de la base locale\n"
        "- **Bulletins météo** : extraction des PDF\n"
        "- **Formulaires** : Kobo et Google Forms"
    )
    st.caption("Sources : Books to Scrape, Gaaraas, Dakar-Auto Motos.")

no_code_tab, code_tab, dashboard_tab, database_tab, weather_tab, forms_tab = st.tabs(
    [
        "Données brutes et CSV",
        "Scraping avec code",
        "Tableau de bord",
        "Base SQL",
        "Bulletins météo",
        "Formulaires",
    ]
)

with no_code_tab:
    st.subheader("Données extraites — fichiers CSV bruts")
    code_scrapes = load_code_scrapes()
    if code_scrapes:
        raw_files = []
        for scrape in code_scrapes:
            raw_data = pd.read_json(io.StringIO(scrape["raw_json"]), orient="records")
            st.markdown(f"**{scrape['source']}** — {len(raw_data)} lignes · {scrape['method']}")
            st.dataframe(raw_data, use_container_width=True, hide_index=True)
            filename = re.sub(r"[^a-z0-9]+", "_", scrape["source"].casefold()).strip("_")
            contents = csv_bytes(raw_data)
            raw_files.append((f"{filename}_brut.csv", contents))
            st.download_button(
                f"Télécharger le CSV brut — {scrape['source']}",
                data=contents,
                file_name=f"{filename}_brut.csv",
                mime="text/csv",
                key=f"download_code_raw_{filename}",
            )
        st.download_button(
            "Télécharger tous les CSV bruts (ZIP)",
            data=zip_download(raw_files),
            file_name="donnees_brutes.zip",
            mime="application/zip",
        )
    else:
        st.info("Lancez une collecte avec code pour afficher les données ici.")

with code_tab:
    st.subheader("Collecter, nettoyer et télécharger")
    source_name = st.selectbox("Source", list(SOURCES))
    page_limit = st.number_input(
        "Nombre maximal de pages (1 à 100)",
        min_value=1,
        max_value=100,
        value=1,
        step=1,
    )
    st.caption("La collecte avec code utilise uniquement Beautiful Soup.")

    notebook_path = PROJECT_DIR / "Collecte_donnees.ipynb"
    if notebook_path.is_file():
        st.download_button(
            "Télécharger le notebook Beautiful Soup",
            data=notebook_path.read_bytes(),
            file_name=notebook_path.name,
            mime="application/x-ipynb+json",
        )

    if st.button("Lancer le scraping avec code", type="primary"):
        source_key = SOURCES[source_name]["key"]
        scraper = SCRAPERS[source_key]
        try:
            records = scraper(int(page_limit))
        except requests.RequestException as error:
            st.error(f"Erreur HTTP pendant le scraping : {error}")
        except ValueError as error:
            st.error(str(error))
        else:
            if not records:
                st.warning("Aucun résultat n’a été retourné par cette source.")
            else:
                raw_data = pd.DataFrame(records)
                clean_data = clean_dataframe(raw_data)
                save_code_scrape(source_name, "Beautiful Soup", raw_data, clean_data)
                st.session_state["last_code_scrape"] = {
                    "source": source_name,
                    "method": "Beautiful Soup",
                    "raw": raw_data,
                    "clean": clean_data,
                }
                st.success(f"{len(clean_data)} ligne(s) collectée(s) et nettoyée(s).")

    last_scrape = st.session_state.get("last_code_scrape")
    if not last_scrape or last_scrape["source"] != source_name:
        saved_scrapes = load_code_scrapes()
        saved_scrape = next(
            (item for item in saved_scrapes if item["source"] == source_name),
            None,
        )
        if saved_scrape:
            last_scrape = {
                "source": saved_scrape["source"],
                "method": saved_scrape["method"],
                "clean": pd.read_json(
                    io.StringIO(saved_scrape["clean_json"]),
                    orient="records",
                ),
            }
    if last_scrape:
        st.markdown(
            f"**Dernière collecte : {last_scrape['source']} — {last_scrape['method']}**"
        )
        st.markdown("**Données collectées et nettoyées**")
        st.dataframe(last_scrape["clean"], use_container_width=True, hide_index=True)
        st.download_button(
            "Télécharger les données nettoyées (CSV)",
            data=csv_bytes(last_scrape["clean"]),
            file_name=f"{last_scrape['source'].lower().replace(' ', '_')}_nettoye.csv",
            mime="text/csv",
        )

with dashboard_tab:
    st.subheader("Tableau de bord et rapport d’analyse")
    st.write(
        "Ce tableau de bord synthétise les données nettoyées issues des collectes avec code (Beautiful Soup). "
        "Il intègre des graphiques interactifs et un rapport détaillé expliquant les variables."
    )
    code_scrapes = load_code_scrapes()
    if not code_scrapes:
        st.info("Lancez une collecte avec code pour alimenter le tableau de bord.")
    else:
        source_choice = st.selectbox(
            "Sélectionner la source à analyser",
            [scrape["source"] for scrape in code_scrapes],
        )
        selected_scrape = next(s for s in code_scrapes if s["source"] == source_choice)
        df_source = pd.read_json(io.StringIO(selected_scrape["clean_json"]), orient="records")

        st.markdown(f"### Analyse de la source : {source_choice}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Nombre d'enregistrements", len(df_source))
        m2.metric("Colonnes analysées", len(df_source.columns))
        m3.metric("Méthode de collecte", selected_scrape["method"])

        st.dataframe(df_source.head(10), use_container_width=True, hide_index=True)

        if "Book" in source_choice:
            st.markdown("#### Graphiques et analyse des variables — Books to Scrape")
            col_a, col_b = st.columns(2)
            with col_a:
                if "Prix" in df_source.columns:
                    prices = df_source["Prix"].astype(str).str.extract(r"([\d\.]+)")[0].astype(float)
                    st.markdown("**Distribution des Prix (£)**")
                    st.bar_chart(prices.value_counts().sort_index())
                    st.caption("Explication : Ce graphique illustre la concentration des prix des ouvrages (10£ - 40£ en majorité).")
            with col_b:
                if "Note" in df_source.columns:
                    st.markdown("**Répartition des Notes (Étoiles)**")
                    ratings = df_source["Note"].value_counts()
                    st.bar_chart(ratings)
                    st.caption("Explication : La répartition des notes (One à Five) permet d'évaluer la qualité perçue des ouvrages.")

            if "Catégorie" in df_source.columns:
                st.markdown("**Top Catégories de Livres**")
                top_cat = df_source["Catégorie"].value_counts().head(10)
                st.bar_chart(top_cat)
                st.caption("Explication : Met en évidence les catégories littéraires les plus denses.")

        elif "Gaaraas" in source_choice or "Motos" in source_choice:
            st.markdown("#### Graphiques et analyse des variables — Annonces de véhicules")
            col_a, col_b = st.columns(2)
            with col_a:
                if "Prix" in df_source.columns:
                    st.markdown("**Analyse des Prix des Annonces**")
                    prices_v = df_source["Prix"].astype(str).str.replace(r"[^\d]", "", regex=True)
                    prices_v = pd.to_numeric(prices_v, errors="coerce").dropna()
                    if not prices_v.empty:
                        st.bar_chart(prices_v.head(20))
                        st.caption("Explication : Présente la variation des prix des annonces automobiles/motos.")
            with col_b:
                if "Marque" in df_source.columns:
                    st.markdown("**Top Marques de Véhicules**")
                    brands = df_source["Marque"].value_counts().head(10)
                    st.bar_chart(brands)
                    st.caption("Explication : Identifie les marques les plus fréquentes (Toyota, Peugeot, etc.).")

        st.divider()
        st.markdown("### Rapport explicatif des variables et graphiques")
        report_path = next(
            (p for root in search_roots() for p in root.rglob("RAPPORT_ANALYSE.md")),
            None,
        )
        if report_path:
            report_text = report_path.read_text(encoding="utf-8")
            with st.expander("Lire le rapport d’analyse complet", expanded=True):
                st.markdown(report_text)
            st.download_button(
                "Télécharger le rapport d’analyse (MD)",
                data=report_text.encode("utf-8"),
                file_name="RAPPORT_ANALYSE.md",
                mime="text/markdown",
            )
        else:
            st.info("Le rapport d’analyse (`RAPPORT_ANALYSE.md`) n’est pas disponible sur le serveur.")

        st.download_button(
            "Télécharger les données de cette source (CSV)",
            data=csv_bytes(df_source),
            file_name=f"{source_choice.lower().replace(' ', '_')}_nettoye.csv",
            mime="text/csv",
        )

with database_tab:
    st.subheader("Base de données SQLite")
    st.write("Les collectes avec code sont stockées localement.")
    st.metric("Collectes code récentes", len(load_code_scrapes()))

with weather_tab:
    st.subheader("Bulletins météo")
    bulletins = available_bulletins()
    if not bulletins:
        st.warning("Aucun bulletin PDF reconnu. Les fichiers doivent être dans un dossier portant l’année (ex. Bulletins_2024/climato_janvier.pdf).")
        with st.expander("Diagnostic : fichiers PDF détectés sur le serveur"):
            st.write(f"Dossier de l’application : `{PROJECT_DIR}`")
            st.write(f"Dossier de travail : `{Path.cwd()}`")
            detected = all_pdfs()
            if detected:
                st.write(f"{len(detected)} PDF trouvé(s) :")
                st.code("\n".join(str(p) for p in detected[:50]))
            else:
                st.write("Aucun fichier PDF n’est présent sur le serveur : ils n’ont pas été déployés avec le dépôt.")
    else:
        years = sorted({year for year, _, _ in bulletins})
        selected_years = st.multiselect("Année", years, default=years)
        month_options = list(MONTH_NAMES.values())
        selected_months = st.multiselect("Mois", month_options, default=month_options)
        selected_bulletins = [
            item
            for item in bulletins
            if item[0] in selected_years and item[1] in selected_months
        ]
        weather_signature = tuple(
            (year, month, path.name) for year, month, path in selected_bulletins
        )
        st.write(f"{len(selected_bulletins)} bulletin(s) correspondent aux filtres.")
        if selected_bulletins:
            if st.button("Extraire et concaténer les bulletins sélectionnés"):
                try:
                    records = [
                        record
                        for year, month, path in selected_bulletins
                        for record in extract_bulletin_pages(year, month, path)
                    ]
                except (pymupdf.FileDataError, OSError) as error:
                    st.error(f"Impossible de lire un bulletin PDF : {error}")
                else:
                    st.session_state["weather_raw"] = pd.DataFrame(records)
                    st.session_state["weather_signature"] = weather_signature

        weather_raw = st.session_state.get("weather_raw")
        if (
            weather_raw is not None
            and not weather_raw.empty
            and st.session_state.get("weather_signature") == weather_signature
        ):
            empty_pages = weather_raw["Texte brut"].fillna("").str.strip().eq("").sum()
            if empty_pages:
                st.warning(
                    f"{empty_pages} page(s) ne contiennent pas de texte extractible; "
                    "elles peuvent être des pages numérisées."
                )
            st.markdown("**Aperçu concaténé des pages extraites**")
            st.dataframe(weather_raw, use_container_width=True, hide_index=True)
            st.download_button(
                "Télécharger les données météo brutes (CSV)",
                data=csv_bytes(weather_raw),
                file_name="bulletins_meteo_bruts.csv",
                mime="text/csv",
            )
            weather_clean = clean_bulletin_pages(weather_raw)
            st.download_button(
                "Télécharger les données météo nettoyées (CSV)",
                data=csv_bytes(weather_clean),
                file_name="bulletins_meteo_nettoyes.csv",
                mime="text/csv",
            )
        elif st.session_state.get("weather_raw") is not None:
            st.info("Relancez l’extraction pour appliquer les filtres Année et Mois actuels.")

with forms_tab:
    st.subheader("📝 Formulaires d’évaluation")
    st.write(
        "Donnez votre avis sur l’application en répondant à l’un des deux formulaires "
        "ci-dessous. Ils contiennent les mêmes questions."
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Formulaires", 2)
    m2.metric("Sections de questions", 6)
    m3.metric("Plateformes", "Kobo · Google")

    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.markdown("### 🟦 KoboToolbox")
            st.write("Formulaire basé sur le fichier XLSForm `Formulaire_evaluation_Kobo.xlsx`, avec logique conditionnelle.")
            if kobo_url and valid_form_url(kobo_url):
                st.link_button("Répondre au formulaire Kobo", kobo_url, type="primary", use_container_width=True)
            else:
                st.info("Lien Kobo à renseigner via la variable d'environnement `KOBO_FORM_URL`.")

    with col2:
        with st.container(border=True):
            st.markdown("### 🟩 Google Forms")
            st.write("Formulaire accessible en ligne pour tous les testeurs et évaluateurs.")
            if google_url and valid_form_url(google_url):
                st.link_button("Répondre au formulaire Google", google_url, type="primary", use_container_width=True)
            else:
                st.info("Lien Google Forms à renseigner via la variable d'environnement `GOOGLE_FORM_URL`.")
