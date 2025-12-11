import argparse
import json
import re
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://maps.swindon.gov.uk/getdata.aspx"
TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: Any) -> Any:
    """Remove simple HTML tags (e.g., <b>postcode</b>) from API strings."""
    if isinstance(text, str):
        return TAG_RE.sub("", text)
    return text


def _safe_json(response: requests.Response) -> Any:
    """Parse JSON even when server sends the wrong content-type."""
    try:
        return response.json()
    except ValueError:
        return json.loads(response.text)


def search_locations(query: str, page_size: int = 150) -> List[Dict[str, Any]]:
    params = {
        "type": "json",
        "service": "LocationSearch",
        "RequestType": "LocationSearch",
        "location": query,
        "pagesize": page_size,
        "startnum": 1,
        "mapsource": "mapsources/LocalInfoLookup",
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    payload = _safe_json(resp)
    columns = payload.get("columns", [])
    data_rows = payload.get("data", [])
    addresses: List[Dict[str, Any]] = []
    for row in data_rows:
        item = {col: row[idx] for idx, col in enumerate(columns) if idx < len(row)}
        for key in ("DisplayName", "Name"):
            if key in item:
                item[key] = strip_tags(item[key])
        addresses.append(item)
    return addresses


def select_address(addresses: List[Dict[str, Any]], house_number: Optional[str]) -> Optional[Dict[str, Any]]:
    if not addresses:
        return None
    if house_number:
        pattern = re.compile(rf"\b{re.escape(str(house_number))}\b", re.IGNORECASE)
        filtered = [addr for addr in addresses if pattern.search(str(addr.get("DisplayName", "")))]
        if filtered:
            return filtered[0]
    return addresses[0]


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _extract_weekday(text: str) -> Optional[str]:
    lowered = text.lower()
    for day in WEEKDAYS:
        if day in lowered:
            return day.title()
    return None


DATE_PATTERN = re.compile(
    r"(?P<dayname>monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*,?\s*"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)"
    r"\s+(?P<year>\d{4})",
    re.IGNORECASE,
)


def _parse_explicit_date(text: str) -> Optional[date]:
    if not text:
        return None
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    day = int(match.group("day"))
    month = MONTHS.get(match.group("month").lower())
    year = int(match.group("year"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_date_for_day(day_name: str, today: date) -> date:
    target = WEEKDAYS.index(day_name.lower())
    current = today.weekday()
    delta = (target - current) % 7
    # If today is the day, keep today; otherwise move forward.
    return today + timedelta(days=delta)


def fetch_waste_info(uprn: str) -> List[Any]:
    params = {
        "RequestType": "LocalInfo",
        "ms": "mapsources/LocalInfoLookup",
        "group": "Waste Collection Days",
        "uid": uprn,
        "format": "json",
    }
    resp = requests.get(BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return _safe_json(resp)


def parse_collections(items: List[Any], today: Optional[date] = None) -> List[Dict[str, Optional[str]]]:
    collections: List[Dict[str, Optional[str]]] = []
    today = today or date.today()
    for item in items:
        results = item.get("Results", {}) if isinstance(item, dict) else {}
        for service_key, details in results.items():
            service_name = service_key.replace("_", " ")
            day: Optional[str] = None
            message: Optional[str] = None
            next_date: Optional[date] = None

            if isinstance(details, dict):
                message = details.get("_") if isinstance(details.get("_"), str) else None
                if message:
                    day = _extract_weekday(message)
                    next_date = _parse_explicit_date(message)

                for alt_key in ("collectday", "collectionroute", "CollectionDay", "collectionday"):
                    alt_value = details.get(alt_key)
                    if isinstance(alt_value, str) and not day:
                        day = alt_value
                    if isinstance(alt_value, str) and not next_date:
                        next_date = _parse_explicit_date(alt_value)
                if not message and isinstance(details.get("Info"), str):
                    message = details["Info"]
                    next_date = next_date or _parse_explicit_date(message)
            elif isinstance(details, str):
                message = details
                day = _extract_weekday(details)
                next_date = _parse_explicit_date(details)

            if day or message:
                if not next_date and day:
                    try:
                        next_date = _next_date_for_day(day, today)
                    except ValueError:
                        next_date = None
                collections.append({
                    "service": service_name,
                    "day": day,
                    "message": message,
                    "date": next_date.isoformat() if next_date else None,
                })
    return collections


def format_output(address: Dict[str, Any], collections: List[Dict[str, Optional[str]]]) -> str:
    lines = []
    lines.append(f"Address: {address.get('DisplayName', address.get('Name', 'Unknown'))}")
    lines.append(f"UPRN: {address.get('UniqueId', 'N/A')}")
    if not collections:
        lines.append("No collection details found.")
        return "\n".join(lines)

    lines.append("Collections:")
    for entry in collections:
        line = f"  - {entry['service']}: "
        parts: List[str] = []
        if entry.get("day"):
            parts.append(entry["day"])
        if entry.get("date"):
            parts.append(f"{entry['date']}")
        if entry.get("message"):
            parts.append(entry["message"])
        if not parts:
            parts.append("No details")
        line += " | ".join(parts)
        lines.append(line)
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lookup Swindon rubbish collection days")
    parser.add_argument("--postcode", required=True, help="Postcode to search (e.g. SN1 2JG)")
    parser.add_argument("--house-number", help="House number to match within the postcode")
    args = parser.parse_args(argv)

    try:
        addresses = search_locations(args.postcode)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Failed to search postcode: {exc}", file=sys.stderr)
        return 1

    chosen = select_address(addresses, args.house_number)
    if not chosen:
        print("No addresses found for that postcode.", file=sys.stderr)
        return 1

    uprn = str(chosen.get("UniqueId"))
    try:
        raw_collections = fetch_waste_info(uprn)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Failed to fetch collection info: {exc}", file=sys.stderr)
        return 1

    collections = parse_collections(raw_collections)
    output = format_output(chosen, collections)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
