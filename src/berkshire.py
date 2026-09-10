"""SEC 13F parsing and quarter comparisons. Monetary values are USD."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / 'data' / 'berkshire'


def parse_table(xml, filing_date):
    root = ET.fromstring(xml)
    rows = []
    for node in root.findall('.//{*}infoTable'):
        def get(tag):
            return (node.findtext('.//{*}' + tag) or '').strip()
        value = float(get('value')) * (1000 if filing_date < '2023-01-03' else 1)
        shares = float(get('sshPrnamt'))
        if value < 0 or shares < 0:
            raise ValueError('13F 出現負數持倉')
        rows.append(dict(cusip=get('cusip'), name=get('nameOfIssuer'),
                         share_class=get('titleOfClass'), option=get('putCall'),
                         unit=get('sshPrnamtType'), value=value, shares=shares))
    if not rows:
        raise ValueError('找不到 13F 持股明細')
    # Multiple investment managers can report separate lines for one security.
    return pd.DataFrame(rows).groupby(['cusip', 'option', 'unit'], as_index=False).agg(
        name=('name', 'first'), share_class=('share_class', 'first'),
        value=('value', 'sum'), shares=('shares', 'sum'))


def load_reports(directory=DATA_DIR):
    manifest = json.loads((directory / 'manifest.json').read_text())
    return sorted(manifest['reports'], key=lambda r: r['period'], reverse=True)


def load_holdings(report, directory=DATA_DIR):
    return parse_table((directory / report['file']).read_bytes(), report['filed'])


def compare_holdings(current, previous=None, metadata=None):
    metadata = metadata or {}
    keys = ['cusip', 'option', 'unit']
    if previous is None:
        result = current.copy()
        result['previous_shares'] = float('nan')
        result['direction'] = '無前季資料'
        result['change_pct'] = float('nan')
    else:
        result = current.merge(previous[keys + ['name', 'share_class', 'shares']],
                               on=keys, how='outer', suffixes=('', '_old'))
        for column in ['name', 'share_class']:
            result[column] = result[column].fillna(result[column + '_old'])
        result[['value', 'shares', 'shares_old']] = result[['value', 'shares', 'shares_old']].fillna(0)
        result['previous_shares'] = result['shares_old']
        def direction(row):
            if row.shares_old == 0:
                return '新建倉'
            if row.shares == 0:
                return '清倉'
            return '加碼' if row.shares > row.shares_old else '減碼' if row.shares < row.shares_old else '持平'
        result['direction'] = result.apply(direction, axis=1)
        result['change_pct'] = (result.shares / result.shares_old.replace(0, float('nan')) - 1) * 100
    total = current.value.sum()
    result['weight'] = result.value / total * 100 if total else 0.0
    result['value_yi'] = result.value / 1e8
    result['ticker'] = result.cusip.map(lambda c: metadata.get(c, {}).get('ticker', '待對照'))
    result['sector'] = result.cusip.map(lambda c: metadata.get(c, {}).get('sector', '未分類'))
    return result.sort_values('value', ascending=False).reset_index(drop=True)
