# ADR 0010: OAuth flow for activity 8: authorization code with PKCE and managed login

## Context

Activity 8 gets tokens with the scopes of ADR 0009 from a script. Self-sign-up is off.

## Alternatives

- **(a)** Authorization code with PKCE through managed login. The tokens come from a browser sign-in; the script never
  handles the password.
- **(b)** `USER_PASSWORD_AUTH` from the script. Simple and headless, but the script sends the password.

## Decision

**(a)** for the design. The exact managed login steps (callback, scopes requested, app client settings) are **not
verified** in the documentation yet; they are verified before activity 8.

## Consequences

- An app client without secret, with the authorization code grant and PKCE, and the scopes of ADR 0009.
- If (a) makes activity 8 impractical headless, the fallback is (b), recorded as an exception with its reason.
