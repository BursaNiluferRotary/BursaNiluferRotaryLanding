"""Fetch the club's public Google Calendar and write events.json.

Google's iCal endpoint sends no CORS header, so the page cannot read it in the
browser. A scheduled GitHub Action runs this script instead and commits the result.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "f244980d655efe355f38fa85b9d95a9f77b81967e401ebfb400a94d5beaba373"
    "%40group.calendar.google.com/public/basic.ics"
)
OUTPUT = Path(__file__).resolve().parent.parent / "events.json"
KEEP_PAST_DAYS = 400  # keep a year of history so the calendar can be browsed back


def unfold(text):
    return text.replace("\r\n ", "").replace("\r\n\t", "").replace("\n ", "").replace("\n\t", "")


def unescape(value):
    return value.replace("\\n", "\n").replace("\\,", ",").replace("\;", ";").replace("\\\\", "\\")


def parse_stamp(value, params):
    """Return (ISO 8601 string in UTC, all_day)."""
    if "VALUE=DATE" in params:
        return datetime.strptime(value, "%Y%m%d").date().isoformat(), True
    if value.endswith("Z"):
        stamp = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return stamp.isoformat().replace("+00:00", "Z"), False
    tzid = next((p.split("=", 1)[1] for p in params if p.startswith("TZID=")), None)
    stamp = datetime.strptime(value, "%Y%m%dT%H%M%S")
    if tzid:
        try:
            from zoneinfo import ZoneInfo
            stamp = stamp.replace(tzinfo=ZoneInfo(tzid))
        except Exception:
            stamp = stamp.replace(tzinfo=timezone.utc)
    else:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), False


def parse(ics):
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", unfold(ics), re.S):
        event = {}
        for line in block.strip().splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            parts = name.split(";")
            key, params = parts[0].upper(), parts[1:]
            if key == "SUMMARY":
                event["summary"] = unescape(value.strip())
            elif key == "LOCATION":
                event["location"] = unescape(value.strip())
            elif key == "DESCRIPTION":
                event["description"] = unescape(value.strip())
            elif key == "STATUS":
                event["status"] = value.strip()
            elif key == "UID":
                event["uid"] = value.strip()
            elif key in ("DTSTART", "DTEND"):
                stamp, all_day = parse_stamp(value.strip(), params)
                event[key.lower().replace("dt", "")] = stamp
                event["allDay"] = all_day
        if event.get("status") == "CANCELLED" or "start" not in event:
            continue
        events.append(event)
    return sorted(events, key=lambda e: e["start"])


def main():
    with urllib.request.urlopen(ICS_URL, timeout=30) as response:
        ics = response.read().decode("utf-8")
    events = parse(ics)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_PAST_DAYS)).isoformat()
    events = [e for e in events if e["start"] >= cutoff[:10]]
    if not events:
        sys.exit("No events parsed — leaving events.json untouched.")
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "events": events,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(events)} events written to {OUTPUT}")


if __name__ == "__main__":
    main()
