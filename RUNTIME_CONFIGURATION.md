# Runtime configuration (SX-001)

API `main.py`, standalone `worker.py`, and `services/storage.py` read the process
environment without loading `.env`. Supply Railway Variables for each deployment
role. Local launchers must explicitly inject a test/development environment;
`.env.example` is documentation and is not automatically loaded.

Preserve the existing start commands: the standalone worker and Uvicorn workers
are different runtime roles. Do not change enabled consumers or delivery modes
as part of this configuration fix. Existing runtime validation remains in place.

Signing behavior is unchanged: `BOT_TOKEN` and `TELEGRAM_BOT_TOKEN` can validate
Telegram auth; media and PayPal ownership bindings use `MEDIA_SIGNING_SECRET`
or the first bot token. Web and Telegram sessions use `WEB_SESSION_SECRET` or
the first bot token. Configuring or rotating any of these values can invalidate
existing signatures. Before a production cutover, coordinate all consumers,
session behavior, media links and pending PayPal bindings; verify that no alias
retains a revoked credential. This change does not introduce old-key acceptance.

Keep real env files out of Git and Docker contexts. No production credentials
belong in test environments, patches, frontend code, logs, or test reports.
Secret rotation, deployment and Git-history cleanup are separate approved steps.
