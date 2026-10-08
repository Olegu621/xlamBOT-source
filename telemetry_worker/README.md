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
5. Store `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` using Wrangler's secret
   commands. Never put their values in Git, config vars, CLI arguments or logs.
6. Verify `/health`, HTTPS registration, authenticated report acceptance and
   actual Telegram delivery. Set the verified workers.dev URL in the client;
   run the full Python/JS/frozen checks and merge the source PR before publishing.
7. Only after public delivery is confirmed, disable the obsolete local
   receiver/ngrok startup. Keep its encrypted settings and report database.

## Privacy and delivery

Reporting is opt-in. Only allowlisted error metadata is stored; no raw logs,
exception messages, source, screenshots or accounts. Credentials are randomly
generated per installation and stored hashed. Source addresses are hashed for
registration rate limits; rate records expire. Payloads are capped at 32 KiB.
The public endpoint provides no admin/setup or report-reading API. Worker
observability is disabled to avoid request/credential logs.

D1 persists reports and Telegram outbox state. Atomic SQL triggers maintain
group totals without scanning all reports every minute. A database lease
serializes Telegram sending, including concurrent requests and cron runs.
Repeated groups have a ten-minute cooldown, with global spacing and bounded
failure backoff. Cron retries pending delivery each minute. Ambiguous delivery
acknowledgements may produce duplicates (at-least-once delivery).

Daily cleanup removes groups with no reports received in 30 days. Installation
credentials remain until the operator removes them; keep registrations bounded.
Sending to Telegram requires Cloudflare to hold the two delivery secrets.

## Verification

`npm test` executes the production queries and migrations against SQLite with
fake Telegram credentials. Also check `npx wrangler deploy --dry-run`, apply local
migrations and exercise registration/events in `npx wrangler dev` before live
deployment. Never use real credentials for automated tests.
