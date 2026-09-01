import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/"
KEYWORD = "scientifique"


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def print_page_summary(page, title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)
    print("URL finale :", page.url)
    print("Titre :", clean_text(page.title()))

    body = page.locator("body").inner_text(timeout=15000)
    print("\n--- TEXTE VISIBLE DE LA PAGE ---")
    print(body[:20000])

    print("\n--- FORMULAIRES / CHAMPS DÉTECTÉS ---")
    forms = page.locator("form")
    print("Nombre de formulaires :", forms.count())
    for i in range(forms.count()):
        form = forms.nth(i)
        print(f"Formulaire {i + 1} : action={form.get_attribute('action')} method={form.get_attribute('method')}")
        fields = form.locator("input, select, textarea, button")
        for j in range(min(fields.count(), 100)):
            field = fields.nth(j)
            print(
                f"  - {field.evaluate('(e) => e.tagName')}"
                f" name={field.get_attribute('name')}"
                f" id={field.get_attribute('id')}"
                f" type={field.get_attribute('type')}"
                f" value={field.get_attribute('value')}"
                f" placeholder={field.get_attribute('placeholder')}"
                f" text={clean_text(field.inner_text())[:120]}"
            )

    print("\n--- LIENS DE PAGINATION DÉTECTÉS ---")
    links = page.locator("a")
    pagination = []
    for i in range(links.count()):
        a = links.nth(i)
        text = clean_text(a.inner_text())
        href = a.get_attribute("href") or ""
        if text in {"1", "2", "3", "4", "5", "…", "51", "Suivant", "Précédent"} or "page" in href.lower():
            pagination.append((text, href))
    for text, href in pagination[:50]:
        print(f"  - {text!r} -> {href}")


def find_keyword_input(page):
    # Try the visible label first.
    candidates = [
        page.get_by_label("Recherche par mot clé", exact=True),
        page.locator("input").filter(has=page.locator("")),
    ]
    try:
        loc = candidates[0]
        if loc.count() > 0:
            return loc.first
    except Exception:
        pass

    # Fallback: inspect inputs and choose the first text-like field whose
    # attributes suggest a keyword/search field.
    inputs = page.locator("input")
    for i in range(inputs.count()):
        inp = inputs.nth(i)
        attrs = " ".join(
            str(inp.get_attribute(x) or "")
            for x in ("name", "id", "placeholder", "aria-label")
        ).lower()
        if any(word in attrs for word in ("mot", "keyword", "search", "recherche", "objet")):
            return inp
    return None


def click_search(page):
    # Prefer the button/link containing the exact visible French label.
    for locator in [
        page.get_by_role("button", name=re.compile("Lancer la recherche", re.I)),
        page.get_by_text("Lancer la recherche", exact=True),
        page.locator("input[type='submit']"),
        page.locator("button[type='submit']"),
    ]:
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
        print_page_summary(page, "ÉTAPE 1 — CE QUE LE PROGRAMME ARRIVE À LIRE SUR LA PAGE BDC")

        print("\n" + "=" * 70)
        print(f"ÉTAPE 2 — RECHERCHE DU MOT-CLÉ : {KEYWORD}")
        print("=" * 70)

        keyword_input = find_keyword_input(page)
        if keyword_input is None:
            print("ERREUR : impossible d'identifier le champ 'Recherche par mot clé'.")
            browser.close()
            raise SystemExit(2)

        print("Champ de recherche identifié :")
        print("  name=", keyword_input.get_attribute("name"))
        print("  id=", keyword_input.get_attribute("id"))
        print("  placeholder=", keyword_input.get_attribute("placeholder"))

        keyword_input.fill(KEYWORD)
        print(f"Mot saisi : {KEYWORD}")

        if not click_search(page):
            print("ERREUR : impossible de trouver le bouton 'Lancer la recherche'.")
            browser.close()
            raise SystemExit(3)

        try:
            page.wait_for_load_state("domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError:
            pass
        page.wait_for_timeout(2500)

        print_page_summary(page, f"RÉSULTAT DE LA RECHERCHE — {KEYWORD}")

        # Important : on ne parcourt pas/extrait pas les annonces individuellement.
        # On rapporte seulement ce que la page de résultats rend visible au navigateur.
        body = clean_text(page.locator("body").inner_text(timeout=15000))
        m = re.search(r"Nombre de résultats\s*:\s*(\d+)", body, re.I)
        if m:
            print("\nNOMBRE DE RÉSULTATS AFFICHÉ PAR LE SITE :", m.group(1))
        else:
            print("\nNOMBRE DE RÉSULTATS : non détecté automatiquement")

        print("\nFIN DU DIAGNOSTIC — aucune annonce n'a été extraite individuellement.")
        browser.close()


if __name__ == "__main__":
    main()
