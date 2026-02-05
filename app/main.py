from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api.endpoints import router
from app.db.cassandra import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect()
    yield
    db.disconnect()

app = FastAPI(title="URL Shortener", lifespan=lifespan)
app.include_router(router)
