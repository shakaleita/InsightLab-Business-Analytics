import importlib,os,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp = tempfile.mkdtemp(prefix='portfolio-test-')
os.environ['APP_DB']=str(Path(temp)/'test.db')
os.environ['OWNER_SETUP_TOKEN']='test-only-setup-token-1234567890123'
if 'main' in sys.modules: del sys.modules['main']
from main import app
client=TestClient(app)
assert client.post('/api/auth/register',json={'username':'qaowner','password':'DemoPassword123!','setup_token':'test-only-setup-token-1234567890123'}).status_code==201
assert client.post('/api/auth/login',json={'username':'qaowner','password':'DemoPassword123!'}).status_code==200

def test_health():
    r=client.get('/api/health')
    assert r.status_code==200 and r.json()['ok']

def test_initial_list():
    r=client.get('/api/items')
    assert r.status_code==200 and isinstance(r.json(),list)

def test_summary():
    r=client.get('/api/summary')
    assert r.status_code==200 and isinstance(r.json(),list)


# v0.3 regression tests
def test_filtered_report_and_csv_export():
    assert client.post('/api/items',json={'date':'2030-01-15','region':'QA-West','product':'Widget','revenue':125,'units':5}).status_code==201
    assert client.post('/api/items',json={'date':'2030-01-15','region':'QA-East','product':'Widget','revenue':50,'units':2}).status_code==201
    r=client.get('/api/report',params={'region':'QA-West'})
    assert r.status_code==200 and r.json()['total_revenue']==125
    csv_resp=client.get('/api/export.csv')
    assert csv_resp.status_code==200 and 'QA-West' in csv_resp.text
    assert client.post('/api/items',json={'date':'2030-01-15','region':'X','product':'X','revenue':-5,'units':1}).status_code==422



def test_v05_monthly_trends_and_safe_export():
    r=client.post('/api/items',json={'date':'2027-04-01','region':'=1+1','product':'Demo','revenue':20,'units':2})
    assert r.status_code==201
    assert any(x['month']=='2027-04' for x in client.get('/api/trends/monthly').json())
    assert "'=1+1" in client.get('/api/export.csv').text

def test_v05_authentication():
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/items').status_code==401
        assert anonymous.post('/api/auth/register',json={'username':'intruder','password':'DemoPassword123!','setup_token':'bad'}).status_code==403
