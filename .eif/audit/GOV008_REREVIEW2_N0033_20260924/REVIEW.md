# GOV-008 independent re-review 2 — N-0033 (/login content disclosure)

Reviewer: verification-controller (independent). Model identity: Claude Sonnet 5 (claude-sonnet-5), Anthropic, knowledge cutoff January 2026.
Date: 2026-09-24. App under test: http://127.0.0.1:3000 (restarted immediately before this review; `/login` returned HTTP 200 on first poll).

Commits reviewed: `d83d7126` ("web: stop printing seed credentials on /login (N-0033 GOV-008 content fail); API URL caption dev-only") and `83895f01` ("web: /login email starts empty (no account name disclosed; N-0033 re-review); test pins it; stale grid-height comments after 99a89db8").

## Criterion: no seed caption disclosed to anonymous visitors

- `git show d83d7126 -- apps/web/src/app/login/page.tsx`: removes the unconditional `Typography` reading `Dev seed (after IAM migration): admin@local / changeme · API {apiUrl(...)}` and replaces it with an `API {apiUrl(...)}` caption gated behind `process.env.NODE_ENV !== 'production'`. VERIFIED (diff read).
- Current source `apps/web/src/app/login/page.tsx:115-120`: the seed-credential caption is gone entirely; only a dev-only API-URL caption remains, and it is excluded in production builds. VERIFIED (file read).
- Rendered HTML: `curl http://127.0.0.1:3000/login` piped to grep found zero occurrences of `admin@local`, zero of `changeme`, and zero of the string `Dev seed`. VERIFIED (command output).

## Criterion: no pre-filled email disclosed to anonymous visitors

- `git show 83895f01 -- apps/web/src/app/login/page.tsx`: changes `useState('admin@local')` to `useState('')` for the email field. VERIFIED (diff read).
- Current source line 26: `const [email, setEmail] = useState('');`. VERIFIED (file read).
- Server-rendered HTML: `data-testid="login-email"` input has `value=""`. VERIFIED (curl output).
- Chrome render: on first load, the email field visually showed `admin@local` and the password field showed masked dots, both highlighted with the browser's autofill tint. This looked like a regression at first glance, so it was checked programmatically: `document.querySelector('[data-testid="login-email"]').value` returned `""` and `.matches(':-webkit-autofill')` returned `true` for both fields. This is Chrome's own saved-password autofill overlay (explicitly flagged in the reviewer brief as not app behaviour) rendering over an input whose real DOM/React value is empty — not a disclosure by the app. VERIFIED (JS evaluation of underlying `.value` vs. autofill pseudo-class; screenshot descriptions: first screenshot shows blue-highlighted fields with `admin@local` visible, JS probe immediately after shows real value `""`).

## Criterion: form works; fake login shows "Invalid credentials"; stays on /login; forgot-password line present

- Typed `nobody@example.invalid` / `wrong` into the (cleared) fields and clicked Sign in. Screenshot after submit shows an MUI `Alert` reading "Invalid credentials", URL remained `http://127.0.0.1:3000/login`, and the "Forgot password? Ask an admin to use **Reset password** on Administration → Users & roles." line is present below the button. VERIFIED (screenshot).
- Direct API check: `curl -X POST http://127.0.0.1:3000/api/v1/auth/login -d '{"email":"nobody@example.invalid","password":"wrong"}'` returned `HTTP 401` with body `{"detail":"Invalid credentials"}`, confirming the UI alert text matches the backend's rejection. VERIFIED (curl output).

## Tests

- `pnpm --filter @cip/web exec vitest run src/app/login` → 1 test file, 1 test passed (`page.test.tsx`: "discloses no account name or password hint (public entry point in session mode)" — asserts rendered text does not match `/changeme|admin@local|dev seed/i` and `login-email` has value `''`). VERIFIED (command output, exit via passed summary).

## Grep for other seed-credential disclosures

- `grep -rniE "admin@local|changeme|dev seed|seed credential" apps/web/src --include="*.ts*"` (excluding the new test file) matched only a code comment: `apps/web/src/app/login/page.tsx:115` — `{/* Never print seed credentials on this page... */}`, which is a comment, not rendered output. No other seed-credential disclosure found in `apps/web/src`. VERIFIED (grep output). Note: this grep covers `apps/web/src` only, with the pattern set given in the brief; it does not prove absence elsewhere in the repo (e.g. `apps/api`, docs) — out of scope for this UI-content criterion but noted as a coverage limitation.

## Overall verdict: VERIFIED

All criteria pass with direct evidence (commits, rendered HTML, live browser interaction distinguishing app state from browser-native autofill, passing test, and a repo grep). No FAIL. One limitation noted: the seed-credential grep was scoped to `apps/web/src` only, per the brief's instruction, not repo-wide.
