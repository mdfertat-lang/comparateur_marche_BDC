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
    unique = list(dict.fromkeys(all_hrefs))
    return unique, all_hrefs


def find_card(page, href):
    """Trouve le conteneur complet de la carte directement dans la page de résultats."""
    path = href.split(DETAIL_LINK, 1)[-1].strip("/")
    link = page.locator(f"a[href*='{path}']").first
    if not link.count():
        return None

    current = link
    for _ in range(10):
        try:
            # La classe entreprise__card identifie directement la carte complète.
            if current.evaluate("e => e.classList.contains('entreprise__card')"):
                return current
        except Exception:
            pass
        current = current.locator("xpath=..").first

    # Fallback : recherche depuis le lien dans les ancêtres.
    current = link
    for _ in range(10):
        try:
            class_attr = current.get_attribute("class") or ""
            if "entreprise__card" in class_attr:
                return current
        except Exception:
            pass
        current = current.locator("xpath=..").first

    return None


def extract_from_card(card):
    """Extrait tous les champs directement depuis une carte BDC, sans ouvrir la fiche détail."""
    out = {
        "Référence": "",
        "Objet": "",
        "Acheteur": "",
        "Date limite de remise des devis": "",
        "Heure": "",
        "Lieu d'exécution": "",
    }

    # ---------------------------------------------------------
    # Référence / Objet / Acheteur
    # ---------------------------------------------------------
    links = card.locator("a.table__links")
    for i in range(links.count()):
        a = links.nth(i)
        text = clean(a.inner_text())

        if text.startswith("Référence :"):
            out["Référence"] = clean(text.split(":", 1)[1])
        elif text.startswith("Objet :"):
            out["Objet"] = clean(text.split(":", 1)[1])
        elif text.startswith("Acheteur :"):
            out["Acheteur"] = clean(text.split(":", 1)[1])

    # ---------------------------------------------------------
    # Date limite / Heure / Lieu
    # ---------------------------------------------------------
    right = card.locator(".entreprise__rightSubCard--top").first
    if right.count():
        spans = right.locator("span")

        for i in range(spans.count()):
            span = spans.nth(i)
            text = clean(span.inner_text())

            # Date : on cible le span contenant l'icône calendrier.
            if span.locator(".fa-calendar").count():
                m = re.search(r"\d{2}/\d{2}/\d{4}", text)
                if m:
                    out["Date limite de remise des devis"] = m.group(0)

            # Heure : on cible le span contenant l'icône horloge.
            elif span.locator(".fa-clock").count():
                m = re.search(r"\d{1,2}:\d{2}", text)
                if m:
                    out["Heure"] = m.group(0)

            # Lieu : le site met la valeur dans data-bs-title.
            elif span.get_attribute("data-bs-title"):
                title = clean(span.get_attribute("data-bs-title"))
                if title:
                    out["Lieu d'exécution"] = title

        # Fallback robuste pour le lieu si data-bs-title n'est pas présent.
        if not out["Lieu d'exécution"]:
            location = right.locator(".fa-location-dot").first
            if location.count():
                parent = location.locator("xpath=ancestor::span[1]")
                if parent.count():
                    text = clean(parent.inner_text())
                    if text:
                        out["Lieu d'exécution"] = text

    if out["Date limite de remise des devis"] and out["Heure"]:
        out["Date limite"] = (
            f"{out['Date limite de remise des devis']} {out['Heure']}"
        )
    else:
        out["Date limite"] = out["Date limite de remise des devis"]

    return out


def report_search(page):
    body = page.locator("body").inner_text(timeout=15000)
    m = re.search(r"Nombre de résultats\s*:?\s*(\d+)", body, re.I)
    unique, all_hrefs = unique_hrefs(page)

    counts = Counter(all_hrefs)
    copy_distribution = Counter(counts.values())

    print("Nombre de résultats affiché :", m.group(1) if m else "NON DÉTECTÉ")
    print("Liens DOM :", len(all_hrefs))
    print("Annonces distinctes :", len(unique))
    print("Copies DOM :", len(all_hrefs) - len(unique))
    print("Répartition des copies :", dict(sorted(copy_distribution.items())))
    return unique


def inspect_cards(page, hrefs, page_name):
    print("\n" + "=" * 80)
    print(f"{page_name} — EXTRACTION DIRECTE DES CARTES")
    print("=" * 80)

    for i, href in enumerate(hrefs, 1):
        print(f"\n--- ANNONCE {i}/{len(hrefs)} ---")
        print("URL :", href)

        card = find_card(page, href)
        if not card:
            print("CARTE INTROUVABLE")
            continue

        fields = extract_from_card(card)

        print("Référence :", fields["Référence"] or "NON DÉTECTÉE")
        print("Objet :", fields["Objet"] or "NON DÉTECTÉ")
        print("Acheteur :", fields["Acheteur"] or "NON DÉTECTÉ")
        print("Date limite de remise des devis :", fields["Date limite de remise des devis"] or "NON DÉTECTÉE")
        print("Heure :", fields["Heure"] or "NON DÉTECTÉE")
        print("Date limite :", fields["Date limite"] or "NON DÉTECTÉE")
        print("Lieu d'exécution :", fields["Lieu d'exécution"] or "NON DÉTECTÉ")

        missing = []
        for key in ["Référence", "Objet", "Acheteur"]:
            if not fields[key]:
                missing.append(key)
        if not fields["Date limite de remise des devis"]:
            missing.append("Date limite")
        if not fields["Heure"]:
            missing.append("Heure")
        if not fields["Lieu d'exécution"]:
            missing.append("Lieu d'exécution")

        print("MANQUANTS :", ", ".join(missing) if missing else "AUCUN")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            locale="fr-FR",
        )
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

            # Vérification de la pagination sans ouvrir les fiches détail.
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
            print("Aucune fiche détail n'a été ouverte : toutes les informations sont extraites directement des cartes de résultats.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
