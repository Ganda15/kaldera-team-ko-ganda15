# Kaldera Team KO

Orchestrateur d'une équipe d'agents LLM (`researcher`, `writer`, `reviewer`,
`finalizer`) coordonnés par un superviseur, pour traiter une demande métier
étape par étape jusqu'à un résultat final.

## Features

- Superviseur qui confie chaque étape à l'agent responsable via une table de routage.
- Sous-agents spécialisés, chacun avec un périmètre de rôle explicite.
- Exécution déterministe et rejouable à partir de scénarios JSON.
- Garde-fous d'exécution : budget d'étapes, budget de tokens par agent, journalisation traçable.
- Chemin d'exécution « live » branché sur Azure AI (Kimi-K2.6) via LangChain + LangGraph.

## Stack

- Python 3.11 (uv)
- LangChain / langchain-core 0.3.x
- langchain-azure-ai 0.1.x (Kimi-K2.6)
- LangGraph 0.2.x
- pytest 8.x

## Setup

```bash
make install              # uv sync — installe les dépendances
cp .env.example .env      # puis renseigner les clés Azure AI
make up                   # docker compose up -d (conteneur d'exécution)
make test                 # lance la suite de tests
```

Sans Docker, `make install` puis `make test` suffisent : le cœur de
l'orchestration tourne sans dépendance réseau.

## Layout

- `src/kaldera/` — superviseur, sous-agents, état partagé, garde-fous d'exécution
- `src/kaldera/agents/` — `researcher`, `writer`, `reviewer`, `finalizer`
- `src/kaldera/graph.py`, `src/kaldera/llm.py` — chemin d'exécution branché sur le LLM
- `specs/flow_spec.md` — spécification du flux métier attendu
- `scenarios/scenarios_test.json` — scénarios d'exécution rejouables
- `tests/` — tests unitaires et d'intégration
- `docker-compose.yml`, `Dockerfile` — service d'exécution conteneurisé

## Useful commands

```bash
make fmt        # ruff format + autofix
make lint       # ruff check
make typecheck  # mypy
make down       # stoppe le service docker
```

## Known issues

- Le chemin « live » branché sur le modèle (`llm.py`) n'est pas couvert par les tests :
  ils utilisent les agents déterministes, sans clé Azure.

## Corrections de l'orchestration

Les défauts de boucle, de rôles et d'écart à la spécification sont corrigés sur la branche
`fix/orchestration`. Détail des défauts, des choix et de leur vérification :
[`docs/DECISIONS.md`](docs/DECISIONS.md).

- Le superviseur est le seul point de passage : il choisit l'agent responsable, vérifie le
  budget avant chaque appel et la progression après, et arrête le flux avec une raison
  (`stop_reason`) en cas d'anomalie.
- Chaque étape a un seul responsable ; la table de routage est dérivée des `handles` et
  vérifiée au démarrage.
- Le chemin LangGraph (`graph.py`) réutilise la même logique que le runner.
- Tests : 14 tests fournis + tests de trace (`tests/test_trace.py`), de routage
  (`tests/test_routing_guards.py`), LangGraph (`tests/test_graph.py`) et de la page de
  démonstration (`tests/test_web.py`) : 32 passent.

## Page de test

`src/kaldera/web.py` sert une page qui rejoue un scénario (fourni ou libre), avec le runner ou
le graphe LangGraph, éventuellement avec une panne simulée, et affiche la trace, les artefacts,
la raison d'arrêt et les contrôles de la spec. Lancement : `docker compose up web`, puis
http://localhost:8000.

## License

Usage interne — tous droits réservés.
