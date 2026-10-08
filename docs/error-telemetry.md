# Error reports (PC only)

This feature is prepared for deployment. `DEFAULT_ENDPOINT` is deliberately empty
until the developer has a real HTTPS receiver. No Telegram token belongs in a
desktop build, public repository, installer or script update.

## User controls

Settings → Error reports / Настройки → Отчёты об ошибках. Remote reporting is
disabled by default. Local reports remain available for download. Users can choose
repeated warnings (three occurrences), errors plus critical failures, or critical
failures only. Info is always local. Disabling cancels pending delivery and events
recorded while disabled are never replayed after enabling.

The report contains a fixed error code, level, version/revision, stage, pseudonymous
device ID and up to eight project stack frames (module/function/line). Exception
messages, source lines, locals, account names, ADB serials, screenshots, raw logs
and filesystem paths are excluded. Installation IDs are random, not hardware IDs.
The receiver additionally applies the same allowlist. Diagnostic data still needs
access controls and a published privacy/retention policy on the deployed server.

Current hooks cover initialization failures, runtime crashes and halts, unhandled
Python/thread/logging exceptions, unexpected web API failures, GPU fallback and
gas-detector exceptions. A normal Stop/Pause or rejected stale input is not an
error. Native process termination/power loss cannot be caught by these Python hooks.
Other error codes are reserved for future explicit hooks; this is not a claim that
every failure in every subsystem is collected.

The game worker only constructs a sanitized event and enqueues it in memory.
A daemon handles persistence and HTTP. Limits: 256 incoming events, 200 retained
groups. Queue overflow is counted. Local files are under the update home's
`error_reports` directory; they contain a receiver registration credential, never
a Telegram credential. Download excludes registration credentials and preferences.

## Developer deployment

1. Revoke any Telegram token pasted into chat using BotFather, issue a new token.
   Keep it in the server's secret manager/environment as `TELEGRAM_BOT_TOKEN`.
2. Open the bot in Telegram and press Start. Obtain your numeric destination
   `TELEGRAM_CHAT_ID` privately through Telegram's `getUpdates` API or an admin
   tool. Do not publish API responses containing user/chat details or the token.
3. Rent/use a Linux server, configure a domain and TLS reverse proxy. Build from
   the repository root: `docker build -f telemetry_service/Dockerfile -t xlambot-reports .`.
   Run with `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, a persistent writable volume
   at `/state` (UID 10001), and port 8080 accessible only to the TLS proxy.
   Use a protected environment file outside Git or a secret manager. Never expose
   the Flask development server. The container is intentionally one worker:
   multiple receiver processes would require a distributed outbox lease.
4. Apply proxy request/body/connection limits. Requests are registered anonymously;
   registration and per-installation rate limits reduce abuse but cannot establish
   that a client is a genuine installation. Ensure the proxy supplies a trusted
   remote address; do not blindly trust caller-supplied forwarding headers. Disable
   request-body, Authorization and Telegram URL logging. Protect SQLite/backups.
5. Set the real HTTPS base URL in `error_telemetry.DEFAULT_ENDPOINT`, or use
   `XLAMBOT_TELEMETRY_ENDPOINT` for a private deployment test. The URL cannot
   contain credentials, query parameters or fragments. Ship the configured source
   change through the normal reviewed, signed release process.
6. Verify registration, duplicate delivery, outage/recovery, opt-out and the
   dashboard Test delivery button with a real private Telegram destination before
   enabling production. Tests currently mock Telegram and do not verify a live bot.

Receiver endpoints are `/v1/register` and `/v1/events`. Issued installation tokens
are stored hashed on the server. A report is acknowledged only after the SQLite
transaction commits. Delivery is retried with exponential backoff, grouped across
installations with a ten-minute cooldown and a global two-second message interval.
Telegram delivery is at least once: a lost Telegram acknowledgement can produce
a duplicate. Sender network failure does not block gameplay. Disabling cannot
retract a request already in flight or data already accepted by the server.

Server storage is capped at 100,000 installations/events and 1,000 groups per
installation. At capacity ingestion is refused, not silently acknowledged. Set up
operator-controlled retention/deletion and monitoring before production; automatic
retention and a remote deletion portal are not implemented in this first version.
Existing accepted reports are retained until the operator deletes them. Developer
backups and Telegram history need their own retention policy.

Server code is in `telemetry_service/`, deliberately excluded from the PC release
builder. The client requires no bootstrap change or new installer.
