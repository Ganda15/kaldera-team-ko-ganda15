# Décisions de correction de l'orchestration

Branche `fix/orchestration`, à partir du commit `37c2cb3`.
Référence métier : [`specs/flow_spec.md`](../specs/flow_spec.md). Les numéros `l. N` renvoient à ses lignes.

## 1. Point de départ

Sur `37c2cb3`, les 14 tests fournis échouent (`14 failed`). Quatre symptômes sont signalés :
deux agents se renvoient la tâche, l'orchestration boucle, un agent fait le travail d'un autre,
le flux ne respecte plus la spécification.

Cause racine : les règles sont écrites (spec, prompt système) mais le code ne les applique pas.
Les frontières reposent sur une phrase du prompt (`agents/base.py`, « Ne traite pas les étapes
des autres agents ») et les garde-fous (`max_steps`, `token_budget`, `agent_id`) existent comme
attributs sans jamais être vérifiés.

Principe retenu : **les agents proposent, l'orchestration impose.**

## 2. Défauts corrigés

| # | Défaut (code d'origine) | Règle de la spec | Correction | Preuve |
|---|---|---|---|---|
| 1 | `runner.py` `load_context()` ne fait que `return` | l. 3-4 | lit `topic` et `required_steps` depuis `initial_context` | `test_load_context_populates_state` |
| 2 | `orchestrator.py` `route()` teste `>` au lieu de `>=` : END jamais atteint | l. 28 | `step_index >= len(required_steps)` → `END` | `test_route_returns_end_once_all_steps_done` |
| 3 | `runner.py` boucle sur `range(HARD_CAP)` : `max_steps` calculé puis ignoré | l. 29 | budget = `min(max_steps, HARD_CAP)` vérifié avant chaque appel ; arrêt au premier tour sans progrès | `test_step_budget_is_enforced`, `test_stuck_agent_aborts_on_first_non_progress` |
| 4 | `STEP_TO_AGENT[REVIEW] = "writer"` ; `Writer.handles = {DRAFT, REVIEW}` ; `Writer.accepts()` renvoie `True` | l. 18-19, 22, 27 | `Writer.handles = {DRAFT}` ; table dérivée des `handles` ; `accepts()` non redéfinissable | `test_review_is_routed_to_reviewer`, `test_each_step_handled_by_exactly_one_agent`, `test_writer_refuses_foreign_step`, `test_routing_guards.py` |
| 5 | `Finalizer()` absent de `AGENTS` : `KeyError` sur FINALIZE | l. 20 | `Finalizer()` enregistré ; une étape sans responsable bloque le démarrage | `test_finalizer_is_registered`, `test_step_without_owner_fails_at_startup` |
| 6 | le runner écrit `status = "done"` à END, même sans résultat final | l. 20, 28 | `done` n'est posé que par le finalizer ; END sans `final` → `aborted` | `test_trace_matches_spec` |
| 7 | `steps.py` associe le libellé `"PROOFREAD"` au lieu de `"REVIEW"` | l. 12 | `STEP_BY_NAME` dérivé de l'énumération `Step` | `test_review_label_resolves_to_review_step`, `test_all_business_labels_resolve` |
| 8 | description du writer copiée de celle du researcher | l. 17-20 | description propre : « Rédige un premier jet à partir de la recherche. » | `test_agent_descriptions_are_distinct` |
| 9a | `base.py` : `used` jamais comparé à `token_budget` | l. 33-34 | `BudgetExceeded` levé avant `act()` si `used > token_budget` | `test_per_agent_token_budget_is_enforced` |
| 9b | `logging_utils.record()` n'écrit que `message` | l. 35-36 | entrée `{agent_id, step, message}` | `test_log_entry_carries_agent_id` |
| 10 | `graph.py` : aucun arc, pas de `compile()`, pas de `recursion_limit`, `build_graph()` jamais appelé | l. 26 | graphe câblé sur les mêmes fonctions que le runner (décision D7) | `test_graph.py` |

## 3. Décisions

**D1. Superviseur déterministe.** La demande donne l'ordre des étapes et la spec donne le
responsable de chaque étape : aucun choix n'est laissé à un LLM. Un superviseur de type
handoff/swarm (un agent désigne le suivant) est écarté, car les transferts libres entre agents
produisent le ping-pong.

**D2. Une étape, un responsable, une table dérivée.** Chaque agent déclare ses étapes dans
`handles`. `build_routing_table()` construit `STEP_TO_AGENT` à partir de ces déclarations et
lève `ValueError` au démarrage si une étape a zéro ou deux responsables. La table ne peut plus
contredire les agents.

**D3. Frontière codée une seule fois.** `accepts()` est défini dans `Agent`. `__init_subclass__`
refuse (`TypeError`) toute sous-classe qui le redéfinit. Une étape hors périmètre lève
`RoleViolation`. Le prompt système n'est plus qu'un rappel.

**D4. Fin observée, jamais déclarée.** Le runner ne force plus `done`. Le flux se termine
`done` seulement si le finalizer l'a posé et que l'artefact `final` existe.

**D5. Post-condition après chaque appel.** Le superviseur vérifie que `step_index` a avancé de
exactement 1. Sinon il arrête le flux dès le premier tour, au lieu de relancer l'agent jusqu'à
`HARD_CAP`. `HARD_CAP = 50` reste un filet de sécurité qui ne doit jamais être atteint.

**D6. Arrêt contrôlé avec raison.** Nouveau champ `TeamState.stop_reason`. Budget d'étapes
atteint, `RoleViolation`, `BudgetExceeded`, absence de progrès et END sans résultat final
mènent tous à `status = "aborted"` avec une raison lisible, sans exception non rattrapée.

**D7. Une seule orchestration pour les deux chemins.** Le tour du superviseur est isolé dans
deux fonctions du runner : `next_agent()` (décider ou arrêter) et `call_agent()` (déléguer puis
vérifier). Le runner et le graphe LangGraph les appellent tous les deux. Dans le graphe, chaque
agent rend la main au superviseur et `recursion_limit = 2 × budget + 3`.

**D8. Finalizer sans étape REVIEW.** La spec ne dit pas ce que le finalizer assemble dans le
scénario `research_only`. Choix retenu : le dernier artefact produit (`review`, sinon `draft`,
sinon `research`). À valider avec le métier.

**D9. Tests de trace.** Les 14 tests fournis vérifient chaque pièce séparément et restent
inchangés. `tests/test_trace.py` rejoue les scénarios et vérifie l'exécution entière : ordre
des agents conforme à la spec, un passage par étape, `done` avec `final`, arrêt d'un agent
bloqué au premier tour. Les responsables attendus sont recopiés de la spec, pas du code.

## 4. Vérification

| Environnement | Commande | Résultat |
|---|---|---|
| Python 3.14, LangGraph 1.2.9 | `python -m pytest -q` | `32 passed` |
| Docker `python:3.11-slim`, LangGraph 0.2.76, FastAPI 0.142 (versions du `pyproject.toml`) | `uv sync` puis `uv run pytest -q` | `32 passed` |
| CLI | `python -m kaldera.cli` | `happy_path` : `done`, 4 étapes ; `research_only` : `done`, 2 étapes |

Les 32 tests : 14 fournis (non modifiés), 3 exécutions des tests de trace, 3 garde-fous de
routage, 3 tests LangGraph, 9 tests de la page de démonstration (`tests/test_web.py`).

## 5. Limites connues

- Le chemin « live » avec le modèle (`llm.py`, Kimi-K2.6 sur Azure AI) n'est pas testé : les
  tests utilisent les agents déterministes, sans clé Azure.
- Un avertissement de bibliothèque reste affiché (Pydantic V1 sous Python 3.14 ; valeur par
  défaut `allowed_objects` de LangGraph 0.2). Il ne vient pas du code du projet.
- D8 est une hypothèse de conception, pas une règle de la spec.
