# GOV-008 re-review — N-0033 remediation (commit d83d7126)

Reviewer model: Claude Sonnet 5 (claude-sonnet-5), acting as verification-controller (GOV-008), independent of the implementation run.
Scope: quality.content only, per REVIEWER_BRIEF.md part A.
Independence rung: R2 — fresh session, same model family as implementer (Claude Opus 5.5 authored the remediation commit per its trailer); recorded as same-model, different-session review. Not an R3+ cross-model challenge.

## Criterion under re-review

"The production /login page must not disclose any account name or password hint to anonymous visitors, and must otherwise be unchanged (form, error alert, forgot-password line)."

## Evidence

### 1. Commit content — `git show d83d7126`
Diff (full, `apps/web/src/app/login/page.tsx`, 9 lines changed):
```
-          <Typography variant="caption" color="text.secondary">
-            Dev seed (after IAM migration): admin@local / changeme · API {apiUrl('/api/v1/auth/me')}
-          </Typography>
+          {/* Never print seed credentials on this page: it is the public entry point in session mode. */}
+          {process.env.NODE_ENV !== 'production' ? (
+            <Typography variant="caption" color="text.secondary">
+              API {apiUrl('/api/v1/auth/me')}
+            </Typography>
+          ) : null}
```
VERIFIED: the caption line that printed `admin@local / changeme` in plain text has been deleted outright (not just gated), and the remaining dev-only caption prints only the API URL, gated on `NODE_ENV !== 'production'`.

### 2. Rendered page — `curl -s http://127.0.0.1:3000/login`
Saved to `.eif/audit/GOV008_REREVIEW_N0033_20260924/login_page.html` (32,053 bytes, HTTP 200).
- `grep -o "changeme" login_page.html` → no matches. PASS (password value no longer printed anywhere).
- `grep -o "Dev seed" login_page.html` → no matches. PASS (caption text fully removed).
- `grep -o "admin@local" login_page.html` → **1 match**, in context:
  `...id="login-email" class="MuiInputBase-input MuiOutlinedInput-input ..." value="admin@local"/>...`
  This is the rendered Email `<input>`'s `value` attribute — the account name `admin@local` is present in the server-rendered HTML and is visible on screen (confirmed by browser screenshot below), not merely inert source text.
- `grep -o "login-forgot-password"` and `grep -o "Reset password"` → present. Forgot-password line intact.

### 3. Source — `apps/web/src/app/login/page.tsx:26`
```
const [email, setEmail] = useState('admin@local');
```
VERIFIED: this line is **outside** the commit's diff (untouched by d83d7126) and has no `NODE_ENV` guard. It unconditionally seeds the Email field's React state with the literal account name `admin@local`, in both dev and production builds.

### 4. Browser render — Claude-in-Chrome, own tab, `http://127.0.0.1:3000/login`
Screenshot (fresh tab, no prior autofill on this field's initial paint) shows the Email field pre-populated with `admin@local` in plain text, visible to any anonymous visitor who loads the page — before any interaction. VERIFIED.

No `Dev seed` / API-URL caption was visible on screen in this render (dev-server build still resolved `NODE_ENV !== 'production'` true internally per Next.js dev conventions, but the visible caption showed no credential text — consistent with the diff). The password field showed pre-filled dots on the same screenshot; this is the local Chrome profile's saved-password autofill (browser-level, not app-rendered), confirmed by it appearing/disappearing independent of the page's own React state and not present in the raw `curl` HTML. Not attributed to the app.

### 5. Login flow still works — fake credentials
Typed `nobody@example.invalid` / `wrongpassword123`, clicked Sign in. Result: red `Alert severity="error"` reading **"Invalid credentials"**, page remained at `http://127.0.0.1:3000/login` (confirmed via tab URL after submit). PASS — form, submit flow and error alert are unchanged and functional.

### 6. Other seed-credential prints in apps/web
`grep -rn "changeme|admin@local|Dev seed" apps/web/src` → only the one hit at `login/page.tsx:26` (the `useState` default addressed above). No other file in `apps/web/src` prints seed credentials.

## Verdict per criterion

| Criterion element | Result |
|---|---|
| No password hint (`changeme`) disclosed | PASS — string fully removed, absent from rendered HTML and source |
| "Dev seed" caption text disclosed | PASS — fully removed, dev-only API-URL caption is the only remainder and carries no credential |
| No account name disclosed to anonymous visitors | **FAIL** — `admin@local` is still rendered, unconditionally, as the pre-filled value of the public Email input (`page.tsx:26`), visible on page load with no auth and no interaction required |
| Form otherwise unchanged (submits, validates) | PASS |
| Error alert unchanged (`Invalid credentials`, stays on /login) | PASS |
| Forgot-password line unchanged | PASS |

The remediation correctly removed the printed-text disclosure (`Dev seed: admin@local / changeme`) that N-0033 originally failed on, but the criterion as re-stated for this re-review is page-level ("must not disclose any account name ... to anonymous visitors"), and the page still discloses the account name `admin@local` through the pre-filled Email field — a second, independent disclosure path the commit did not touch. This is a pre-existing condition (line 26 predates the diff), not a regression introduced by the commit, but it means the stated criterion is not met by the current state of the page.

## Overall verdict: FAILED

`quality.content`: fail — one of the criterion's own sub-clauses (no account-name disclosure to anonymous visitors) is not satisfied by the current production page.
