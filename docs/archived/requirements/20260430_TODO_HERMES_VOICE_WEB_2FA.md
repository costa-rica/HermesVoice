# HermesVoice Web 2FA TODO

## Phase 1: Auth Tests

- [x] Add failing tests for allowed web email parsing.
- [x] Add failing tests for email/password login starting a 2FA challenge without setting a session cookie.
- [x] Add failing tests for successful, incorrect, expired, and reused verification codes.

## Phase 2: 2FA Implementation

- [x] Add web email allow-list configuration.
- [x] Add in-memory, expiring, one-time login challenges.
- [x] Add SMTP-backed verification code delivery behind a testable service function.
- [x] Update login routes and HTML for email/password plus code verification without JavaScript.
- [x] Preserve API key authentication for non-browser websocket use.

## Phase 3: Verification

- [x] Run the full API test suite.
- [x] Run a secret filename scan before committing.
- [x] Commit feature, tests, and TODO updates without pushing.
