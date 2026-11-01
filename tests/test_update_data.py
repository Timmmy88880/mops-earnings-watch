import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from scripts.update_data import (
    SourceError, classify_announcement, merge_records, parse_history, refresh_dataset,
)


def row(title, code="2330", date="2026-10-29"):
    return {"code": code, "name": "測試公司", "date": date, "time": "14:00:00",
            "title": title, "market": "sii", "sequence": "1"}


class ClassificationTests(unittest.TestCase):
    def test_excludes_future_board_dates_even_when_they_mention_financial_reports(self):
        self.assertIsNone(classify_announcement(row("公告115年第三季財務報告董事會預計召開日期"), 2026, 3))

    def test_classifies_reported_and_self_reported_without_confusing_ytd(self):
        for title, expected in [
            ("本公司董事會通過115年度第3季合併財務報表", "reported"),
            ("公告本公司一一五年第三季財務報告", "reported"),
            ("本公司董事會通過115年前三季合併財務報告", "reported"),
            ("公告本公司本(115)年第三季財務報表", "reported"),
            ("公告本公司115年Q3累計合併稅後自結損益", "self_reported"),
            ("公告本公司2026年第三季及前三季度自結合併財務報表", "self_reported"),
        ]:
            with self.subTest(title=title):
                self.assertEqual(classify_announcement(row(title), 2026, 3), expected)

    def test_excludes_old_periods_monthly_numbers_and_subsidiary_reports(self):
        for title in [
            "公告本公司114年第三季合併財務報告", "公告本公司115年第二季財務報告",
            "公告本公司115年9月份自結財務報告", "代子公司公告115年第三季合併財務報告",
            "公告本公司115年第三季法人說明會日期", "更正115年第三季財務報告部分資訊",
        ]:
            with self.subTest(title=title):
                self.assertIsNone(classify_announcement(row(title), 2026, 3))

    def test_reads_actual_quarter_results_inside_an_ir_summary(self):
        summary = row("公告本公司今日法人說明會摘要", "2408")
        self.assertEqual(classify_announcement(summary, 2026, 3,
            "南亞科技公布115年第3季自結合併財務資訊，營業收入及本期淨利。"), "self_reported")

    def test_tsmc_earnings_release_is_a_report_but_a_meeting_invitation_is_not(self):
        self.assertEqual(classify_announcement(row("台積公司2026年第三季每股盈餘新台幣29.43元"),
            2026, 3, "台積公司今日公布2026年第三季財務報告。"), "reported")
        self.assertIsNone(classify_announcement(row("本公司召開2026年第三季法人說明會"), 2026, 3))

    def test_subsidiary_title_or_board_item_is_not_the_parent_report(self):
        self.assertIsNone(classify_announcement(row("公告本公司重要子公司115年第三季財務報告"), 2026, 3))
        self.assertIsNone(classify_announcement(row("公告本公司董事會重要決議事項"), 2026, 3,
            "通過子公司甲公司115年第三季合併財務報告。"))

    def test_report_and_quarter_must_belong_to_the_same_board_item(self):
        self.assertIsNone(classify_announcement(row("公告本公司董事會重要決議事項"), 2026, 3,
            "(1)通過本公司115年第二季財務報告。(2)通過本公司115年第三季資本支出案。"))

    def test_year_nearest_the_quarter_controls_the_reporting_period(self):
        self.assertIsNone(classify_announcement(row("公告本公司115年董事會通過114年度第三季財務報告"), 2026, 3))

    def test_mops_entity_prompt_does_not_make_own_report_a_subsidiary_report(self):
        self.assertEqual(classify_announcement(row("公告本公司今日法人說明會摘要"), 2026, 3,
            "3.與公司關係(請輸入本公司或子公司):本公司 5.南亞科技公布115年第3季自結合併財務資訊。"), "self_reported")


class ParsingTests(unittest.TestCase):
    def test_reads_official_row_fields_and_market_from_the_details_button(self):
        records = parse_history((Path(__file__).parent / "fixtures/history.html").read_text())
        self.assertEqual(records[0]["code"], "2330")
        self.assertEqual(records[0]["date"], "2026-10-15")
        self.assertEqual(records[0]["market"], "sii")
        self.assertEqual(records[0]["sequence"], "1")

    def test_rejects_block_pages_and_truncated_responses(self):
        for source in ["<html><body>FOR SECURITY REASONS</body></html>",
                       "<html><table><tr><td>2330</td>", "<html><body>unexpected</body></html>"]:
            with self.subTest(source=source):
                with self.assertRaises(SourceError):
                    parse_history(source)

    def test_accepts_an_explicit_official_no_data_response(self):
        self.assertEqual(parse_history("<html><body>公開資訊觀測站 查無資料</body></html>"), [])

    def test_tdr_rows_use_a_different_endpoint_and_do_not_break_regular_stock_parsing(self):
        source = (Path(__file__).parent / "fixtures/history.html").read_text()
        tdr = '''<tr><td>9110</td><td>越南控-DR</td><td>115/10/02</td>
        <td>16:31:43</td><td>證券變動月報表</td><td><input type="button"
        onclick="document.t59sb01_form.action='ajax_t59sb01';document.t59sb01_form.co_id.value='9110';"></td></tr>'''
        result = parse_history(source.replace('</table>', tdr + '</table>'))
        self.assertEqual(len(result), 3)
        self.assertNotIn('9110', [r['code'] for r in result])


class MergeAndRefreshTests(unittest.TestCase):
    def test_upgrades_self_report_to_reported_without_duplicating_the_company(self):
        old = dict(row("自結", date="2026-10-12"), status="self_reported")
        new = dict(row("財報", date="2026-10-27"), status="reported")
        result = merge_records([old], [new, copy.deepcopy(new)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "reported")
        self.assertEqual(result[0]["date"], "2026-10-27")

    def test_a_later_self_report_does_not_downgrade_an_existing_report(self):
        old = dict(row("財報", date="2026-10-15"), status="reported")
        new = dict(row("自結", date="2026-10-29"), status="self_reported")
        self.assertEqual(merge_records([old], [new])[0]["status"], "reported")

    def test_failed_network_refresh_leaves_the_last_good_file_byte_identical(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "data.json"
            original = '{"meta":{"checked_at":"2026-10-29T07:32:00Z"},"records":[]}\n'
            output.write_text(original)
            def unavailable(start, end):
                raise SourceError("source unavailable")
            with self.assertRaises(SourceError):
                refresh_dataset({"year": 2026, "quarter": 3, "from_date": "2026-10-01",
                    "through_date": "2026-12-31"}, output,
                    datetime(2026, 11, 2, tzinfo=timezone.utc), unavailable, lambda record: "")
            self.assertEqual(output.read_text(), original)


if __name__ == "__main__":
    unittest.main()
