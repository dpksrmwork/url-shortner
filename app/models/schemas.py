from pydantic import BaseModel, HttpUrl
from datetime import datetime

class ShortenRequest(BaseModel):
    url: HttpUrl
    custom_alias: str | None = None
    user_id: str | None = None
    ttl_days: int = 1095

class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    long_url: str

class URLStats(BaseModel):
    short_code: str
    long_url: str
    clicks: int
    expires_at: datetime | None
