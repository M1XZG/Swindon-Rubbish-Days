# Swindon Rubbish Days

Simple CLI that looks up Swindon Borough Council rubbish and recycling collection days by postcode and house number.

## How it works
- Searches the council's iShare API at `https://maps.swindon.gov.uk/getdata.aspx` with `RequestType=LocationSearch` to resolve addresses (UPRN) for a postcode.
- Picks the address that matches your house number (or the first result if no match).
- Fetches `RequestType=LocalInfo` with `group=Waste Collection Days` for that UPRN and prints each waste stream and its next collection day/message.

## Setup
1. Install Python 3.10+.
2. (Recommended) Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt  # use pip3 if pip points to Python 2
   ```

## Usage
```bash
python main.py --postcode "SN1 2JG" --house-number "10"
```
- `--postcode` is required.
- `--house-number` is optional but improves matching if the postcode returns multiple addresses.

Example output:
```
Address: Wat Tyler House, ... SN1 2JG
UPRN: 100121342852
Collections:
   - Bulky Waste Collection Day: Friday | 2025-12-12 | Your next collection day is: Friday
   - Clinical Waste Collection Day: Wednesday | 2025-12-10 | Your next collection day is: Wednesday
   - Bulky Waste For Link: Friday | 2025-12-12
   - Clinical Waste For Link: Wednesday | 2025-12-10
   - Food Waste Trial: No
```

## Notes
- The council endpoint responds with JSON but sets an incorrect content-type; the script handles this gracefully.
- If no explicit date is present in the response, the script derives the next occurrence of the given weekday starting from today.
- The API does not require authentication or cookies for these requests.
- If no matching address is found for a house number, the script falls back to the first address in the postcode results.

## Playwright scraper (to capture dated schedules)
The council web page shows dated schedules that are not in the public iShare JSON. A helper scraper uses Playwright to extract those dates from the rendered page.

Setup (one-time browser download):
```bash
python3 -m playwright install chromium
```

Run:
```bash
python3 scrape.py --postcode "SN2 7TN" --house-number "48"
```
Add `--headful` to watch the browser.
