# Fair 64K vs 80K — STATUS

Updated: 2026-10-03 19:07:24 +0200. Runs=60.
Same current fixtures (multi-file coding + multi_hop). 5 runs / suite / ctx.
Productive local-quality stays **65536** until a later cutover decision.
Keep-awake: systemd-inhibit pc-keepawake (separate).

| Context | Tool | Compact | KB | Supervisor | Coding | MultiHop | Drift |
|---|---|---|---|---|---|---|---|
| 65536 | 5/5 | 4/5 | 5/5 | 5/5 | 3/5 | 3/5 | 5 |
| 81920 | 5/5 | 5/5 | 5/5 | 4/5 | 4/5 | 4/5 | 3 |

Last: multi_hop ctx=81920 r=5 pass=True elapsed=106.071 @ 2026-10-03T19:07:21+0200
