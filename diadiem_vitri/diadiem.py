import os
import csv
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.alert import Alert


CENLAB_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"
USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I5"


def load_rows_from_csv(csv_filename: str):
    """
    KR.csv dùng delimiter ';' với headers:
    ViTri;KyHIeu;MoTa;LON;LAT
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, csv_filename)

    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, r in enumerate(reader, start=1):
            vitri = (r.get("ViTri") or "").strip()
            mota = (r.get("MoTa") or "").strip()

            # Tên nơi lấy mẫu là bắt buộc => vitri rỗng thì bỏ qua
            if not vitri:
                print(f"⚠️ Bỏ qua dòng #{i} vì ViTri trống")
                continue

            rows.append({"ViTri": vitri, "MoTa": mota, "_rownum": i})

    print(f"📌 CSV path: {csv_path}")
    print(f"📌 CSV headers: {reader.fieldnames}")
    return rows


def run():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 35)

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
        print("✅ Đã click card: Lấy mẫu - Quan trắc")

        dia_diem_item = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-drawer-item[aria-label='Địa điểm quan trắc']"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dia_diem_item)
        driver.execute_script("arguments[0].click();", dia_diem_item)
        print("✅ Đã click menu: Địa điểm quan trắc")

        time.sleep(5)
        return driver, wait

    except Exception as e:
        print("❌ Error:", e)
        driver.save_screenshot("cenlab_error.png")
        driver.quit()
        raise


def _get_active_dialog(driver, wait):
    """
    Lấy dialog popup đang mở (Kendo dialog).
    Tùy build có thể là kendo-dialog hoặc .k-dialog
    """
    dialog = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog"))
    )
    return dialog


def _accept_alert_if_any(driver, short_wait_seconds=2):
    """
    Nếu có alert JS (window.alert) thì accept và trả về text.
    """
    try:
        WebDriverWait(driver, short_wait_seconds).until(EC.alert_is_present())
        a = Alert(driver)
        txt = a.text
        a.accept()
        return txt
    except TimeoutException:
        return None


def add_locations_from_csv(driver, wait, csv_filename="KR.csv", pause_each=0.2):
    rows = load_rows_from_csv(csv_filename)
    print(f"📄 Đọc CSV xong: {len(rows)} dòng")

    for r in rows:
        vitri = r["ViTri"]
        mota = r["MoTa"]

        # 1) Click nút Thêm
        add_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Thêm']")))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_btn)
        driver.execute_script("arguments[0].click();", add_btn)

        # 2) Chờ dialog popup và chỉ thao tác bên trong dialog
        dialog = _get_active_dialog(driver, wait)

        # 3) Clear combobox branch_id (để trống) trong dialog nếu có nút clear
        try:
            combo = dialog.find_element(By.CSS_SELECTOR, "kendo-combobox[controls='branch_id']")
            clear_btns = combo.find_elements(By.CSS_SELECTOR, ".k-clear-value")
            if clear_btns:
                driver.execute_script("arguments[0].click();", clear_btns[0])
        except Exception:
            pass

        # 4) Nhập ViTri vào input controls="name" (trong dialog)
        name_input = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='name'], .k-dialog input[controls='name']"))
        )
        name_input.clear()
        name_input.send_keys(vitri)

        # 5) Nhập MoTa vào textarea controls="note1" (trong dialog)
        note1 = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog textarea[controls='note1'], .k-dialog textarea[controls='note1']"))
        )
        note1.clear()
        note1.send_keys(mota)

        # 6) Click Lưu (trong dialog). Nếu bị alert, accept rồi retry 1 lần.
        def click_save_in_dialog():
            save_btn = wait.until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "(//kendo-dialog//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')]"
                    " | //div[contains(@class,'k-dialog')]//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')])[1]"
                ))
            )
            driver.execute_script("arguments[0].click();", save_btn)

        click_save_in_dialog()

        alert_text = _accept_alert_if_any(driver, short_wait_seconds=2)
        if alert_text:
            print(f"⚠️ Alert sau khi lưu dòng #{r['_rownum']}: {alert_text}")

            # Retry: đảm bảo name vẫn còn, nhập lại + click lưu lần nữa
            # (thường do UI chưa commit hoặc click quá nhanh)
            dialog = _get_active_dialog(driver, wait)

            name_input = wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='name'], .k-dialog input[controls='name']"))
            )
            name_input.clear()
            name_input.send_keys(vitri)

            note1 = wait.until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog textarea[controls='note1'], .k-dialog textarea[controls='note1']"))
            )
            note1.clear()
            note1.send_keys(mota)

            click_save_in_dialog()

            # nếu vẫn alert lần 2 thì accept và bỏ qua dòng này
            alert_text2 = _accept_alert_if_any(driver, short_wait_seconds=2)
            if alert_text2:
                print(f"❌ Vẫn lỗi dòng #{r['_rownum']} sau retry: {alert_text2} -> BỎ QUA DÒNG")
                # đóng popup nếu có nút đóng (tùy UI); nếu không có thì cứ để user xử lý
                driver.save_screenshot(f"save_failed_row_{r['_rownum']}.png")
                continue

        # 7) Đợi dialog đóng hẳn (dialog biến mất)
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))

        print(f"✅ Đã thêm & lưu dòng #{r['_rownum']}: {vitri[:60]}")
        time.sleep(pause_each)


if __name__ == "__main__":
    driver, wait = run()
    add_locations_from_csv(driver, wait, csv_filename="KR.csv", pause_each=0.2)
    # driver.quit()
