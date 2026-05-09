import os
import csv
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException


# ========= CONFIG =========
CENLAB_LOGIN_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"
ADDRESS_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/monitoring/address"

USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"

CSV_FILENAME = "NM_VITRI.csv"

# ================== CHẠY TIẾP TỪ ĐÂU ==================
START_FROM_NAME = "Kênh Tẻ - HCM_NM_KT - Triều Lên"   # Để "" nếu chạy từ đầu


# ========= LOAD CSV =========
def load_vi_tri_map(csv_filename: str):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, csv_filename)

    vitri_map = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        print(f"📌 Đang đọc file: {csv_path}")
        
        for r in reader:
            ten_noi_lay_mau = (r.get("Tên nơi lấy mẫu") or "").strip()
            if not ten_noi_lay_mau:
                continue

            sub_names = [
                (r.get("Tên vị trí") or "").strip(),
                (r.get("Tên vị trí mẫu lặp") or "").strip(),
                (r.get("Tên vị trí mẫu trắng hiện trường") or "").strip(),
                (r.get("Tên vị trí mẫu trắng vận chuyển") or "").strip(),
                (r.get("Tên vị trí mẫu trắng thiết bị") or "").strip(),
            ]
            sub_names = [name for name in sub_names if name]

            if sub_names:
                vitri_map[ten_noi_lay_mau] = sub_names

    print(f"✅ Đã nạp {len(vitri_map)} địa điểm từ CSV\n")
    return vitri_map


# ========= HELPERS =========
def accept_alert_if_any(driver, seconds=3):
    try:
        WebDriverWait(driver, seconds).until(EC.alert_is_present())
        a = Alert(driver)
        txt = a.text
        a.accept()
        return txt
    except TimeoutException:
        return None


def wait_for_address_grid(wait):
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "kendo-grid, .k-grid")))


def set_page_size_500(driver, wait):
    try:
        dropdown_wrap = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "kendo-dropdownlist .k-dropdown-wrap[aria-label='dòng / trang']"))
        )
        driver.execute_script("arguments[0].click();", dropdown_wrap)
        time.sleep(0.8)
        
        opt_500 = wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@role='option' and normalize-space()='500']")))
        driver.execute_script("arguments[0].click();", opt_500)
        time.sleep(2.5)
        print("✅ Đã đặt hiển thị 500 dòng/trang")
        return True
    except Exception as e:
        print(f"⚠️ Không đổi được sang 500 dòng/trang: {e}")
        return False


def get_address_names_current_page(driver):
    wait_for_address_grid(WebDriverWait(driver, 10))
    spans = driver.find_elements(By.XPATH, "//td[@role='gridcell']//a//span[normalize-space()!='']")
    names = []
    seen = set()
    for sp in spans:
        try:
            txt = sp.text.strip()
            if txt and txt not in seen:
                seen.add(txt)
                names.append(txt)
        except:
            continue
    return names


def open_address_detail_by_name(driver, wait, name: str):
    el = wait.until(
        EC.element_to_be_clickable((By.XPATH, f"//span[normalize-space()='{name}']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "kendo-tabstrip")))
    time.sleep(1.0)


def click_tab_danh_sach_vi_tri(driver, wait):
    tab = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//span[normalize-space()='Danh sách vị trí']"))
    )
    driver.execute_script("arguments[0].click();", tab)
    time.sleep(1.0)


def add_one_position(driver, wait, ten_vi_tri: str):
    add_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Thêm']")))
    driver.execute_script("arguments[0].click();", add_btn)

    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog")))

    name_input = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "input[controls='name'], input[formcontrolname='name']"))
    )
    name_input.clear()
    name_input.send_keys(ten_vi_tri)

    save_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//kendo-dialog//button[contains(.,'Lưu')] | //button[contains(.,'Lưu')]")))
    driver.execute_script("arguments[0].click();", save_btn)

    accept_alert_if_any(driver, 3)
    wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))
    time.sleep(0.6)


# ========= MAIN PROCESS =========
def process_all_addresses(driver, wait, vitri_map: dict):
    driver.get(ADDRESS_URL)
    wait_for_address_grid(wait)
    set_page_size_500(driver, wait)

    started = False if START_FROM_NAME else True

    print("\n🔄 Bắt đầu xử lý danh sách...")

    names = get_address_names_current_page(driver)
    print(f"📌 Tìm thấy {len(names)} địa điểm (500 dòng)")

    for name in names:
        if not started:
            if name == START_FROM_NAME:
                started = True
                print(f"🔥 BẮT ĐẦU TỪ: {name}")
            else:
                continue

        if name not in vitri_map:
            continue

        print(f"\n➡️ Xử lý: {name}")
        try:
            open_address_detail_by_name(driver, wait, name)
            click_tab_danh_sach_vi_tri(driver, wait)

            for sub_name in vitri_map[name]:
                add_one_position(driver, wait, sub_name)
                print(f"   ✅ Đã thêm: {sub_name}")

            print(f"🎉 Hoàn thành: {name}")
        except Exception as e:
            print(f"❌ Lỗi khi xử lý {name}: {e}")
            try:
                driver.save_screenshot(f"error_{name[:40]}.png".replace(" ", "_").replace("/", "_"))
            except:
                pass

        # Quay lại danh sách
        driver.get(ADDRESS_URL)
        wait_for_address_grid(wait)
        time.sleep(1.5)

    print("\n✅ HOÀN THÀNH XỬ LÝ TẤT CẢ ĐỊA ĐIỂM TRONG TRANG 500 DÒNG!")


# ========= LOGIN =========
def login_and_go_to_address_page():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 45)

    driver.get(CENLAB_LOGIN_URL)

    wait.until(EC.visibility_of_element_located((By.ID, "user-name"))).send_keys(USERNAME)
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='password']"))).send_keys(PASSWORD)
    
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-login[type='submit']"))).click()

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid-layout-container")))

    monitoring_card = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//div[contains(@class,'title') and normalize-space()='Lấy mẫu - Quan trắc']/ancestor::kendo-card[1]"))
    )
    driver.execute_script("arguments[0].click();", monitoring_card)

    dia_diem_item = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-drawer-item[aria-label='Địa điểm quan trắc']"))
    )
    driver.execute_script("arguments[0].click();", dia_diem_item)

    driver.get(ADDRESS_URL)
    wait_for_address_grid(wait)

    return driver, wait


# ========= RUN =========
if __name__ == "__main__":
    vitri_map = load_vi_tri_map(CSV_FILENAME)
    driver, wait = login_and_go_to_address_page()
    process_all_addresses(driver, wait, vitri_map)

    # driver.quit()   # Bỏ comment nếu muốn tự đóng trình duyệt