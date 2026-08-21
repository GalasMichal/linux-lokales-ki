---
name: angular-standalone
description: >
  Angular standalone components, signals, inject(), and modern Angular CLI patterns.
  Use when working on Angular 17+ projects, components, services, routing, or migration from NgModules.
---

# Angular Standalone (17+)

## Defaults

- Standalone components; no new NgModules unless project already uses them
- `inject()` over constructor DI
- Signals for local/component state; RxJS for async streams from HTTP/WebSocket
- `input()` / `output()` / `model()` instead of `@Input`/`@Output` where project already does
- Lazy routes via `loadComponent` / `loadChildren`

## File layout

- One component per folder: `.ts`, `.html`, `.scss`, optional `.spec.ts`
- Services: `providedIn: 'root'` unless scoped feature
- Barrel exports only if project already uses them

## Templates

- `@if`, `@for`, `@switch` (control flow) when project uses them
- `track` in `@for` for lists
- Avoid `*ngIf`/`*ngFor` in new code if project migrated

## Change detection

- `OnPush` for presentational components when sensible
- Avoid creating new object/array refs in template bindings

## i18n

- If `@ngx-translate/core` is present: keys in `assets/i18n/`, pipe or `TranslateService` in TS

## Testing

- Follow project runner (Jest/Karma/Vitest)
- Test behavior, not implementation details
