# xlamBOT contributor rules

## Scope and ownership

- This repository owns the PC Python sources; public distribution is `Olegu621/xlamBOT`.
- Do not change APKs, Android application packages, or xlamBOT Mobile. Installing, deleting or modifying emulators is outside a PC bot fix unless specifically requested.
- Preserve device profiles, calibration, queues, history, recordings, and models. Never delete user data as an error recovery strategy.
- Inspect applicable instructions and the current Git diff before editing. Use branches and pull requests; merge source changes before publishing their compiled distribution.

## Runtime invariants

- Each device owns its configuration scope, observation store, capture stream, controller, and battle state. Never use another device's frame or settings.
- Accept observations in strictly increasing frame order. A cached state must retain its original timestamp. Never publish a cached state again to make it appear fresh.
- Recognition threads publish observations only. Ordinary touch input belongs to one device worker. Only watchdog/Stop may release touches from another thread.
- Bind decisions to immutable observations. Validate screen epoch, frame age, stream health and cancellation before non-release input. Release touches after invalidation; do not send a delayed attack into a menu.
- Treat missing, stale, transitional and unrecognized observations separately. Do not infer battle readiness from old player detections.
- Brawler grid-to-detail transitions must refresh the decision observation before Select. Confirm detail controls independently; a generic Home icon alone cannot identify a brawler page.
- Recheck visible controls before menu actions. Recovery must not use arbitrary taps to navigate unknown screens. Keep the four-second unknown grace and 1.5-second retry interval.
- Reward handling must run on the owner, use bounded actions and obey Stop/Pause. Do not launch background click loops or uninterruptible multi-second holds.
- A detector failure is an unavailable measurement, never evidence of safe terrain. With gas avoidance enabled, release movement until valid gas recognition resumes.
- Record one result per confirmed battle episode, including battles shorter than 25 seconds. Unknown trophy changes remain unknown; formula estimates must be labeled estimated.
- Bind trophy-rate baselines to configured account identity. Never assign legacy observations to the currently selected account.

## Configuration and interfaces

- Validate profile keys and resolved path containment centrally, including Windows reserved names. Avoid collisions between device identities.
- Lock the entire read/validate/merge/write transaction. Atomic replacement alone does not prevent lost updates.
- Validate every element of variable-length arrays, finite numbers, explicit enums, and supported numeric/`auto` unions.
- Keep Russian and English interface behavior consistent. Use approachable labels and preserve the simple default panel; diagnostics should be optional.
- Isolate corrupt history files so one device cannot break statistics for every device. Never fabricate zero when no measurement exists.
- Preserve the classic gameplay rollback. Do not reintroduce TrioSafety's arbiter or expensive per-frame motion tracking without explicit authorization and measured evidence.
- Do not remove the shared GPU synchronization lock without a multi-device stability benchmark. Do not claim GPU acceleration or smarter Think levels from an unmeasured change.

## Validation and releases

- Run `python -m unittest discover -s tests -q` from this repository using Python 3.13, plus relevant JS tests/syntax checks. Add regression coverage for real failure triggers, not assertions that simply mirror code.
- Test compiled updates in the frozen EXE with an isolated update home; require `/panel` and authenticated API health checks. Do not substitute source import success for frozen verification.
- Bootstrap files (`update_client.py`, `xlambot_launcher.py`) cannot be delivered by script updates. Bootstrap changes require a rebuilt EXE and verified installer/runtime delivery. State this limitation if delivery is incomplete.
- Verify signed pending updates; on failure try the last verified current/previous revision before bundled code. Never weaken signatures, hashes, path restrictions or ABI checks to make an update install.
- Publish script updates only with `tools/publish.py`; preserve its source provenance and immutable source revision tag. Never reuse a published revision or bypass failed source synchronization.
- Keep only the current installer in public GitHub Releases; distribution files belong in the repository. Explicitly target `Olegu621/xlamBOT`, since a checkout may track a different upstream.
- Never commit signing keys, real credentials, device profiles, match history, recordings, local paths or account screenshots.
- Report concrete changes, verification and remaining limitations. Do not claim all bugs are eliminated or performance improved without supporting checks.
