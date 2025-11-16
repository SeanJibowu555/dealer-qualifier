from playwright.sync_api import sync_playwright

def get_fca_status(name: str):
    url = f"https://register.fca.org.uk/s/search?q={name}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=60000)
        page.wait_for_selector(".search-result", timeout=60000)

        elements = page.query_selector_all(".search-result")

        results = []
        for el in elements:
            title = el.query_selector(".search-result__title").inner_text().strip()
            status = el.query_selector(".search-result__status").inner_text().strip()
            frn = el.query_selector(".search-result__frn").inner_text().strip() if el.query_selector(".search-result__frn") else "Unknown"

            results.append({
                "title": title,
                "status": status,
                "frn": frn,
                "url": page.url
            })

        browser.close()
        return results
