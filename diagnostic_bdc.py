import re
from collections import Counter
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
KEYWORD = "scientifique"
DETAIL_LINK = "/bdc/entreprise/consultation/show/"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def report_page_structure(page, title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("URL finale :", page.url)
    print("Titre :", clean_text(page.title()))

    text = page.locator("body").inner_text(timeout=15000)
    m = re.search(r"Nombre de résultats\s*:?\s*(\d+)", text, re.I)
    print("Nombre de résultats affiché :", m.group(1) if m else "non détecté")

    links = page.locator(f"a[href*='{DETAIL_LINK}']")
    hrefs = []
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href") or ""
        if href:
            hrefs.append(urljoin(page.url, href))
    counts = Counter(hrefs)
    unique_hrefs = list(dict.fromkeys(hrefs))

    print("Liens de fiches détectés dans le DOM :", len(hrefs))
    print("Fiches d'annonces DISTINCTES détectées :", len(unique_hrefs))
    print("Doublons de liens dans le DOM :", sum(v - 1 for v in counts.values() if v > 1))
    if counts:
        print("Distribution des copies d'un même lien :", dict(sorted(Counter(counts.values()).items())))

    print("\n--- STRUCTURE DES BLOCS ---")
    for selector in ["div.card", "article", "li"]:
        loc = page.locator(selector)
        if loc.count():
            print(f"{selector} : {loc.count()} élément(s)")

    print("\n--- CONTENEURS DES LIENS (SANS CONTENU DES ANNONCES) ---")
    seen = set()
    for i in range(min(links.count(), 12)):
        info = links.nth(i).evaluate("""
            e => { const p=[]; let n=e.parentElement;
            for(let i=0;n&&i<5;i++,n=n.parentElement)
              p.push({tag:n.tagName.toLowerCase(),id:n.id||'',cls:n.className||''});
            return p; }
        """)
        key = repr(info)
        if key not in seen:
            seen.add(key)
            print("  ", info)

    print("\n--- CHAMPS / CONTRÔLES ---")
    fields = page.locator("input, select, textarea, button")
    for i in range(fields.count()):
        f = fields.nth(i)
        print(f"- {f.evaluate('e => e.tagName')} name={f.get_attribute('name')} id={f.get_attribute('id')} type={f.get_attribute('type')} value={f.get_attribute('value')} text={clean_text(f.inner_text())[:100]}")

    print("\n--- PAGINATION ---")
    all_links = page.locator("a")
    seen = set()
    for i in range(all_links.count()):
        a = all_links.nth(i)
        t = clean_text(a.inner_text())
        h = a.get_attribute("href") or ""
        if t in {"Précédent", "Suivant", "…"} or t.isdigit() or "page" in h.lower():
            item = (t, h)
            if item not in seen:
                seen.add(item)
                print(f"- {t!r} -> {h}")


def find_keyword_input(page):
    try:
        loc = page.get_by_label("Recherche par mot clé", exact=True)
        if loc.count(): return loc.first
    except Exception: pass
    inputs = page.locator("input")
    for i in range(inputs.count()):
        inp = inputs.nth(i)
        attrs = " ".join(str(inp.get_attribute(x) or "") for x in ("name","id","placeholder","aria-label")).lower()
        if any(w in attrs for w in ("mot","keyword","search","recherche")):
            return inp
    return None


def click_search(page):
    for loc in [
        page.get_by_role("button", name=re.compile("Lancer la recherche", re.I)),
        page.get_by_text("Lancer la recherche", exact=True),
        page.locator("input[type='submit']"),
        page.locator("button[type='submit']")]:
        try:
            if loc.count():
                loc.first.click(); return True
        except Exception: pass
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width":1440,"height":1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        report_page_structure(page, "ÉTAPE 1 — LECTURE DE LA PAGE BDC")

        print("\n" + "=" * 70)
        print(f"ÉTAPE 2 — TEST DE RECHERCHE : {KEYWORD}")
        print("=" * 70)
        inp = find_keyword_input(page)
        if inp is None:
            raise SystemExit("Impossible d'identifier le champ de recherche")
        print("Champ identifié :", inp.get_attribute("name"), inp.get_attribute("id"), inp.get_attribute("placeholder"))
        inp.fill(KEYWORD)
        print("Mot saisi :", KEYWORD)
        if not click_search(page):
            raise SystemExit("Impossible de trouver Lancer la recherche")
        try: page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError: pass
        page.wait_for_timeout(2500)
        report_page_structure(page, f"RÉSULTAT DE LA RECHERCHE — {KEYWORD}")
        print("\nFIN DU TEST : aucune annonce n'a été extraite individuellement.")
        browser.close()

if __name__ == "__main__":
    main()
