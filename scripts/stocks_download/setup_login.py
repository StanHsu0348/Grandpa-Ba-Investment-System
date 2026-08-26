"""
一次性(或 session 過期後重跑)登入設定腳本。

會開啟一個真正的瀏覽器視窗，由你自己手動輸入帳號密碼、通過 CAPTCHA 完成登入。
登入成功後，把瀏覽器的登入狀態（cookies）存到 auth_state.json，
之後 daily_download.py 就能重複使用這個已登入的 session 自動下載，不必每次手動登入。

用法:
    python setup_login.py

什麼時候要重跑這個腳本:
    - 第一次設定時
    - daily_download.py 執行失敗，訊息顯示 session 已過期/被導回登入頁時
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "auth_state.json"
LOGIN_URL = "https://stocks.ddns.net/Login.aspx"
DOWNLOAD_URL = "https://stocks.ddns.net/App/DownloadList.aspx"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL)

        print("=" * 60)
        print("瀏覽器視窗已開啟，請自己在裡面輸入帳號密碼並完成登入（含 CAPTCHA）。")
        print("登入成功、確定已經看到討論區頁面之後，回到這個視窗按 Enter 繼續。")
        print("=" * 60)
        input()

        # 登入成功後網站本身可能還在跑自己的轉址，先等它穩定下來，
        # 避免我們的 goto 跟網站的轉址互相打架 (navigation interrupted)。
        try:
            page.wait_for_load_state("load", timeout=5000)
        except Exception:
            pass
        page.wait_for_timeout(1000)

        for attempt in range(3):
            try:
                page.goto(DOWNLOAD_URL, wait_until="load")
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"導航被中斷，重試中... ({e})")
                page.wait_for_timeout(1500)

        page.wait_for_load_state("networkidle")

        if "Login.aspx" in page.url:
            print("看起來還沒登入成功（被導回登入頁了），請重新執行本程式再試一次。")
            browser.close()
            sys.exit(1)

        context.storage_state(path=str(STATE_FILE))

        dump_file = BASE_DIR / "downloadlist_dump.html"
        dump_file.write_text(page.content(), encoding="utf-8")

        print(f"登入狀態已儲存到: {STATE_FILE}")
        print(f"下載頁面內容已存到: {dump_file}（供除錯確認用，之後可刪除）")
        browser.close()


if __name__ == "__main__":
    main()
