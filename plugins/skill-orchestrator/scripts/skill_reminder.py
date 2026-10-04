#!/usr/bin/env python3
"""Logique du hook UserPromptSubmit du plugin skill-orchestrator (lancé par skill-reminder.sh).

Lit le JSON de l'événement sur l'entrée standard et écrit sur la sortie standard un JSON
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ...}}.
Aucun accès réseau, aucune écriture de fichier. Bibliothèque standard, Python 3.6 ou plus.

Le hook ne décide rien : il signale les formulations de pilotage repérées, avec un drapeau
quand une négation les précède. C'est Claude qui interprète l'intention. Un indice qui
affirmerait « mode choix demandé » pour « pas besoin du mode choix » ferait plus de mal
qu'aucun indice.

SKILL_ORCHESTRATOR_HOOK : on (défaut) = rappel court + indices ; hints = indices seulement ;
off = rien (géré aussi par le lanceur).
"""

import json
import os
import re
import sys
import unicodedata

MARKER = "[Orchestration des skills]"
REMINDER = (MARKER + " Demande simple : réponds directement, sans skill. Début de mission : suis la ligne "
            "« Réglages durables » (question de départ, procédure directe ou mode choix). Orchestration retenue : "
            "lis d’abord le skill skill-orchestrator, puis applique sa procédure.")

# Expressions où « skill » ne désigne pas un skill de Claude.
NOT_CLAUDE_SKILLS = re.compile(r"\b(soft|hard|people|tech(nical)?|life|key|language) skills?\b"
                               r"|\bskills? (section|gap|matrix)\b|\bcompetences?\b")

# (libellé, motif) sur un texte en minuscules, sans accents, apostrophes droites.
CONTROLS = [
    ("orchestration", r"(?<!skill-)\borchestr(e|es|er|ez|ation|ations)\b"),
    ("mode choix", r"\bmode choix\b|\bchoice mode\b|propose[- ]?moi (plusieurs|des|quelques) skills"
                   r"|(je )?(veux|voudrais|souhaite) choisir (les |mes |le )?skills?"
                   r"|laisse[- ]moi choisir (les |le )?skills?|let me (choose|pick) (the )?skills?"),
    ("mode automatique", r"\bmode auto(matique)?\b|\bauto(matic)? mode\b"),
    ("recherche Internet de skills",
     r"recherche (sur )?internet|internet search"
     r"|(cherche|trouve|recherche|installe|search|find|look)[^.?!;]{0,50}\bskills?\b[^.?!;]{0,50}(internet|en ligne|sur le web|web|online)"
     r"|(internet|en ligne|web|online)[^.?!;]{0,40}\bskills?\b"
     r"|(trouve|cherche)[^.?!;]{0,20} et installe|find and install"),
    ("skills installés seulement", r"(uniquement|seulement) (avec )?(mes|les) skills install|only (my )?installed skills"),
    ("aucun skill", r"n'?utilise (aucun|pas de|plus de) skills?|sans (aucun )?skills?\b|don'?t use (any )?skills?"
                    r"|\bno skills? (for|this|at all)"),
    ("skill nommé", r"\butilise (uniquement |seulement )?(le|les) skills? [a-z0-9][\w:.-]*"
                    r"|\buse (only )?the [a-z0-9][\w:.-]* skill\b"),
    ("rapport des skills utilisés", r"quels? skills? (as[- ]tu|avez[- ]vous|tu as|ont ete) (utilise|employe|charge)"
                                    r"|which skills (did|have) you (use|used|load)"),
    ("contrôle des skills", r"(verifie|audite|controle|scanne)[^.?!;]{0,40}\bskills?\b"
                            r"|\bskills?\b[^.?!;]{0,30}(pirat|compromis|malveillant|dangereu|fonctionnel|safe|malicious)"
                            r"|\b(audit|scan)\b[^.?!;]{0,30}\bskills?\b"),
    ("préférence durable", r"(enregistre|memorise|garde|retiens)[^.?!;]{0,40}(reglage|par defaut)"
                           r"|par defaut desormais|desormais par defaut"
                           r"|preferences?[^.?!;]{0,30}(skills?|mode (choix|auto)|recherche internet)"),
]
CONTROLS = [(label, re.compile(pattern)) for label, pattern in CONTROLS]
# Formulations négatives par nature : le drapeau de négation n'y apporterait rien.
INHERENTLY_NEGATIVE = {"aucun skill", "skills installés seulement"}

# Négation ou désactivation dans la même proposition, juste avant la formulation.
NEGATION = re.compile(r"(\bpas\b|\bne\b|\bn'|\bsans\b|\binutile\b|\bjamais\b|\bdesactive|\barrete|\bstop"
                      r"|\bno need\b|\bdon'?t\b|\bdo not\b|\bnot\b|\bwithout\b|\bnever\b|\bdisable|\bturn off)")


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text)


def find_controls(prompt):
    """[(libellé, négation possible)] pour chaque type de formulation repéré."""
    text = NOT_CLAUDE_SKILLS.sub(" ", normalize(prompt))
    found = []
    for label, pattern in CONTROLS:
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        negated = label not in INHERENTLY_NEGATIVE
        for m in matches if negated else []:
            clause_start = max(text.rfind(c, 0, m.start()) for c in ".?!;,") + 1
            window = text[max(clause_start, m.start() - 40): m.end()]
            if not NEGATION.search(window):
                negated = False
                break
        found.append((label, negated))
    return found


# Début possible d'une mission : un verbe de production et un livrable dans le même message.
MISSION_VERB = re.compile(
    r"\b(redige[rsz]?|ecri[st]|ecrire|prepare[rsz]?|cree[rsz]?|fai[st]|faire|genere[rsz]?|construi[st]|construire"
    r"|developpe[rsz]?|code[rsz]?|programme[rsz]?|analyse[rsz]?|resume[rsz]?|synthetise[rsz]?|tradui[st]|traduire"
    r"|concoi[st]|concevoir|planifie[rsz]?|produi[st]|produire|elabore[rsz]?|corrige[rsz]?|resou[st]|resoudre"
    r"|write|create|build|draft|prepare|generate|develop|implement|analy[sz]e|design|summari[sz]e|translate"
    r"|make|produce|solve)\b")
MISSION_DELIVERABLE = re.compile(
    r"\b(documents?|rapports?|presentations?|diapo\w*|slides?|deck|fiches?|resumes?|syntheses?|memoire|dissertation"
    r"|lettre|cv|tableaux?|tableur|excel|graphiques?|sites?|applications?|app|scripts?|programmes?|fonctions?"
    r"|modules?|analyses?|etudes?|plans?|examens?|exercices?|formulaires?|guides?|articles?|essais?"
    r"|notebooks?|dashboards?|tableau de bord|word|docx|pptx|xlsx|pdf|reports?|spreadsheets?|websites?|papers?"
    r"|essays?|thesis|summar(y|ies)|charts?|diagrammes?|diagrams?|schemas?|cours|revisions?|quiz|flashcards?"
    r"|projets?|projects?|series?)\b")


def find_mission(prompt):
    """Livrable repéré si le message ressemble au début d'une mission, sinon None."""
    if prompt.lstrip().startswith("/"):
        return None  # commande : elle règle elle-même la question
    text = normalize(prompt)
    deliverable = MISSION_DELIVERABLE.search(text)
    if MISSION_VERB.search(text) and deliverable:
        return deliverable.group(0)
    return None


def build_context(prompt, mode):
    lines = [] if mode == "hints" else [REMINDER]
    deliverable = find_mission(prompt)
    if deliverable:
        lines.append(MARKER + f" Le message ressemble au début d'une mission (livrable repéré : « {deliverable} »). "
                     "Si c'est bien une nouvelle mission et que la question de départ n'a pas encore été posée, "
                     "applique la ligne « Réglages durables » avant tout travail.")
    controls = find_controls(prompt)
    if controls:
        parts = [f"« {label} »" + (" (négation possible)" if negated else "") for label, negated in controls]
        lines.append(MARKER + " Formulations de pilotage repérées : " + ", ".join(parts)
                     + ". Simple indice : décide d'après l'intention réelle du message (négation, question, "
                       "autre sens), puis applique la table des commandes du skill skill-orchestrator.")
    return "\n".join(lines)


def main():
    mode = os.environ.get("SKILL_ORCHESTRATOR_HOOK", "on")
    if mode == "off":
        return
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        prompt = json.loads(raw).get("prompt") or ""
    except (ValueError, AttributeError):
        prompt = ""
    if not isinstance(prompt, str):
        prompt = ""
    context = build_context(prompt, mode)
    if context:
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
