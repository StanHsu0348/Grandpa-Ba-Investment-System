"""Account-scoped watchlists. PostgreSQL for cloud; SQLite for local use."""
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

DEFAULT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'private' / 'watchlists.sqlite3'


class WatchlistError(RuntimeError):
    pass


class WatchlistStore:
    def __init__(self, path=None, database_url=None):
        self.database_url = database_url or os.environ.get('WATCHLIST_DATABASE_URL')
        self.backend = 'postgres' if self.database_url else 'sqlite'
        self.path = Path(path or os.environ.get('WATCHLIST_DB_PATH') or DEFAULT_PATH)
        if self.backend == 'sqlite':
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise WatchlistError('無法開啟觀察清單儲存空間') from error
        default_time = "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')" if self.backend == 'postgres' else "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
        with self._connect() as db:
            db.execute(f'''CREATE TABLE IF NOT EXISTS watchlist (
                owner TEXT NOT NULL, market TEXT NOT NULL CHECK(market IN ('tw', 'us')),
                symbol TEXT NOT NULL, company TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT ({default_time}),
                PRIMARY KEY(owner, market, symbol))''')

    @contextmanager
    def _connect(self):
        db = None
        try:
            if self.backend == 'postgres':
                import psycopg
                from psycopg.rows import dict_row
                db = psycopg.connect(self.database_url, connect_timeout=10, row_factory=dict_row)
            else:
                db = sqlite3.connect(self.path, timeout=10)
                db.row_factory = sqlite3.Row
            with db:
                yield db
        except Exception as error:
            # Never display connection strings (which can contain credentials).
            raise WatchlistError('觀察清單資料庫暫時無法使用') from error
        finally:
            if db is not None:
                db.close()

    def _sql(self, query):
        return query.replace('?', '%s') if self.backend == 'postgres' else query

    @staticmethod
    def _validate(owner, market=None, symbol=None):
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError('缺少登入帳號')
        if market is not None and market not in ('tw', 'us'):
            raise ValueError('不支援的市場')
        if symbol is not None and (not isinstance(symbol, str) or not symbol.strip()):
            raise ValueError('缺少股票代碼')

    def list(self, owner):
        self._validate(owner)
        with self._connect() as db:
            return [dict(row) for row in db.execute(self._sql(
                'SELECT market, symbol, company, added_at FROM watchlist WHERE owner=? ORDER BY added_at DESC, market, symbol'), (owner,))]

    def contains(self, owner, market, symbol):
        self._validate(owner, market, symbol)
        with self._connect() as db:
            return db.execute(self._sql('SELECT 1 FROM watchlist WHERE owner=? AND market=? AND symbol=?'),
                              (owner, market, symbol)).fetchone() is not None

    def add(self, owner, market, symbol, company):
        self._validate(owner, market, symbol)
        with self._connect() as db:
            db.execute(self._sql('INSERT INTO watchlist(owner,market,symbol,company) VALUES(?,?,?,?) ON CONFLICT(owner,market,symbol) DO NOTHING'),
                       (owner, market, symbol, company))

    def remove(self, owner, market, symbol):
        self._validate(owner, market, symbol)
        with self._connect() as db:
            db.execute(self._sql('DELETE FROM watchlist WHERE owner=? AND market=? AND symbol=?'), (owner, market, symbol))
