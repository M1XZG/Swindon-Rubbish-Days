import argparse
import re
from typing import Any, Dict, List, Optional

from playwright.sync_api import Playwright, sync_playwright

PAGE_URL = "https://www.swindon.gov.uk/info/20122/rubbish_and_recycling_collection_days"
DATE_RE = re.compile(
    r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*\d{1,2}\s+[a-z]+\s+\d{4}",
    re.IGNORECASE,
)


def accept_cookies(page) -> None:
    for text in ["Accept Recommended Settings", "Accept all", "Accept"]:
        btn = page.get_by_role("button", name=re.compile(text, re.IGNORECASE))
        if btn.count() and btn.first.is_visible():
            btn.first.click()
            break


def fill_postcode(page, postcode: str) -> None:
    page.wait_for_timeout(500)
    locators = [
        page.get_by_label(re.compile("postcode", re.IGNORECASE)),
        page.get_by_placeholder(re.compile("postcode", re.IGNORECASE)),
        page.get_by_role("textbox", name=re.compile("postcode", re.IGNORECASE)),
        page.locator("input[name=postcode]"),
        page.locator("input[id*=postcode]"),
        page.locator("input[type=search]"),
        page.locator("input[type=text]"),
        page.locator("input"),
    ]
    box = None
    for loc in locators:
        try:
            candidate = loc.locator(":visible").first
            candidate.wait_for(state="visible", timeout=8000)
            box = candidate
            break
        except Exception:
            continue
    if not box:
        raise RuntimeError("Could not find postcode input (try --headful to see the page)")
    box.fill(postcode)
    search_button = page.get_by_role("button", name=re.compile("search", re.IGNORECASE))
    if search_button.count():
        search_button.first.click()
    else:
        box.press("Enter")


def pick_address(page, house_number: Optional[str]) -> None:
    # Wait for address select or list to appear
    select = page.locator("select")
    if select.count() == 0:
        try:
            select = page.wait_for_selector("select", timeout=5000)
        except Exception:
            return
        select = page.locator("select")
    if select.count() == 0:
        return
    options = select.first.evaluate("(el) => Array.from(el.options).map(o => ({value:o.value,text:o.textContent}))")
    choice = options[0]["value"] if options else None
    if house_number:
        for opt in options:
            if str(house_number) in (opt.get("text") or ""):
                choice = opt["value"]
                break
    if choice:
        select.first.select_option(value=choice)


def extract_collections(page) -> List[Dict[str, Any]]:
    script = """
    const dateRe = /(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s*,?\s*\d{1,2}\s+[a-z]+\s+\d{4}/i;
    const matches = [];
    document.querySelectorAll('strong, b').forEach(el => {
      const txt = (el.textContent || '').trim();
      if (!dateRe.test(txt)) return;
      let title = null;
      let node = el;
      while (node) {
        const h3 = node.querySelector ? node.querySelector('h3') : null;
        if (h3 && h3.textContent.trim()) { title = h3.textContent.trim(); break; }
        if (node.previousElementSibling) {
          const prevH3 = node.previousElementSibling.closest('h3');
          if (prevH3 && prevH3.textContent.trim()) { title = prevH3.textContent.trim(); break; }
        }
        node = node.parentElement;
      }
      if (!title) {
        const nearest = el.closest('section, article, div');
        const h3 = nearest ? nearest.querySelector('h3') : null;
        if (h3 && h3.textContent.trim()) title = h3.textContent.trim();
      }
      matches.push({title, date: txt});
    });
    return matches;
    """
    return page.evaluate(script)


def scrape(postcode: str, house_number: Optional[str], headless: bool = True) -> List[Dict[str, Any]]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.goto(PAGE_URL, wait_until="networkidle")
        accept_cookies(page)
        fill_postcode(page, postcode)
        page.wait_for_timeout(2500)
        pick_address(page, house_number)
        page.wait_for_timeout(3000)
        data = extract_collections(page)
        browser.close()
        return data


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Scrape Swindon collection dates via Playwright")
    parser.add_argument("--postcode", required=True, help="Postcode, e.g. SN2 7TN")
    parser.add_argument("--house-number", help="House number")
    parser.add_argument("--headful", action="store_true", help="Run browser non-headless for debugging")
    args = parser.parse_args(argv)

    results = scrape(args.postcode, args.house_number, headless=not args.headful)
    if not results:
        print("No dates found.")
        return 1
    for entry in results:
        print(f"{entry.get('title') or 'Collection'}: {entry.get('date')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
