#!/usr/bin/env python3
"""Mesure la qualité du classement de find_skills.py : ancien score contre nouveau.

Les deux classements tournent sur le même catalogue collecté, avec les requêtes
étiquetées de tests/retrieval_queries.json. Indicateurs par partie (dev ou test) :
MRR@10, P@5, Recall@5, et temps moyen par requête (index compris pour le nouveau).

  python3 tests/eval_find_skills.py                 # partie dev, catalogue installé
  python3 tests/eval_find_skills.py --split test    # partie test : à ne regarder qu'à la fin
  python3 tests/eval_find_skills.py --root ~/autres/skills --details

Les étiquettes décrivent le catalogue de l'auteur. Sans ce catalogue (dépôt public,
intégration continue), le script le signale et s'arrête sans erreur.
"""

import argparse
import importlib.util
import json
import sys
import time
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "plugins/skill-orchestrator/skills/skill-orchestrator/scripts/find_skills.py"
QUERIES = Path(__file__).resolve().parent / "retrieval_queries.json"


def load_module():
    spec = importlib.util.spec_from_file_location("find_skills", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Ancien classement, recopié tel quel (sous-chaînes, sans découpage en mots) ---

def fold(text):
    """Minuscules sans accents, pour comparer « présentation » et « presentation »."""
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in normalized if not unicodedata.combining(c))


def legacy_score(skill, keywords):
    name, desc = fold(skill["name"]), fold(skill["description"])
    total, matched = 0, 0
    for keyword in keywords:
        hit = False
        if keyword in name:
            total += 3
            hit = True
        count = desc.count(keyword)
        if count:
            total += min(count, 3)
            hit = True
        matched += hit
    if keywords and matched == len(keywords) and len(keywords) > 1:
        total += 2
    return total


def legacy_rank(skills, keywords):
    """Comme l'ancien main() : tri stable par score décroissant, ordre du disque à égalité."""
    keywords = [fold(k) for k in keywords if k.strip()]
    ranked = [(legacy_score(s, keywords), s) for s in skills]
    return [s for value, s in sorted(ranked, key=lambda item: -item[0]) if value > 0]


# --- Indicateurs ---

def metrics(results, relevant):
    names = [s["name"] for s in results]
    first = next((i + 1 for i, n in enumerate(names[:10]) if n in relevant), None)
    top5 = names[:5]
    return {
        "mrr": 1.0 / first if first else 0.0,
        "p5": sum(n in relevant for n in top5) / 5,
        "r5": len(set(top5) & relevant) / len(relevant),
    }


def evaluate(queries, rankers, details, available):
    """Indicateurs moyens par classement ; seuls comptent les skills étiquetés présents."""
    table = {}
    for label, ranker in rankers:
        sums, elapsed = {"mrr": 0.0, "p5": 0.0, "r5": 0.0}, 0.0
        for query in queries:
            keywords = query["query"].split()
            start = time.perf_counter()
            results = ranker(keywords)
            elapsed += time.perf_counter() - start
            scores = metrics(results, set(query["relevant"]) & available)
            for key in sums:
                sums[key] += scores[key]
            if details:
                top = ", ".join(s["name"] for s in results[:5]) or "(rien)"
                print(f"  [{label}] {query['query']!r}  MRR={scores['mrr']:.2f}  -> {top}")
        n = len(queries)
        table[label] = {key: value / n for key, value in sums.items()}
        table[label]["ms"] = 1000 * elapsed / n
    return table


def main():
    parser = argparse.ArgumentParser(description="Évalue le classement de find_skills.py.")
    parser.add_argument("--root", action="append", default=[],
                        help="dossier de skills à évaluer (remplace les dossiers par défaut)")
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev",
                        help="partie des requêtes (défaut dev ; test seulement pour le bilan final)")
    parser.add_argument("--queries", default=str(QUERIES), help="fichier des requêtes étiquetées")
    parser.add_argument("--details", action="store_true", help="afficher les 5 premiers résultats par requête")
    args = parser.parse_args()

    fs = load_module()
    roots = [(Path(r).expanduser(), "extra") for r in args.root] if args.root else fs.default_roots()
    skills = fs.collect(roots)
    data = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    splits = ["dev", "test"] if args.split == "all" else [args.split]

    labelled = {n for split in splits for q in data[split] for n in q["relevant"]}
    present = labelled & {s["name"] for s in skills}
    if not present:
        print(f"Aucun catalogue réel trouvé ({len(skills)} skills, aucun skill étiqueté) : "
              "évaluation sans objet, rien à mesurer.")
        return 0
    if len(present) < len(labelled):
        missing = ", ".join(sorted(labelled - present))
        print(f"Skill(s) étiqueté(s) absent(s) du catalogue, ignoré(s) dans les calculs : {missing}")

    start = time.perf_counter()
    index = fs.Index(skills)
    index_ms = 1000 * (time.perf_counter() - start)
    rankers = [
        ("ancien", lambda kw: legacy_rank(skills, kw)),
        ("nouveau", lambda kw: [s for _, s in fs.rank(skills, kw)]),
    ]
    print(f"Catalogue : {len(skills)} skills ; index du nouveau classement : {index_ms:.1f} ms "
          "(reconstruit à chaque requête, compris dans les temps ci-dessous).")
    del index
    for split in splits:
        # Requête dont aucun skill étiqueté n'est installé : sans objet.
        queries = [q for q in data[split] if set(q["relevant"]) & present]
        print(f"\nPartie {split} ({len(queries)} requêtes)")
        table = evaluate(queries, rankers, args.details, present)
        print(f"  {'':10}{'MRR@10':>8}{'P@5':>8}{'R@5':>8}{'ms/req':>9}")
        for label, row in table.items():
            print(f"  {label:10}{row['mrr']:8.3f}{row['p5']:8.3f}{row['r5']:8.3f}{row['ms']:9.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
