"""Market-scoped navigation shared by peer comparisons and research pages."""
import streamlit as st


def select_research_stock(market, table_key, symbols):
    rows = st.session_state.get(table_key, {}).get('selection', {}).get('rows', [])
    if rows and 0 <= rows[0] < len(symbols):
        st.session_state[f'_{market}_research_symbol'] = str(symbols[rows[0]])


def render_research_navigation(market):
    incoming = st.session_state.pop(f'_{market}_research_symbol', None)
    if incoming:
        st.session_state[f'{market}_search_query'] = incoming
        st.session_state[f'_{market}_linked_symbol'] = incoming
        st.session_state.pop(f'{market}_search_pick', None)
        st.session_state[f'{market}_research_view'] = '個股研究'
    # A controlled selector can switch views on every peer click, including
    # when users have manually returned from research to the screener.
    view = st.segmented_control(
        '研究功能', ['企業篩選', '個股研究', 'IRR 排行'],
        default='企業篩選', key=f'{market}_research_view',
        label_visibility='collapsed',
    )
    return view or '企業篩選', incoming
