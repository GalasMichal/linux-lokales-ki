---
name: roblox-luau
description: >
  Roblox Luau scripting — ServerScriptService, LocalScripts, RemoteEvents, ModuleScripts, DataStore patterns.
  Use when working on Roblox games, Luau code, or Roblox Studio workflows.
---

# Roblox Luau

## Structure

- **Server**: `ServerScriptService`, `ServerStorage` — authority, DataStore, validation
- **Client**: `StarterPlayerScripts`, `StarterGui` — UI, input, local effects
- **Shared**: `ReplicatedStorage` ModuleScripts — types, constants, shared logic (no secrets)

## Security

- Never trust client for economy, damage, or inventory — validate on server
- Use `RemoteEvent` / `RemoteFunction` with server-side checks
- Rate-limit sensitive remotes

## Patterns

```lua
-- ModuleScript export
local M = {}
function M.doThing(player) ... end
return M
```

- Prefer `--!strict` when project uses it
- Use `task.wait()` not `wait()` in modern Luau

## DataStore

- Wrap in pcall; retry with backoff
- No secrets or API keys in client scripts

## Performance

- Avoid infinite loops without yield
- Batch DataStore writes; don't save every frame

## Studio workflow

- Test in Play Solo and with 2 players for remotes
- Document place structure if multi-place game
