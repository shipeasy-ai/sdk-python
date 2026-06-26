---
name: shipeasy-setup
description: Project pointer — Shipeasy is integrated here. Triggers on "set up shipeasy", "onboard shipeasy", "new contributor shipeasy".
---

# Shipeasy is integrated in this repo

This project uses Shipeasy. The full skill lives in the `shipeasy` Claude Code plugin. This file is the breadcrumb so new contributors can find their way without the plugin pre-installed.

## With plugin installed

`/shipeasy:install` or invoke the `shipeasy-setup` skill.

## Without the plugin

```bash
claude plugin marketplace add shipeasy-ai/shipeasy
claude plugin install shipeasy@shipeasy
/shipeasy:install
```

Cursor / Windsurf / non-Claude harness:

```bash
npx @shipeasy/cli plugin install
```

## Feature add-ons (run after base)

- `/shipeasy:ops:install` — feedback (bugs + feature requests) + errors + alerts
- `/shipeasy:flags:install` — gates, configs, kill switches, experiments, events
- `/shipeasy:i18n:install` — translations
