import os
import csv
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException


# ========= CONFIG =========
CENLAB_LOGIN_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"
ADDRESS_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/monitoring/address"

USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"

CSV_FILENAME = "KR.csv"  # đặt cùng thư mục với file .py

# 6 vị trí con cần tạo
SUB_LOCATIONS = [
    ("Triều Lên", "L"),
    ("Triều Xuống", "X"),
    ("Triều Lên Lặp", "LL"),
    ("Triều Xuống Lặp", "XL"),
    ("Triều Lên Trắng", "LT"),
    ("Triều Xuống Trắng", "XT"),
]


# ========= CSV =========
def load_vi_tri_map(csv_filename: str):
    """
    Trả về dict: { ViTri: {"LON": "...", "LAT": "..."} }
    CSV của bạn dùng delimiter ';'
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, csv_filename)

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Không thấy file CSV ở: {csv_path}")

    m = {}
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        print(f"📌 CSV path: {csv_path}")
        print(f"📌 CSV headers: {reader.fieldnames}")

        for i, r in enumerate(reader, start=1):
            vitri = (r.get("ViTri") or "").strip()
            lon = (r.get("LON") or "").strip()
            lat = (r.get("LAT") or "").strip()

            if not vitri:
                continue

            m[vitri] = {"LON": lon, "LAT": lat, "_rownum": i}

    print(f"📄 Nạp CSV xong: {len(m)} ViTri")
    return m


# ========= HELPERS =========
def accept_alert_if_any(driver, seconds=2):
    try:
        WebDriverWait(driver, seconds).until(EC.alert_is_present())
        a = Alert(driver)
        txt = a.text
        a.accept()
        return txt
    except TimeoutException:
        return None


def wait_for_address_grid(wait):
    # Chờ có grid hiện ra (có thể thay selector nếu bạn biết chính xác kendo-grid của trang)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "kendo-grid, .k-grid")))


def set_page_size_100(driver, wait):
    """
    Click dropdown "dòng / trang" và chọn 100.
    """
    dropdown_wrap = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "kendo-dropdownlist .k-dropdown-wrap[aria-label='dòng / trang']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dropdown_wrap)
    driver.execute_script("arguments[0].click();", dropdown_wrap)

    # chọn option 100
    opt_100 = wait.until(EC.element_to_be_clickable((By.XPATH, "//li[@role='option' and normalize-space()='100']")))
    driver.execute_script("arguments[0].click();", opt_100)

    # chờ dropdown hiển thị 100
    wait.until(
        EC.text_to_be_present_in_element(
            (By.CSS_SELECTOR, "kendo-dropdownlist .k-dropdown-wrap[aria-label='dòng / trang'] .k-input"),
            "100",
        )
    )
    print("✅ Đã đổi dòng/trang sang 100")
    time.sleep(1)


def login_and_go_to_address_page():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 40)

    driver.get(CENLAB_LOGIN_URL)

    user_el = wait.until(EC.visibility_of_element_located((By.ID, "user-name")))
    user_el.clear()
    user_el.send_keys(USERNAME)

    pass_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='password']")))
    pass_el.clear()
    pass_el.send_keys(PASSWORD)

    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-login[type='submit']"))).click()

    # dashboard
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid-layout-container")))

    # click card "Lấy mẫu - Quan trắc"
    monitoring_card = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//div[contains(@class,'title') and normalize-space()='Lấy mẫu - Quan trắc']/ancestor::kendo-card[1]")
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", monitoring_card)
    driver.execute_script("arguments[0].click();", monitoring_card)
    print("✅ Đã click card: Lấy mẫu - Quan trắc")

    # click drawer "Địa điểm quan trắc"
    dia_diem_item = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-drawer-item[aria-label='Địa điểm quan trắc']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dia_diem_item)
    driver.execute_script("arguments[0].click();", dia_diem_item)
    print("✅ Đã click menu: Địa điểm quan trắc")

    # vào đúng URL list cho chắc
    driver.get(ADDRESS_URL)
    wait_for_address_grid(wait)
    time.sleep(1)

    # đổi page size 100
    set_page_size_100(driver, wait)

    return driver, wait


def get_address_names_current_page(driver, wait):
    """
    Lấy danh sách tên địa điểm (text trong td->a->span) ở trang hiện tại.
    """
    wait_for_address_grid(wait)

    # Selector mềm: mọi span nằm trong a nằm trong td gridcell
    spans = driver.find_elements(By.XPATH, "//td[@role='gridcell']//a//span[normalize-space()!='']")
    names = []
    seen = set()
    for sp in spans:
        try:
            txt = sp.text.strip()
        except StaleElementReferenceException:
            continue
        if txt and txt not in seen:
            seen.add(txt)
            names.append(txt)

    return names


def open_address_detail_by_name(driver, wait, name: str):
    """
    Click vào dòng địa điểm theo tên (span text).
    """
    wait_for_address_grid(wait)
    el = wait.until(
        EC.element_to_be_clickable((By.XPATH, f"//td[@role='gridcell']//a//span[normalize-space()='{name}']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)

    # chờ tabstrip hiện ra
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "kendo-tabstrip, .k-tabstrip-items")))
    time.sleep(0.5)


def click_tab_danh_sach_vi_tri(driver, wait):
    tab = wait.until(
        EC.element_to_be_clickable((By.XPATH, "//li[@role='tab']//span[normalize-space()='Danh sách vị trí']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", tab)
    driver.execute_script("arguments[0].click();", tab)
    time.sleep(0.5)


def add_one_sub_location(driver, wait, ten_vi_tri: str, ma_viet_tat: str, lon: str, lat: str):
    """
    Trong tab 'Danh sách vị trí', click Thêm -> popup -> fill name/code/gps_x/gps_y -> Lưu -> chờ popup đóng.
    """
    # click nút Thêm (tab danh sách vị trí)
    add_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[title='Thêm']")))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_btn)
    driver.execute_script("arguments[0].click();", add_btn)

    # popup/dialog
    dialog = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))

    # fill 4 input
    name_input = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='name'], .k-dialog input[controls='name']"))
    )
    code_input = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='code'], .k-dialog input[controls='code']"))
    )
    x_input = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='gps_x'], .k-dialog input[controls='gps_x']"))
    )
    y_input = wait.until(
        EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog input[controls='gps_y'], .k-dialog input[controls='gps_y']"))
    )

    name_input.clear()
    name_input.send_keys(ten_vi_tri)

    code_input.clear()
    code_input.send_keys(ma_viet_tat)

    x_input.clear()
    x_input.send_keys(lon)

    y_input.clear()
    y_input.send_keys(lat)

    # click Lưu trong popup
    save_btn = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "(//kendo-dialog//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')]"
                " | //div[contains(@class,'k-dialog')]//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')])[1]",
            )
        )
    )
    driver.execute_script("arguments[0].click();", save_btn)

    # nếu alert xuất hiện thì accept và báo lỗi
    alert_text = accept_alert_if_any(driver, seconds=2)
    if alert_text:
        print(f"⚠️ Alert khi lưu '{ten_vi_tri}': {alert_text}")
        # có alert => coi như fail lần này, bạn muốn retry thì nói mình thêm retry
        return False

    # chờ popup đóng
    wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))
    time.sleep(0.3)
    return True


def process_all_addresses(driver, wait, vitri_map: dict):
    """
    Vòng lặp lớn: click tuần tự hết các địa điểm trên trang (tối đa 100 dòng/trang).
    Với mỗi địa điểm:
    - Nếu không có trong CSV (cột ViTri) => in thông báo, quay lại ADDRESS_URL và làm tiếp
    - Nếu có => vào tab Danh sách vị trí và thêm 6 vị trí con theo yêu cầu.
    """
    # đảm bảo đang ở trang list
    driver.get(ADDRESS_URL)
    wait_for_address_grid(wait)
    set_page_size_100(driver, wait)

    names = get_address_names_current_page(driver, wait)
    print(f"📌 Tìm thấy {len(names)} địa điểm trên trang hiện tại (tối đa 100).")

    for idx, name in enumerate(names, start=1):
        try:
            print(f"\n➡️ ({idx}/{len(names)}) Đang xử lý địa điểm: {name}")

            open_address_detail_by_name(driver, wait, name)

            # kiểm tra có trong CSV theo cột ViTri
            if name not in vitri_map:
                print(f"❌ Không có '{name}' trong CSV cột ViTri -> bỏ qua và quay lại danh sách.")
                driver.get(ADDRESS_URL)
                wait_for_address_grid(wait)
                set_page_size_100(driver, wait)
                continue

            lon = vitri_map[name].get("LON", "")
            lat = vitri_map[name].get("LAT", "")

            # nếu thiếu tọa độ vẫn nhập được hay không tùy hệ thống
            # bạn muốn bắt buộc có lon/lat thì bật check dưới:
            # if not lon or not lat:
            #     print(f"⚠️ '{name}' có trong CSV nhưng thiếu LON/LAT -> bỏ qua.")
            #     driver.get(ADDRESS_URL); wait_for_address_grid(wait); set_page_size_100(driver, wait)
            #     continue

            # click tab "Danh sách vị trí"
            click_tab_danh_sach_vi_tri(driver, wait)

            # vòng lặp nhỏ: thêm 6 lần
            ok_count = 0
            for (ten_vi_tri, ma_viet_tat) in SUB_LOCATIONS:
                ok = add_one_sub_location(driver, wait, ten_vi_tri, ma_viet_tat, lon, lat)
                if ok:
                    ok_count += 1
                    print(f"✅ Đã thêm: {ten_vi_tri} ({ma_viet_tat})")
                else:
                    print(f"⚠️ Thêm thất bại: {ten_vi_tri} ({ma_viet_tat})")

            print(f"🎉 Xong '{name}' | thêm thành công {ok_count}/6 vị trí. Quay lại danh sách...")

            # quay lại trang danh sách để xử lý thẻ kế tiếp
            driver.get(ADDRESS_URL)
            wait_for_address_grid(wait)
            set_page_size_100(driver, wait)

        except Exception as e:
            print(f"❌ Lỗi khi xử lý '{name}': {e}")
            driver.save_screenshot(f"error_{idx}_{name}.png".replace(" ", "_"))
            # cố quay về list để tiếp tục
            driver.get(ADDRESS_URL)
            wait_for_address_grid(wait)
            try:
                set_page_size_100(driver, wait)
            except Exception:
                pass
            continue


# ========= MAIN =========
if __name__ == "__main__":
    vitri_map = load_vi_tri_map(CSV_FILENAME)
    driver, wait = login_and_go_to_address_page()
    process_all_addresses(driver, wait, vitri_map)

    # driver.quit()
