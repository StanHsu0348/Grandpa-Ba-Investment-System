"""Download official SEC 13F originals. Run with SEC_USER_AGENT='Name email'."""
import json
import hashlib
import os
from pathlib import Path
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.berkshire import DATA_DIR, parse_table


def fetch(url):
    agent = os.environ.get('SEC_USER_AGENT', '')
    if '@' not in agent:
        raise ValueError('請設定 SEC_USER_AGENT，內容包含管理者名稱與聯絡 email')
    time.sleep(.2)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': agent}), timeout=45) as response:
        return response.read()


def main():
    recent = json.loads(fetch('https://data.sec.gov/submissions/CIK0001067983.json'))['filings']['recent']
    records = [dict(zip(recent, values)) for values in zip(*recent.values())]
    filings = [r for r in records if r['form'] in ('13F-HR', '13F-HR/A')]
    periods = sorted({r['reportDate'] for r in filings if r['reportDate']}, reverse=True)[:9]
    reports = []
    DATA_DIR.mkdir(exist_ok=True)
    for period in periods:
        sources, combined = [], None
        for row in sorted([r for r in filings if r['reportDate'] == period], key=lambda r: (r['filingDate'], r['accessionNumber'])):
            accession = row['accessionNumber']
            base = 'https://www.sec.gov/Archives/edgar/data/1067983/' + accession.replace('-', '') + '/'
            primary_name = row['primaryDocument'].split('/')[-1]
            primary = ET.fromstring(fetch(base + primary_name))
            amendment = primary.findtext('.//{*}amendmentType')
            index = json.loads(fetch(base + 'index.json'))
            table = None
            for item in index['directory']['item']:
                name = item['name']
                if name.endswith('.xml') and name != primary_name:
                    content = fetch(base + name)
                    root = ET.fromstring(content)
                    if root.findall('.//{*}infoTable'):
                        table = content
                        break
            if table is None:
                raise ValueError('找不到明細：' + accession)
            parsed = parse_table(table, row['filingDate'])
            expected = primary.findtext('.//{*}tableValueTotal')
            if expected is not None and abs(parsed.value.sum() - float(expected) * (1000 if row['filingDate'] < '2023-01-03' else 1)) > 1:
                raise ValueError('申報總市值與明細不一致：' + accession)
            if row['form'].endswith('/A') and amendment not in ('RESTATEMENT', 'NEW HOLDINGS'):
                raise ValueError('不支援的修正類型：' + str(amendment))
            if amendment == 'NEW HOLDINGS':
                if combined is None:
                    raise ValueError('缺少原始申報，無法套用新增持股修正')
                combined.extend(ET.fromstring(table))
            else:
                combined = ET.fromstring(table)
                sources = []
            sources.append(base + accession + '-index.htm')
            raw_file = accession + '.xml'
            (DATA_DIR / raw_file).write_bytes(table)
        snapshot = ET.tostring(combined, encoding='utf-8')
        filename = period + '-' + hashlib.sha256(snapshot).hexdigest()[:12] + '.xml'
        # Stored modern periods all use dollar units.
        (DATA_DIR / filename).write_bytes(snapshot)
        reports.append(dict(period=period, filed=row['filingDate'], file=filename, sources=sources))
    if not reports:
        raise ValueError('SEC 未回傳可用申報')
    temporary = DATA_DIR / 'manifest.tmp'
    temporary.write_text(json.dumps({'reports': reports}, indent=2) + '\n')
    temporary.replace(DATA_DIR / 'manifest.json')
    print('Updated', len(reports), 'quarters')


if __name__ == '__main__':
    main()
