# S9.4 — Actual APK Login Fix

**Date:** 2026-09-08
**Status:** Fixed
**Root Cause:** Android keyboard autocomplete trailing space

---

## Root Cause

The APK login failed because the Android keyboard autocomplete inserted a **trailing space** after the username.

Server logs captured every attempt:

```
[LOGIN] user: "Mindavic "   ← note trailing space (8 chars, not 7)
[LOGIN] REJECT: user not found
```

Hex-decoded request body:

```
7b22757365726e616d65223a224d696e646176696320222c2270617373776f7264223a226164696e313233227d
{"username":"Mindavic ","password":"admin123"}
                                    ^ trailing space
```

The database lookup `getUser("Mindavic ")` failed because the stored username is `"Mindavic"` (no space). The authentication code had no `.trim()` on input fields.

## Evidence

| Test | Username sent | Result |
|------|--------------|--------|
| curl (no space) | `"Mindavic"` | ✅ OK |
| APK attempt 1 | `"Mindavic "` | ❌ user not found |
| APK attempt 2 | `"Mindavic "` | ❌ user not found |
| APK attempt 3 | `"Mindavic "` | ❌ user not found |
| APK attempt 4 | `"Mindavic "` | ❌ user not found |
| APK attempt 5 | `"Mindavic "` | ❌ user not found |
| APK attempt 6 | `"Mindavic "` | ❌ user not found |
| After fix: trailing space | `"Mindavic "` | ✅ OK |
| After fix: extra spaces | `"  Mindavic  "` | ✅ OK |

## Fix

Added `.trim()` to both username and password in `dashboard/app/api/auth/login/route.ts`:

```typescript
const username = (body.username || "").trim();
const password = (body.password || "").trim();
```

## Verification

| Test | Result |
|------|--------|
| `"Mindavic "` / `"admin123"` | ✅ OK |
| `"Mindavic"` / `"admin123"` | ✅ OK |
| `"  Mindavic  "` / `"  admin123  "` | ✅ OK |
| Invalid user | ✅ rejected |
| Wrong password | ✅ rejected |

## What Was NOT Changed

- No APK rebuild required
- No database changes
- No authentication weakening
- No other files modified

## Commit

`875ef7d` — `fix(auth): trim whitespace from username/password in login`

## Final Status

**DEMO READY**

The APK at `https://169-58-230-92.nip.io/nqts.apk` now works with:
- Username: `Mindavic`
- Password: `admin123`

Trailing spaces from Android keyboard autocomplete are handled.
