from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from app.models.schemas import ShortenRequest, ShortenResponse, URLStats
from app.services.url_service import url_service

router = APIRouter()

@router.post("/shorten", response_model=ShortenResponse)
def shorten_url(req: ShortenRequest):
    return url_service.create_short_url(req)

@router.get("/stats/{short_code}", response_model=URLStats)
def get_stats(short_code: str):
    return url_service.get_stats(short_code)

@router.get("/{short_code}")
def redirect_url(short_code: str):
    long_url = url_service.get_long_url(short_code)
    return RedirectResponse(url=long_url, status_code=301)
