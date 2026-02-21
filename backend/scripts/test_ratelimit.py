import httpx
import asyncio

async def test_ratelimit():
    # Test 1: Direct request (untrusted)
    # Note: This requires the backend to be running and docker-compose to be up
    # We'll use curl for a simpler test if possible, but httpx is fine for a script.
    
    url = "http://localhost:8000/api/v1/health/live"
    
    # We can't easily spoof the source IP from outside the container 
    # but we can check if it respects X-Forwarded-For when coming from 'untrusted' IP.
    
    async with httpx.AsyncClient() as client:
        # Case A: External request with spoofed X-Forwarded-For
        # Backend should see source_ip = host.docker.internal (or whatever docker uses)
        # If that IP is NOT in trusted_proxies, it should ignore the header.
        resp = await client.get(url, headers={"X-Forwarded-For": "8.8.8.8"})
        print(f"Untrusted XFF Response: {resp.status_code}")
        
    print("\nTo truly verify, we need to add the host.docker.internal IP to TRUSTED_PROXIES in .env and restart.")

if __name__ == "__main__":
    asyncio.run(test_ratelimit())
