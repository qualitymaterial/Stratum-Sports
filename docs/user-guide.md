# Stratum Sports: The Market Intelligence User Guide

Stratum Sports is an institutional-grade **Market Intelligence Backbone** for NBA betting. We provide the intelligence layer that powers individual betting strategies, syndicates, and third-party analytics platforms.

This guide covers both **End-User Operations** (the Web Dashboard) and **Infrastructure Administration** (API and Webhook management).

---

## 1. Quick Links & Architecture

*   **Product Tiers:** [docs/product-tiers.md](file:///Users/briananderson/Documents/Prototypes/Stratum%20Sports/docs/product-tiers.md)
*   **Production Runbook:** [docs/production-runbook.md](file:///Users/briananderson/Documents/Prototypes/Stratum%20Sports/docs/production-runbook.md)
*   **API Root:** `http://localhost:8000/api/v1`
*   **Web Console:** `http://localhost:3000`

---

## 2. Access Tiers & Feature Matrix

### 🟢 Community (Free)
*   **Intelligence:** 10-minute delayed odds.
*   **Scope:** Watchlist capped at 3 games.
*   **Redaction:** Signal metadata is hidden (you see that a move happened, but not which books moved or the velocity).
*   **Exports:** CSV export is disabled.

### 🔵 Stratum Pro
*   **Intelligence:** Real-time odds and zero-latency signals.
*   **Discovery:** Full access to high-confidence signals (`STEAM`, `DISLOCATION`).
*   **Analytics:** Complete CLV (Closing Line Value) audit tools and performance scorecards.
*   **Alerts:** Push notifications via personal Discord Webhooks.

### 🟣 Infrastructure (Partner)
*   **Delivery:** Real-time Webhook dispatch of all market moves.
*   **Scale:** High-concurrency REST API access (120 req/min).
*   **Admin:** Webhook delivery logs, secret rotation, and HMAC signing verification.

---

## 3. End-User Operations (Dashboard)

### The Command Center (`/app/dashboard`)
The dashboard provides a real-time view of the NBA slate. 
*   **Consensus View:** Every game shows a "Consensus" line derived from 5+ major books (Pinnacle, Circa, etc.).
*   **Heat Indicators:** Small badges next to games indicate active market stress (e.g., `STEAM IN PROGRESS`).

### Game Analysis (`/app/games/[id]`)
*   **Movement Charts:** Visual delta of the consensus spread since the market opened.
*   **Context Score:** AI-driven analysis blending injury reports, player props, and pace data.
*   **Signal Log:** A chronological audit trail of exactly how the line moved.

---

## 4. Infrastructure Administration (Partner Only)

As a Partner, you interact with the system primarily via **Webhooks** and the **REST API**.

### Webhook Management
Manage your delivery endpoints from the **Partner Console** or via the API:
*   `POST /partner/webhooks`: Register a new endpoint.
*   `GET /partner/webhooks/logs`: Audit every signal delivery attempt (Status codes, Latency, Errors).
*   `POST /partner/webhooks/{id}/secret`: Rotate your signing secret for security compliance.

### Verifying Signatures (Security)
Every webhook delivery includes an `X-Stratum-Signature` header. This is an HMAC-SHA256 hash of the JSON payload created using your **Webhook Secret**. 

**Implementation Example (Python):**
```python
import hmac
import hashlib

def verify_stratum_webhook(payload_body, secret_key, received_signature):
    expected_sig = hmac.new(
        secret_key.encode(),
        msg=payload_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_sig, received_signature)
```

### Signal Types (Payload Glossary)
| Event | Trigger | Value |
| :--- | :--- | :--- |
| `signal.detected` | A major market move or sync event. | Real-time |
| `signal.clv_finalized` | Signal cross-referenced with Close. | ~60m post-commence |
| `system.limit_alert` | API quota nearing 90% utilization. | Immediate |

---

## 5. Billing & Scaling

*   **Individual Users:** Managed via the "Billing" link in the header. Subscriptions are billed monthly via Stripe.
*   **Infrastructure Partners:** Onboarding is managed by the account team. If you hit your **Soft Limit** (50,000 monthly signals), the system will fire an anomaly alert to your designated admin channel. Overage pricing is automatically applied at **$2.00 per 1,000 requests** unless upgraded to an Enterprise plan.

---

## 6. Operator Deployment (Running Locally)

### Prerequisites
- Docker Desktop
- The Odds API Key (`ODDS_API_KEY`)

### Start the Stack
```bash
cp .env.example .env
docker compose up --build
```

### Health Checks
- **Liveness:** `http://localhost:8000/api/v1/health/live` (Checks if API is responsive)
- **Readiness:** `http://localhost:8000/api/v1/health/ready` (Checks DB and Redis connections)

---

## 7. Troubleshooting

| Symptom | Check |
| :--- | :--- |
| **Empty Dashboard** | Verify `worker` container logs for "Odds ingestion cycle completed". |
| **No Signals** | Signals require market movement. Check a game closer to tip-off (2-3 hours prior). |
| **Webhook Timeouts** | Ensure your server responds with a `200 OK` within 5 seconds. |
| **Rate Limit Errors** | Check `X-RateLimit-Remaining` headers in your API responses. |

---

## 8. Support
- **Technical Support:** `dev-support@stratumsports.com`
- **Billing Questions:** `billing@stratumsports.com`
- **Sales & API Access:** `api-access@stratumsports.com`
