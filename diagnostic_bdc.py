import re
from collections import Counter
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
KEYWORD = "scientifique"
DETAIL_LINK = "/bdc/entreprise/consultation/show/"


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def unique_hrefs(page):
    links = page.locator(f"a[href*='{DETAIL_LINK}']")
    all_hrefs = []
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        if href:
            all_hrefs.append(urljoin(page.url, href))
    return list(dict.fromkeys(all_hrefs)), all_hrefs


def find_card(page, href):
    """Trouve le conteneur de résultat correspondant au lien sans ouvrir la fiche détail."""
    path = href.split(DETAIL_LINK, 1)[-1].strip("/")
    link = page.locator(f"a[href*='{path}']").first
    if not link.count():
        return None

    current = link
    best = None
    for _ in range(10):
        try:
            text = current.inner_text()
            html = current.evaluate("e => e.outerHTML")
            if text and len(clean(text)) >= 80:
                best = (clean(text), html)
                # Une carte doit contenir au moins deux libellés connus.
                known = sum(
                    label.lower() in text.lower()
                    for label in ["référence", "objet", "acheteur", "date limite", "lieu d'exécution"]
                )
                if known >= 2:
                    return best
        except Exception:
            pass
        current = current.locator("xpath=..").first

    return best


def extract_from_card(text):
    """Extrait les champs directement depuis le texte de la carte de résultat."""
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    out = {}

    labels = [
        "Référence",
        "Objet",
        "Acheteur",
        "Date limite de remise des devis",
        "Date limite de réception des devis",
        "Lieu d'exécution",
    ]

    # Cas normal : libellé et valeur sur la même ligne, ou valeur sur la ligne suivante.
    for i, line in enumerate(lines):
        for label in labels:
            pattern = rf"^{re.escape(label)}\s*:?\s*(.*)$"
            m = re.match(pattern, line, re.I)
            if not m:
                continue
            value = clean(m.group(1))
            if not value and i + 1 < len(lines):
                value = lines[i + 1]
            if value:
                out[label] = value

    # Le site peut afficher la référence sous forme de #XXXX sans libellé exploitable.
    if "Référence" not in out:
        m = re.search(r"#\s*([A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ./_\- ]{1,100})", text)
        if m:
            out["Référence"] = clean(m.group(1))

    return out


def report_search(page):
    body = page.locator("body").inner_text(timeout=15000)
    m = re.search(r"Nombre de résultats\s*:?\s*(\d+)", body, re.I)
    unique, all_hrefs = unique_hrefs(page)

    print("Nombre de résultats affiché :", m.group(1) if m else "NON DÉTECTÉ")
    print("Liens DOM :", len(all_hrefs))
    print("Annonces distinctes :", len(unique))
    print("Copies DOM :", len(all_hrefs) - len(unique))
    print("Répartition des copies :", dict(sorted(Counter(all_hrefs).values() and Counter(Counter(all_hrefs).values()).items())))
    return unique


def inspect_cards(page, hrefs, page_name):
    print("\n" + "=" * 80)
    print(f"{page_name} — EXTRACTION DIRECTE DES CARTES")
    print("=" * 80)

    for i, href in enumerate(hrefs, 1):
        print(f"\n--- ANNONCE {i}/{len(hrefs)} ---")
        print("URL :", href)
        result = find_card(page, href)
        if not result:
            print("CARTE INTROUVABLE")
            continue

        text, html = result
        print("TEXTE DE LA CARTE :")
        print(text)

        fields = extract_from_card(text)
        print("\nCHAMPS INTERPRÉTÉS :")
        for key in ["Référence", "Objet", "Acheteur", "Date limite de remise des devis", "Date limite de réception des devis", "Lieu d'exécution"]:
            if key in fields:
                print(f"{key} = {fields[key]}")

        missing = []
        if "Référence" not in fields:
            missing.append("Référence")
        if "Objet" not in fields:
            missing.append("Objet")
        if "Acheteur" not in fields:
            missing.append("Acheteur")
        if not any(k in fields for k in ["Date limite de remise des devis", "Date limite de réception des devis"]):
            missing.append("Date limite")
        print("MANQUANTS :", ", ".join(missing) if missing else "AUCUN")

        # HTML limité au cas où la structure doit encore être corrigée.
        if missing:
            print("\nHTML DU CONTENEUR (pour correction) :")
            print(html[:10000])


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)

            print("=" * 80)
            print("DIAGNOSTIC BDC — EXTRACTION DIRECTE DES CARTES")
            print("=" * 80)
            print("URL initiale :", page.url)

            field = page.locator("#search_consultation_entreprise_keyword")
            if not field.count():
                raise SystemExit("Champ de recherche introuvable")

            field.fill(KEYWORD)
            form = page.locator("form").filter(has=field).first
            try:
                with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
                    form.evaluate("form => form.submit()")
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(2500)

            print("\nRECHERCHE :", KEYWORD)
            print("URL résultat :", page.url)
            page1 = report_search(page)
            inspect_cards(page, page1, "PAGE 1")

            # Vérification de la pagination sans ouvrir les fiches.
            next_page = page.locator("a[href*='page=2']").last
            if next_page.count():
                href2 = next_page.get_attribute("href")
                page2_url = urljoin(page.url, href2)
                print("\nURL PAGE 2 :", page2_url)
                page.goto(page2_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                page2 = report_search(page)
                inspect_cards(page, page2, "PAGE 2")
            else:
                page2 = []
                print("\nLien vers la page 2 introuvable.")

            overlap = sorted(set(page1) & set(page2))
            print("\n" + "=" * 80)
            print("COMPARAISON PAGE 1 / PAGE 2")
            print("=" * 80)
            print("Annonces distinctes page 1 :", len(page1))
            print("Annonces distinctes page 2 :", len(page2))
            print("Annonces communes :", len(overlap))
            if overlap:
                print("ATTENTION :")
                for href in overlap:
                    print("-", href)
            else:
                print("OK : aucune fiche commune.")

            print("\n" + "=" * 80)
            print("FIN DU DIAGNOSTIC")
            print("=" * 80)
            print("Aucune fiche détail n'a été ouverte : l'extraction est faite directement depuis les cartes de résultats.")
            print("Aucun dépôt de production n'a été modifié.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
