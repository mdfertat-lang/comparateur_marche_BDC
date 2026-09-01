import re
from collections import Counter
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
KEYWORD = "scientifique"
DETAIL_LINK = "/bdc/entreprise/consultation/show/"


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def visible_text(page):
    return page.locator("body").inner_text(timeout=15000)


def unique_detail_hrefs(page):
    links = page.locator(f"a[href*='{DETAIL_LINK}']")
    hrefs = []
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        if href:
            hrefs.append(urljoin(page.url, href))
    return list(dict.fromkeys(hrefs)), hrefs


def report_page(page, title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("URL :", page.url)
    print("Titre :", clean_text(page.title()))
    text = visible_text(page)
    m = re.search(r"Nombre de résultats\s*:?\s*(\d+)", text, re.I)
    print("Nombre de résultats affiché :", m.group(1) if m else "non détecté")
    unique, all_hrefs = unique_detail_hrefs(page)
    distribution = Counter(Counter(all_hrefs).values())
    print("Liens de fiches dans le DOM :", len(all_hrefs))
    print("Annonces DISTINCTES détectées :", len(unique))
    print("Copies supplémentaires dans le DOM :", len(all_hrefs) - len(unique))
    print("Répartition des copies :", dict(sorted(distribution.items())))
    print("\n--- LIENS DISTINCTS DES ANNONCES DE CETTE PAGE ---")
    for i, href in enumerate(unique, 1):
        print(f"{i}. {href}")
    return unique


def find_keyword_input(page):
    loc = page.locator("#search_consultation_entreprise_keyword")
    return loc.first if loc.count() else None


def submit_search(page):
    # Le diagnostic ne dépend plus du texte du bouton. On soumet le formulaire
    # directement, comme le fait le portail, après avoir rempli le champ keyword.
    form = page.locator("form").filter(has=page.locator("#search_consultation_entreprise_keyword")).first
    if form.count():
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                form.evaluate("form => form.submit()")
            return True
        except PlaywrightTimeoutError:
            return True
    # Secours : appuyer sur Entrée dans le champ.
    try:
        page.locator("#search_consultation_entreprise_keyword").press("Enter")
        return True
    except Exception:
        return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        report_page(page, "ÉTAPE 1 — PAGE BDC INITIALE")

        keyword_input = find_keyword_input(page)
        if keyword_input is None:
            raise SystemExit("Champ de recherche introuvable")
        keyword_input.fill(KEYWORD)
        if not submit_search(page):
            raise SystemExit("Impossible de soumettre la recherche")
        page.wait_for_timeout(2500)

        page1 = report_page(page, f"ÉTAPE 2 — {KEYWORD.upper()} — PAGE 1")

        # Le portail fournit directement le lien vers la page 2 avec tous les
        # paramètres de recherche. On le suit sans reconstruire l'URL.
        next_page = page.locator("a[href*='page=2']").last
        if next_page.count():
            href2 = next_page.get_attribute("href")
            page2_url = urljoin(page.url, href2)
            print("\nURL PAGE 2 :", page2_url)
            page.goto(page2_url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            page2 = report_page(page, f"ÉTAPE 3 — {KEYWORD.upper()} — PAGE 2")
        else:
            print("\nImpossible de trouver le lien vers la page 2.")
            page2 = []

        overlap = sorted(set(page1) & set(page2))
        print("\n" + "=" * 70)
        print("ÉTAPE 4 — COMPARAISON PAGE 1 / PAGE 2")
        print("=" * 70)
        print("Annonces distinctes page 1 :", len(page1))
        print("Annonces distinctes page 2 :", len(page2))
        print("Annonces communes aux deux pages :", len(overlap))
        if overlap:
            print("ATTENTION : les mêmes fiches apparaissent sur les deux pages :")
            for href in overlap:
                print("-", href)
        else:
            print("OK : aucune fiche commune entre les deux premières pages.")

        print("\nFIN DU DIAGNOSTIC : aucune fiche n'a été ouverte ni son contenu métier extrait.")
        browser.close()


if __name__ == "__main__":
    main()
