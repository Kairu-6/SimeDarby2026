# Cloudflare Pages deployment

Two Expo web exports are prepared: the resident/cleaner app and the iPad kiosk. Both use a Pages advanced-mode worker to forward `/api/*` to the Python backend over HTTPS. The browser therefore uses its own origin, avoiding mixed content and LAN-only API addresses. Hardware endpoints are deliberately not exposed by this public proxy.

The checked-in Wrangler configs use `https://api.example.com` as a placeholder. The deployment script replaces it with your `-ApiOrigin`; do not deploy the placeholder unchanged. Temporary preview hostnames recorded in verification notes are historical and may stop working.

The FastAPI/PyTorch vision service cannot run inside a static Pages export. Host Python separately, or keep the laptop running behind a Cloudflare Tunnel for a temporary preview. Use the API origin, without a path, as the script argument. The tunnel used during development runs an isolated sample-data database and disables hardware endpoints.

```powershell
# Authenticate locally; never paste a Cloudflare token into chat/source code.
wrangler login
wrangler whoami

# Build and publish both sites after authentication succeeds.
.\scripts\deploy-pages.ps1 -ApiOrigin https://YOUR-PYTHON-API-HOST

# Prepare both uploads without publishing (also works while login is unavailable).
.\scripts\deploy-pages.ps1 -ApiOrigin https://YOUR-PYTHON-API-HOST -BuildOnly
```

The default project names are `sime-loop-app` and `sime-loop-kiosk`; override with `-AppProject` and `-KioskProject`. The script checks for existing projects, builds each surface, copies `_worker.js`, `_routes.json` and `_headers`, writes Wrangler configs and deploys with Wrangler. No device key or Cloudflare credential is included in the web build. Confirm that any existing project with the chosen name belongs to this prototype before updating it.

After the real domains are known, set backend `PUBLIC_APP_URL` to the resident app's HTTPS URL. The kiosk build also receives that URL in `EXPO_PUBLIC_APP_URL` so its server-generated claim key opens the correct app. If Cloudflare assigns a suffixed domain because a name is unavailable, rebuild with the actual app URL rather than sharing a guessed hostname.

For actual hardware operation, use the private/LAN Python endpoint from the ESP32, set `DEMO_MODE=false`, and configure separate `DEVICE_API_KEY` and `KIOSK_API_KEY` values. Pair the tablet through its Connection settings. Restrict real kiosk access to the intended station/operator; the public preview's unauthenticated demo controls are for sample data only.

Both web sites depend on the configured API host. Static Pages assets remain published if the laptop stops, but live sessions, points and model inference need the API online. Quick Tunnel hostnames change on restart; update `API_ORIGIN` and redeploy when that happens.

Deployment references: [Pages Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/), [Wrangler Pages commands](https://developers.cloudflare.com/workers/wrangler/commands/pages/), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/).
