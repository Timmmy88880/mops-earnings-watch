#!/usr/bin/env python3
"""Refresh one reporting period from official MOPS announcements; stdlib only."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://mopsov.twse.com.tw/mops/web/ajax_t05st01"
TAIPEI = timezone(timedelta(hours=8))


class SourceError(RuntimeError):
    """An official response could not be verified; do not replace good data."""


class HistoryParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.cells = None
        self.cell = None
        self.action = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.cells, self.action = [], ""
        elif tag == "td" and self.cells is not None:
            self.cell = []
        elif tag == "input" and self.cells is not None:
            self.action = attrs.get("onclick", self.action)

    def handle_data(self, text):
        if self.cell is not None:
            self.cell.append(text)

    def handle_endtag(self, tag):
        if tag == "td" and self.cells is not None and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.cells is not None:
            self.rows.append((self.cells, self.action))
            self.cells, self.cell = None, None


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)


def validate_response(source):
    if not re.search(r"</html\s*>", source, re.I):
        raise SourceError("MOPS returned truncated HTML")
    if re.search(r"FOR SECURITY REASONS|因為安全性考量|access denied|request rejected", source, re.I):
        raise SourceError("MOPS did not provide an accessible response")
    if "公開資訊觀測站" not in source:
        raise SourceError("Unexpected response from MOPS")


def parse_history(source: str) -> list[dict]:
    validate_response(source)
    parser = HistoryParser()
    parser.feed(source)
    result = []
    for cells, action in parser.rows:
        if len(cells) < 5 or not re.fullmatch(r"\d{4,6}", cells[0]):
            continue
        # TDR announcements share the page but use t59sb01 rather than the
        # domestic/company financial-report detail schema.
        if "ajax_t59sb01" in action:
            continue
        match = re.fullmatch(r"(\d{3})/(\d{2})/(\d{2})", cells[2])
        if not match:
            raise SourceError("Announcement has an invalid date")
        roc, month, day = map(int, match.groups())
        iso = date(roc + 1911, month, day).isoformat()
        fields = dict(re.findall(r"\.([A-Za-z_]+)\.value=['\"]([^'\"]*)['\"]", action))
        if not fields.get("TYPEK") or not fields.get("seq_no"):
            raise SourceError("Announcement is missing its source reference")
        result.append({"code": cells[0], "name": cells[1], "date": iso, "time": cells[3],
                       "title": cells[4], "market": fields["TYPEK"], "sequence": fields["seq_no"]})
    if not result and "查無資料" not in source:
        raise SourceError("No recognizable announcement table in MOPS response")
    return result


def has_period(text, year, quarter):
    text = re.sub(r"[()（）]", "", text)
    chinese = {1: "一", 2: "二", 3: "三", 4: "四"}[quarter]
    quarter_re = rf"第\s*[{quarter}{chinese}]\s*季|前\s*[{quarter}{chinese}]\s*季|Q\s*{quarter}|{quarter}\s*Q"
    # Chinese ROC digits occur in announcements such as 一一五年第三季.
    digits = "零一二三四五六七八九"
    roc_digits = "".join(digits[int(n)] for n in str(year - 1911))
    accepted_years = {str(year), str(year - 1911), roc_digits}
    years = list(re.finditer(r"(\d{3,4}|[零一二三四五六七八九]{3})\s*年(?:度)?", text))
    for period in re.finditer(quarter_re, text, re.I):
        preceding = [match for match in years if match.end() <= period.start()]
        if preceding:
            closest = preceding[-1]
            if closest.group(1) in accepted_years and period.start() - closest.end() <= 24:
                return True
    return bool(re.search(rf"{quarter}\s*Q\s*{str(year)[2:]}\b", text, re.I))


def classify_announcement(record: dict, year: int, quarter: int, detail_text: str = "") -> str | None:
    title = record["title"]
    own_entity_title = re.sub(r"本公司(?:及|與)子公司", "本公司", title)
    if re.search(r"子公司|代重要|預計|召開日期|更正|更補正|更換|業績預告", own_entity_title):
        return None
    summary = bool(re.search(r"法[人說].{0,8}摘要|董事會重要決議|董事會決議事項", title))
    if not summary and re.search(r"法[人說]|說明會|基準日|股利|私募|資金運用", title):
        return None
    # MOPS includes this instruction as boilerplate in its entity field.
    body = re.sub(r"[（(]請輸入本公司或子公司[）)]", "", detail_text)
    clauses = [title] + re.split(r"[。；;，,\n]", body)
    statuses = []
    for clause in clauses:
        entity = re.sub(r"本公司(?:及|與)子公司", "本公司", clause)
        if "子公司" in entity or not has_period(clause, year, quarter):
            continue
        if re.search(r"自結|自行結算", clause):
            statuses.append("self_reported")
        elif re.search(r"財務報告|財務報表|財報|財報務告", clause):
            statuses.append("reported")
    if "reported" in statuses:
        return "reported"
    if "self_reported" in statuses:
        return "self_reported"
    return None


def needs_detail(record):
    return bool(re.search(r"法[人說].{0,8}摘要|董事會重要決議|董事會決議事項|每股盈餘", record["title"]))


def source_url(record):
    params = {"step": "2", "firstin": "1", "off": "1", "TYPEK": record["market"],
              "co_id": record["code"], "year": record["date"][:4], "month": record["date"][5:7],
              "spoke_date": record["date"].replace("-", ""),
              "spoke_time": record["time"].replace(":", ""), "seq_no": record["sequence"]}
    return ENDPOINT + "?" + urlencode(params)


def merge_records(existing: list, incoming: list) -> list:
    merged = {}
    for record in existing + incoming:
        old = merged.get(record["code"])
        if old is None:
            merged[record["code"]] = record
        elif old["status"] != "reported" and record["status"] == "reported":
            merged[record["code"]] = record
        elif old["status"] == record["status"] and (record["date"], record["time"]) < (old["date"], old["time"]):
            merged[record["code"]] = record
    return sorted(merged.values(), key=lambda r: (r["date"], r["time"], r["code"]), reverse=True)


def request_html(params):
    request = Request(ENDPOINT, data=urlencode(params).encode(), headers={
        "User-Agent": "Mozilla/5.0 (compatible; MOPSEarningsTracker/1.0)",
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html",
    })
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                body = response.read(20_000_001)
            if len(body) > 20_000_000:
                raise SourceError("MOPS response exceeded the expected size")
            source = body.decode("utf-8", errors="strict")
            validate_response(source)
            return source
        except Exception as error:
            if attempt == 2:
                raise SourceError(f"MOPS request failed: {error}") from error
            time.sleep(2 * (attempt + 1))
    raise SourceError("MOPS request did not complete")


def fetch_history(start, end):
    print(f"Querying MOPS {start} to {end}", flush=True)
    return request_html({"step": "1", "firstin": "1", "off": "1", "TYPEK": "all", "co_id": "",
                         "year": str(start.year - 1911), "month": f"{start.month:02}",
                         "b_date": f"{start.day:02}", "e_date": f"{end.day:02}"})


def fetch_detail(record):
    source = request_html({"step": "2", "firstin": "1", "off": "1", "TYPEK": record["market"],
                           "co_id": record["code"], "year": record["date"][:4],
                           "month": record["date"][5:7], "spoke_date": record["date"].replace("-", ""),
                           "spoke_time": record["time"].replace(":", ""), "seq_no": record["sequence"]})
    parser = TextParser()
    parser.feed(source)
    text = " ".join(" ".join(parser.parts).split())
    if record["code"] not in text or "說明" not in text:
        raise SourceError(f"Missing detail for {record['code']}")
    return text


def month_windows(start, end):
    while start <= end:
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(end, next_month - timedelta(days=1))
        yield start, stop
        start = next_month


def validate_dataset(data):
    records = data["records"]
    if len({r["code"] for r in records}) != len(records):
        raise ValueError("Dataset contains duplicate companies")
    for record in records:
        if record["status"] not in {"reported", "self_reported"}:
            raise ValueError("Invalid report status")
        if record["market"] not in {"sii", "otc", "rotc", "pub"}:
            raise ValueError("Invalid market")
        date.fromisoformat(record["date"])
        if not record["url"].startswith(ENDPOINT + "?"):
            raise ValueError("Announcement must link to the official MOPS endpoint")
    return data


def refresh_dataset(config, output, now=None, fetch_history=fetch_history, fetch_detail=fetch_detail):
    now = now or datetime.now(timezone.utc)
    previous = json.loads(output.read_text()) if output.exists() else {"meta": {}, "records": []}
    start = date.fromisoformat(config["from_date"])
    checked = previous["meta"].get("checked_at")
    if checked:
        checked_day = datetime.fromisoformat(checked.replace("Z", "+00:00")).astimezone(TAIPEI).date()
        start = max(start, checked_day - timedelta(days=config.get("lookback_days", 14)))
    end = min(now.astimezone(TAIPEI).date(), date.fromisoformat(config["through_date"]))
    # Always validate at least one source response, even after the tracking window closes.
    start = min(start, end)
    all_rows = []
    for begin, stop in month_windows(start, end):
        all_rows.extend(parse_history(fetch_history(begin, stop)))
    incoming = []
    for record in all_rows:
        if not (config["from_date"] <= record["date"] <= end.isoformat()):
            continue
        if len(record["code"]) != 4:
            continue
        detail = fetch_detail(record) if needs_detail(record) else ""
        status = classify_announcement(record, config["year"], config["quarter"], detail)
        if status:
            incoming.append({**record, "status": status, "url": source_url(record),
                             "cumulative": bool(re.search(r"前三季|前3季|Q3累計", record["title"], re.I))})
    records = merge_records(previous["records"], incoming)
    timestamp = now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    changed = records != previous["records"]
    latest = max((r["date"] + "T" + r["time"] + "+08:00" for r in records), default=None)
    meta = {**previous["meta"], "year": config["year"], "quarter": config["quarter"],
            "checked_at": timestamp,
            "updated_at": timestamp if changed else previous["meta"].get("updated_at", timestamp),
            "latest_announcement_at": latest, "schedule": config["schedule"],
            "repository": config["repository"], "source": "公開資訊觀測站", "source_url": ENDPOINT,
            "query_from": start.isoformat(), "query_through": end.isoformat(),
            "last_query_announcements": len(all_rows)}
    data = validate_dataset({"meta": meta, "records": records})
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".earnings-", suffix=".json", dir=output.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print(f"Verified {len(records)} companies; {len(incoming)} matching announcements", flush=True)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "web/data/2026-q3.json")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.validate_only:
            data = validate_dataset(json.loads(args.output.read_text()))
            print(f"Valid dataset: {len(data['records'])} companies")
        else:
            refresh_dataset(json.loads(args.config.read_text()), args.output)
    except (SourceError, ValueError, KeyError, OSError) as error:
        print(f"Update stopped; last good dataset preserved: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
