# API usage examples

These examples exercise the public authentication lifecycle and operational
endpoints against a local server. Start the application with `python
scripts/dev.py serve` and use `http://127.0.0.1:8000` as the base URL.

The generated OpenAPI document at `/docs` remains the source of truth for all
request and response schemas.

## Register a user

```bash
curl --request POST http://127.0.0.1:8000/register/ \
  --header "Content-Type: application/json" \
  --data '{"username":"alice","password":"replace-this-password","email":"alice@example.com"}'
```

Example response:

```json
{
  "id": 1,
  "username": "alice",
  "role": "user",
  "email": "alice@example.com",
  "email_verified_at": null
}
```

Email is optional, normalized to lowercase, and unique when supplied. Usernames
must also be unique. Treat passwords used in examples as disposable local
values, never production credentials.

## Verify an email address

Email delivery is disabled by default. After configuring SMTP, request a
verification message with the same response for known, unknown, and already
verified addresses:

```bash
curl --request POST http://127.0.0.1:8000/auth/email-verification/request \
  --header "Content-Type: application/json" \
  --data '{"email":"alice@example.com"}'
```

The email contains a time-limited opaque token. The API never returns that raw
token. The frontend submits the token from the link:

```bash
curl --request POST http://127.0.0.1:8000/auth/email-verification/confirm \
  --header "Content-Type: application/json" \
  --data '{"token":"paste-token-from-verification-link"}'
```

Successful confirmation is single use. Expired, consumed, unknown, and
wrong-purpose tokens all receive the same generic `400` response.

## Reset a forgotten password

Password recovery is available only for active accounts with a verified email,
but the request endpoint always returns the same `202` response. This prevents
clients from discovering which accounts exist:

```bash
curl --request POST http://127.0.0.1:8000/auth/password-reset/request \
  --header "Content-Type: application/json" \
  --data '{"email":"alice@example.com"}'
```

The reset email contains an opaque, time-limited token. Submit it with a new
password of at least 12 characters and no more than 72 UTF-8 bytes:

```bash
curl --request POST http://127.0.0.1:8000/auth/password-reset/confirm \
  --header "Content-Type: application/json" \
  --data '{"token":"paste-token-from-reset-link","new_password":"replace-with-a-long-new-password"}'
```

A successful reset consumes all outstanding password-reset tokens and revokes
every refresh token for the account. It does not issue a new session. Existing
JWT access tokens are stateless and remain valid until their configured expiry.

## Log in

The login endpoint follows the OAuth2 password form convention, so its body is
form encoded rather than JSON:

```bash
curl --request POST http://127.0.0.1:8000/login/ \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=alice" \
  --data-urlencode "password=replace-this-password"
```

Example response:

```json
{
  "access_token": "eyJ...",
  "refresh_token": "opaque-random-value",
  "token_type": "bearer"
}
```

Set the returned values in your shell for the next examples:

```bash
ACCESS_TOKEN="paste-access-token"
REFRESH_TOKEN="paste-refresh-token"
```

Access tokens are JWTs and are short lived. Refresh tokens are opaque secrets;
the database stores only their hashes.

## Read the current user

```bash
curl http://127.0.0.1:8000/auth/me \
  --header "Authorization: Bearer ${ACCESS_TOKEN}"
```

Example response:

```json
{
  "id": 1,
  "username": "alice",
  "role": "user"
}
```

Missing, malformed, expired, or otherwise invalid access tokens return `401`.

## Rotate a refresh token

```bash
curl --request POST http://127.0.0.1:8000/auth/refresh \
  --header "Content-Type: application/json" \
  --data "{\"refresh_token\":\"${REFRESH_TOKEN}\"}"
```

The response has the same shape as login. Replace both local token variables
with the new values. A successful rotation revokes the submitted refresh token,
so replaying it returns `401`.

## Log out

```bash
curl --request POST http://127.0.0.1:8000/auth/logout \
  --header "Content-Type: application/json" \
  --data "{\"refresh_token\":\"${REFRESH_TOKEN}\"}"
```

Logout revokes the refresh token. Existing access tokens remain valid until
their configured expiration; clients should discard both tokens locally.

## Call an admin endpoint

Admin routes require an access token whose current database user has the
`admin` role. Registration never grants this role and the API does not provide
a public self-promotion path.

```bash
ADMIN_ACCESS_TOKEN="paste-admin-access-token"

curl http://127.0.0.1:8000/admin/users \
  --header "Authorization: Bearer ${ADMIN_ACCESS_TOKEN}"
```

To change an existing user's role as an admin:

```bash
curl --request PATCH http://127.0.0.1:8000/admin/users/1/role \
  --header "Authorization: Bearer ${ADMIN_ACCESS_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{"role":"admin"}'
```

Non-admin users receive `403`; an unknown user ID returns `404`.

## Inspect health and metrics

```bash
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:8000/metrics
```

Liveness confirms that the process can respond. Readiness additionally checks
database connectivity. Restrict `/metrics` to trusted monitoring networks in
production.

## Trace a request with a correlation ID

```bash
curl --include http://127.0.0.1:8000/health/live \
  --header "X-Request-ID: docs-example-001"
```

The response includes the validated `X-Request-ID`, and the same value appears
in the structured request log. Invalid IDs are replaced rather than trusted.

## PowerShell authentication flow

```powershell
$baseUrl = "http://127.0.0.1:8000"

Invoke-RestMethod -Method Post -Uri "$baseUrl/register/" `
  -ContentType "application/json" `
  -Body '{"username":"alice","password":"replace-this-password"}'

$tokens = Invoke-RestMethod -Method Post -Uri "$baseUrl/login/" `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{ username = "alice"; password = "replace-this-password" }

$headers = @{ Authorization = "Bearer $($tokens.access_token)" }
Invoke-RestMethod -Uri "$baseUrl/auth/me" -Headers $headers

$rotated = Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/refresh" `
  -ContentType "application/json" `
  -Body (@{ refresh_token = $tokens.refresh_token } | ConvertTo-Json)

Invoke-RestMethod -Method Post -Uri "$baseUrl/auth/password-reset/request" `
  -ContentType "application/json" `
  -Body '{"email":"alice@example.com"}'
```

## Error response conventions

Expected client errors use a JSON `detail` field and include `X-Request-ID`:

```json
{
  "detail": "Invalid username or password"
}
```

Unexpected errors return a generic `500` response without leaking internal
exception details. Use the correlation ID to locate the matching structured
log entry.
