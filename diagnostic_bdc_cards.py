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
    hrefs = []
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        if href:
            hrefs.append(urljoin(page.url, href))
    return list(dict.fromkeys(hrefs)), hrefs


def inspect_link(page, href):
    link = page.locator(f"a[href='{href.replace(page.url, '')}']")
    if not link.count():
        link = page.locator(f"a[href*='{href.split('/')[-1]}']")
    if not link.count():
        return None
    el = link.first
    # Le lien est répété plusieurs fois dans chaque carte. On remonte
    # jusqu'au premier conteneur suffisamment riche en texte.
    current = el
    for _ in range(8):
        txt = clean(current.inner_text())
        if len(txt) >= 80:
            return txt, clean(current.evaluate("e => e.outerHTML"))[:8000]
        current = current.locator("xpath=..").first
    return clean(el.inner_text()), clean(el.evaluate("e => e.outerHTML"))[:8000]


def extract_from_card(text):
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
    for i, line in enumerate(lines):
        for label in labels:
            if line.lower() == label.lower() or line.lower().startswith(label.lower() + " :"):
                value = clean(re.sub(rf"^{re.escape(label)}\s*:?\s*", "", line, flags=re.I))
                if not value and i + 1 < len(lines):
                    value = lines[i + 1]
                if value:
                    out[label] = value
    # Fallback: référence souvent présente dans le texte du lien/titre.
    if "Référence" not in out:
        m = re.search(r"#([A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ./_\- ]{1,100})", text)
        if m:
            out["Référence"] = clean(m.group(1))
    return out


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
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

        print("=" * 80)
        print("DIAGNOSTIC BDC — EXTRACTION DIRECTE DES CARTES DE RÉSULTATS")
        print("=" * 80)
        print("Recherche :", KEYWORD)
        print("URL :", page.url)
        body = page.locator("body").inner_text(timeout=15000)
        m = re.search(r"Nombre de résultats\s*:??\s*(\d+)", body, re.I)
        print("Nombre de résultats affiché :", m.group(1) if m else "NON DÉTECTÉ")

        unique, all_hrefs = unique_hrefs(page)
        print("Liens DOM :", len(all_hrefs))
        print("Annonces distinctes :", len(unique))
        print("Duplication DOM :", dict(Counter(all_hrefs)))

        print("\n" + "=" * 80)
        print("10 PREMIÈRES ANNONCES — DONNÉES DE LA CARTE")
        print("=" * 80)
        for i, href in enumerate(unique[:10], 1):
            print(f"\n--- ANNONCE {i}/10 ---")
            print("URL :", href)
            result = inspect_link(page, href)
            if not result:
                print("CARTE INTROUVABLE")
                continue
            text, html = result
            print("TEXTE DE LA CARTE :")
            print(text)
            print("\nCHAMPS INTERPRÉTÉS :")
            fields = extract_from_card(text)
            for key, value in fields.items():
                print(f"{key} = {value}")
            missing = [x for x in ["Référence", "Objet", "Acheteur"] if x not in fields]
            date_ok = any(k in fields for k in ["Date limite de remise des devis", "Date limite de réception des devis"])
            if not date_ok:
                missing.append("Date limite")
            print("MANQUANTS :", ", ".join(missing) if missing else "AUCUN")
            print("\nHTML DU CONTENEUR :")
            print(html)

        print("\nFIN DU DIAGNOSTIC")
        browser.close()


if __name__ == "__main__":
    main()
