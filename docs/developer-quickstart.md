# 🚀 Stratum Sports: Developer Quickstart

Welcome to the **Market Intelligence Backbone**. This guide will take you from "Zero to First Signal" in under 5 minutes. 

Stratum provides the infrastructure you need to build professional betting tools, proprietary trading algorithms, and institutional-grade analytics.

---

## 1. Get Your Access
1.  **Whitelist & Tier:** Ensure your account is upgraded to the **Infrastructure Tier** ($149/mo).
2.  **The Portal:** Navigate to the [Infrastructure Portal](/app/developer). This is your command center for keys, logs, and monitoring.
3.  **API Key:** Generate your access token in the **Portal**. This token is used in your `Authorization: Bearer <token>` header for all REST calls.
4.  **Webhooks:** Add your first endpoint in the **Portal**. You will immediately receive a **Webhook Secret** (e.g., `whsec_...`).

---

## 2. Your First Request
The easiest way to see what's happening in the market right now is the `signals` feed.

```bash
curl -X GET "https://api.stratumsports.com/api/v1/intel/signals?min_score=75&market=spreads" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

**Response Snapshot:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "event_id": "nba_lal_gsw_2024",
    "signal_type": "STEAM",
    "direction": "UNDER",
    "strength_score": 92,
    "created_at": "2024-02-27T18:00:00Z"
  }
]
```

---

## 3. Listen for Real-Time Moves (Webhooks)
Don't poll us—let us push to you. 

### Step 1: Set up a Listener
Configure your server to receive POST requests. Your endpoint must return a `200 OK` within **5 seconds** to prevent retries.

### Step 2: Live Monitoring (Infrastructure Portal)
Once your listener is live, use the **Delivery Logs** in the Portal to:
*   **Audit Status:** See real-time HTTP response codes from your server.
*   **Measure Latency:** Track the "relay-to-receive" time (ms) to ensure your execution bot is competitive.
*   **Debug Failures:** Review error payloads and retry attempts.

### Step 3: Verify the Signature
    Every payload is signed using your `whsec_...` key. **Never trust an unsigned request.**

**Python (FastAPI) Example:**
```python
from fastapi import FastAPI, Request, Header, HTTPException
import hmac, hashlib

app = FastAPI()
STRATUM_SECRET = "your_whsec_here"

@app.post("/webhook")
async def handle_stratum_signal(request: Request, x_stratum_signature: str = Header(None)):
    body = await request.body()
    
    # Verify signature
    mac = hmac.new(STRATUM_SECRET.encode(), body, hashlib.sha256)
    if not hmac.compare_digest(mac.hexdigest(), x_stratum_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Process signal
    payload = await request.json()
    print(f"Detected {payload['event']} for {payload['event_id']}")
    return {"status": "ok"}
```

---

## 4. Test Without Waiting (The Simulator)
Market moves don't happen on a schedule. To test your integration right now, use our **Signal Simulator**.

1.  **Open two terminals.**
2.  In Terminal 1, start your local listener.
3.  In Terminal 2, run the Stratum Test Utility:

```bash
# This forces a "STEAM" move payload to your local endpoint
python backend/scripts/test_webhook.py --url http://localhost:8000/webhook --secret whsec_test
```

---

## 5. What Can You Build?
Stratum is the "Intelligence Layer." Here are few patterns we support:

*   **⚡ Automated Execution:** Listen for `STEAM` signals > 90 score and automatically fire orders via your bookmaker API.
*   **📡 Discord/Telegram Bots:** Pipe `signal.detected` events into private channels for your syndicate.
*   **📊 Performance Auditor:** Use the `signal.clv_finalized` event to audit how much alpha your own betting models are generating vs. the closing line.

---

## 6. Monitoring & Quotas
Track your consumption in real-time via the **Metered Usage** dashboard in the Portal:
*   **Infrastructure Tier:** Includes 50,000 monthly deliveries.
*   **Rate Limits:** 120 requests per minute by default.
*   **Status Indicators:** A green "Live Update Active" light in the Portal confirms your data stream is synchronized with the Stratum backbone.

---

## 💡 Pro Tip: The "Close Capture" Advantage
We boost our polling frequency to **60s** during the "Golden Hour" (60 minutes before tip-off). If you are building an execution bot, listen for signals in this window for the highest liquidity and most accurate CLV projections.

---
**Need Help?** Join our [Developer Discord](#) or email `dev-support@stratumsports.com`.
