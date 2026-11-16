APP_TITLE = 'InsightLab'
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Any
import sqlite3, os
from contextlib import contextmanager
from pathlib import Path

DB = Path(os.environ.get("APP_DB", str(Path(__file__).parent / "app.db")))
app = FastAPI(title=APP_TITLE, version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@contextmanager
def db():
    con = sqlite3.connect(DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

def rows(cursor):
    return [dict(r) for r in cursor.fetchall()]

def setup(sql):
    with db() as con:
        con.executescript(sql)

@app.get("/api/health")
def health():
    return {"ok": True, "service": APP_TITLE}


from fastapi import UploadFile,File
import csv,io
setup("""CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,date TEXT NOT NULL,region TEXT NOT NULL,product TEXT NOT NULL,revenue REAL NOT NULL,units INTEGER NOT NULL);""")
class Record(BaseModel):
    date:str
    region:str=Field(min_length=1,max_length=100)
    product:str=Field(min_length=1,max_length=100)
    revenue:float = Field(ge=0,le=1_000_000_000,allow_inf_nan=False)
    units:int = Field(ge=0,le=1_000_000)

    @field_validator('date')
    @classmethod
    def validate_date(cls,value:str):
        from datetime import date
        if len(value)!=10 or date.fromisoformat(value).isoformat()!=value:
            raise ValueError('Use valid ISO date YYYY-MM-DD')
        return value
@app.get('/api/items')
def items():
    with db() as c:return rows(c.execute('SELECT * FROM records ORDER BY id DESC LIMIT 200'))
@app.post('/api/items',status_code=201)
def create_item(d:Record):
    with db() as c:
        cur=c.execute('INSERT INTO records(date,region,product,revenue,units) VALUES(?,?,?,?,?)',(d.date,d.region,d.product,d.revenue,d.units))
        return dict(c.execute('SELECT * FROM records WHERE id=?',(cur.lastrowid,)).fetchone())
@app.post('/api/import')
async def import_csv(file:UploadFile=File(...)):
    content=await file.read(2_000_001)
    if len(content)>2_000_000:raise HTTPException(413,'File too large (2MB limit)')
    try:
        parsed=list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
        if len(parsed)>5000:raise ValueError('Maximum 5000 rows')
        # Validate every row before starting any database insert.
        parsed=[Record(**r) for r in parsed]
        parsed=[(r.date,r.region,r.product,r.revenue,r.units) for r in parsed]
    except (ValueError,UnicodeDecodeError,KeyError,TypeError) as e:raise HTTPException(422,f'Invalid CSV: {e}')
    with db() as c:c.executemany('INSERT INTO records(date,region,product,revenue,units) VALUES(?,?,?,?,?)',parsed)
    return {'imported':len(parsed)}
@app.get('/api/summary')
def summary():
    with db() as c:return rows(c.execute('SELECT region AS label,ROUND(SUM(revenue),2) AS value FROM records GROUP BY region ORDER BY value DESC'))


# v0.3: analytics slicing and CSV export
from fastapi.responses import StreamingResponse

@app.get('/api/report')
def report(region: str | None = None, start: str | None = None, end: str | None = None):
    conditions=[]
    params=[]
    if region:
        conditions.append('region=?');params.append(region)
    if start:
        conditions.append('date>=?');params.append(start)
    if end:
        conditions.append('date<=?');params.append(end)
    where=' WHERE '+' AND '.join(conditions) if conditions else ''
    with db() as con:
        group=rows(con.execute("""SELECT product,COUNT(*) AS entries,
          ROUND(SUM(revenue),2) AS revenue,SUM(units) AS units FROM records"""+where+
          ' GROUP BY product ORDER BY revenue DESC',params))
        return {'filters':{'region':region,'start':start,'end':end},'products':group,
                'total_revenue':round(sum(r['revenue'] for r in group),2)}

@app.get('/api/export.csv')
def export_csv():
    import csv, io
    with db() as con:
        records=rows(con.execute('SELECT date,region,product,revenue,units FROM records ORDER BY id'))
    stream=io.StringIO()
    writer=csv.DictWriter(stream,fieldnames=['date','region','product','revenue','units'])
    writer.writeheader()
    for rec in records:
        # Excel/LibreOffice-compatible CSV import should not execute formula-like cells.
        safe={key:("'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\\t','\\r')) else value)
              for key,value in rec.items()}
        writer.writerow(safe)
    return StreamingResponse(iter([stream.getvalue()]),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="insightlab-export.csv"'})


@app.get('/api/trends/monthly')
def monthly_trends():
    with db() as con:
        return rows(con.execute("""SELECT substr(date,1,7) AS month,
           COUNT(*) AS records,ROUND(SUM(revenue),2) AS revenue,SUM(units) AS units
           FROM records WHERE length(date)>=7 GROUP BY substr(date,1,7) ORDER BY month"""))

from security import install_auth
install_auth(app,DB)
