# Cloudflare receiver

Managed alternative to the Windows/ngrok receiver. The Python client protocol
is unchanged. Deploy this backend separately; it is not packaged in the PC EXE.

Use the Workers **Free** plan and D1 free allowances. Do not enable paid usage.
Workers request allowances and D1 read/write/storage allowances are separate:
https://developers.cloudflare.com/d1/platform/pricing/ . Quota exhaustion can
temporarily reject reports; the client keeps its bounded queue and retries.

## Deployment

1. `npm ci`, then `npx wrangler login --scopes account:read user:read workers:write workers_scripts:write d1:write`.
2. `npx wrangler d1 create xlambot-errors` and put its database ID into a local
   ignored `wrangler.local.jsonc` copied from `wrangler.jsonc`.
3. `npx wrangler d1 migrations apply xlambot-errors --remote --config wrangler.local.jsonc`.
4. Deploy with `npx wrangler deploy --config wrangler.local.jsonc`.
5. Store `TELEGRAM_BOT_TOKEN` and a random `TELEGRAM_WEBHOOK_SECRET` using Wrangler secrets (stdin, never CLI arguments). Register `/telegram` with Telegram `setWebhook`, the same secret token, and message-only updates. Set the bot command menu to `/stats`, `/today`, `/hour`, `/alltime`, `/help`.
6. Verify `/health`, authenticated reports/statistics, and webhook command replies. Merge source changes before publishing the signed PC update.
7. Disable obsolete Windows/ngrok receiver startup, preserving encrypted settings and databases.

## Privacy and delivery

Error reporting and community statistics have separate, disabled-by-default consent controls. Error reports stay private in D1: no exception messages, raw logs, source, screenshots or account data. Inspect them through authenticated Cloudflare administration; there is no public report-reading endpoint and no Telegram error delivery.

Statistics uploads contain only installation-salted device IDs and match IDs, times, outcomes and trophy changes. They include historical matches after explicit consent. Formula estimates and unknown changes remain separate from observed changes. No brawler names, account tags or device serials are transmitted. Previous anonymous aggregate results remain after opt-out; new uploads stop and presence is cleared. Online expires after 150 seconds without a heartbeat (client interval 60 seconds).

Telegram accepts only authenticated webhook requests. Commands reply to the requesting chat and topic with global aggregates. `/stats` includes all-time totals and shorter period summaries; `/today` uses Moscow midnight, `/hour` a rolling hour. The database claims updates to prevent concurrent/repeated replies; ambiguous network acknowledgement can still cause a duplicate reply. Ordinary messages and error details are never posted or retained by this command handler.

Statistics are self-reported by consenting clients, not a count of downloads or all installations. Old clients cannot report presence. Server-side match IDs prevent retry inflation; credentials bind uploads to their installation. Credentials are randomly generated and stored hashed. Request bodies are limited to 32 KiB, 32 devices and 50 matches per upload. Cloudflare quota exhaustion causes retries without interrupting gameplay. No paid plan is required or enabled.

Daily cleanup removes error groups inactive for 30 days and Telegram update claims older than seven days. Anonymous match totals and device participation are retained for all-time statistics. Worker observability is disabled; Telegram secrets never enter the PC distribution.

## Verification

`npm test` executes the production queries and migrations against SQLite with
fake Telegram credentials. Also check `npx wrangler deploy --dry-run`, apply local
migrations and exercise registration/events in `npx wrangler dev` before live
deployment. Never use real credentials for automated tests.
