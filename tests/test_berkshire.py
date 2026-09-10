import unittest

from src.berkshire import parse_table, compare_holdings, load_reports, load_holdings


def xml(rows):
    return '<informationTable xmlns="urn:test">' + ''.join(
        f'<infoTable><nameOfIssuer>{name}</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>{cusip}</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>{shares}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>'
        for cusip, name, value, shares in rows) + '</informationTable>'


class BerkshireTests(unittest.TestCase):
    def test_aggregate_and_units(self):
        source = xml([('1', 'A', 10, 2), ('1', 'A', 20, 3)])
        modern = parse_table(source, '2023-01-03')
        self.assertEqual(len(modern), 1)
        self.assertEqual(modern.iloc[0].shares, 5)
        self.assertEqual(modern.iloc[0].value, 30)
        self.assertEqual(parse_table(source, '2022-12-31').iloc[0].value, 30000)

    def test_changes_and_exits(self):
        old = parse_table(xml([(str(i), str(i), 100, 10) for i in range(4)]), '2026-01-01')
        new = parse_table(xml([('0', '0', 80, 20), ('1', '1', 200, 5), ('2', '2', 300, 10), ('4', '4', 50, 5)]), '2026-01-01')
        result = compare_holdings(new, old).set_index('cusip')
        self.assertEqual(result.loc['0', 'direction'], '加碼')
        self.assertEqual(result.loc['0', 'change_pct'], 100)
        self.assertEqual(result.loc['1', 'direction'], '減碼')
        self.assertEqual(result.loc['2', 'direction'], '持平')
        self.assertEqual(result.loc['3', 'direction'], '清倉')
        self.assertEqual(result.loc['3', 'change_pct'], -100)
        self.assertEqual(result.loc['3', 'weight'], 0)
        self.assertEqual(result.loc['4', 'direction'], '新建倉')
        self.assertTrue(result.loc['4', 'change_pct'] != result.loc['4', 'change_pct'])
        self.assertAlmostEqual(result.weight.sum(), 100)

    def test_missing_previous(self):
        current = parse_table(xml([('1', 'A', 10, 2)]), '2026-01-01')
        result = compare_holdings(current)
        self.assertEqual(result.iloc[0].direction, '無前季資料')
        self.assertEqual(result.iloc[0].sector, '未分類')

    def test_real_snapshots(self):
        reports = load_reports()
        self.assertGreaterEqual(len(reports), 2)
        for report in reports:
            table = load_holdings(report)
            self.assertGreater(table.value.sum(), 0)
            self.assertFalse(table.duplicated(['cusip', 'option', 'unit']).any())
