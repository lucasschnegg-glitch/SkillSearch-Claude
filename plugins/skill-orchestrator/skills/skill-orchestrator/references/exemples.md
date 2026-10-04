# Exemples

Les noms de skills ci-dessous sont illustratifs : utilise ceux qui existent réellement dans l'environnement.

## 1. Mode automatique, demande substantielle

> Utilisateur : Prépare un rapport Word de deux pages sur les résultats du trimestre à partir de ce fichier Excel.

Réponse attendue, première ligne :

> Skills retenus : `xlsx` (lecture fiable du classeur), `docx` (mise en page Word).

Puis le travail commence sans demande de validation. Si une relecture finale est utile au moment de livrer : « J'ajoute `copy-editing` pour la relecture. »

## 2. Mode automatique, demande simple

> Utilisateur : Combien de jours ouvrés entre le 3 et le 21 novembre ?

Réponse directe, sans annonce ni recherche de skill.

## 3. Mode choix, sans Internet

> Utilisateur : Mode choix pour cette tâche. Fais-moi une présentation de 10 diapositives sur la réassurance pour mon cours.

Réponse attendue :

> Trois options, concurrentes pour la production des diapositives :
>
> 1. **`academic-pptx` + `pptx`**. Structure argumentée pour un public qui évalue le raisonnement, puis fichier PowerPoint. Avantages : rigueur, notes de présentation. Limites : sobre visuellement. Se distingue par la qualité du fond.
> 2. **`mck-ppt-design`**. Diapositives de style conseil avec graphiques intégrés. Avantages : rendu très professionnel. Limites : moins adapté à un exposé pédagogique. Se distingue par la forme.
> 3. **`slides`**. Présentation HTML avec graphiques. Avantages : rapide, interactive. Limites : pas de fichier .pptx. Se distingue par le format.
>
> Recommandation : option 1, car un cours demande d'abord un raisonnement clair. Laquelle préfères-tu ?

Puis arrêt. Pendant l'attente, Claude peut lire le support de cours fourni, mais ne rédige pas les diapositives.

## 4. Mode choix, une seule option pertinente

> Utilisateur : Je veux choisir les skills. Convertis ce PDF en texte.

> Une seule option convient : `pdf`, qui extrait le texte de façon fiable, y compris les tableaux. Les autres skills de documents ne lisent pas les PDF. Je l'utilise ?

## 5. Option Internet désactivée, besoin non couvert

> Utilisateur : Génère un diagramme BPMN exportable vers Camunda.

Aucun skill disponible ne couvre l'export Camunda. Claude travaille avec ses moyens et ajoute une phrase :

> Aucun de tes skills ne couvre l'export BPMN pour Camunda ; je produis le XML BPMN 2.0 directement. Si tu veux, active la recherche Internet pour cette tâche et je chercherai un skill dédié.

Aucune recherche Web n'est lancée.

## 6. Mode automatique avec Internet

> Utilisateur : Mode automatique avec recherche Internet. Génère un diagramme BPMN exportable vers Camunda.

Déroulé attendu : recherche dans le catalogue local, puis requête générique (« Claude skill BPMN Camunda »), sources officielles d'abord, lecture complète du candidat, vérifications, installation dans `~/.claude/skills/<nom>/`, vérification de la reconnaissance, puis rapport :

> Skill installé : `bpmn-modeler`
> Source : https://github.com/auteur/depot (licence MIT)
> Version : commit `3f2a91c`
> Emplacement : `~/.claude/skills/bpmn-modeler/`, reconnu dans cette session.

Si aucun candidat ne passe les vérifications : « Aucun skill externe fiable trouvé (deux candidats écartés : licence absente, script qui télécharge un binaire). Je continue sans. »

## 7. Mode choix avec Internet

Même présentation qu'en mode choix, avec pour chaque candidat la source, l'auteur, la licence, la date de dernière mise à jour et le résultat des vérifications. Aucune installation avant la réponse de l'utilisateur.

## 8. Rapport

> Utilisateur : Quels skills as-tu utilisés et pourquoi ?

> - `xlsx` : lecture du classeur, pour extraire les chiffres sans erreur de cellule.
> - `docx` : production du rapport, pour une mise en page Word propre.
> - Écarté : `mck-ppt-design`, inutile puisque le livrable n'est pas une présentation.

## 9. Préférence durable

> Utilisateur : Enregistre le mode choix par défaut.

Dans Claude Code, Claude met à jour la ligne du bloc `skill-orchestrator` de `~/.claude/CLAUDE.md` :

> Réglages durables : sélection = choix ; recherche Internet = désactivée ; explications = courtes.

Dans Cowork, Claude donne cette ligne à coller dans les instructions globales.
