import json
import os
import unicodedata
from datetime import datetime, timedelta, timezone
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

    # Les commits sont renvoyés du plus récent au plus ancien.
    return commits


def find_j_and_j_minus_1(repo):
    commits = get_resultats_history(repo)
    if not commits:
        raise RuntimeError(f"Aucun commit trouvé pour resultats.json dans {repo}.")

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)

    j_commit = None
    j1_commit = None

    for commit in commits:
        value = get_commit_date(commit)
        if not value:
            continue
        date = datetime.fromisoformat(value.replace("Z", "+00:00")).date()

        if date == today and j_commit is None:
            j_commit = commit
        elif date == yesterday and j1_commit is None:
            j1_commit = commit

        if j_commit and j1_commit:
            break

    if not j_commit:
        raise RuntimeError(f"Aucun resultats.json correspondant à J ({today}) trouvé dans {repo}.")
    if not j1_commit:
        raise RuntimeError(f"Aucun resultats.json correspondant à J-1 ({yesterday}) trouvé dans {repo}.")

    return j_commit, j1_commit


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


def compare_reports(current, previous):
    previous_refs = {
        normalize_reference(get_reference(item))
        for item in extract_annonces(previous)
        if normalize_reference(get_reference(item))
    }

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
        "comparaison": "J versus J-1",
        "bdc": {},
        "marches_publics": {},
    }

    for key, repo in SOURCES.items():
        j_commit, j1_commit = find_j_and_j_minus_1(repo)
        current = get_file_from_ref(repo, j_commit["sha"])
        previous = get_file_from_ref(repo, j1_commit["sha"])
        nouvelles = compare_reports(current, previous)

        output[key] = {
            "depot_source": repo,
            "commit_j": j_commit["sha"],
            "date_j": get_commit_date(j_commit),
            "commit_j_moins_1": j1_commit["sha"],
            "date_j_moins_1": get_commit_date(j1_commit),
            "nombre_nouvelles": len(nouvelles),
            "annonces": nouvelles,
        }

    return output


def main():
    output = build_output()

    with open("nouveautes.json", "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print("Comparaison terminée.")
    print("BDC :", output["bdc"]["nombre_nouvelles"], "nouvelle(s)")
    print("Marchés publics :", output["marches_publics"]["nombre_nouvelles"], "nouvelle(s)")
    print("Fichier créé : nouveautes.json")


if __name__ == "__main__":
    main()
