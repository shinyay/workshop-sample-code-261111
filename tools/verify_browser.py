import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, expect, sync_playwright


def fill_request(page: Page, title: str) -> None:
    page.get_by_label("件名", exact=False).fill(title)
    page.get_by_label("申請者名（架空）", exact=False).fill("架空 てすと")
    page.get_by_label("担当部署", exact=False).select_option("engineering")
    page.get_by_label("申請種別", exact=False).select_option("equipment")
    page.get_by_label("申請内容", exact=False).fill(
        "ブラウザーで画面と操作を確認するための、架空の申請です。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="専用デモデータを使う実ブラウザー確認")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--stage", choices=["starter", "reference"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()
    url = args.url.rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        parser.error("起動済みのローカル専用ポータルを指定してください。")
    args.output.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    screenshots: list[str] = []
    script_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.channel, headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="ja-JP")
            page.set_default_timeout(10000)
            page.on("pageerror", lambda error: script_errors.append(str(error)))
            health = page.request.get(f"{url}/healthz")
            assert health.ok and health.json()["stage"] == args.stage
            initial = page.request.get(f"{url}/api/requests").json()
            assert initial["count"] == 12, "先に専用デモデータを12件へリセットしてください。"
            assert initial["items"][-1]["title"] == "検証用キーボードの購入"
            page.goto(f"{url}/requests?scoutTheme=light")
            expect(page.get_by_text("12件を表示", exact=True)).to_be_visible()
            expect(page.locator("tbody tr")).to_have_count(12)
            expected_label = "完成例" if args.stage == "reference" else "初期アプリ"
            expect(page.locator(".workshop-note strong")).to_have_text(expected_label)

            def capture(name: str) -> None:
                path = args.output / f"{name}.png"
                page.screenshot(path=str(path), full_page=True)
                screenshots.append(str(path.resolve()))

            capture("list-light-desktop")
            checks.append("desktop list and all 12 rows")
            page.goto(f"{url}/requests")
            page.keyboard.press("Tab")
            expect(page.locator(".skip-link")).to_be_focused()
            page.keyboard.press("Enter")
            expect(page.locator("#main")).to_be_focused()
            checks.append("keyboard skip link reaches main content")

            if args.stage == "reference":
                page.get_by_label("担当部署", exact=True).select_option("engineering")
                page.get_by_label("申請状態", exact=True).select_option("pending")
                page.get_by_role("button", name="絞り込む", exact=True).click()
                expect(page.get_by_text("1件を表示", exact=True)).to_be_visible()
                expect(page.locator("tbody tr")).to_have_count(1)
                expect(page.get_by_role("link", name="検証用キーボードの購入")).to_be_visible()
                assert (
                    page.request.get(
                        f"{url}/api/requests?department=engineering&status=pending"
                    ).json()["count"]
                    == 1
                )
                page.get_by_label("担当部署", exact=True).select_option("corporate")
                page.get_by_label("申請状態", exact=True).select_option("rejected")
                page.get_by_role("button", name="絞り込む", exact=True).click()
                expect(page.get_by_text("0件を表示", exact=True)).to_be_visible()
                capture("filter-empty")
                page.get_by_role("link", name="条件を解除する", exact=True).click()
                expect(page.get_by_text("12件を表示", exact=True)).to_be_visible()
                checks.append("AND filtering, API agreement, no matches, and clearing")
            else:
                expect(page.locator(".filter-form")).to_have_count(0)
                assert page.request.get(f"{url}/api/requests?department=engineering").status == 400
                checks.append("starter has no filtering and rejects unsupported queries")

            page.get_by_role("link", name="検証用キーボードの購入").click()
            expect(page.get_by_role("heading", level=1)).to_have_text("検証用キーボードの購入")
            expect(page.get_by_role("button", name="承認する", exact=True)).to_be_visible()
            checks.append("detail displays the seeded request and available decisions")
            page.goto(f"{url}/requests/new")
            title = "ブラウザー確認用の架空申請"
            fill_request(page, title)
            page.locator("#title").focus()
            page.keyboard.press("Tab")
            expect(page.locator("#applicant")).to_be_focused()
            page.locator("#details").fill("短い説明")
            assert not page.locator("form").evaluate("(form) => form.checkValidity()")
            page.locator("form").evaluate("(form) => form.setAttribute('novalidate', '')")
            page.get_by_role("button", name="申請を登録", exact=True).click()
            expect(page.get_by_role("alert")).to_be_visible()
            expect(page.locator("#details")).to_have_attribute("aria-invalid", "true")
            expect(page.locator("#title")).to_have_value(title)
            capture("form-validation")
            fill_request(page, title)
            page.get_by_role("button", name="申請を登録", exact=True).click()
            expect(page.get_by_role("heading", level=1)).to_have_text(title)
            assert page.url.endswith("/requests/13")
            capture("detail-pending")
            page.get_by_role("button", name="承認する", exact=True).click()
            expect(page.locator(".processed-message")).to_contain_text("承認済み")
            expect(page.get_by_role("button", name="差し戻す", exact=True)).to_have_count(0)
            assert page.request.get(f"{url}/api/requests/13").json()["status"] == "approved"
            page.goto(f"{url}/requests/new")
            fill_request(page, "差し戻し確認用の架空申請")
            page.get_by_role("button", name="申請を登録", exact=True).click()
            assert page.url.endswith("/requests/14")
            page.get_by_role("button", name="差し戻す", exact=True).click()
            expect(page.locator(".processed-message")).to_contain_text("差し戻し")
            assert page.request.get(f"{url}/api/requests/14").json()["status"] == "rejected"
            checks.append(
                "native input validation, server errors, preserved values, creation, both decisions"
            )

            page.goto(f"{url}/requests?scoutTheme=dark")
            expect(page.locator("html")).to_have_attribute("data-theme", "dark")
            capture("list-dark-desktop")
            page.set_viewport_size({"width": 375, "height": 812})
            page.goto(f"{url}/requests?scoutTheme=light")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), (
                "ページ全体が画面幅を超えています。"
            )
            table = page.locator(".table-scroll")
            table.focus()
            expect(table).to_be_focused()
            page.keyboard.press("ArrowRight")
            page.wait_for_function("() => document.querySelector('.table-scroll').scrollLeft > 0")
            capture("list-mobile")
            page.goto(f"{url}/requests/new")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            capture("form-mobile")
            response = page.goto(f"{url}/requests?unexpected=x")
            assert response is not None and response.status == 400
            expect(page.get_by_role("alert")).to_contain_text("検索条件")
            capture("error-mobile")
            checks.append(
                "light/dark rendering, 375px layouts, keyboard table scrolling, error page"
            )
            assert not script_errors, script_errors
            report = {
                "stage": args.stage,
                "browser": browser.version,
                "checks": checks,
                "screenshots": screenshots,
                "uncaught_script_errors": script_errors,
                "demo_requests_created": [13, 14],
            }
            (args.output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(json.dumps(report, ensure_ascii=True, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
