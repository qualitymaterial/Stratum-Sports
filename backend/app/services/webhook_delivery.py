import hmac
import hashlib
import json
import logging
import asyncio
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone
    UTC = timezone.utc
from datetime import datetime
from typing import Any, Dict

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.api_partner_webhook import ApiPartnerWebhook, WebhookDeliveryLog
from app.models.clv_record import ClvRecord
from app.models.signal import Signal

logger = logging.getLogger(__name__)
settings = get_settings()

async def dispatch_signal_to_webhooks(db: AsyncSession, signals: list[Signal]) -> None:
    """
    Main entry point for dispatching signals to all active partner webhooks.
    """
    if not signals:
        return

    # In a real enterprise system, this would push to a Task Queue (Celery/RabbitMQ).
    # For this baseline, we'll use a background asyncio gather to prevent blocking the poller.
    
    # 1. Fetch all active webhooks
    stmt = select(ApiPartnerWebhook).where(ApiPartnerWebhook.is_active.is_(True))
    webhooks = (await db.execute(stmt)).scalars().all()
    
    if not webhooks:
        return

    # 2. Build delivery tasks
    tasks = []
    
    # Internal Observability / logging config
    k_enabled = settings.kalshi_skew_gate_enabled
    k_mode = settings.kalshi_skew_gate_mode
    k_thresh = settings.kalshi_skew_gate_threshold
    
    for signal in signals:
        gate_data = None
        if k_enabled:
            gate_data = {
                "kalshi_liquidity_skew": signal.kalshi_liquidity_skew,
                "kalshi_skew_bucket": signal.kalshi_skew_bucket,
                "kalshi_gate_pass": signal.kalshi_gate_pass,
                "kalshi_gate_threshold": signal.kalshi_gate_threshold,
                "kalshi_gate_mode": k_mode
            }
            
            # None counts as a pass in shadow mode. But in enforce, if it explicitly failed:
            if k_mode == "enforce" and signal.kalshi_gate_pass is False:
                logger.info(
                    "KalshiGate[ENFORCE] Signal suppressed",
                    extra={
                        "signal_id": str(signal.id),
                        "skew": signal.kalshi_liquidity_skew,
                        "pass": False,
                        "mode": k_mode
                    }
                )
                continue
                
            logger.info(
                f"KalshiGate[{k_mode.upper()}] Signal processed",
                extra={
                    "signal_id": str(signal.id),
                    "skew": signal.kalshi_liquidity_skew,
                    "pass": signal.kalshi_gate_pass,
                    "mode": k_mode
                }
            )

        # Prepare the payload once per signal
        payload = {
            "event": "signal.detected",
            "signal_id": str(signal.id),
            "event_id": signal.event_id,
            "market": signal.market,
            "signal_type": signal.signal_type,
            "direction": signal.direction,
            "strength_score": signal.strength_score,
            "time_bucket": signal.time_bucket,
            "from_value": signal.from_value,
            "to_value": signal.to_value,
            "created_at": signal.created_at.isoformat(),
            "metadata": signal.metadata_json
        }
        
        if gate_data:
            payload["kalshi_gate"] = gate_data
        
        for webhook in webhooks:
            # Note: In an institutional setup, we would verify the user_id 
            # owns the signal or has a specific subscription.
            # For now, we broadcast to all active partner webhooks.
            tasks.append(_deliver_webhook(webhook, signal.id, payload))

    if tasks:
        # Trigger fire-and-forget delivery
        async def run_delivery():
            await asyncio.gather(*tasks)
        asyncio.create_task(run_delivery())


async def dispatch_clv_to_webhooks(db: AsyncSession, clv_records: list[ClvRecord]) -> None:
    """
    Dispatches CLV enrichment updates to all active partner webhooks.
    """
    if not clv_records:
        return

    stmt = select(ApiPartnerWebhook).where(ApiPartnerWebhook.is_active.is_(True))
    webhooks = (await db.execute(stmt)).scalars().all()
    if not webhooks:
        return

    tasks = []
    for record in clv_records:
        payload = {
            "event": "signal.clv_finalized",
            "signal_id": str(record.signal_id),
            "event_id": record.event_id,
            "market": record.market,
            "signal_type": record.signal_type,
            "outcome_name": record.outcome_name,
            "entry_line": record.entry_line,
            "entry_price": record.entry_price,
            "close_line": record.close_line,
            "close_price": record.close_price,
            "clv_line": record.clv_line,
            "clv_prob": record.clv_prob,
            "computed_at": record.computed_at.isoformat(),
        }
        for webhook in webhooks:
            tasks.append(_deliver_webhook(webhook, record.signal_id, payload))

    if tasks:
        async def run_delivery():
            await asyncio.gather(*tasks)
        asyncio.create_task(run_delivery())

async def _deliver_webhook(webhook: ApiPartnerWebhook, signal_id: Any, payload: Dict[str, Any]) -> None:
    """
    Handles the individual HTTP POST with exponential backoff and logging.
    """
    from app.core.database import AsyncSessionLocal
    
    start_time = datetime.now(UTC)
    payload_str = json.dumps(payload)
    
    # Generate HMAC signature
    signature = hmac.new(
        webhook.secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-Stratum-Signature": f"sha256={signature}",
        "User-Agent": "Stratum-Webhook-Engine/1.0"
    }

    status_code = None
    response_body = None
    error = None
    attempts = 0
    max_retries = settings.webhook_max_retries

    async with httpx.AsyncClient(timeout=settings.webhook_timeout_seconds) as client:
        while attempts <= max_retries:
            attempts += 1
            try:
                response = await client.post(webhook.url, content=payload_str, headers=headers)
                status_code = response.status_code
                response_body = response.text[:1000] # Cap body storage
                
                # Success on 2xx
                if 200 <= status_code < 300:
                    error = None
                    break
                
                # Don't retry on 4xx (Client Errors)
                if 400 <= status_code < 500:
                    error = f"Client error: {status_code}"
                    break
                
                # Retry on 5xx or other non-success
                error = f"Server error: {status_code}"
                
            except httpx.RequestError as e:
                error = str(e)
                logger.warning(f"Webhook attempt {attempts} failed to {webhook.url}: {error}")
            
            if attempts <= max_retries:
                delay = settings.webhook_initial_delay_seconds * (settings.webhook_backoff_factor ** (attempts - 1))
                await asyncio.sleep(delay)
            else:
                logger.error(f"Webhook delivery permanently failed after {attempts} attempts to {webhook.url}")

    duration = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

    # Log the final outcome
    async with AsyncSessionLocal() as db:
        log = WebhookDeliveryLog(
            webhook_id=webhook.id,
            signal_id=signal_id,
            status_code=status_code,
            payload=payload,
            response_body=response_body,
            duration_ms=duration,
            attempts=attempts,
            error=error
        )
        db.add(log)
        await db.commit()
