import os
import sys
import pyotp
import requests
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL")
SCREENSHOTS_DIR = "screenshots"


def _screenshot(page, owner, step):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = f"{SCREENSHOTS_DIR}/{owner}_{step}.png"
    try:
        page.screenshot(path=path, full_page=True)
        print(f"[{owner}] Screenshot guardado: {path}")
    except Exception as e:
        print(f"[{owner}] No se pudo guardar screenshot '{step}': {e}")


def get_balance(email, password, totp_secret, owner):
    print(f"[{owner}] Abriendo browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context()
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        try:
            print(f"[{owner}] Navegando a Cocos...")
            page.goto("https://app.cocos.capital/", wait_until="load")
            page.wait_for_timeout(3000)
            _screenshot(page, owner, "01_login_page")

            print(f"[{owner}] Llenando credenciales...")
            page.locator('input[type="email"], input[type="text"]').first.fill(email)
            page.locator('input[type="password"]').first.fill(password)
            page.get_by_role("button", name="Iniciar sesión").click()

            try:
                print(f"[{owner}] Esperando TOTP...")
                page.wait_for_selector("text=Ingresá el código", timeout=10000)
                _screenshot(page, owner, "02_totp_page")
                totp_code = pyotp.TOTP(totp_secret).now()
                print(f"[{owner}] Ingresando TOTP: {totp_code}")
                page.keyboard.type(totp_code)
                page.wait_for_timeout(2000)
            except Exception:
                print(f"[{owner}] Sin TOTP, continuando...")
                _screenshot(page, owner, "02_after_login")

            try:
                page.wait_for_url("**/trusted-device**", timeout=10000)
                print(f"[{owner}] Pantalla dispositivo seguro, aceptando...")
                _screenshot(page, owner, "03_trusted_device")
                page.get_by_role("button", name="Sí, guardar como dispositivo seguro").click()
            except Exception:
                pass

            print(f"[{owner}] Navegando a portfolio...")
            page.goto("https://app.cocos.capital/capital-portfolio", wait_until="load")
            page.wait_for_timeout(3000)
            _screenshot(page, owner, "04_portfolio_page")

            print(f"[{owner}] Extrayendo balance...")
            balance_text = page.evaluate("""() => {
                const xpath = '//p[contains(@class,"_availableWrapper_")]';
                const result = document.evaluate(xpath, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
                const el = result.singleNodeValue;
                return el ? el.textContent.trim() : null;
            }""")

            if not balance_text:
                _screenshot(page, owner, "05_balance_not_found")
                raise Exception(f"[{owner}] No se encontró el valor en el DOM")

        except Exception:
            _screenshot(page, owner, "ERROR_final_state")
            browser.close()
            raise

        browser.close()

        clean = balance_text.replace("$", "").replace(".", "").replace(",", ".").strip()
        balance = float(clean)
        print(f"[{owner}] Balance: {balance}")
        return balance


def send_to_webhook(owner, balance):
    if not WEBHOOK_URL:
        print("N8N_WEBHOOK_URL no configurado, saltando webhook.")
        return
    print(f"[{owner}] Enviando a n8n...")
    r = requests.post(WEBHOOK_URL, json={"owner": owner, "totalBalance": balance})
    print(f"[{owner}] Webhook response: {r.status_code}")


def run_account(suffix, owner_name):
    email       = os.environ.get(f"COCOS_EMAIL{suffix}")
    password    = os.environ.get(f"COCOS_PASSWORD{suffix}")
    totp_secret = os.environ.get(f"COCOS_TOTP_SECRET{suffix}")

    if not email or not password or not totp_secret:
        print(f"[{owner_name}] Variables no configuradas, saltando.")
        return

    balance = get_balance(email, password, totp_secret, owner_name)
    send_to_webhook(owner_name, balance)


if __name__ == "__main__":
    run_account("", "Leandro")
    run_account("_2", "Esposa")
