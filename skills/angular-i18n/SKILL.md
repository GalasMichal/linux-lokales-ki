---
name: angular-i18n
description: >
  ngx-translate i18n for Angular — translation keys, DE/EN JSON files, pipes, and TranslateService.
  Use when adding or editing translations, language switcher, or i18n keys in assets/i18n/.
---

# Angular i18n (ngx-translate)

## File layout

- Keys: `src/assets/i18n/de.json`, `en.json` (or project path)
- Keep key structure nested and consistent (`section.subsection.key`)
- Same keys in all locale files — missing keys show raw key in UI

## Component usage

- Template: `{{ 'key.path' | translate }}` or `[innerHTML]="'key' | translate"` only for trusted HTML
- TS: inject `TranslateService`, use `instant()` for sync or `get()` for Observable
- Language switch: `translate.use('de' | 'en')`, persist preference in localStorage if project does

## Adding strings

1. Add key to **both** de.json and en.json
2. Use descriptive key paths, not English sentence as key
3. Avoid duplicating long HTML in JSON unless CMS pattern already exists

## App config

- `provideHttpClient()` + `TranslateHttpLoader` or project loader
- Default lang matches project (often `de` for DE user)

## Do not

- Hardcode user-visible strings in new UI without translation keys (if project uses i18n)
- Mix ngx-translate with Angular built-in `$localize` in same component without reason
