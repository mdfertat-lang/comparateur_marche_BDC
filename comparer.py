import json
import os
import smtplib
import unicodedata
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from urllib.parse import quote
from urllib.request import Request, urlopen


SOURCES = {
    "bdc": "mdfertat-lang/veille-bon-de-commande-maroc",
    "marches_publics": "mdfertat-lang/veille-marches-publics-maroc",
}

API = "https://api.github.com"


def github_get(url):
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN ou GH_TOKEN est requis.")

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "comparateur-marche-bdc",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def get_file_from_ref(repo, ref):
    owner, name = repo.split("/", 1)
    path = quote("resultats.json", safe="")
    data = github_get(f"{API}/repos/{owner}/{name}/contents/{path}?ref={quote(ref, safe='')}")
    if data.get("encoding") != "base64":
        raise RuntimeError(f"Format inattendu pour resultats.json dans {repo}@{ref}.")

    import base64
    return json.loads(base64.b64decode(data["content"]).decode("utf-8"))


def get_commit_date(commit):
    return commit.get("commit", {}).get("committer", {}).get("date") or commit.get("commit", {}).get("author", {}).get("date")


def get_resultats_history(repo, max_pages=5):
    owner, name = repo.split("/", 1)
    commits = []

    for page in range(1, max_pages + 1):
        url = (
            f"{API}/repos/{owner}/{name}/commits"
            f"?path=resultats.json&per_page=100&page={page}"
        )
        batch = github_get(url)
        if not batch:
            break
        commits.extend(batch)
        if len(batch) < 100:
            break

    return commits


def find_j_j_minus_1_j_minus_2(repo):
    commits = get_resultats_history(repo)
    if not commits:
        raise RuntimeError(f"Aucun commit trouvé pour resultats.json dans {repo}.")

    today = datetime.now(timezone.utc).date()
    target_dates = {
        today: "j",
        today - timedelta(days=1): "j1",
        today - timedelta(days=2): "j2",
    }
    found = {"j": None, "j1": None, "j2": None}

    for commit in commits:
        value = get_commit_date(commit)
        if not value:
            continue

        date = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        key = target_dates.get(date)

        if key and found[key] is None:
            found[key] = commit

        if all(found.values()):
            break

    labels = {
        "j": f"J ({today})",
        "j1": f"J-1 ({today - timedelta(days=1)})",
        "j2": f"J-2 ({today - timedelta(days=2)})",
    }

    for key, label in labels.items():
        if not found[key]:
            raise RuntimeError(f"Aucun resultats.json correspondant à {label} trouvé dans {repo}.")

    return found["j"], found["j1"], found["j2"]


def get_reference(item):
    """Retourne la référence quel que soit le nom de champ utilisé par la source."""
    for key in ("Référence", "reference", "référence", "Reference"):
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def normalize_reference(value):
    value = str(value or "").strip().upper()
    value = unicodedata.normalize("NFKC", value)
    return " ".join(value.split())


def extract_annonces(report):
    annonces = report.get("annonces", [])
    if not isinstance(annonces, list):
        raise RuntimeError("Le champ 'annonces' de resultats.json n'est pas une liste.")
    return annonces


def compare_reports(current, previous_reports):
    previous_refs = set()

    for report in previous_reports:
        previous_refs.update(
            normalize_reference(get_reference(item))
            for item in extract_annonces(report)
            if normalize_reference(get_reference(item))
        )

    nouvelles = []
    seen = set()

    for item in extract_annonces(current):
        reference = normalize_reference(get_reference(item))
        if not reference or reference in seen:
            continue
        if reference not in previous_refs:
            nouvelles.append(item)
            seen.add(reference)

    return nouvelles


def build_output():
    output = {
        "date_execution": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "comparaison": "J versus J-1 et J-2",
        "bdc": {},
        "marches_publics": {},
    }

    for key, repo in SOURCES.items():
        j_commit, j1_commit, j2_commit = find_j_j_minus_1_j_minus_2(repo)
        current = get_file_from_ref(repo, j_commit["sha"])
        previous_j1 = get_file_from_ref(repo, j1_commit["sha"])
        previous_j2 = get_file_from_ref(repo, j2_commit["sha"])
        nouvelles = compare_reports(current, [previous_j1, previous_j2])

        output[key] = {
            "depot_source": repo,
            "commit_j": j_commit["sha"],
            "date_j": get_commit_date(j_commit),
            "commit_j_moins_1": j1_commit["sha"],
            "date_j_moins_1": get_commit_date(j1_commit),
            "commit_j_moins_2": j2_commit["sha"],
            "date_j_moins_2": get_commit_date(j2_commit),
            "nombre_nouvelles": len(nouvelles),
            "annonces": nouvelles,
        }

    return output


def envoyer_email(output):
    email = "mdfertat@gmail.com"
    mot_de_passe = os.environ["EMAIL_PASSWORD"]
    date_du_jour = datetime.now().strftime("%d/%m/%Y")
    sujet = f"Nouvelles annonces marchés publics et BDC - {date_du_jour}"

    lignes = []
    lignes.append("NOUVELLES ANNONCES — MARCHÉS PUBLICS MAROCAINS")
    lignes.append("=" * 60)
    lignes.append("")
    lignes.append("Comparaison : J versus J-1 et J-2")
    lignes.append("")

    total = output["bdc"]["nombre_nouvelles"] + output["marches_publics"]["nombre_nouvelles"]
    lignes.append(f"Total : {total} nouvelle(s) annonce(s).")
    lignes.append("")

    for key, titre in (("bdc", "BONS DE COMMANDE (BDC)"), ("marches_publics", "MARCHÉS PUBLICS")):
        annonces = output[key]["annonces"]

        lignes.append("=" * 60)
        lignes.append(titre)
        lignes.append("=" * 60)
        lignes.append("")

        if not annonces:
            lignes.append("Aucune nouvelle annonce.")
            lignes.append("")
            continue

        lignes.append(f"{len(annonces)} nouvelle(s) annonce(s).")
        lignes.append("")

        for i, annonce in enumerate(annonces, start=1):
            lignes.append("-" * 60)
            lignes.append(f"ANNONCE {i}")
            lignes.append("-" * 60)

            reference = get_reference(annonce)
            objet = str(annonce.get("objet", "")).replace("Objet :", "").strip()
            acheteur = str(annonce.get("acheteur", "")).replace("Acheteur public :", "").strip()
            lieu = str(annonce.get("lieu", "")).replace("Lieu d'exécution :", "").strip()
            date_limite = annonce.get("date_limite", "")
            mot_cle = annonce.get("mot_cle") or annonce.get("mot_cles", "")

            if isinstance(mot_cle, list):
                mot_cle = ", ".join(str(x) for x in mot_cle)

            lignes.append(f"Référence : {reference}")
            lignes.append(f"Objet : {objet}")
            lignes.append(f"Acheteur public : {acheteur}")
            lignes.append(f"Lieu d'exécution : {lieu}")
            lignes.append(f"Date limite : {date_limite}")
            lignes.append(f"Mot-clé trouvé : {mot_cle}")

            if annonce.get("alerte_date"):
                lignes.append(f"ALERTE : {annonce['alerte_date']}")

            if annonce.get("url"):
                lignes.append(f"Lien : {annonce['url']}")

            lignes.append("")

    contenu = "\n".join(lignes)
    message = MIMEText(contenu, "plain", "utf-8")
    message["Subject"] = sujet
    message["From"] = email
    message["To"] = email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as serveur:
        serveur.login(email, mot_de_passe)
        serveur.send_message(message)

    print("")
    print("========================================")
    print("EMAIL ENVOYÉ")
    print("========================================")
    print("Expéditeur :", email)
    print("Destinataire :", email)


def main():
    output = build_output()

    with open("nouveautes.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print("Comparaison terminée.")
    print("Comparaison : J versus J-1 et J-2")
    print("BDC :", output["bdc"]["nombre_nouvelles"], "nouvelle(s)")
    print("Marchés publics :", output["marches_publics"]["nombre_nouvelles"], "nouvelle(s)")
    print("Fichier créé : nouveautes.json")

    envoyer_email(output)


if __name__ == "__main__":
    main()
