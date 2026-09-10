import pytest
from src.watchlist import WatchlistStore


def test_persistence_idempotency_and_account_isolation(tmp_path):
    path = tmp_path / 'private' / 'watchlist.sqlite3'
    store = WatchlistStore(path)
    store.add('甲', 'us', 'AAPL', 'Apple')
    store.add('甲', 'us', 'AAPL', 'Apple')
    store.add('乙', 'us', 'AAPL', 'Apple')
    store.add('甲', 'tw', '2330', '台積電')
    assert len(WatchlistStore(path).list('甲')) == 2
    assert len(store.list('乙')) == 1
    store.remove('甲', 'us', 'AAPL')
    assert not store.contains('甲', 'us', 'AAPL')
    assert store.contains('乙', 'us', 'AAPL')
    assert store.list('不存在') == []


def test_markets_do_not_collide_and_queries_are_parameterized(tmp_path):
    store = WatchlistStore(tmp_path / 'watchlist.sqlite3')
    owner = "user' OR 1=1 --"
    store.add(owner, 'tw', 'ABC', 'A')
    store.add(owner, 'us', 'ABC', 'B')
    store.remove(owner, 'tw', 'ABC')
    assert store.list(owner)[0]['company'] == 'B'
    assert store.list('user') == []


def test_reject_missing_identity_and_invalid_market(tmp_path):
    store = WatchlistStore(tmp_path / 'watchlist.sqlite3')
    with pytest.raises(ValueError):
        store.list('')
    with pytest.raises(ValueError):
        store.add('user', 'unknown', 'AAPL', 'Apple')
