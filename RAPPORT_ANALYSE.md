# Rapport d'Analyse et Documentation — Projet Data Collection

## 1. Présentation du Projet
Ce projet d'examen individuel porte sur la collecte de données via **Web Scraping** (avec Python et BeautifulSoup), le nettoyage des données, le stockage dans une base de données SQLite (`collecte.db`), le déploiement d'une application interactive **Streamlit**, ainsi que la mise en place de deux formulaires d'évaluation (KoboToolbox et Google Forms).

---

## 2. Sources de Données et Variables Extraites

### 2.1. Books to Scrape (`https://books.toscrape.com/catalogue/page-1.html`)
- **Pagination** : Du catalogue initial jusqu'à la dernière page.
- **Variables extraites** :
  - `V1` : Titre du livre
  - `V2` : Prix (converti en valeur numérique pour analyse)
  - `V3` : Disponibilité (en stock / rupture de stock)
  - `V4` : Nombre de produits sur la page
  - `V5` : Note du produit (One, Two, Three, Four, Five)
  - `V6` : Nombre de reviews
  - `V7` : Description détaillée
  - `V8` : Type de produit (Catégorie)
  - `V9` : Tax

### 2.2. Gaaraas — Annonces Auto Dakar (`https://www.gaaraas.com/fr/users/dakar-auto?page=1`)
- **Pagination** : 100 pages à partir de la page 1.
- **Variables extraites** :
  - `V1` : Marque du véhicule
  - `V2` : Modèle du véhicule
  - `V3` : Année de fabrication
  - `V4` : Prix (nettoyé et converti en numérique)
  - `V5` : Kilométrage
  - `V6` : Type de boîte de vitesses
  - `V7` : Région de vente

### 2.3. Dakar-Auto — Motos (`https://dakar-auto.com/senegal/motos-and-scooters-3`)
- **Variables extraites** : Titre, Prix, Catégorie, Kilométrage, Localisation, Image, URL annonce.

### 2.4. Bulletins Météo (2020 - 2021)
- Extraction de texte à partir de documents PDF locaux (`Bulletins_2020` et `Bulletins_2021`) via PyMuPDF (`fitz`), concaténation, et nettoyage.

---

## 3. Rapport d'Analyse et Explication des Graphiques des Variables

### 3.1. Analyse des Livres (Books to Scrape)
- **Distribution des Prix** : La majorité des ouvrages se concentrent entre 10 £ et 50 £. Le graphique en histogramme ou barre montre une asymétrie positive, indiquant que les livres spécialisés ou rares dépassent les 60 £.
- **Répartition par Note (Étoiles)** : Les notes vont de 1 à 5 étoiles. On observe une distribution relativement homogène, ce qui témoigne d'un échantillon diversifié sans biais excessif de notation.
- **Top Catégories** : Les catégories les plus représentées (ex. *Fiction*, *Travel*, *Mystery*) dominent le catalogue, permettant d'analyser la corrélation entre la catégorie d'un livre, sa notation moyenne et sa tarification.

### 3.2. Analyse Automobile (Gaaraas & Dakar-Auto)
- **Distribution des Prix des Véhicules** : Les prix des annonces automobiles affichent une forte variance, reflétant l'hétérogénéité du parc automobile d'occasion au Sénégal (véhicules utilitaires abordables vs SUV haut de gamme).
- **Marques et Modèles Fréquents** : Les marques asiatiques et européennes (Toyota, Peugeot, Hyundai, Renault) constituent le cœur des annonces.
- **Boîte de Vitesses et Kilométrage** : L'analyse croisée du kilométrage et de la boîte de vitesses (manuelle vs automatique) met en évidence l'âge moyen du parc et la décote observée.

---

## 4. Formulaires d'Évaluation (KoboToolbox & Google Forms)
Les deux formulaires ont été conçus en stricte conformité avec le cahier des charges (`Questions des deux formulaire d_évaluation.pdf`) et structurés en 6 sections :
1. **Section 1 : Informations sur l'évaluateur** (Date, Nom facultatif, Rôle/profession avec logique conditionnelle pour "Autre").
2. **Section 2 : Première impression et interface** (Apparence, ergonomie, clarté).
3. **Section 3 : Fonctionnalités de scraping et données** (Collecte, rapidité, fidélité des données brutes/nettoyées).
4. **Section 4 : Tableau de bord et visualisations** (Pertinence des graphiques, lisibilité des métriques).
5. **Section 5 : Expérience utilisateur globale** (Recommandation, réutilisation).
6. **Section 6 : Suggestions d'amélioration et Note finale** (Points forts, pistes d'amélioration, remerciements).

---

## 5. Conclusion
Le projet atteint tous ses objectifs : le scraping par code utilise exclusivement BeautifulSoup, les données sont nettoyées et stockées dans SQLite, l'application Streamlit offre une navigation fluide avec tableaux de bord et rapports graphiques détaillés, et les formulaires d'évaluation opérationnels sont pleinement intégrés.
