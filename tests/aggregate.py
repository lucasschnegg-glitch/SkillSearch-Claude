#!/usr/bin/env python3
"""Synthèse des passages de run_evals.py : taux de réussite par cas et par bras, avec intervalles.

Usage :
  python3 tests/aggregate.py [racine] [--model M] [--split dev|heldout|all] [--json fichier|-]
                             [--recheck] [--include-legacy] [--lift full:baseline ...]

Lit <racine>/<modèle>/<bras>/run<i>/summary.json (défaut : tests/results). Pour chaque cas et chaque bras :
réussites / passages valides, taux avec intervalle de Wilson à 95 %, coût moyen, tours moyens, skills
invoqués (outil Skill, hors skill-orchestrator), recherches de catalogue. Les erreurs d'infrastructure
sont exclues des dénominateurs et comptées à part. L'écart (lift) full − baseline par cas est donné avec
l'intervalle de Newcombe (différence de deux proportions).

Les anciens résumés sans meta.json (results/opus/summary.json...) ne sont lus qu'avec --include-legacy,
comme bras « full » : ils ont été jugés avec les anciens critères.
"""

import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_results as checker  # noqa: E402

Z95 = 1.959963984540054


def wilson(k, n, z=Z95):
    if n == 0:
        return None, None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe(k1, n1, k2, n2, z=Z95):
    """Intervalle hybride de Newcombe (méthode 10) pour p1 − p2."""
    if not n1 or not n2:
        return None, None, None
    p1, p2 = k1 / n1, k2 / n2
    l1, u1 = wilson(k1, n1, z)
    l2, u2 = wilson(k2, n2, z)
    d = p1 - p2
    return d, d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def entry_status(e):
    if e.get("status") in ("pass", "fail", "infra"):
        return e["status"]
    return "pass" if e.get("ok") else "fail"  # ancien format


def invoked_count(e):
    if "useful_skills_invoked" in e:
        return e["useful_skills_invoked"]
    names = [s for s in e.get("skills_loaded") or [] if not s.endswith(" (lu)")]
    return len(checker.useful(names))


def collect(root, include_legacy=False, recheck=False):
    """Liste de résumés enrichis (modèle, bras, passage) et liste des dossiers anciens ignorés."""
    root = Path(root)
    if recheck:
        for d in checker.run_dirs(root):
            checker.check_run_dir(d, quiet=True)
    entries, legacy = [], []
    for summary in sorted(root.rglob("summary.json")):
        run_dir = summary.parent
        meta = checker.read_meta(run_dir)
        try:
            items = json.loads(summary.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if not meta and re.fullmatch(r"run\d+", run_dir.name) and run_dir.parent.name in checker.ARMS:
            # Dossier publié sans meta.json (non versionné : chemins de la machine) : la
            # disposition <modèle>/<bras>/run<i> suffit à retrouver le passage.
            meta = {"model": run_dir.parent.parent.name, "arm": run_dir.parent.name, "run": int(run_dir.name[3:])}
        if not meta:
            if not include_legacy:
                legacy.append(str(run_dir))
                continue
            meta = {"model": run_dir.name, "arm": "full", "run": "ancien"}
        for e in items:
            e = dict(e)
            e["model"] = meta.get("model") or e.get("model")
            e["arm"] = meta.get("arm") or e.get("arm") or "full"
            e["run"] = meta.get("run", e.get("run"))
            e["status"] = entry_status(e)
            entries.append(e)
    return entries, legacy


def cell_stats(items):
    valid = [e for e in items if e["status"] != "infra"]
    k = sum(1 for e in valid if e["status"] == "pass")
    lo, hi = wilson(k, len(valid))
    infra = {}
    for e in items:
        if e["status"] == "infra":
            kind = (e.get("infra") or {}).get("kind", "?")
            infra[kind] = infra.get(kind, 0) + 1
    return {"passes": k, "valid": len(valid), "runs": len(items), "infra": infra,
            "rate": k / len(valid) if valid else None, "wilson95": [lo, hi],
            "cost_usd": mean([e.get("cost_usd") for e in valid]), "turns": mean([e.get("turns") for e in valid]),
            "skills_invoked": mean([invoked_count(e) for e in valid]),
            "catalog_searches": mean([e.get("catalog_searches") for e in valid]),
            "versions": sorted({json.dumps(e.get("version"), sort_keys=True) for e in items if e.get("version")})}


def aggregate(entries, split="all", lifts=(("full", "baseline"),), case_order=None):
    cases = {c["id"]: c for c in checker.load_cases()}
    order = case_order or list(cases)
    result = {}
    for model in sorted({e["model"] or "?" for e in entries}):
        rows = [e for e in entries if (e["model"] or "?") == model]
        for e in rows:
            e["split"] = cases.get(e["id"], {}).get("split", e.get("split", "dev"))
        if split != "all":
            rows = [e for e in rows if e["split"] == split]
        arms = [a for a in checker.ARMS if any(e["arm"] == a for e in rows)]
        ids = [i for i in order if any(e["id"] == i for e in rows)] + \
            sorted({e["id"] for e in rows} - set(order))
        cells = []
        for cid in ids:
            for arm in arms:
                items = [e for e in rows if e["id"] == cid and e["arm"] == arm]
                if items:
                    cells.append({"case": cid, "split": cases.get(cid, {}).get("split", "dev"), "arm": arm,
                                  **cell_stats(items)})
        totals = []
        for part in ("dev", "heldout", "all"):
            for arm in arms:
                items = [e for e in rows if e["arm"] == arm and (part == "all" or e["split"] == part)]
                if not items:
                    continue
                stats = cell_stats(items)
                rates = [c["rate"] for c in cells if c["arm"] == arm and c["rate"] is not None
                         and (part == "all" or c["split"] == part)]
                stats["mean_case_rate"] = mean(rates)
                totals.append({"split": part, "arm": arm, **stats})
        lift_rows = []
        for a, b in lifts:
            for cid in ids + ["(total)"]:
                ca = [c for c in (totals if cid == "(total)" else cells)
                      if c["arm"] == a and (c.get("case") == cid or (cid == "(total)" and c["split"] == split))]
                cb = [c for c in (totals if cid == "(total)" else cells)
                      if c["arm"] == b and (c.get("case") == cid or (cid == "(total)" and c["split"] == split))]
                if ca and cb and ca[0]["valid"] and cb[0]["valid"]:
                    d, lo, hi = newcombe(ca[0]["passes"], ca[0]["valid"], cb[0]["passes"], cb[0]["valid"])
                    lift_rows.append({"case": cid, "a": a, "b": b, "lift": d, "newcombe95": [lo, hi],
                                      "a_rate": ca[0]["rate"], "b_rate": cb[0]["rate"],
                                      "n": [ca[0]["valid"], cb[0]["valid"]]})
        infra = [{"case": e["id"], "arm": e["arm"], "run": e["run"], **(e.get("infra") or {})}
                 for e in rows if e["status"] == "infra"]
        failures = {}
        for e in rows:
            if e["status"] == "fail":
                for r in e.get("checks") or []:
                    if not r.get("ok"):
                        key = f"{e['id']} [{e['arm']}] {r.get('critere')}"
                        failures[key] = failures.get(key, 0) + 1
        result[model] = {"arms": arms, "cells": cells, "totals": totals, "lift": lift_rows, "infra": infra,
                         "failed_criteria": dict(sorted(failures.items(), key=lambda kv: -kv[1]))}
    return result


def pct(x):
    return "–" if x is None else f"{100 * x:.0f}"


def fmt(x, digits=2):
    return "–" if x is None else f"{x:.{digits}f}"


def interval(pair):
    lo, hi = pair
    return "–" if lo is None else f"[{pct(lo)}–{pct(hi)}]"


def markdown(result, split):
    lines = []
    for model, data in result.items():
        lines.append(f"## {model} (cas : {split})\n")
        lines.append("| Cas | Split | Bras | Réussis / valides | Taux % [IC 95 %] | Infra | Coût $ | Tours | Skills invoqués | Recherches catalogue |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for c in data["cells"]:
            infra = ", ".join(f"{k} {v}" for k, v in c["infra"].items()) or "0"
            lines.append(f"| `{c['case']}` | {c['split']} | {c['arm']} | {c['passes']}/{c['valid']} | "
                         f"{pct(c['rate'])} {interval(c['wilson95'])} | {infra} | {fmt(c['cost_usd'])} | "
                         f"{fmt(c['turns'], 1)} | {fmt(c['skills_invoked'], 1)} | {fmt(c['catalog_searches'], 1)} |")
        lines.append("\n**Totaux par bras** (taux groupé sur toutes les sessions valides ; « moyenne des cas » = "
                     "moyenne non pondérée des taux par cas)\n")
        lines.append("| Split | Bras | Réussis / valides | Taux % [IC 95 %] | Moyenne des cas % | Infra | Coût $ moyen | Tours |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for t in data["totals"]:
            infra = sum(t["infra"].values())
            lines.append(f"| {t['split']} | {t['arm']} | {t['passes']}/{t['valid']} | {pct(t['rate'])} "
                         f"{interval(t['wilson95'])} | {pct(t['mean_case_rate'])} | {infra} | {fmt(t['cost_usd'])} | "
                         f"{fmt(t['turns'], 1)} |")
        if data["lift"]:
            lines.append("\n**Écart de taux (lift)**, en points, avec intervalle de Newcombe à 95 % : l'écart est net "
                         "seulement si l'intervalle exclut 0.\n")
            lines.append("| Cas | Comparaison | Taux A % | Taux B % | Lift (pts) [IC 95 %] | n (A, B) |")
            lines.append("|---|---|---|---|---|---|")
            for r in data["lift"]:
                lo, hi = r["newcombe95"]
                lines.append(f"| `{r['case']}` | {r['a']} − {r['b']} | {pct(r['a_rate'])} | {pct(r['b_rate'])} | "
                             f"{100 * r['lift']:+.0f} [{100 * lo:+.0f} ; {100 * hi:+.0f}] | {r['n'][0]}, {r['n'][1]} |")
        if data["infra"]:
            lines.append(f"\n**Erreurs d'infrastructure** ({len(data['infra'])}, exclues des taux)\n")
            for i in data["infra"]:
                lines.append(f"- `{i['case']}` [{i['arm']}/run{i['run']}] {i.get('kind')} : {str(i.get('detail', ''))[:120]}")
        mixed = [c for c in data["cells"] if len(c["versions"]) > 1]
        if mixed:
            lines.append("\nAttention : plusieurs versions du plugin ou des instructions mélangées dans "
                         + ", ".join(f"`{c['case']}` [{c['arm']}]" for c in mixed[:8]) + ".")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="Synthèse des passages de run_evals.py (Markdown et JSON).")
    p.add_argument("racine", nargs="?", default=str(HERE / "results"))
    p.add_argument("--model", help="ne garder que ce modèle (nom du dossier)")
    p.add_argument("--split", choices=["dev", "heldout", "all"], default="all")
    p.add_argument("--json", help="écrire le JSON dans ce fichier (« - » : sur la sortie standard, sans Markdown)")
    p.add_argument("--recheck", action="store_true", help="revérifier chaque passage avant la synthèse")
    p.add_argument("--include-legacy", action="store_true", help="lire aussi les anciens summary.json sans meta.json")
    p.add_argument("--lift", action="append", help="comparaison A:B (défaut : full:baseline), répétable")
    args = p.parse_args(argv)
    lifts = [tuple(x.split(":", 1)) for x in (args.lift or ["full:baseline"])]
    entries, legacy = collect(args.racine, args.include_legacy, args.recheck)
    if args.model:
        entries = [e for e in entries if e["model"] == args.model or checker.short_name(e["model"] or "") == args.model]
    result = aggregate(entries, args.split, lifts)
    if args.json == "-":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(markdown(result, args.split) if result else "Aucun résultat.")
    if legacy:
        print(f"Anciens résumés ignorés (sans meta.json, critères d'avant) : {', '.join(legacy)} ; "
              "--include-legacy pour les lire.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:  # sortie coupée (| head)
        sys.stdout = open(os.devnull, "w")
        sys.exit(0)
