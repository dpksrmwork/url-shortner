from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, HttpUrl
from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement
from datetime import datetime, timedelta
import hashlib
import base64
import os

app = FastAPI(title="URL Shortener")

# Cassandra connection
cluster = Cluster(['localhost'], port=9042)
session = cluster.connect('url_shortener')

# Prepare statements
insert_url = session.prepare("INSERT INTO urls (short_code, long_url, created_at, expires_at, user_id) VALUES (?, ?, ?, ?, ?)")
insert_dedup = session.prepare("INSERT INTO url_dedup (url_hash, short_code, created_at) VALUES (?, ?, ?)")
get_url = session.prepare("SELECT long_url, expires_at FROM urls WHERE short_code = ?")
get_dedup = session.prepare("SELECT short_code FROM url_dedup WHERE url_hash = ?")
increment_clicks = session.prepare("UPDATE url_clicks SET click_count = click_count + 1 WHERE short_code = ?")

class ShortenRequest(BaseModel):
    url: HttpUrl
    custom_alias: str | None = None
    user_id: str | None = None
    ttl_days: int = 1095  # 3 years default

class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    long_url: str

def generate_short_code(url: str) -> str:
    hash_bytes = hashlib.sha256(url.encode()).digest()[:6]
    return base64.urlsafe_b64encode(hash_bytes).decode()[:8]

def get_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()

@app.post("/shorten", response_model=ShortenResponse)
def shorten_url(req: ShortenRequest):
    url_str = str(req.url)
    url_hash = get_url_hash(url_str)
    
    # Check deduplication
    result = session.execute(get_dedup, [url_hash])
    row = result.one()
    if row:
        short_code = row.short_code
        return ShortenResponse(
            short_code=short_code,
            short_url=f"http://localhost:8000/{short_code}",
            long_url=url_str
        )
    
    # Generate or use custom alias
    short_code = req.custom_alias if req.custom_alias else generate_short_code(url_str)
    
    # Check if short_code exists
    result = session.execute(get_url, [short_code])
    if result.one():
        raise HTTPException(status_code=409, detail="Short code already exists")
    
    # Insert URL
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=req.ttl_days)
    session.execute(insert_url, [short_code, url_str, created_at, expires_at, req.user_id])
    session.execute(insert_dedup, [url_hash, short_code, created_at])
    
    return ShortenResponse(
        short_code=short_code,
        short_url=f"http://localhost:8000/{short_code}",
        long_url=url_str
    )

@app.get("/{short_code}")
def redirect_url(short_code: str):
    result = session.execute(get_url, [short_code])
    row = result.one()
    
    if not row:
        raise HTTPException(status_code=404, detail="URL not found")
    
    if row.expires_at and datetime.now() > row.expires_at:
        raise HTTPException(status_code=410, detail="URL expired")
    
    # Increment click count asynchronously
    session.execute_async(increment_clicks, [short_code])
    
    return RedirectResponse(url=row.long_url, status_code=301)

@app.get("/stats/{short_code}")
def get_stats(short_code: str):
    url_result = session.execute(get_url, [short_code])
    url_row = url_result.one()
    
    if not url_row:
        raise HTTPException(status_code=404, detail="URL not found")
    
    clicks_result = session.execute("SELECT click_count FROM url_clicks WHERE short_code = %s", [short_code])
    clicks_row = clicks_result.one()
    
    return {
        "short_code": short_code,
        "long_url": url_row.long_url,
        "clicks": clicks_row.click_count if clicks_row else 0,
        "expires_at": url_row.expires_at
    }

@app.on_event("shutdown")
def shutdown():
    cluster.shutdown()
