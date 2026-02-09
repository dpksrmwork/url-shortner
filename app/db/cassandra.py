import os
os.environ['CASSANDRA_DRIVER_ALLOW_ASYNCORE'] = '1'

from cassandra.cluster import Cluster
from cassandra.query import PreparedStatement
from app.core.config import settings

class CassandraDB:
    def __init__(self):
        self.cluster = None
        self.session = None
        self.prepared_statements = {}
    
    def connect(self):
        self.cluster = Cluster(
            [settings.cassandra_host], 
            port=settings.cassandra_port
        )
        # Connect without keyspace first, then use it
        self.session = self.cluster.connect()
        self.session.set_keyspace(settings.cassandra_keyspace)
        self._prepare_statements()
    
    def _prepare_statements(self):
        self.prepared_statements = {
            'insert_url': self.session.prepare(
                "INSERT INTO urls (short_code, long_url, created_at, expires_at, user_id) VALUES (?, ?, ?, ?, ?)"
            ),
            'insert_dedup': self.session.prepare(
                "INSERT INTO url_dedup (url_hash, short_code, created_at) VALUES (?, ?, ?)"
            ),
            'get_url': self.session.prepare(
                "SELECT long_url, expires_at FROM urls WHERE short_code = ?"
            ),
            'get_dedup': self.session.prepare(
                "SELECT short_code FROM url_dedup WHERE url_hash = ?"
            ),
            'increment_clicks': self.session.prepare(
                "UPDATE url_clicks SET click_count = click_count + 1 WHERE short_code = ?"
            ),
            'get_clicks': self.session.prepare(
                "SELECT click_count FROM url_clicks WHERE short_code = ?"
            )
        }
    
    def disconnect(self):
        if self.cluster:
            self.cluster.shutdown()

db = CassandraDB()
