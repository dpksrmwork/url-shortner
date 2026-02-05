from datetime import datetime, timedelta
from fastapi import HTTPException
import hashlib
import base64
from app.db.cassandra import db
from app.models.schemas import ShortenRequest, ShortenResponse, URLStats
from app.core.config import settings

class URLService:
    @staticmethod
    def generate_short_code(url: str) -> str:
        hash_bytes = hashlib.sha256(url.encode()).digest()[:6]
        return base64.urlsafe_b64encode(hash_bytes).decode()[:8]
    
    @staticmethod
    def get_url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()
    
    def create_short_url(self, req: ShortenRequest) -> ShortenResponse:
        url_str = str(req.url)
        url_hash = self.get_url_hash(url_str)
        
        # Check deduplication
        result = db.session.execute(db.prepared_statements['get_dedup'], [url_hash])
        row = result.one()
        if row:
            return ShortenResponse(
                short_code=row.short_code,
                short_url=f"{settings.base_url}/{row.short_code}",
                long_url=url_str
            )
        
        # Generate or use custom alias
        short_code = req.custom_alias if req.custom_alias else self.generate_short_code(url_str)
        
        # Check if short_code exists
        result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        if result.one():
            raise HTTPException(status_code=409, detail="Short code already exists")
        
        # Insert URL
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=req.ttl_days)
        db.session.execute(db.prepared_statements['insert_url'], 
                          [short_code, url_str, created_at, expires_at, req.user_id])
        db.session.execute(db.prepared_statements['insert_dedup'], 
                          [url_hash, short_code, created_at])
        
        return ShortenResponse(
            short_code=short_code,
            short_url=f"{settings.base_url}/{short_code}",
            long_url=url_str
        )
    
    def get_long_url(self, short_code: str) -> str:
        result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        row = result.one()
        
        if not row:
            raise HTTPException(status_code=404, detail="URL not found")
        
        if row.expires_at and datetime.now() > row.expires_at:
            raise HTTPException(status_code=410, detail="URL expired")
        
        # Increment click count asynchronously
        db.session.execute_async(db.prepared_statements['increment_clicks'], [short_code])
        
        return row.long_url
    
    def get_stats(self, short_code: str) -> URLStats:
        url_result = db.session.execute(db.prepared_statements['get_url'], [short_code])
        url_row = url_result.one()
        
        if not url_row:
            raise HTTPException(status_code=404, detail="URL not found")
        
        clicks_result = db.session.execute(db.prepared_statements['get_clicks'], [short_code])
        clicks_row = clicks_result.one()
        
        return URLStats(
            short_code=short_code,
            long_url=url_row.long_url,
            clicks=clicks_row.click_count if clicks_row else 0,
            expires_at=url_row.expires_at
        )

url_service = URLService()
