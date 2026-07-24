# Date/Time Contract and Firmware Integration

This document describes the project's conventions for date/time values across the
backend, frontend (SPA) and device firmware (ESP32). It also lists the recommended
payload and headers for the firmware and guidance for developers.

## Summary (short)
- Backend stores and returns ISO datetimes as naive UTC strings in the format
  `YYYY-MM-DDTHH:MM:SS` (no timezone suffix). Example: `2025-10-26T13:55:57`.
- Backend `EventPayload` accepts ISO strings that are timezone-aware; they are
  converted to naive UTC internally (tz information normalized to UTC then
  dropped). Tests enforce this behavior (`tests/test_datetime_contracts.py`).
- Frontend must display times in the user's local timezone. The SPA should
  receive ISO naïve UTC strings from backend and convert them using the
  browser's Date or Intl APIs. Example (JS):

```js
const dt = new Date('2025-10-26T13:55:57Z'); // append Z if treating as UTC
const formatted = new Intl.DateTimeFormat(undefined, { dateStyle: 'short', timeStyle: 'short' }).format(dt);
```

Note: the frontend code may append a `Z` when parsing naive UTC strings (safe)
or parse and treat them explicitly as UTC using a library such as Luxon.

## Firmware (ESP32) payload and headers

Preferred approach for devices sending events:

- Endpoint: POST /api/eventos
- Content-Type: application/json
- Headers:
  - `X-Device-Id`: unique device id (string)
  - (optional) `Authorization` or `X-Admin-Token` for admin operations (not for normal devices)

Sample JSON payload (single event):

```json
{
  "device_id": "ESP32-01",
  "paciente_id": "PAC-0001",         
  "cama_id": "201A / Leito 1",
  "postura": "supino",
  "confianca": 0.95,
  "amostra_ms": 60000,
  "ts_utc": "2025-10-26T13:55:57Z",
  "pressao_pico": null
}
```

Guidelines:
- Send timestamps in UTC when possible (append `Z`) or include timezone offset.
- Backend will normalize tz-aware timestamps to UTC (tests ensure normalization).
- For bulk uploads, POST `/api/grade` with a JSONL file is supported (each line a
  JSON event). This is efficient for batched uploads.

## Admin import endpoint (developer convenience)

The app includes an admin import helper and an admin HTTP endpoint that accepts
either a JSON list or a JSONL file to import alert records directly into the
database. This is intended for development and controlled import use only.

- Endpoint: POST /api/admin/import_alerts
- Accepts: multipart file upload (JSONL) or application/json body (array of alerts)
- Security: requires either an environment variable `UPP_ADMIN_TOKEN` to be set
  and the caller to supply header `X-Admin-Token: <token>`, or (fallback for dev)
  a valid session cookie `session_user` (i.e., logged-in user).

Alert record minimal shape (accepted by DAO `inserir_alertas`):

```json
{
  "paciente_id": "PAC-0001",
  "inicio": "2025-10-26T13:55:57",
  "tipo": "imobilidade",
  "perfil": "alto",            
  "janela_min": 120,
  "status": "aberto"
}
```

Notes on security: do not expose the admin import endpoint publicly without
authentication. For production use, prefer using an administrative interface
behind additional auth/ACL.

## Frontend responsibilities
- Always treat incoming ISO strings from the backend as UTC and convert them to
  local time for display.
- When sending timestamps to the backend from the frontend (if any), send
  ISO strings in UTC.

## Tests
- Contract tests exist in `tests/` and validate normalization and formats. Keep
  these tests green in CI to prevent regressions.

## Summary checklist for developers
- [ ] Firmware: send ISO UTC timestamps or timezone-aware strings.
- [ ] Backend: continues to return naive ISO UTC strings; document any change.
- [ ] Frontend: format for display using Intl/Luxon and do not store local-only
  formatted strings as canonical values.
