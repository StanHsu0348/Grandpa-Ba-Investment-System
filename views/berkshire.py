"""Berkshire Hathaway quarterly SEC holdings dashboard."""
import json
import xml.etree.ElementTree as ET

import plotly.express as px
import streamlit as st

from src.berkshire import DATA_DIR, compare_holdings, load_holdings, load_reports

st.markdown('''<section class="hero"><div class="eyebrow">GRANDPA BA INVESTOR · SEC 13F</div>
<h1>看見波克夏的布局。</h1><p>Berkshire Hathaway 季度持股，從組合配置到每一筆增減。</p></section>''', unsafe_allow_html=True)
try:
    reports = load_reports()
    if not reports:
        raise ValueError('尚無可用期別')
    metadata = json.loads((DATA_DIR / 'securities.json').read_text())
    periods = [report['period'] for report in reports]
    if st.session_state.get('berkshire_period') not in periods:
        st.session_state.berkshire_period = periods[0]
    # Native selection widgets inside a popover have no editable search input.
    with st.popover(f"資料期別：{st.session_state.berkshire_period}", use_container_width=True):
        period = st.radio('資料期別', periods, key='berkshire_period', label_visibility='collapsed')
    selected = periods.index(period)
    report = reports[selected]
    current = load_holdings(report)
    previous_report = reports[selected + 1] if selected + 1 < len(reports) else None
    # Never compare non-adjacent quarters.
    if previous_report:
        import pandas as pd
        if pd.Period(report['period'], freq='Q').ordinal - pd.Period(previous_report['period'], freq='Q').ordinal != 1:
            previous_report = None
    previous = load_holdings(previous_report) if previous_report else None
    holdings = compare_holdings(current, previous, metadata)
except (OSError, ValueError, KeyError, ET.ParseError) as error:
    st.error('無法讀取波克夏持股資料，請管理者執行 scripts/update_berkshire.py 更新資料。')
    st.stop()

st.caption(f"季末持倉日：{report['period']} · 申報日：{report['filed']} · 幣別：美元 · 資料來源：SEC EDGAR")
st.caption('此頁為已下載的官方申報快照；由管理者更新，非即時股價或即時交易資料。')
cols = st.columns(5)
cols[0].metric('估計市值（億美元）', f'{current.value.sum() / 1e8:,.2f}')
cols[1].metric('持股個股數量', f'{len(current):,}')
for column, direction in zip(cols[2:], ['加碼', '減碼', '清倉']):
    column.metric(direction + '個股數量', str((holdings.direction == direction).sum()) if previous_report else '—')
if previous_report:
    st.caption(f"相較 {previous_report['period']} · 另有 {(holdings.direction == '新建倉').sum()} 檔新建倉（不計入加碼數量）。個股按 CUSIP／證券類別計數，不同股別分開計算。")
else:
    st.info('缺少相鄰前季資料，因此不判斷本期加減碼或清倉。')

left, right = st.columns([1, 1], gap='large')
with left:
    st.subheader('持股產業分布')
    sectors = holdings[holdings.value > 0].groupby('sector', as_index=False).value.sum()
    fig = px.pie(sectors, names='sector', values='value', hole=.55,
                 color_discrete_sequence=['#244c3c', '#a58e5d', '#607c70', '#c5b890', '#93aca0', '#73808d', '#b99e86', '#c7cfc7'])
    fig.update_traces(textinfo='percent', hovertemplate='%{label}<br>%{percent}<br>US$ %{value:,.0f}<extra></extra>')
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=350, legend=dict(orientation='h'))
    st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader('資料口徑')
    st.markdown('持股比例 = 個股申報市值 ÷ 本期 13F 總市值。\n\n異動比例 =（本期股數 − 前季股數）÷ 前季股數；新建倉以前季零持股為基準，比例留空，清倉為 −100%。')
    st.caption('13F 僅涵蓋申報範圍內的證券，不代表波克夏全部資產；不含完整現金、私人企業與海外持倉。股數變化也可能來自拆股、合併或股別轉換，不等同實際買賣。')
    st.caption('股票代碼及產業為本專案維護的輔助對照，非 13F 原生欄位；未對照證券保留 CUSIP 並列入「未分類」。')
    for i, source in enumerate(report['sources']):
        st.link_button(f'查看 SEC 本期原始申報 {i + 1}', source)
    if previous_report:
        for i, source in enumerate(previous_report['sources']):
            st.link_button(f'查看 SEC 前季原始申報 {i + 1}', source)

st.subheader('持股細節')
query = st.text_input('搜尋代碼、公司或 CUSIP', placeholder='例如 AAPL、APPLE')
directions = ['新建倉', '加碼', '減碼', '清倉', '持平', '無前季資料']
active_directions = [direction for direction in directions if st.session_state.get('berkshire_direction_' + direction, False)]
with st.popover('異動方向：' + ('、'.join(active_directions) or '全部'), use_container_width=True):
    st.caption('可複選；未勾選時顯示全部。')
    choices = [direction for direction in directions
               if st.checkbox(direction, key='berkshire_direction_' + direction)]
filtered = holdings
if query:
    filtered = filtered[filtered[['ticker', 'name', 'cusip']].apply(lambda col: col.str.contains(query.strip(), case=False, regex=False)).any(axis=1)]
if choices:
    filtered = filtered[filtered.direction.isin(choices)]
# Lead with portfolio conviction and quarterly action; keep filing identifiers secondary.
primary_columns = {
    'ticker': '股票代碼',
    'name': '公司名稱',
    'weight': '持股比重（%）',
    'direction': '本季動作',
    'change_pct': '股數增減（%）',
    'value_yi': '持倉市值（億美元）',
    'sector': '產業',
}
audit_columns = {
    'shares': '本期股數',
    'previous_shares': '前季股數',
    'cusip': 'CUSIP',
    'share_class': '股別',
    'option': '選擇權',
    'unit': '股數單位',
}
display = filtered[list(primary_columns)].rename(columns=primary_columns)
st.caption('依持股比重由大到小排列；點選股票所在列，即可前往美股「個股研究」。')

def open_us_research():
    rows = st.session_state['berkshire_holdings_select']['selection']['rows']
    if rows:
        ticker = str(filtered.iloc[rows[0]]['ticker'])
        if ticker != '待對照':
            st.session_state['_us_research_symbol'] = ticker
            st.session_state['_berkshire_open_research'] = True
        else:
            st.session_state['_berkshire_unmapped_selection'] = True

st.dataframe(display, hide_index=True, use_container_width=True,
             key='berkshire_holdings_select', on_select=open_us_research,
             selection_mode='single-row', column_config={
    '股票代碼': st.column_config.TextColumn('股票代碼', width='small'),
    '公司名稱': st.column_config.TextColumn('公司名稱', width='medium'),
    '持股比重（%）': st.column_config.NumberColumn(
        '持股比重（%）', format='%.2f',
        help='占本季 13F 申報總市值的比例，反映這檔股票在組合中的分量。'),
    '本季動作': st.column_config.TextColumn('本季動作', width='small'),
    '股數增減（%）': st.column_config.NumberColumn(
        '股數增減（%）', format='%+.2f',
        help='相較前季的股數變化，並非股價報酬率。新建倉無前季基準，顯示空白；清倉為 −100%。'),
    '持倉市值（億美元）': st.column_config.NumberColumn(
        '持倉市值（億美元）', format='%.2f',
        help='季末申報的持倉市值，並非買進成本或本季投入金額。'),
})
if st.session_state.pop('_berkshire_open_research', False):
    st.switch_page('views/us.py')
if st.session_state.pop('_berkshire_unmapped_selection', False):
    st.info('這筆持股尚未對照股票代碼，暫時無法連至美股研究。')
if display.empty:
    st.info('沒有符合條件的持股。')
full_columns = {**primary_columns, **audit_columns}
full_display = filtered[list(full_columns)].rename(columns=full_columns)
with st.expander('查看股數與申報識別資料'):
    st.dataframe(full_display, hide_index=True, use_container_width=True,
                 column_config={
                     '本期股數': st.column_config.NumberColumn('本期股數', format='%.0f'),
                     '前季股數': st.column_config.NumberColumn('前季股數', format='%.0f'),
                 })
st.download_button('下載完整持股明細 CSV', full_display.to_csv(index=False).encode('utf-8-sig'),
                   file_name=f"berkshire-{report['period']}.csv", mime='text/csv')
