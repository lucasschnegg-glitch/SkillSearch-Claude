#!/usr/bin/env python3
"""Recherche locale dans le catalogue de skills (bibliothèque standard uniquement).

Parcourt les dossiers où Claude Code et Cowork rangent les skills installés,
lit le frontmatter de chaque SKILL.md et classe les skills selon les mots-clés.
Aucun accès réseau, aucune écriture.

Classement : la requête est découpée en mots (minuscules, sans accents), privée
des mots vides français et anglais et ramenée à une forme simple (pluriels, -ing).
Presque toutes les descriptions sont en anglais : chaque mot français est complété
par ses traductions (dictionnaire SYNONYMES, poids plus faible que le mot tapé).
Le score est un BM25 sur deux champs, le nom (pondéré plus fort) et la
description, avec un bonus quand un mot de la requête est un mot du nom ; un
skill qui couvre tous les mots de la requête passe devant celui qui n'en couvre
qu'une partie. À score égal, l'ordre est alphabétique.

Exemples :
  python3 find_skills.py presentation slides pptx
  python3 find_skills.py --all
  python3 find_skills.py --json --limit 5 excel tableau
  python3 find_skills.py --root /chemin/vers/skills docx
"""

import argparse
import functools
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".trash", ".staging", "__pycache__", ".venv", "venv"}
MAX_DEPTH = 8
BLOCK_INDICATORS = (">", ">-", "|", "|-", ">+", "|+")

# Réglages du classement (choisis sur la partie « dev » de tests/retrieval_queries.json).
K1 = 1.2                 # saturation de la fréquence d'un mot
POIDS_NOM, B_NOM = 3.0, 0.5      # le nom compte trois fois plus que la description
POIDS_DESC, B_DESC = 1.0, 0.75
BONUS_NOM = 1.0          # mot de la requête = mot du nom, au prorata de la longueur du nom
POIDS_SYNONYME = 0.6     # traduction ou synonyme ajouté par le dictionnaire
POIDS_FRAGMENT = 0.5     # mot isolé d'une expression (« base » dans « base de données »)
POIDS_SENS_ECARTE = 0.3  # « résumé » pris au sens de synthèse : le sens anglais (CV) pèse peu
PART_SECONDAIRE = 0.3    # d'un même concept, seul le meilleur mot compte en entier
COORDINATION = 0.5       # exposant de la part des concepts trouvés : favorise qui les couvre tous

MOTS_VIDES = frozenset("""
a au aux avec ce ces cet cette d dans de des du elle en est et etre il ils j je l la le les
leur leurs lui m ma mais me mes mon n ne nos notre nous on ou par pas pour qu que qui s sa
sans se ses son sont sur t ta te tes ton tous tout toute toutes tres tu un une vos votre
vous y
an and are as at be by for from how i in into is it its of on or that the their this to
use used using via was what when which with you your
""".split())

# Dictionnaire français → anglais (et quelques équivalences anglaises). Les clés de
# plusieurs mots (« tableau de bord ») sont reconnues dans la requête avant le
# découpage mot à mot. Accents et pluriels sont indifférents.
SYNONYMES = {
    # Documents et bureautique
    "tableur": ["spreadsheet", "xlsx", "excel"],
    "feuille de calcul": ["spreadsheet", "xlsx", "excel"],
    "classeur": ["workbook", "spreadsheet", "xlsx"],
    "excel": ["xlsx", "spreadsheet"],
    "spreadsheet": ["xlsx", "excel"],
    "formule": ["formula"],
    "word": ["docx", "document"],
    "traitement de texte": ["docx", "document"],
    "présentation": ["slides", "pptx", "deck", "powerpoint"],
    "diapositive": ["slides", "pptx", "presentation", "deck"],
    "diapo": ["slides", "pptx", "presentation", "deck"],
    "diaporama": ["slides", "pptx", "presentation", "deck"],
    "powerpoint": ["pptx", "slides", "presentation"],
    "slides": ["pptx", "presentation", "deck"],
    "soutenance": ["defense", "presentation", "thesis"],
    "graphique": ["chart", "plot", "graph", "visualization", "dataviz"],
    "courbe": ["curve", "plot", "chart"],
    "visualisation": ["visualization", "chart", "dataviz"],
    "tableau": ["table", "spreadsheet"],
    "tableau de bord": ["dashboard", "kpi", "metrics"],
    "rapport": ["report"],
    "compte rendu": ["report", "minutes", "summary"],
    "mise en page": ["layout", "formatting"],
    "mise en forme": ["formatting", "styling"],
    "police": ["font", "typography"],
    "modèle": ["template", "model"],
    "fichier": ["file"],
    "dossier": ["folder", "directory"],
    "convertir": ["convert", "conversion"],
    "extraire": ["extract", "extraction"],
    "imprimer": ["print"],
    "télécharger": ["download"],
    "capture d'écran": ["screenshot"],
    "capture écran": ["screenshot"],
    # Rédaction
    "résumé": ["summary", "summarize", "synthesis"],
    "résumer": ["summarize", "summary"],
    "synthèse": ["synthesis", "summary", "summarize"],
    "synthétiser": ["summarize", "synthesis"],
    "summary": ["summarize"],
    "summarize": ["summary"],
    "fiche": ["cheat sheet", "notes", "summary", "flashcards"],
    "fiche de révision": ["cheat sheet", "revision", "study notes", "summary"],
    "lettre de motivation": ["cover letter", "job", "career", "cv"],
    "lettre": ["letter"],
    "cv": ["resume", "career", "job"],
    "candidature": ["job", "career", "apply"],
    "emploi": ["job", "career", "employment"],
    "entretien": ["interview"],
    "relire": ["proofread", "review", "copy editing", "edit"],
    "relecture": ["proofread", "review", "copy editing", "edit"],
    "corriger": ["fix", "correct", "proofread", "edit"],
    "correction": ["fix", "correct", "proofread"],
    "orthographe": ["spelling", "grammar", "proofread"],
    "grammaire": ["grammar", "proofread"],
    "rédiger": ["write", "writing", "draft"],
    "rédaction": ["writing", "write", "draft"],
    "écrire": ["write", "writing"],
    "réécrire": ["rewrite", "edit"],
    "reformuler": ["rewrite", "paraphrase"],
    "traduire": ["translate", "translation"],
    "traduction": ["translation", "translate"],
    "texte": ["text", "prose"],
    "humaniser": ["humanize", "humanizer", "human"],
    "ia": ["ai", "llm"],
    "intelligence artificielle": ["ai", "llm"],
    "bibliographie": ["bibliography", "citation", "references"],
    "référence": ["reference", "citation"],
    "recherche": ["research", "search"],
    "livre": ["book"],
    "lire": ["read", "reading"],
    "lecture": ["reading", "read"],
    "courriel": ["email"],
    "mail": ["email"],
    # Études
    "cours": ["course", "lecture", "study"],
    "chapitre": ["chapter"],
    "examen": ["exam", "quiz", "assessment"],
    "examen blanc": ["mock exam", "practice exam", "exam simulation"],
    "exercice": ["exercise", "practice", "problem"],
    "corrigé": ["solution", "answer"],
    "devoir": ["assignment", "homework"],
    "révision": ["revision", "study", "exam"],
    "réviser": ["study", "revision", "exam"],
    "étudier": ["study", "learn"],
    "étude": ["study", "research"],
    "apprendre": ["learn", "learning", "study"],
    "apprentissage": ["learning"],
    "apprentissage automatique": ["machine learning", "ml"],
    "apprentissage profond": ["deep learning"],
    "réseau de neurones": ["neural network", "deep learning"],
    "mémoire": ["thesis", "dissertation", "memory"],
    "thèse": ["thesis"],
    "enseigner": ["teach"],
    "expliquer": ["explain"],
    "mathématiques": ["math", "mathematics"],
    "maths": ["math"],
    "démonstration": ["proof"],
    "preuve": ["proof"],
    # Statistiques et données
    "statistique": ["statistics", "statistical", "stats"],
    "probabilité": ["probability"],
    "économétrie": ["econometrics"],
    "série temporelle": ["time series", "forecasting"],
    "prévision": ["forecast", "forecasting", "prediction"],
    "prédiction": ["prediction", "forecast"],
    "bayésien": ["bayesian"],
    "bayésienne": ["bayesian"],
    "vraisemblance": ["likelihood"],
    "échantillon": ["sample", "sampling"],
    "hypothèse": ["hypothesis"],
    "données": ["data", "dataset"],
    "base de données": ["database", "sql", "schema"],
    "requête": ["query"],
    "schéma": ["schema", "diagram"],
    "diagramme": ["diagram", "flowchart", "chart"],
    "organigramme": ["flowchart", "org chart", "diagram"],
    "logigramme": ["flowchart"],
    "carte mentale": ["mind map"],
    "processus": ["process", "workflow"],
    "flux": ["flow", "workflow", "pipeline"],
    "comptabilité": ["accounting", "bookkeeping"],
    "facture": ["invoice"],
    "impôt": ["tax"],
    "risque": ["risk"],
    "investissement": ["investment"],
    "bourse": ["stock", "market"],
    "tarification": ["pricing"],
    "prix": ["price", "pricing"],
    # Code et applications
    "test": ["testing"],
    "tester": ["test", "testing"],
    "test unitaire": ["unit test", "pytest", "jest", "tdd"],
    "unitaire": ["unit"],
    "débogage": ["debug", "debugging", "bug"],
    "déboguer": ["debug", "debugging", "bug"],
    "bogue": ["bug", "debug"],
    "erreur": ["error", "bug"],
    "revue de code": ["code review", "pull request", "reviewer"],
    "relecture de code": ["code review", "reviewer"],
    "développement": ["development"],
    "développer": ["develop", "development"],
    "appli": ["app", "application"],
    "logiciel": ["software", "app"],
    "bureau": ["desktop"],
    "application de bureau": ["desktop app", "electron"],
    "site web": ["website", "web", "landing page"],
    "site internet": ["website", "web", "landing page"],
    "page web": ["web page", "website"],
    "page d'accueil": ["landing page", "homepage"],
    "interface": ["ui", "frontend"],
    "interface utilisateur": ["ui", "ux", "user interface", "frontend"],
    "maquette": ["mockup", "wireframe", "prototype"],
    "conception": ["design"],
    "concevoir": ["design"],
    "déployer": ["deploy", "deployment"],
    "déploiement": ["deploy", "deployment"],
    "sécurité": ["security", "audit", "vulnerability"],
    "vulnérabilité": ["vulnerability", "security"],
    "faille": ["vulnerability", "security"],
    "mot de passe": ["password", "secret", "credential"],
    "sauvegarde": ["backup"],
    "automatiser": ["automate", "automation"],
    "automatisation": ["automate", "automation"],
    "planifier": ["plan", "planning", "schedule"],
    "planification": ["plan", "planning", "schedule"],
    "tâche": ["task"],
    "projet": ["project"],
    "outil": ["tool"],
    "gestion": ["management"],
    "réunion": ["meeting"],
    "calendrier": ["calendar", "schedule"],
    "agenda": ["calendar", "schedule"],
    "prise de notes": ["note taking", "notes"],
    "carnet": ["notebook"],
    "cahier": ["notebook"],
    "connaissance": ["knowledge"],
    "graphe": ["graph"],
    "moteur de recherche": ["search engine", "seo"],
    "référencement": ["seo"],
    "réseaux sociaux": ["social media"],
    "publicité": ["ads", "advertising"],
    "marque": ["brand"],
    "couleur": ["color"],
    "créer": ["create", "build", "generate"],
    "générer": ["generate"],
    "nouveau": ["new"],
    "améliorer": ["improve", "optimize"],
    "optimiser": ["optimize"],
    "analyser": ["analyze", "analysis"],
    "analyse": ["analysis", "analyze"],
    "vérifier": ["verify", "check", "validate"],
    "nettoyer": ["clean", "cleanup"],
    "organiser": ["organize"],
    "chercher": ["search", "find"],
    "trouver": ["find"],
    "hors ligne": ["offline", "local"],
    "tablette": ["tablet", "ipad"],
    "téléphone": ["mobile", "phone"],
    "modèle de langage": ["llm", "language model"],
}

# Vocabulaire personnel du propriétaire : ses matières, son domaine, ses outils.
# Format : "mot ou expression en français": ["traduction", "synonyme", ...].
# Ces entrées s'ajoutent à SYNONYMES au chargement (une clé déjà présente reçoit
# les traductions en plus). Exemple de vocabulaire actuariel à ajouter ici :
#   "sinistre": ["claim", "claims"], "provision": ["reserve", "reserving"].
SYNONYMES_PERSONNELS = {}

# « résumé » veut dire synthèse en français et CV en anglais. Le sens anglais est
# gardé si la requête parle d'emploi ; sinon un « résumé » accentué ou entouré de
# vocabulaire d'études est lu comme une synthèse.
CONTEXTE_CV = {"cv", "emploi", "job", "candidature", "poste", "recrutement", "embauche",
               "career", "carriere", "hiring", "linkedin"}
CONTEXTE_SYNTHESE = {"cours", "course", "fiche", "chapitre", "synthese", "texte", "article",
                     "livre", "lecture", "revision", "examen", "document", "note", "notes"}

# Formes que les règles de pluriel abîmeraient.
RACINES_FIXES = {"series": "serie", "analyses": "analysis", "news": "news", "canvas": "canvas",
                 "atlas": "atlas", "pandas": "pandas", "kubernetes": "kubernetes",
                 "postgres": "postgres", "redis": "redis", "always": "always", "macos": "macos",
                 "chaos": "chaos", "kudos": "kudos", "watchos": "watchos", "visionos": "visionos"}
# Noms en -ing à ne pas confondre avec le verbe (« machine learning » n'est pas « learn »).
GARDER_ING = {"learning", "something", "anything", "nothing", "everything", "morning", "evening"}

_MOT = re.compile(r"[^\W_]+")
_LIGATURES = str.maketrans({"œ": "oe", "æ": "ae"})


def default_roots():
    """Dossiers de skills installés, du plus général au plus local."""
    home = Path.home()
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude"))
    roots = [
        (config / "skills", "user"),
        (config / "plugins" / "cache", "plugin"),
        (config / "plugins" / "synced", "plugin-synced"),
        (Path("/mnt/skills"), "app"),
    ]
    # Skills du projet : .claude/skills du dossier courant et de ses parents.
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".claude" / "skills"
        if candidate.is_dir() and candidate != config / "skills":
            roots.append((candidate, "project"))
    return roots


def iter_skill_files(root, depth=0):
    try:
        entries = list(os.scandir(root))
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        return
    for entry in entries:
        if entry.is_file() and entry.name == "SKILL.md":
            # Un skill ne contient pas d'autre skill : les copies rangées dans ses dossiers
            # (_external/, assets/...) ne sont pas chargées par Claude Code.
            yield Path(entry.path)
            return
    for entry in entries:
        if (entry.is_dir(follow_symlinks=False) and entry.name not in SKIP_DIRS
              and not entry.name.startswith(".") and depth < MAX_DEPTH):
            # Dossiers cachés (.archive, .git…) : skills rangés ou copies, que Claude Code ne charge pas.
            yield from iter_skill_files(entry.path, depth + 1)


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace('\\"', '"') if value[0] == '"' else inner.replace("''", "'")
    return value


def parse_frontmatter(text):
    """Lecture minimale du frontmatter YAML : clés de premier niveau, scalaires, blocs > ou |,
    et valeurs poursuivies sur des lignes indentées (y compris entre guillemets)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data, key, block, folded = {}, None, [], False

    def store():
        if key is not None:
            value = " ".join(part.strip() for part in block).strip()
            data[key] = value if folded else _unquote(value)

    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match and not line.startswith((" ", "\t")):
            store()
            key, value = match.group(1), match.group(2).strip()
            folded = value in BLOCK_INDICATORS
            block = [] if folded or not value else [value]
        elif key is not None and (folded or line.startswith((" ", "\t"))):
            # Bloc > ou | : toutes les lignes ; valeur simple : seulement la suite indentée.
            block.append(line)
    store()
    return data


def fold(text):
    """Minuscules sans accents, pour comparer « présentation » et « presentation »."""
    if text.isascii():
        return text.casefold()
    normalized = unicodedata.normalize("NFKD", text.casefold().translate(_LIGATURES))
    return "".join(c for c in normalized if not unicodedata.combining(c))


def words(text):
    """Mots en minuscules sans accents ; « skill-creator » ou « ckm:slides » donnent deux mots."""
    return _MOT.findall(fold(text))


@functools.lru_cache(maxsize=None)
def stem(word):
    """Racine prudente : pluriels anglais et français, terminaison -ing."""
    if word in RACINES_FIXES:
        return RACINES_FIXES[word]
    if len(word) <= 3 or not word.isalpha():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("eaux"):
        return word[:-1]
    if word.endswith("zzes"):
        word = word[:-3]
    elif word.endswith(("sses", "xes", "ches", "shes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    if word.endswith("ing") and len(word) >= 7 and word not in GARDER_ING:
        word = word[:-3]
        if word[-1] == word[-2] and word[-1] not in "lsz":
            word = word[:-1]
    return word


def terms(text):
    """Mots utiles d'un texte, ramenés à leur racine."""
    return [stem(w) for w in words(text) if w not in MOTS_VIDES]


def _load_synonyms():
    """Dictionnaire indexé par la suite de racines de la clé (mots vides compris)."""
    table = {}
    for source in (SYNONYMES, SYNONYMES_PERSONNELS):
        for key, values in source.items():
            seq = tuple(stem(w) for w in words(key))
            if not seq:
                continue
            expansion = table.setdefault(seq, [])
            for value in values:
                for term in terms(value):
                    if term not in expansion:
                        expansion.append(term)
    return table


_SYNONYMS = None


def synonyms():
    global _SYNONYMS
    if _SYNONYMS is None:
        _SYNONYMS = _load_synonyms()
    return _SYNONYMS


def parse_query(keywords):
    """Transforme les mots-clés en concepts : {racine: poids}. Un concept regroupe un mot
    (ou une expression) de la requête et ses traductions."""
    raw = " ".join(keywords)
    table = synonyms()
    longest = max((len(k) for k in table), default=1)
    plain = words(raw)
    seq = [stem(w) for w in plain]
    accented = {fold(w) for w in _MOT.findall(raw.casefold()) if fold(w) != w}
    present = set(plain)

    concepts, i = [], 0
    while i < len(seq):
        for size in range(min(longest, len(seq) - i), 1, -1):
            key = tuple(seq[i:i + size])
            if key in table:
                fragments = [t for t, w in zip(key, plain[i:i + size]) if w not in MOTS_VIDES]
                concept = {t: POIDS_FRAGMENT for t in fragments}
                for term in table[key]:
                    concept[term] = max(concept.get(term, 0.0), POIDS_SYNONYME)
                concepts.append(concept)
                i += size
                break
        else:
            word, term = plain[i], seq[i]
            i += 1
            if word in MOTS_VIDES:
                continue
            concept = {term: 1.0}
            expansion = table.get((term,), [])
            if term == "resume":
                if present & CONTEXTE_CV:
                    expansion = table.get(("cv",), [])
                elif "resume" in accented or present & CONTEXTE_SYNTHESE:
                    concept[term] = POIDS_SENS_ECARTE
                else:
                    expansion = []
            for extra in expansion:
                if extra not in concept:
                    concept[extra] = POIDS_SYNONYME
            concepts.append(concept)

    unique, seen = [], set()
    for concept in concepts:
        signature = tuple(concept.items())
        if signature not in seen:
            seen.add(signature)
            unique.append(concept)
    return unique


class Index:
    """Index inversé du catalogue : pour chaque racine, ses occurrences dans le nom et la description."""

    def __init__(self, skills):
        self.skills = skills
        self.name_len, self.desc_len, self.postings = [], [], {}
        for doc, skill in enumerate(skills):
            name_terms, desc_terms = terms(skill["name"]), terms(skill.get("description") or "")
            self.name_len.append(len(name_terms))
            self.desc_len.append(len(desc_terms))
            for field, field_terms in ((0, name_terms), (1, desc_terms)):
                for term in field_terms:
                    counts = self.postings.setdefault(term, {}).setdefault(doc, [0, 0])
                    counts[field] += 1
        count = max(len(skills), 1)
        self.avg_name = max(sum(self.name_len) / count, 1.0)
        self.avg_desc = max(sum(self.desc_len) / count, 1.0)

    def idf(self, term):
        df = len(self.postings.get(term, ()))
        n = len(self.skills)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def scores(self, concepts):
        """Score de chaque skill trouvé : somme, sur les concepts, du meilleur mot (BM25F)
        plus une part des autres et d'un bonus si le mot figure dans le nom, multipliée par
        la part des concepts de la requête que le skill couvre."""
        totals = {}
        for concept in concepts:
            parts = {}
            for term, weight in concept.items():
                postings = self.postings.get(term)
                if not postings:
                    continue
                idf = self.idf(term)
                for doc, (tf_name, tf_desc) in postings.items():
                    tf = (POIDS_NOM * tf_name / (1 - B_NOM + B_NOM * self.name_len[doc] / self.avg_name)
                          + POIDS_DESC * tf_desc / (1 - B_DESC + B_DESC * self.desc_len[doc] / self.avg_desc))
                    value = weight * idf * tf / (K1 + tf)
                    bonus = BONUS_NOM * weight * idf / max(self.name_len[doc], 1) if tf_name else 0.0
                    parts.setdefault(doc, []).append((value, bonus))
            for doc, found in parts.items():
                values = sorted((v for v, _ in found), reverse=True)
                total = values[0] + PART_SECONDAIRE * sum(values[1:]) + max(b for _, b in found)
                found_total = totals.setdefault(doc, [0.0, 0])
                found_total[0] += total
                found_total[1] += 1
        share = len(concepts)
        return {doc: total * (matched / share) ** COORDINATION for doc, (total, matched) in totals.items()}


def rank(skills, keywords, index=None):
    """Skills qui correspondent aux mots-clés, du plus pertinent au moins pertinent : [(score, skill)]."""
    concepts = parse_query(keywords)
    if not concepts or not skills:
        return []
    index = index or Index(skills)
    found = [(round(score, 6), skills[doc]) for doc, score in index.scores(concepts).items() if score > 0]
    # Égalité de score : ordre alphabétique du nom, puis origine et chemin, pour un résultat stable.
    found.sort(key=lambda item: (-item[0], fold(item[1]["name"]), item[1]["name"],
                                 item[1]["origin"], item[1]["path"]))
    return found


def origin_label(path, kind):
    parts = path.parts
    if kind == "plugin" and "cache" in parts:
        # cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
        idx = parts.index("cache")
        if len(parts) > idx + 2:
            return f"plugin {parts[idx + 2]}@{parts[idx + 1]}"
    if kind == "user" and "synced" in parts:
        return "compte claude.ai (synchronisé)"
    return {"user": "personnel", "project": "projet", "app": "application",
            "plugin-synced": "plugin synchronisé"}.get(kind, kind)


def collect(roots):
    skills, seen = [], {}
    for root, kind in roots:
        if not root.is_dir():
            continue
        for skill_file in iter_skill_files(root):
            try:
                text = skill_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            meta = parse_frontmatter(text)
            name = meta.get("name") or skill_file.parent.name
            origin = origin_label(skill_file, kind)
            # Le cache des plugins peut garder plusieurs versions : on garde la plus récente.
            dedup_key = (name, origin)
            mtime = skill_file.stat().st_mtime
            if dedup_key in seen:
                previous = seen[dedup_key]
                if previous["_mtime"] >= mtime:
                    continue
                skills.remove(previous)
            entry = {
                "name": name,
                "description": meta.get("description", ""),
                "origin": origin,
                "path": str(skill_file.parent),
                "model_invocable": meta.get("disable-model-invocation", "").lower() != "true",
                "_mtime": mtime,
            }
            seen[dedup_key] = entry
            skills.append(entry)
    return skills


def main():
    parser = argparse.ArgumentParser(description="Recherche dans les skills installés localement.")
    parser.add_argument("keywords", nargs="*", help="mots-clés (français et anglais conseillés)")
    parser.add_argument("--all", action="store_true", help="lister tous les skills trouvés")
    parser.add_argument("--limit", type=int, default=15, help="nombre maximal de résultats (défaut 15)")
    parser.add_argument("--json", action="store_true", help="sortie JSON")
    parser.add_argument("--root", action="append", default=[], help="dossier supplémentaire à parcourir")
    args = parser.parse_args()

    roots = default_roots() + [(Path(r).expanduser(), "extra") for r in args.root]
    skills = collect(roots)
    keywords = [k for k in args.keywords if k.strip()]

    if args.all or not keywords:
        results = sorted(skills, key=lambda s: s["name"])
    else:
        results = [s for _, s in rank(skills, keywords)][: args.limit]

    for skill in results:
        skill.pop("_mtime", None)

    if args.json:
        json.dump({"count": len(results), "scanned": len(skills), "results": results},
                  sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    print(f"{len(results)} résultat(s) sur {len(skills)} skills trouvés.")
    for skill in results:
        flag = "" if skill["model_invocable"] else " [invocation manuelle seulement]"
        desc = skill["description"]
        if len(desc) > 220:
            desc = desc[:217] + "..."
        print(f"- {skill['name']} ({skill['origin']}){flag}\n  {desc or '(sans description)'}\n  {skill['path']}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        # Sortie tronquée par un pipe (head, etc.) : ce n'est pas une erreur.
        sys.stderr.close()
