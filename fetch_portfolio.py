import os
import json
import pyotp
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

EMAIL       = os.environ["COCOS_EMAIL"]
PASSWORD    = os.environ["COCOS_PASSWORD"]
TOTP_SECRET = os.environ["COCOS_TOTP_SECRET"]
WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")

API_URL = "https://api.cocos.capital/api"


def get_token_via_browser():
    print("Abriendo browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        print("Navegando a Cocos...")
        page.goto("https://app.cocos.capital/", wait_until="load")
        page.wait_for_timeout(3000)
        page.screenshot(path="screenshot.png")
        print("Screenshot guardado en screenshot.png")

        print("Llenando email...")
        page.locator('input[type="email"], input[type="text"]').first.fill(EMAIL)

        print("Llenando password...")
        page.locator('input[type="password"]').first.fill(PASSWORD)

        print("Haciendo click en Iniciar sesión...")
        page.get_by_role("button", name="Iniciar sesión").click()

        # Esperar posible campo de TOTP
        try:
            print("Esperando campo TOTP (10s)...")
            page.wait_for_selector("text=Ingresá el código", timeout=10000)
            totp_code = pyotp.TOTP(TOTP_SECRET).now()
            print(f"Ingresando TOTP: {totp_code}")
            page.keyboard.type(totp_code)
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"No aparecio campo TOTP ({e}), continuando...")

        # Manejar pantalla de "dispositivo seguro" si aparece
        try:
            page.wait_for_url("**/trusted-device**", timeout=10000)
            print("Pantalla de dispositivo seguro, cerrando...")
            page.get_by_role("button", name="Sí, guardar como dispositivo seguro").click()
        except Exception:
            pass

        # Navegar directo al portfolio y esperar que cargue
        print("Navegando a portfolio...")
        page.goto("https://app.cocos.capital/capital-portfolio", wait_until="load")
        page.wait_for_timeout(3000)

        # Extraer valor del DOM con el XPath original
        print("Extrayendo valor del portfolio...")
        balance_text = page.evaluate("""() => {
            const xpath = '//p[contains(@class,"_availableWrapper_")]';
            const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            const el = result.singleNodeValue;
            return el ? el.textContent.trim() : null;
        }""")

        browser.close()

        if not balance_text:
            raise Exception("No se encontró el valor en el DOM")

        print(f"Balance encontrado: {balance_text}")
        # "$61.859.053,47" → 61859053.47
        clean = balance_text.replace("$", "").replace(".", "").replace(",", ".").strip()
        balance = float(clean)
        print(f"Balance parseado: {balance}")
        return balance


def get_balance(token=None):
    pass  # ya no se usa


def send_to_webhook(balance):
    if not WEBHOOK_URL:
        print("N8N_WEBHOOK_URL no configurado, saltando webhook.")
        return
    print("Enviando a n8n...")
    r = requests.post(WEBHOOK_URL, json={"totalBalance": balance})
    print(f"Webhook response: {r.status_code}")


if __name__ == "__main__":
    balance = get_token_via_browser()
    send_to_webhook(balance)
