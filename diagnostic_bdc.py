import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
KEYWORD = "scientifique"
DETAIL_LINK = "/bdc/entreprise/consultation/show/"


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def visible_text(page):
    return page.locator("body").inner_text(timeout=15000)


def report_page_structure(page, title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("URL finale :", page.url)
    print("Titre :", clean_text(page.title()))

    text = visible_text(page)
    result_match = re.search(r"Nombre de résultats\s*:\s*(\d+)", text, re.I)
    print("Nombre de résultats affiché :", result_match.group(1) if result_match else "non détecté")

    detail_links = page.locator(f"a[href*='{DETAIL_LINK}']")
    print("Nombre d'annonces visibles sur cette page :", detail_links.count())

    print("\n--- CHAMPS DE RECHERCHE / CONTRÔLES ---")
    inputs = page.locator("input, select, textarea, button")
    for i in range(inputs.count()):
        field = inputs.nth(i)
        tag = field.evaluate("e => e.tagName")
        print(
            f"- {tag}"
            f" name={field.get_attribute('name')}"
            f" id={field.get_attribute('id')}"
            f" type={field.get_attribute('type')}"
            f" value={field.get_attribute('value')}"
            f" aria-label={field.get_attribute('aria-label')}"
            f" text={clean_text(field.inner_text())[:100]}"
        )

    print("\n--- PAGINATION ---")
    links = page.locator("a")
    found = set()
    for i in range(links.count()):
        a = links.nth(i)
        text_value = clean_text(a.inner_text())
        href = a.get_attribute("href") or ""
        if (
            text_value in {"Précédent", "Suivant", "…"}
            or text_value.isdigit()
            or "page" in href.lower()
        ):
            item = (text_value, href)
            if item not in found:
                found.add(item)
                print(f"- {text_value!r} -> {href}")


def find_keyword_input(page):
    try:
        loc = page.get_by_label("Recherche par mot clé", exact=True)
        if loc.count() > 0:
            return loc.first
    except Exception:
        pass

    inputs = page.locator("input")
    for i in range(inputs.count()):
        inp = inputs.nth(i)
        attrs = " ".join(
            str(inp.get_attribute(x) or "")
            for x in ("name", "id", "placeholder", "aria-label")
        ).lower()
        if any(word in attrs for word in ("mot", "keyword", "search", "recherche")):
            return inp
    return None


def click_search(page):
    candidates = [
        page.get_by_role("button", name=re.compile("Lancer la recherche", re.I)),
        page.get_by_text("Lancer la recherche", exact=True),
        page.locator("input[type='submit']"),
        page.locator("button[type='submit']"),
    ]
    for locator in candidates:
        try:
            if locator.count() > 0:
                locator.first.click()
                return True
        except Exception:
            continue
    return False


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(20000)

        print("Accès à :", URL)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        report_page_structure(page, "ÉTAPE 1 — LECTURE DE LA PAGE BDC")

        print("\n" + "=" * 70)
        print(f"ÉTAPE 2 — TEST DE RECHERCHE : {KEYWORD}")
        print("=" * 70)

        keyword_input = find_keyword_input(page)
        if keyword_input is None:
            print("ERREUR : impossible d'identifier le champ 'Recherche par mot clé'.")
            browser.close()
            raise SystemExit(2)

        print("Champ identifié :")
        print("  name=", keyword_input.get_attribute("name"))
        print("  id=", keyword_input.get_attribute("id"))
        print("  placeholder=", keyword_input.get_attribute("placeholder"))

        keyword_input.fill(KEYWORD)
        print("Mot saisi :", KEYWORD)

        if not click_search(page):
            print("ERREUR : impossible de trouver 'Lancer la recherche'.")
            browser.close()
            raise SystemExit(3)

        try:
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(2500)

        # On ne lit ni ne sauvegarde le contenu des annonces individuellement.
        # On rapporte uniquement ce que le navigateur arrive à voir au niveau
        # de la structure de la page : compteur, nombre de cartes, pagination,
        # champs et URL résultante.
        report_page_structure(page, f"RÉSULTAT DE LA RECHERCHE — {KEYWORD}")

        print("\nFIN DU TEST : aucune annonce n'a été extraite individuellement.")
        browser.close()


if __name__ == "__main__":
    main()
