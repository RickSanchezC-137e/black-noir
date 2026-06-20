# Deviations Journal (Rule 4 / build plan §6, Step 19)

All deviations from blueprint paths/assumptions, with justification. CANON.md remains source of truth.

| # | Deviation | Blueprint expectation | Actual | Justification |
|---|---|---|---|---|
| D1 | Repo root path | `/opt/noir` (07_build_plan) | `/home/jarvis/noir` | Old project lives under `/home/jarvis/jarvis` (not `/opt`), working user is `jarvis` (uid 1000) with sudo. Keep new repo beside old for parity. Neutral namespace preserved. |
| D2 | Old project path | `/opt/jarvis-old` | `/home/jarvis/jarvis` | Existing deployment location. |
| D3 | Secrets backup path | `noir/secrets/backup/` (INSTRUCTIONS) / `/opt/secrets-backup` (07) | `/home/jarvis/secrets-backup/<DATE>/` | Placed **entirely outside any git repo** (stronger than gitignored-subdir). Satisfies CANON §12.2 "вне git". `/home/jarvis` is not a git repo; verified no `.git` ancestor. |
| D4 | Repo layout | 07_build_plan uses `core/`, `eval/`; 08_conventions uses `backend/app/...` | Following **08_conventions §2** (`backend/app/...`) | 08 is the detailed implementation reference ("без догадок"); 07 is a higher-level sketch. CANON §9 doesn't mandate dir layout. |
| D5 | Build/test port | core listens `:8000` (final) | `:8001` during parallel build | Old jarvis still binds `127.0.0.1:8000`. New core uses `:8001` for smoke until decommission (Step 5), then takes `:8000`. No `:8080`, no `/jarvis/*`. |
| D6 | gpg encryption of backup | `gpg --symmetric` (07 step 2.3) | skipped (chmod 600 + outside-git) | Symmetric gpg needs interactive passphrase; storing one on same host adds no real security. Archive restore-tested instead. Owner may gpg-encrypt for off-site copy. |

## Outstanding MISSING secrets (manual transfer required)
- `DUCKDNS_TOKEN` = `<<TAKE_FROM_OLD_PROJECT>>` — not present on host (manual DuckDNS registration). Domain `jarvisgod.duckdns.org`→89.208.97.41 preserved. Request from owner.

## Hardware decision (Step 4)
- No GPU, 4 vCPU, 7.8 GiB RAM → profile "weak machine / no GPU": orchestrator+reflex via Claude API `opus-4-8`; embeddings local `all-MiniLM-L6-v2` (dim=384); STT faster-whisper CPU (base/small); TTS Piper. No local LLM until GPU available. Recorded in `core/config/llm_layer.yaml`.
