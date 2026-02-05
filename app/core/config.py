from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    cassandra_host: str = "localhost"
    cassandra_port: int = 9042
    cassandra_keyspace: str = "url_shortener"
    base_url: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"

settings = Settings()
