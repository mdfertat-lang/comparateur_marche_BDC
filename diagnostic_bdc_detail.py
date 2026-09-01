import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.marchespublics.gov.ma/bdc/entreprise/consultation/show/370721"


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="fr-FR")
        page.set_default_timeout(15000)

        print("=" * 70)
        print("DIAGNOSTIC CIBLE — FICHE BDC SIDI BENNOUR")
        print("=" * 70)
        print("URL :", URL)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError as exc:
            print("TIMEOUT DE NAVIGATION :", repr(exc))
            print("URL après timeout :", page.url)

        print("URL finale :", page.url)
        print("Titre :", clean(page.title()))

        body = page.locator("body").inner_text(timeout=15000)
        lines = [clean(x) for x in body.splitlines() if clean(x)]

        print("\n--- TEXTE VISIBLE AVEC NUMÉROS DE LIGNE ---")
        for i, line in enumerate(lines, 1):
            print(f"{i:03d} | {line}")

        print("\n--- ÉLÉMENTS CONTENANT LES LIBELLÉS ---")
        labels = [
            "OBJET",
            "Acheteur public",
            "Date mise en ligne",
            "Date limite de réception des devis",
            "Lieu d'exécution",
        ]
        for label in labels:
            print(f"\n### {label}")
            loc = page.get_by_text(label, exact=False)
            count = min(loc.count(), 10)
            print("Occurrences :", loc.count())
            for i in range(count):
                el = loc.nth(i)
                try:
                    print("TEXT :", clean(el.inner_text()))
                    print("TAG  :", el.evaluate("e => e.tagName"))
                    print("CLASS:", el.get_attribute("class"))
                    print("HTML :", clean(el.evaluate("e => e.outerHTML"))[:2500])
                    parent = el.locator("xpath=..").first
                    print("PARENT HTML :", clean(parent.evaluate("e => e.outerHTML"))[:4000])
                except Exception as exc:
                    print("LECTURE ELEMENT IMPOSSIBLE :", repr(exc))

        print("\n--- TITRE / MÉTADONNÉES ---")
        print("TITLE :", clean(page.title()))
        for selector in ["h1", "h2", "h3", "h4", "meta", "time"]:
            loc = page.locator(selector)
            print(f"SELECTOR {selector} : {loc.count()} élément(s)")
            for i in range(min(loc.count(), 20)):
                el = loc.nth(i)
                try:
                    print(clean(el.evaluate("e => e.outerHTML"))[:2500])
                except Exception:
                    pass

        print("\nFIN DU DIAGNOSTIC CIBLE")
        browser.close()


if __name__ == "__main__":
    main()
