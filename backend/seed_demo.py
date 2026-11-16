"""Insert optional synthetic demonstration records (safe to rerun)."""
from fastapi.testclient import TestClient
from main import app

SEEDS = [{'date': '2026-11-01', 'region': 'Europe', 'product': 'Consulting', 'revenue': 9200, 'units': 3}, {'date': '2026-11-02', 'region': 'North America', 'product': 'Support', 'revenue': 4100, 'units': 5}]
client=TestClient(app)
if client.get('/api/items').json():
    print('Existing records found; skipping seed.')
else:
    for record in SEEDS:
        result=client.post('/api/items',json=record)
        result.raise_for_status()
    print('Added',len(SEEDS),'synthetic sample records.')
