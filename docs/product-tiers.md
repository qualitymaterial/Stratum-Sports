# Stratum Sports: Product Tiers & Customer Segments

Stratum Sports is positioned as a **Market Intelligence Backbone** for NBA betting. We provide the intelligence layer that powers everything from individual betting strategies to institutional-grade analytics platforms.

Depending on your goals—whether you are looking for an edge in your weekly plays or building a multi-million dollar betting fund—we have a tier designed for your workflow.

---

## 1. Segment Overview

| Tier | Target User | Buying Motivation | Primary Interface |
| :--- | :--- | :--- | :--- |
| **Community (Free)** | Curious Bettor | "Show me value." | Web Dashboard (Delayed) |
| **Stratum Pro** | Serious / Pro Bettors | "Give me an edge." | Real-time Web + Discord Alerts |
| **Infrastructure (API)** | Builders / Funds / Tools | "Let me build on it." | Webhooks + REST API + Commercial Rights |

---

## 2. Tier Details

### 🟢 Community Tier (Free)
*Best for: Users learning market dynamics and tracking seasonal trends.*

*   **Market Data:** NBA odds delayed by **10 minutes**.
*   **Watchlist:** Track up to **3 games** simultaneously.
*   **Signals:** Access to historical signals and basic "Heat" indicators.
*   **Redaction:** Signal metadata (velocity, book components, and exact score breakdowns) is hidden.
*   **Alerts:** Not available.

### 🔵 Stratum Pro
*Best for: Professional bettors, syndicates, and high-volume traders.*

*   **Real-time Intelligence:** Zero-delay access to the Stratum Signal Engine.
*   **Discord Alerts:** Real-time push notifications for `STEAM`, `DISLOCATION`, and `KEY_CROSS` events.
*   **Full Diagnostics:** Deep dive into every signal, including which books moved first and the exact velocity of the move.
*   **CLV Management:** Automated tracking of Closing Line Value (CLV) to audit your execution quality.
*   **Performance Analytics:** 1-click signal quality presets to filter for "High Confidence" or "Low Noise" moves.
*   **Data Portability:** 1-click CSV exports for custom external modeling.

### 🟣 Infrastructure Tier (API & Partner)
*Best for: Betting tool makers, analytics sites, and quant funds building proprietary software.*

*   **Webhooks:** Real-time push delivery of every signal and CLV event directly to your server.
*   **Institutional Limits:** High-concurrency REST API access (**120 req/min**).
*   **Commercial Rights:** Permitted use of Stratum data in 3rd party applications or client-facing tools.
*   **Anomaly Monitoring:** Real-time monitoring of your API consumption with dedicated support.
*   **Historical Data:** Programmatic access to the full historical library of signals and consensus movements.

---

## 3. Infrastructure Partner Commercials

The Infrastructure tier is further segmented by scale and technical requirements:

| Plan | Pricing | Target | Features |
| :--- | :--- | :--- | :--- |
| **Builder** | $49/mo | Individual Devs | 30 req/min, 1 Webhook |
| **Pro Infra** | $149/mo | Growing Apps / Small Funds | 120 req/min, 5 Webhooks, Soft Limit 50k/mo |
| **Enterprise** | Contact Sales | Large Platforms / High Freq Labs | Custom limits, Dedicated Webhook queue, SLA |

---

## 4. Feature Matrix Comparison

| Feature | Community | Pro | Infrastructure |
| :--- | :---: | :---: | :---: |
| Real-time Odds | ❌ (10m delay) | ✅ | ✅ |
| Signal Metadata | ❌ (Redacted) | ✅ | ✅ |
| Discord Push Alerts | ❌ | ✅ | ✅ |
| Webhook Support | ❌ | ❌ | ✅ |
| CLV Tracking | ❌ | ✅ | ✅ |
| REST API Keys | ❌ | ❌ | ✅ |
| Commercial Usage | ❌ | ❌ | ✅ |
| CSV Data Export | ❌ | ✅ | ✅ |

---

## 5. Transitioning Between Tiers

*   **To Stratum Pro:** Upgrade instantly via the Dashboard. Billing is handled through Stripe.
*   **To Infrastructure Tier:** Contact `api-access@stratumsports.com` or visit our documentation portal at `https://api-docs.stratumsports.com`. Partners are typically onboarded within 24 hours.
