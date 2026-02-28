import hmac
import hashlib
import json
import uuid
import argparse
from datetime import UTC, datetime

import httpx

def generate_test_payload():
    return {
        "event": "signal.test_delivery",
        "signal_id": str(uuid.uuid4()),
        "event_id": "test_event_123",
        "market": "spreads",
        "signal_type": "KEY_CROSS",
        "direction": "over",
        "strength_score": 85,
        "time_bucket": "G30",
        "from_value": -3.5,
        "to_value": -4.0,
        "created_at": datetime.now(UTC).isoformat(),
        "metadata": {"is_test": True}
    }

async def send_test_webhook(url: str, secret: str):
    print(f"🚀 Sending test signal to {url}...")
    
    payload = generate_test_payload()
    payload_str = json.dumps(payload)
    
    # Generate HMAC signature
    signature = hmac.new(
        secret.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-Stratum-Signature": f"sha256={signature}",
        "User-Agent": "Stratum-Webhook-Tester/1.0"
    }

    start_time = datetime.now(UTC)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, content=payload_str, headers=headers)
            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000
            
            print(f"✅ Status: {response.status_code}")
            print(f"⏱️  Duration: {duration:.1f}ms")
            print(f"📄 Response: {response.text[:200]}...")
            
            if response.status_code >= 200 and response.status_code < 300:
                print("\n✨ SUCCESS: Webhook received and acknowledged.")
            else:
                print("\n⚠️  WARNING: Received non-2xx status code.")
                
    except Exception as e:
        print(f"\n❌ ERROR: Delivery failed: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test a Stratum Webhook delivery.")
    parser.add_argument("url", help="The partner's webhook URL")
    parser.add_argument("secret", help="The partner's webhook secret (whsec_...)")
    
    args = parser.parse_args()
    
    import asyncio
    asyncio.run(send_test_webhook(args.url, args.secret))
