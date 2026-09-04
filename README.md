# Comparateur marchés publics / BDC

Ce dépôt compare les rapports `resultats.json` produits par les deux veilles :

- `mdfertat-lang/veille-bon-de-commande-maroc`
- `mdfertat-lang/veille-marches-publics-maroc`

## Fonctionnement

`comparer.py` récupère, pour chaque dépôt source :

1. le dernier `resultats.json` de J ;
2. le dernier `resultats.json` de J-1 ;
3. compare les annonces à partir de leur champ `Référence` ;
4. conserve uniquement les annonces présentes en J et absentes en J-1.

Le résultat est écrit dans `nouveautes.json`, séparément pour les BDC et les marchés publics.

## Exécution automatique

Le workflow `.github/workflows/comparer.yml` peut être lancé manuellement ou automatiquement chaque jour.

Le secret GitHub `SOURCES_TOKEN` doit contenir un token ayant au minimum un accès **Contents: Read** aux deux dépôts sources privés.

Le workflow du comparateur utilise ensuite son propre `GITHUB_TOKEN` pour publier `nouveautes.json` dans ce dépôt.

## Exécution locale

PowerShell :

```powershell
$env:GITHUB_TOKEN="votre_token"
python comparer.py
```

Le token n'est pas stocké dans le dépôt.
