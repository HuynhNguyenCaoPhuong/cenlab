import os
import csv
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.alert import Alert


CENLAB_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"

USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"


def load_rows_from_csv(csv_filename: str):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, csv_filename)

    rows = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")

        for i, r in enumerate(reader, start=1):
            ten_noi_lay_mau = (r.get("Tên nơi lấy mẫu") or "").strip()
            ten_viet_tat = (r.get("Tên viết tắt") or "").strip()
            dia_chi = (r.get("Địa chỉ (tiếng Việt)") or r.get("Địa chỉ") or "").strip()

            if not ten_noi_lay_mau:
                print(f"⚠️ Bỏ qua dòng #{i} vì thiếu Tên nơi lấy mẫu")
                continue

            rows.append({
                "ten_noi_lay_mau": ten_noi_lay_mau,
                "ten_viet_tat": ten_viet_tat,
                "dia_chi": dia_chi,
                "_rownum": i
            })

    print(f"📌 CSV path: {csv_path}")
    print(f"📌 Đã đọc {len(rows)} dòng hợp lệ từ CSV")
    return rows


def run():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    try:
        driver.get(CENLAB_URL)

        user_el = wait.until(EC.visibility_of_element_located((By.ID, "user-name")))
        user_el.clear()
        user_el.send_keys(USERNAME)

        pass_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='password']")))
        pass_el.clear()
        pass_el.send_keys(PASSWORD)

        wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-login[type='submit']"))).click()

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid-layout-container")))

        monitoring_card = wait.until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//div[contains(@class,'title') and normalize-space()='Lấy mẫu - Quan trắc']/ancestor::kendo-card[1]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", monitoring_card)
        driver.execute_script("arguments[0].click();", monitoring_card)

        dia_diem_item = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-drawer-item[aria-label='Địa điểm quan trắc']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dia_diem_item)
        driver.execute_script("arguments[0].click();", dia_diem_item)

        print("✅ Đã vào trang Địa điểm quan trắc")
        time.sleep(5)

        return driver, wait

    except Exception as e:
        print("❌ Error trong quá trình login/menu:", e)
        driver.save_screenshot("cenlab_error.png")
        driver.quit()
        raise


def _get_active_dialog(driver, wait):
    return wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))


def _accept_alert_if_any(driver, short_wait_seconds=3):
    try:
        WebDriverWait(driver, short_wait_seconds).until(EC.alert_is_present())
        a = Alert(driver)
        txt = a.text
        a.accept()
        return txt
    except TimeoutException:
        return None


def add_locations_from_csv(driver, wait, csv_filename="NM.csv", pause_each=0.5):
    rows = load_rows_from_csv(csv_filename)
    print(f"📄 Bắt đầu thêm {len(rows)} địa điểm...")

    for r in rows:
        ten_noi_lay_mau = r["ten_noi_lay_mau"]
        ten_viet_tat = r["ten_viet_tat"]
        dia_chi = r["dia_chi"]

        try:
            # Click nút Thêm
            add_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Thêm']")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_btn)
            driver.execute_script("arguments[0].click();", add_btn)

            time.sleep(1.8)

            dialog = _get_active_dialog(driver, wait)

            # ====================== XÓA "THUỘC CƠ SỞ" ======================
            try:
                branch_combo = dialog.find_element(By.CSS_SELECTOR, 
                    "kendo-combobox[controls='branch_id'], kendo-combobox[formcontrolname='branch_id']")
                
                clear_btns = branch_combo.find_elements(By.CSS_SELECTOR, ".k-clear-value, .k-i-x, button.k-clear-button")
                for btn in clear_btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                        print("   ✓ Đã xóa 'Thuộc cơ sở'")
                        break
            except Exception as e:
                print(f"   ⚠️ Không tìm thấy hoặc không xóa được 'Thuộc cơ sở': {e}")

            # ====================== TÊN NƠI LẤY MẪU ======================
            name_input = dialog.find_element(By.CSS_SELECTOR, 
                "input[formcontrolname='name'], input[controls='name'], input[name='name']")
            driver.execute_script("arguments[0].value = '';", name_input)
            name_input.send_keys(ten_noi_lay_mau)

            # ====================== TÊN VIẾT TẮT ======================
            short_input = dialog.find_element(By.CSS_SELECTOR, 
                "input[formcontrolname='code'], input[controls='code'], input[name='code']")
            driver.execute_script("arguments[0].value = '';", short_input)
            short_input.send_keys(ten_viet_tat)

            # ====================== ĐỊA CHỈ ======================
            address_input = dialog.find_element(By.CSS_SELECTOR, 
                "input[formcontrolname='address'], input[controls='address'], input[name='address']")
            driver.execute_script("arguments[0].value = '';", address_input)
            address_input.send_keys(dia_chi)

            # ====================== SẮP XẾP = 1 ======================
            try:
                sort_input = dialog.find_element(By.CSS_SELECTOR, 
                    "kendo-numerictextbox[controls='sort'] input.k-input, " +
                    "kendo-numerictextbox[controls='sort'] .k-formatted-value")
                
                driver.execute_script("arguments[0].value = '';", sort_input)
                driver.execute_script("arguments[0].value = '2';", sort_input)
                
                driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                    arguments[0].dispatchEvent(new Event('blur', { bubbles: true }));
                """, sort_input)
            except:
                pass

            # ====================== LƯU ======================
            save_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH,
                "//kendo-dialog//button[contains(.,'Lưu')] | //div[contains(@class,'k-dialog')]//button[contains(.,'Lưu')]"
            )))
            driver.execute_script("arguments[0].click();", save_btn)

            alert_text = _accept_alert_if_any(driver, 4)
            if alert_text:
                print(f"⚠️ Alert dòng #{r['_rownum']}: {alert_text}")

            wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))

            print(f"✅ Đã thêm dòng #{r['_rownum']}: {ten_noi_lay_mau}")

            time.sleep(pause_each)

        except Exception as e:
            print(f"❌ Lỗi dòng #{r['_rownum']} ({ten_noi_lay_mau}): {e}")
            driver.save_screenshot(f"error_row_{r['_rownum']}.png")
            continue


if __name__ == "__main__":
    driver, wait = run()
    add_locations_from_csv(driver, wait, csv_filename="NM.csv", pause_each=0.5)
    # driver.quit()