# FlightsBot

<img src="assets/plane.svg" alt="Stylized airliner taking off" width="260">

Monitors Aeroitalia flight availability and sends a push notification to your phone
when flights appear or disappear on a route.

It queries the Aeroitalia booking API every 5 minutes and compares the list of flights
with the previous run. If anything changes, it sends a notification through **Gotify**
(a self-hosted notification server), reachable from outside the home network via a
Cloudflare tunnel.

---

## Contents

- [Components](#components)
- [Quick start](#quick-start)
- [Changing dates and route](#changing-dates-and-route)
- [Notifications: Gotify](#notifications-gotify)
- [Access from outside: Cloudflare tunnel](#access-from-outside-cloudflare-tunnel)
- [Authentication: JWT and subscription key](#authentication-jwt-and-subscription-key)

---

## Components

Three Docker containers, plus one process on the PC for external access.

| Component           | What it does                             | Container                 |
| ------------------- | ---------------------------------------- | ------------------------- |
| `monitor_single.py` | Monitors **a single date**               | `flightsbot-app-1`        |
| `monitor_multi.py`  | Monitors **several dates** per cycle     | `flightsbot-app-multi-1`  |
| Gotify              | Notification server, port 9000           | `flightsbot-gotify-1`     |
| `cloudflared`       | Exposes Gotify on `gotify.aibtc.finance` | Windows process (service) |

The two scripts are independent: they can run together, separately, or one can be shut
down. They use distinct state files, so they never interfere with each other.

## Quick start

**`monitor_single.py` only (original setup):**

```powershell
docker compose up -d
```

**Including `monitor_multi.py`:** this needs the overlay file, and **both** `-f` flags
must be passed.

```powershell
docker compose -f docker-compose.yml -f docker-compose.multi.yml up -d app-multi
```

> Naming `app-multi` explicitly at the end matters: without it, Compose reconciles every
> service and may recreate `app` and `gotify` too.

**Useful commands:**

```powershell
# container status
docker ps -a

# live logs
docker logs -f flightsbot-app-1
docker logs -f flightsbot-app-multi-1

# stop
docker compose stop app
docker compose -f docker-compose.yml -f docker-compose.multi.yml stop app-multi
```

---

## Changing dates and route

### `monitor_multi.py` → edit and restart (no build)

The script is **mounted as a volume**, so the container reads the file straight from
disk. Edit the top of the file:

```python
ORIGIN = "CAG"
DESTINATION = "LIN"
DATES = ["2026-08-22", "2026-08-23"]
ADULTS = 1
```

Then:

```powershell
docker compose -f docker-compose.yml -f docker-compose.multi.yml restart app-multi
```

### `monitor_single.py` → edit and **rebuild**

This script is **copied into the image** at build time (`COPY monitor_single.py .` in the
Dockerfile). Editing the file on disk has no effect until the image is rebuilt:

```python
DATE = "2026-08-22"
```

```powershell
docker compose up -d --build app
```

### After changing dates

- Old dates stay in `flight_state_multi.json` as orphan entries: harmless, but the file
  can be reset to `{}` for cleanliness.
- The initial report is sent again on restart: `first_run` resets every time the process
  starts.

---

## Notifications: Gotify

**From home:** <http://192.168.1.137:9000>
**From outside:** <https://gotify.aibtc.finance>

The phone needs the **Gotify** app (Play Store). It uses an always-open WebSocket rather
than Google push, so the connection has to stay alive to receive notifications.

### The token

`GOTIFY_TOKEN` is the token of an _application_ created inside Gotify, and it is set as an
environment variable in **two separate places**:

- `docker-compose.yml` → `app` service
- `docker-compose.multi.yml` → `app-multi` service

If it gets rotated, both must be updated.

The `GOTIFY_URL` variable present in `docker-compose.yml` is **ignored**. Therefore:

- the IP `192.168.1.137` is the PC's address on the home network, assigned via **DHCP**:
  if the router changes it, notifications silently stop being delivered;
- for the same reason, moving the project to another PC requires editing that line in
  both scripts.

A static DHCP lease on the router avoids the first problem.

---

## Access from outside: Cloudflare tunnel

The public domain is **<https://gotify.aibtc.finance>**, served by a Cloudflare
_named tunnel_. No port is open on the router: it is the PC that opens an outbound
connection to Cloudflare.

### How it works

It is a **remotely-managed** tunnel: the configuration (which hostname maps to which local
service) lives **only in the Cloudflare dashboard**. There is no config file on the PC —
only the **token**, which the connector uses to authenticate and download the config.

The rule currently configured is:

```
gotify.aibtc.finance  →  HTTP  →  192.168.1.137:9000
```

The _connector_ is not an object to be created in the dashboard: **it is the `cloudflared`
process running on the PC**. An empty connector list simply means the process is not
running.

## Authentication: JWT and subscription key

The Aeroitalia API requires two credentials, both of which expire.

**`jwt.txt`** — `Bearer` token. It regenerates **by itself**: when the API returns `401`,
the script launches Playwright, opens `aeroitalia.com` in headless Chromium, simulates a
flight search and intercepts the `Authorization` header from the site's own calls, saving
it.

**`subkey.txt`** — Azure subscription key (`Ocp-Apim-Subscription-Key`). It is rotated
periodically by Aeroitalia and **does not regenerate by itself**. Once expired, every call
returns `401` permanently and it must be updated by hand.
