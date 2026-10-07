import asyncio
import httpx

async def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': 'https://migroto.com',
        'Referer': 'https://migroto.com/'
    }
    url = 'https://admin.migroto.com/api/occupations/261313/full'
    print('Testing URL:', url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(url, headers=headers)
            print('Status:', r.status_code)
            print('Content-Type:', r.headers.get('content-type'))
            print('Body preview:', r.text[:1000])
        except Exception as e:
            print('Err:', e)

asyncio.run(main())
