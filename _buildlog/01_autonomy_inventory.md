# Autonomy Inventory — old Jarvis → Noir (Rule 3 / build plan Step 3)

> Goal: Noir autonomy must be **≥** old Jarvis. Every autonomous behavior below has a Noir replacement.
> Old permission model GREEN/YELLOW/RED is replaced by canonical Governor ALLOW/CONFIRM/DENY/KILL.

## Old Jarvis autonomy model (observed, read-only)

Old Jarvis has **no cron jobs and no periodic scheduler loop** — it is *event-driven + always-on*:
- 2 systemd services, both `Restart=always` (`jarvis.service` uvicorn :8000, `jarvis-telegram.service`).
- Caddy reverse proxy (80/443 → localhost:8000), auto Let's Encrypt.
- Permission engine `config/permissions.py` (GREEN/YELLOW/RED) with action_log audit in SQLite.
- Task queue `core/tasks.py` (TaskHub/TaskManager, async worker `while True`, streams `/ws/tasks`).
- Activity bus `core/activity.py` (`/ws/activity`).
- Proactive Telegram notifications `integrations/notifier.py` (`POST /telegram/notify`).
- Self-improvement `agents/self_improve.py` (write+test code in sandbox → apply_module → activate `agents/generated`).
- Web access `agents/web_access.py` (Tavily search + Playwright browse/screenshot).

## Mapping table

| # | Old Jarvis autonomous behavior | Where (old) | Noir replacement | Governor class |
|---|---|---|---|---|
| 1 | Always-on API server, infinite restart | `jarvis.service` Restart=always | `noir-core.service` Restart=always + watchdog on `/api/core` | system |
| 2 | Always-on Telegram bot | `jarvis-telegram.service` | `noir-bot.service` Restart=always (step 6.7) | external_send |
| 3 | TLS + reverse proxy + domain | Caddy + jarvisgod.duckdns.org | reuse Caddy → :8000; DuckDNS (token MISSING, request owner) | system |
| 4 | Permission levels GREEN/YELLOW/RED | `config/permissions.py` | Governor ALLOW/CONFIRM/DENY/KILL (`04_governor.md`) | all |
| 5 | GREEN = silent read/search/analyze | permissions GREEN | ALLOW (read) | read |
| 6 | YELLOW = act + notify owner | permissions YELLOW | ALLOW + audit + `/ws/notify`/Telegram | local_write |
| 7 | RED = act + red notify (autonomous) | permissions RED | ALLOW with reversibility wrapper + audit | system/local_write |
| 8 | Financial: <$50 auto, >$50 pending, >$200/day blocked | permissions financial rails | Governor money rails (limit/delay/revoke), CONFIRM>limit, DENY over daily cap | money |
| 9 | Hard-RED: server-rent, data-delete, core/permission self-modify | permissions hard categories | deny-list (constitution) + CONFIRM/self_modify; reversibility | self_modify/system |
| 10 | `/permit <action> green|yellow|red` owner override | Telegram cmd → `action_levels` table | Governor policy override via owner (Telegram), audited | self_modify |
| 11 | Immutable audit trail | `action_log` (SQLite) | `agent_log` (SQLite, insert-only) + `autonomy/audit.jsonl` | — |
| 12 | Async task queue + lifecycle stream | `core/tasks.py` → `/ws/tasks` | Orchestrator `tasks` table + `/ws/tasks` | — |
| 13 | Activity stream | `core/activity.py` → `/ws/activity` | `/ws/activity` | — |
| 14 | Proactive owner notifications | `integrations/notifier.py` `/telegram/notify` | Telegram bot + `/ws/notify`; Governor CONFIRM escalations | external_send |
| 15 | Self-improvement (sandbox write+test→activate) | `agents/self_improve.py` | Scout→hypotheses→Factory(sandbox)→Eval→Champion+rollback (`09_self_improvement.md`) | self_modify |
| 16 | Web search + browse | `agents/web_access.py` | `mcp_search` (Tavily) + `mcp_browser` (Playwright) modules | external_send |

## Enhancements over old (required by Rule 3)
- **Watchdog** (`autonomy/watchdog.py`) on `/api/core` health — old had only systemd restart.
- **Exponential backoff** on restarts (`max_restarts_per_hour`).
- **Budgets** (`autonomy/budget.py`): llm_tokens/hour, external_calls/hour — old had only per-$ financial caps.
- **Deterministic deny-list** + immutable constitution (Governor/kill-switch/deny-list/Eval/rollback) — old "hard-RED" was softer (still autonomous).
- **Kill switch** with auto-triggers (runaway, error storm, constitution-modify attempt, anomalous spend, security violation) — new.
- **Reversibility wrapper** + 1-step rollback — new.

## DoD Step 3 status
- [x] Old autonomy fully inventoried (no cron; event-driven + always-on + permissions + self-improve).
- [x] old→new mapping table (no behavior lost).
- [ ] `policy.yaml` + scheduler/watchdog/budget/audit implemented (build step 6.2/autonomy — pending core).
