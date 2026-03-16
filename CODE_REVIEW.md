## Purpose

I will spend time here delving into the code to understand how it works.

The idea is to understand every part of the code.

## things to remove

- context / environment detection

## session log

### 2026-03-15

- I trying to get the full advantage of the "hexagonal design pattern"
- the core seems properly implemented but the adaptater and ports way less
- so I'm trying to understand if it is okay to have a kind of half pattern of not
  - for me, no as it removes trust from the capacity of the codebase to fully implemente a design pattern
  - if 80% of the codebase respect the DP, and 20% not it can be explained
  - if it's the other way around that's simply bad design, and a good home for disorder

- so the migration was partly done
  - especially regarding the LLM adaptater

- the COPA design seems quite appropriate for this kind of app that want to be cross platform
