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
    # Soumission directe du formulaire, sans dépendre du texte du bouton.
    form = page.locator("form").filter(has=page.locator("#search_consultation_entreprise_keyword")).first
    if form.count():
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                form.evaluate("form => form.submit()")
            return True
        except PlaywrightTimeoutError:
            return True
    try:
        page.locator("#search_consultation_entreprise_keyword").press("Enter")
        return True
    except Exception:
        return False


def extract_labeled_field(text, label):
    """Extrait une valeur située après un libellé, même si le texte est sur la ligne suivante."""
    lines = [clean_text(x) for x in text.splitlines()]
    lines = [x for x in lines if x]
    label_re = re.compile(rf"^{re.escape(label)}\s*:??\s*(.*)$", re.I)
    for i, line in enumerate(lines):
        m = label_re.match(line)
        if m:
            value = clean_text(m.group(1))
            if value:
                return value
            if i + 1 < len(lines):
                return lines[i + 1]
    # Secours si le libellé est noyé dans une ligne plus longue.
    m = re.search(rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:Référence|Objet|Acheteur|Date limite|Date de mise|Lieu|Montant)\s*:|$)", text, re.I)
    return clean_text(m.group(1)) if m else "NON DÉTECTÉ"


def extract_date_limite(text):
    patterns = [
        r"Date limite de remise des devis\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})\s*(?:à|a)?\s*(\d{1,2}:\d{2})?",
        r"Date limite\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})\s*(?:à|a)?\s*(\d{1,2}:\d{2})?",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            date = m.group(1)
            heure = m.group(2)
            return f"{date} {heure}" if heure else date
    return "NON DÉTECTÉ"


def read_detail(browser, href, index, total):
    detail = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
    detail.set_default_timeout(20000)
    print("\n" + "-" * 70)
    print(f"FICHE {index}/{total}")
    print("URL :", href)
    try:
        detail.goto(href, wait_until="domcontentloaded", timeout=30000)
        detail.wait_for_timeout(1800)
        text = visible_text(detail)
        print("URL finale :", detail.url)
        print("Titre :", clean_text(detail.title()))
        print("Référence :", extract_labeled_field(text, "Référence"))
        print("Objet :", extract_labeled_field(text, "Objet"))
        print("Acheteur :", extract_labeled_field(text, "Acheteur"))
        print("Date limite :", extract_date_limite(text))

        # Signale les cas où les champs principaux n'ont pas été reconnus.
        missing = []
        if extract_labeled_field(text, "Référence") == "NON DÉTECTÉ":
            missing.append("Référence")
        if extract_labeled_field(text, "Objet") == "NON DÉTECTÉ":
            missing.append("Objet")
        if extract_labeled_field(text, "Acheteur") == "NON DÉTECTÉ":
            missing.append("Acheteur")
        if extract_date_limite(text) == "NON DÉTECTÉ":
            missing.append("Date limite")
        if missing:
            print("ATTENTION — champs non détectés :", ", ".join(missing))
            print("--- LIGNES VISIBLES POTENTIELLEMENT UTILES ---")
            for line in [clean_text(x) for x in text.splitlines() if clean_text(x)]:
                if any(word.lower() in line.lower() for word in ["référence", "objet", "acheteur", "date", "limite", "devis", "lieu"]):
                    print(line)
    except Exception as exc:
        print("ERREUR OUVERTURE/LECTURE :", repr(exc))
    finally:
        detail.close()


def inspect_pages(browser, page1, page2):
    print("\n" + "=" * 70)
    print("ÉTAPE 5 — LECTURE DES FICHES D'ANNONCES")
    print("=" * 70)
    print("Objectif : ouvrir chaque fiche et vérifier la lecture de Référence, Objet, Acheteur et Date limite.")

    all_pages = [("PAGE 1", page1), ("PAGE 2", page2)]
    for page_name, links in all_pages:
        print("\n" + "#" * 70)
        print(f"{page_name} — {len(links)} fiche(s) à ouvrir")
        print("#" * 70)
        for i, href in enumerate(links, 1):
            read_detail(browser, href, i, len(links))


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        # La page initiale sert uniquement de contrôle technique.
        report_page(page, "ÉTAPE 1 — PAGE BDC INITIALE (CONTRÔLE TECHNIQUE)")

        keyword_input = find_keyword_input(page)
        if keyword_input is None:
            raise SystemExit("Champ de recherche introuvable")
        keyword_input.fill(KEYWORD)
        if not submit_search(page):
            raise SystemExit("Impossible de soumettre la recherche")
        page.wait_for_timeout(2500)

        page1 = report_page(page, f"ÉTAPE 2 — {KEYWORD.upper()} — PAGE 1")

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

        inspect_pages(browser, page1, page2)

        print("\n" + "=" * 70)
        print("FIN DU DIAGNOSTIC")
        print("=" * 70)
        print("Les annonces des pages 1 et 2 de la recherche 'scientifique' ont été ouvertes individuellement.")
        print("Aucune modification n'a été faite aux dépôts de veille de production.")
        browser.close()


if __name__ == "__main__":
    main()
