---
description: Implement and verify the Infrastructure Webhook Delivery Engine
---

# Webhook Delivery Engine Implementation

This workflow implements the "Infrastructure" identity by adding real-time webhook delivery for signals, enabling partners to receive intelligence without polling.

## 1. Database Schema
1. Create `ApiPartnerWebhook` model.
   - `id`, `user_id`, `url`, `secret` (for signing), `is_active`, `event_types`.
2. Create `WebhookDeliveryLog` model.
   - `id`, `webhook_id`, `signal_id`, `status_code`, `payload`, `response_body`, `duration_ms`.

## 2. Core Service Implementation
1. Create `backend/app/services/webhook_delivery.py`.
   - `dispatch_signal_to_webhooks(db, signal)`: Fetches active webhooks for the signal's partner and queues delivery.
   - `_deliver_webhook(webhook, payload)`: Uses `httpx` with retries and HMAC signing.

## 3. Integration
// turbo
1. Update `backend/app/tasks/poller.py` to call delivery at the end of the signal detection cycle.
2. Update `backend/app/api/routes/partner.py` to allow partners to manage their webhook URLs.

## 4. Verification
1. Run `backend/tests/test_webhook_delivery.py`.
2. Verify delivery attempt shows in `webhook_delivery_logs`.
