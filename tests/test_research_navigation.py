from unittest.mock import patch

from src.research_navigation import select_research_stock


def test_peer_selection_uses_display_order_and_market_scope():
    state = {
        'peer': {'selection': {'rows': [1]}},
        'us_roe_threshold_slider': 15,
        '_tw_research_symbol': '2330',
    }
    with patch('src.research_navigation.st.session_state', state):
        select_research_stock('us', 'peer', ['MSFT', 'AAPL'])
    assert state['_us_research_symbol'] == 'AAPL'
    assert state['_tw_research_symbol'] == '2330'
    assert state['us_roe_threshold_slider'] == 15


def test_empty_or_stale_selection_does_not_navigate():
    for rows in [[], [5], [-1]]:
        state = {'peer': {'selection': {'rows': rows}}}
        with patch('src.research_navigation.st.session_state', state):
            select_research_stock('tw', 'peer', ['2330'])
        assert '_tw_research_symbol' not in state
