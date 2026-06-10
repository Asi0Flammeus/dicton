# Macros — expansion de texte déclenchée à la voix

## Concept

Une **Macro** associe un **déclencheur** parlé à une **valeur** insérée verbatim. Pendant une
dictée, si l'utilisateur prononce un déclencheur (« crqpt url »), dicton remplace l'occurrence
par la valeur définie (`https://crqpt.com`) — du simple lien jusqu'au bloc multi-paragraphes.

Langage ubiquitaire :

| Terme               | Définition                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------- |
| **Macro**           | `{ déclencheur(s) → valeur }`. Nom de code `macro` ; jamais prononcé (détection inline).     |
| **Orthographe** (`spelling`) | Une transcription Whisper connue du déclencheur. Une macro en porte **une ou plusieurs**. |
| **Valeur** (`value`) | Le texte de remplacement, **byte-exact**, éventuellement multi-paragraphes.                  |
| **Jeton** (`token`) | Sentinelle opaque qui remplace temporairement la valeur pendant le cleanup LLM.             |

> Le nom « Snippet » est écarté : déjà employé par Wispr Flow.

## Problème central — pourquoi ce n'est pas un simple `str.replace`

Deux contraintes se combinent et dictent toute l'architecture :

1. **Whisper n'est pas déterministe.** « crqpt » est transcrit `crypte` / `CRQPT` / `cripte` selon
   la prise. Un match littéral raterait souvent → on enregistre **plusieurs orthographes** par macro
   et on **normalise** avant de comparer.
2. **La valeur est byte-exact.** Le LLM de cleanup ne doit jamais la voir (il paraphraserait une URL,
   reformaterait un bloc) → la valeur **contourne** le cleanup via un jeton placeholder.

Activation retenue : **inline nue** (pas de mot-sentinelle ; on scanne chaque dictée). C'est la plus
naturelle mais la moins robuste ; le filet de sécurité est la liste d'orthographes, curable à la volée.
Repli futur si l'inline déborde : ajouter un mot-sentinelle optionnel — le modèle de données ci-dessous
y survit sans réécriture.

## Décisions

| Branche             | Décision                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------- |
| **Nom**             | Macro                                                                                                       |
| **Détection**       | Inline nue — chaque dictée est scannée, sans mot-sentinelle                                                 |
| **Matching**        | Normalisation (minuscules, sans accents/ponctuation, espaces compactés) + « contient » **aux frontières de mots** ; orthographes multiples ; **la plus longue gagne** |
| **Valeur**          | Byte-exact, multi-paragraphes ; **saisie au clavier** dans la fenêtre (pas de presse-papiers)              |
| **Sécurité LLM**    | Placeholder en deux temps : détection sur le brut → jeton → cleanup → restauration → valeur verbatim        |
| **Édition**         | Fenêtre Qt autonome (`dicton macros`) : liste / créer / éditer / supprimer                                 |
| **Saisie déclencheur** | Tapée **ou** 🎤 enregistrée → stocke la transcription Whisper **brute** ; « + ajouter une orthographe » |
| **Stockage**        | `~/.config/dicton/macros.json` (stdlib, zéro dépendance ; YAML possible plus tard si lisibilité voulue)    |
| **Rechargement**    | Le daemon **relit `macros.json`** au moment de matcher (cache mtime) — pas de redémarrage, pas d'IPC        |
| **Ouverture fenêtre** | `dicton macros` (CLI) — pas de 3ᵉ hotkey global                                                           |

## Modèle de données — `~/.config/dicton/macros.json`

```json
[
  {
    "id": "crqpt-url",
    "spellings": ["crqpt url", "crypte url", "CRQPT URL"],
    "value": "https://crqpt.com"
  },
  {
    "id": "signature",
    "spellings": ["ma signature"],
    "value": "Cordialement,\nAsi0\n— alysis"
  }
]
```

- `id` : identifiant stable (slug ou uuid4 court) pour que la fenêtre édite/supprime sans dépendre de
  l'index du tableau.
- `spellings` : ≥ 1. C'est la liste qu'on enrichit quand Whisper surprend.
- `value` : verbatim, `\n` inclus. Écrite par l'app (échappement correct), jamais à la main.

Fichier en `0o600` (cohérent avec `config.toml`, même répertoire XDG). Synchronisable via les clouds
si symlinké.

## Règles de matching (et cas-limites)

Normalisation `normalize(s)` : `casefold()` → NFKD + suppression des diacritiques → conservation des
seuls alphanumériques + espaces → compactage des espaces.

| Cas                                    | Comportement                                                              |
| -------------------------------------- | ------------------------------------------------------------------------ |
| Plusieurs orthographes d'une macro     | N'importe laquelle matche                                                 |
| Frontières de mots                     | « url » ne déclenche **pas** dans « urlencode » (match sur suite de mots entiers) |
| Plusieurs occurrences dans une dictée  | **Toutes** remplacées                                                     |
| Deux macros matchent un texte chevauchant | **L'orthographe la plus longue gagne** (évite l'ombrage partiel)       |
| Dictée = uniquement le déclencheur     | Expansion en la seule valeur (tombe naturellement)                       |
| Valeur en début de phrase              | Insérée **verbatim** (le byte-exact prime sur l'auto-majuscule)          |

## Sécurité LLM — placeholder en deux temps

Point d'insertion : `src/dicton/pipeline.py:320` (juste après `joined`, autour de l'appel
`cleanup_mod.cleanup` ligne 329).

```
BRUT     "envoie le crqpt url au client"
  expand()  →  détecte + tokenise
TOKENISÉ "envoie le ⟦M0⟧ au client"          (⟦M0⟧ = jeton opaque, U+E000…)
  cleanup LLM  (le jeton est une donnée inerte, préservée mot pour mot)
NETTOYÉ  "Envoie le ⟦M0⟧ au client."
  restore()  →  ⟦M0⟧ → valeur
FINAL    "Envoie le https://crqpt.com au client."
```

La valeur n'est **jamais** vue par le LLM ; la phrase autour est tout de même corrigée.

**Risque clé — survie du jeton.** Le modèle de cleanup pourrait supprimer un caractère exotique. C'est
le seul défaut capable de casser la feature silencieusement.
- *Mitigation 1* : choisir un jeton que les modèles préservent de façon fiable, **validé empiriquement**
  contre les 4 modèles de `CLEANUP_MODELS` (test d'intégration, pas seulement mock).
- *Mitigation 2 (repli)* : si **un** jeton manque dans la sortie nettoyée → on jette le résultat du
  cleanup et on restaure les jetons dans le texte **tokenisé pré-cleanup**. La macro se déclenche
  toujours (valeur byte-exact présente), au prix de la passe de polish dans ce cas rare. Priorité
  assumée : fiabilité de la feature > polish.

## Architecture — éditeur découplé du daemon

Le choix `dicton macros` (CLI) rend l'éditeur **indépendant** du daemon ; ils ne se rencontrent qu'à
travers le fichier JSON.

```
dicton macros (process fenêtre Qt)         daemon (process long)
  ├─ CRUD sur macros.json                     ├─ à chaque dictée :
  ├─ 🎤 : capture courte + stt.transcribe()    │    relit macros.json (cache mtime)
  └─ écrit macros.json                  ─────► └─ expand()/restore() autour du cleanup
```

- Pas d'IPC, pas de file-watcher, pas de redémarrage.
- La 🎤 réutilise `src/dicton/stt.py:transcribe` (httpx + clé Groq de `config`). Seul coût accepté :
  un second petit chemin enregistrement→STT, mais c'est une **réutilisation** d'une fonction propre,
  pas une réimplémentation.

## Fenêtre `dicton macros`

```
 Macros                                   [ + Nouvelle ]
 ──────────────────────────────────────────────────────
  crqpt url            → https://crqpt.com
  ma signature         → Cordialement, …
 ──────────────────────────────────────────────────────
  Édition : « crqpt url »
    Déclencheur (ce que tu dis) :
      [ crqpt url                         ]  🎤
      [ + ajouter une orthographe              ]
    Valeur (insérée verbatim) :
      ┌────────────────────────────────────┐
      │ https://crqpt.com                  │
      │ (multi-lignes, byte-exact)         │
      └────────────────────────────────────┘
                 [ Enregistrer ]   [ Supprimer ]
```

## Plan d'implémentation (tracer-bullet)

### Phase 1 — Le moteur (les macros se déclenchent, sans UI)

- `src/dicton/macros.py` :
  - `@dataclass Macro: id: str; spellings: list[str]; value: str`
  - `load() -> list[Macro]` / `save(...)` sur `macros.json`, cache mtime.
  - `normalize(s) -> str`
  - `expand(raw, macros) -> tuple[str, dict[str, str]]` (texte tokenisé + map jeton→valeur)
  - `restore(text, token_map) -> str` (+ repli si jeton manquant)
- Branchement `pipeline.py:_end` : `tokenized, tok = macros.expand(joined, macros.load())` →
  cleanup sur `tokenized` → `cleaned = macros.restore(cleaned, tok)`.
- `tests/test_macros.py` : normalisation (accents/casse/ponctuation), frontières de mots,
  orthographes multiples, la-plus-longue-gagne, occurrences multiples, round-trip expand/restore,
  **survie du jeton au cleanup** (mock respx) + **repli** quand le jeton est supprimé.
- Manuel : seed `macros.json` → dictée → la macro se déclenche de bout en bout.

**Livrable Phase 1** : feature fonctionnelle via `macros.json` édité à la main, avant toute GUI.

### Phase 2 — Fenêtre `dicton macros`

- `src/dicton/macros_ui.py` (Qt) : liste, créer, éditer (orthographes + valeur multi-lignes),
  supprimer, écrire `macros.json`.
- 🎤 : `sounddevice.InputStream` court + `stt.transcribe` → remplit le champ orthographe avec le brut.
- `cli.py` : sous-commande `dicton macros` (motif Typer, comme `dicton config`).
- Tests : logique CRUD (séparée de Qt autant que possible) ; câblage capture STT (mock).

### Phase 3 — Polish

- Validation (déclencheur/valeur vides ; orthographe en doublon entre macros → avertir).
- Optionnel : panneau « transcriptions brutes récentes » pour récupérer une orthographe après un raté.
- README + cette doc finalisés.

Chaque phase se clôt sur la **gate de validation** du repo : `./scripts/check.sh lint` + `pytest` au vert
(cf. `CLAUDE.md`).

## Hors-scope (v1)

Contenu dynamique (date / presse-papiers / variables), macros par application, macros imbriquées,
regex, mot-sentinelle. Le sentinelle reste le repli le moins cher si l'inline nue se révèle trop
bruyante à l'usage.
