print("СТАРТ")

from playwright.sync_api import sync_playwright


print("Playwright импортирован")


with sync_playwright() as p:

    print("Запускаем браузер")

    browser = p.chromium.launch(headless=False)

    print("Браузер открыт")

    page = browser.new_page()

    page.goto("https://www.google.com")

    print("Страница открыта")

    print(page.title())

    browser.close()

    print("Готово")