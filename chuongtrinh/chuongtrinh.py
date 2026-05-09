import os
import csv
import time
from collections import defaultdict
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    ElementClickInterceptedException,
)


# ========= CONFIG =========
LOGIN_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"

USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"

CSV_FILENAME = "VITRICS3.csv"
DONE_FILENAME = "done3.csv"  # log để chạy lại không nhập trùng

PROGRAM_CODE = "CS2.26-0057"
BATCH_NAME = "Vị trí quan trắc gửi Cơ sở 3 - Tháng 05/2026"

# Ngày chạy: 01-10 và 23-25
DAYS_TO_RUN = list(range(1, 31))
# DAYS_TO_RUN = list(range(1, 11)) + list(range(23, 26))

# ========= BASIC HELPERS =========
def base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def done_path():
    return os.path.join(base_dir(), DONE_FILENAME)


def accept_alert_if_any(driver, seconds=2):
    try:
        WebDriverWait(driver, seconds).until(EC.alert_is_present())
        a = Alert(driver)
        txt = a.text
        a.accept()
        return txt
    except TimeoutException:
        return None


def sniff_delimiter(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            return csv.Sniffer().sniff(sample, delimiters=";,").delimiter
        except Exception:
            return ";"


def safe_js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    try:
        el.click()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        driver.execute_script("arguments[0].click();", el)


# ========= CSV / DONE LOG =========
def load_plan_by_day(csv_filename: str):
    csv_path = os.path.join(base_dir(), csv_filename)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Không thấy file CSV: {csv_path}")

    delim = sniff_delimiter(csv_path)

    plan = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)

        print(f"📌 CSV path: {csv_path}")
        print(f"📌 Detected delimiter: '{delim}'")
        print(f"📌 CSV headers: {reader.fieldnames}")

        for i, r in enumerate(reader, start=1):
            ngay_raw = (r.get("Ngày") or r.get("Ngay") or "").strip()
            if not ngay_raw:
                continue

            try:
                day = int(float(ngay_raw))
            except Exception:
                continue

            row = {
                "day": day,
                "noi_thuc_hien": (r.get("Nơi thực hiện") or r.get("Noi thuc hien") or "").strip(),
                "vi_tri_qt": (r.get("Vị trí quan trắc") or r.get("Vi tri quan trac") or "").strip(),
                "sample": (r.get("Số lượng mẫu") or r.get("So luong mau") or "").strip(),
                "sample_qc": (r.get("Số lượng mẫu QC") or r.get("So luong mau QC") or "").strip(),
                "_rownum": i,
            }

            if not row["noi_thuc_hien"] or not row["vi_tri_qt"]:
                continue

            plan[day].append(row)

    return plan


def make_done_key(day: int, noi_thuc_hien: str, vi_tri_qt: str, sample: str, sample_qc: str):
    return f"{int(day):02d}|{noi_thuc_hien.strip()}|{vi_tri_qt.strip()}|{str(sample).strip()}|{str(sample_qc).strip()}"


def load_done_keys():
    path = done_path()
    keys = set()
    if not os.path.exists(path):
        return keys

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            k = (r.get("key") or "").strip()
            if k:
                keys.add(k)

    print(f"📌 Đã nạp done.csv: {len(keys)} dòng đã xử lý")
    return keys


def append_done_row(day, noi_thuc_hien, vi_tri_qt, sample, sample_qc, status="ok", note=""):
    path = done_path()
    file_exists = os.path.exists(path)
    k = make_done_key(day, noi_thuc_hien, vi_tri_qt, sample, sample_qc)

    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["ts", "day", "noi_thuc_hien", "vi_tri_qt", "sample", "sample_qc", "status", "note", "key"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        writer.writerow({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "day": int(day),
            "noi_thuc_hien": noi_thuc_hien,
            "vi_tri_qt": vi_tri_qt,
            "sample": sample,
            "sample_qc": sample_qc,
            "status": status,
            "note": note,
            "key": k
        })


# ========= KENDO COMBOBOX (type -> dropdown -> CLICK option) =========
def open_kendo_combobox_and_click_option(driver, dialog, controls_name: str, value: str, max_retries=2):
    """
    Kendo ComboBox:
    - Click input
    - Gõ value
    - Mở listbox (ALT+ARROW_DOWN / ARROW_DOWN)
    - Nếu list báo "No data found" => retry
    - Click option khớp text (ưu tiên match tuyệt đối), nếu không có thì click option đầu tiên
    - Xác nhận input hiển thị đúng value (retry nhẹ)
    """
    def _get_listbox():
        boxes = driver.find_elements(By.CSS_SELECTOR, "ul[role='listbox']")
        return boxes[-1] if boxes else None

    def _list_has_no_data(listbox):
        try:
            return "no data found" in (listbox.text or "").strip().lower()
        except StaleElementReferenceException:
            return True

    def _click_option_exact(listbox, text):
        option_xpath = (
            ".//li[@role='option' or contains(@class,'k-list-item') or contains(@class,'k-item')]"
            f"[.//span[normalize-space()='{text}'] or normalize-space(.)='{text}']"
        )
        opts = listbox.find_elements(By.XPATH, option_xpath)
        if not opts:
            return False
        opt = opts[0]
        safe_js_click(driver, opt)
        return True

    def _read_input_text():
        try:
            inp = dialog.find_element(By.CSS_SELECTOR, f"kendo-combobox[controls='{controls_name}'] input.k-input")
            return (inp.get_attribute("value") or "").strip()
        except Exception:
            return ""

    last_err = ""
    for attempt in range(max_retries + 1):
        combo_input = dialog.find_element(By.CSS_SELECTOR, f"kendo-combobox[controls='{controls_name}'] input.k-input")

        combo_input.click()
        combo_input.send_keys(Keys.CONTROL, "a")
        combo_input.send_keys(value)

        # mở dropdown (Kendo hay ăn ALT+DOWN)
        combo_input.send_keys(Keys.ALT, Keys.ARROW_DOWN)
        time.sleep(0.2)

        try:
            WebDriverWait(driver, 6).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "ul[role='listbox']")) > 0)
        except TimeoutException:
            combo_input.send_keys(Keys.ARROW_DOWN)
            time.sleep(0.25)

        listbox = _get_listbox()
        if not listbox:
            last_err = f"Không thấy listbox cho combobox {controls_name}"
            continue

        if _list_has_no_data(listbox):
            last_err = f"NO DATA FOUND '{value}' (controls={controls_name}) attempt {attempt+1}/{max_retries+1}"
            print(f"⚠️ {last_err}")
            combo_input.send_keys(Keys.CONTROL, "a")
            combo_input.send_keys(Keys.BACKSPACE)
            time.sleep(0.35)
            continue

        # click option match tuyệt đối
        if _click_option_exact(listbox, value):
            time.sleep(0.2)
        else:
            # fallback: click option đầu tiên
            try:
                first = listbox.find_element(By.XPATH, ".//li[@role='option' or contains(@class,'k-list-item')][1]")
                safe_js_click(driver, first)
                time.sleep(0.2)
            except NoSuchElementException:
                last_err = f"Không tìm thấy option để click cho '{value}' (controls={controls_name})"
                continue

        # verify input value (nếu chưa đúng, thử click lại 1 lần)
        shown = _read_input_text()
        if shown and shown.lower() == value.strip().lower():
            return True, ""
        # đôi khi input hiển thị khác (ví dụ label khác), thì coi như ok nếu không rỗng
        if shown:
            return True, ""

        last_err = f"Đã click option nhưng input không nhận (controls={controls_name}) attempt {attempt+1}/{max_retries+1}"
        print(f"⚠️ {last_err}")
        time.sleep(0.3)

    return False, last_err or f"Chọn combobox thất bại: {controls_name}='{value}'"


def fill_kendo_numeric(dialog, controls_name: str, value: str):
    num_input = dialog.find_element(
        By.CSS_SELECTOR,
        f"kendo-numerictextbox[controls='{controls_name}'] input[role='spinbutton']"
    )
    num_input.click()
    num_input.send_keys(Keys.CONTROL, "a")
    num_input.send_keys(str(value))
    num_input.send_keys(Keys.TAB)


def click_save_in_dialog(driver, wait):
    save_btn = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "(//kendo-dialog//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')]"
            " | //div[contains(@class,'k-dialog')]//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')])[1]"
        ))
    )
    safe_js_click(driver, save_btn)


def close_outer_dialog(driver, wait):
    close_btn = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "a.k-dialog-close[aria-label='Close'], a.k-dialog-close[title='Close']"))
    )
    safe_js_click(driver, close_btn)


def wait_new_dialog_open(driver, wait, prev_count):
    wait.until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "kendo-dialog, .k-dialog")) > prev_count)
    dialogs = driver.find_elements(By.CSS_SELECTOR, "kendo-dialog, .k-dialog")
    return dialogs[-1]


def find_day_dialog(driver, wait):
    return wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))


def find_add_button_in_day_dialog(driver, wait):
    day_dialog = find_day_dialog(driver, wait)

    # ưu tiên icon plus trong popup ngày
    plus_icons = day_dialog.find_elements(By.CSS_SELECTOR, "button .k-i-plus")
    if plus_icons:
        btn = plus_icons[0].find_element(By.XPATH, "./ancestor::button[1]")
        return btn

    # fallback: title
    btns = day_dialog.find_elements(By.CSS_SELECTOR, "button[title='Thêm']")
    if btns:
        return btns[0]

    # fallback: text
    btns = day_dialog.find_elements(By.XPATH, ".//button[contains(normalize-space(.),'Thêm') or contains(normalize-space(.),'Add')]")
    if btns:
        return btns[0]

    raise TimeoutException("Không tìm thấy nút 'Thêm' trong popup ngày.")


# ========= MAIN FLOW =========
def login_and_go_to_program(driver, wait):
    driver.get(LOGIN_URL)

    u = wait.until(EC.visibility_of_element_located((By.ID, "user-name")))
    u.clear()
    u.send_keys(USERNAME)

    p = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='password']")))
    p.clear()
    p.send_keys(PASSWORD)

    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-login[type='submit']"))).click()

    # dashboard
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid-layout-container")))

    # card "Lấy mẫu - Quan trắc"
    monitoring_card = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(@class,'title') and normalize-space()='Lấy mẫu - Quan trắc']/ancestor::kendo-card[1]"
        ))
    )
    safe_js_click(driver, monitoring_card)
    print("✅ Đã click card: Lấy mẫu - Quan trắc")

    # drawer "Chương trình quan trắc" index=4 (tránh nhầm "Lịch quan trắc")
    program_item = wait.until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "li.k-drawer-item[data-kendo-drawer-index='4']"))
    )
    safe_js_click(driver, program_item)
    print("✅ Đã click menu: Chương trình quan trắc (index=4)")

    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "li.k-drawer-item[data-kendo-drawer-index='4'][aria-selected='true']")
    ))

    # chọn chương trình
    prog_code = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[normalize-space()='{PROGRAM_CODE}']")))
    safe_js_click(driver, prog_code)
    print(f"✅ Đã chọn chương trình: {PROGRAM_CODE}")

    time.sleep(3)

    # chọn đợt
    batch = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[normalize-space()='{BATCH_NAME}']")))
    safe_js_click(driver, batch)
    print(f"✅ Đã chọn đợt lấy mẫu: {BATCH_NAME}")

    # chờ lịch
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "td[monthslot], .k-calendar")))


def click_day_cell(driver, wait, day: int):
    """
    Click ô ngày bằng TD monthslot (không click span).
    <td monthslot ...><span class="k-link k-nav-day">01</span></td>
    """
    day_text = f"{day:02d}"

    day_td = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            f"//td[@monthslot and .//span[contains(@class,'k-nav-day') and normalize-space()='{day_text}']]"
        ))
    )
    safe_js_click(driver, day_td)

    print(f"📅 Đã click ngày {day_text}/02/2026")
    time.sleep(0.8)

    # popup ngày
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "kendo-dialog, .k-dialog")))


def add_rows_for_day(driver, wait, rows_for_day, done_keys: set):
    for r in rows_for_day:
        day = r["day"]
        noi = r["noi_thuc_hien"]
        vt = r["vi_tri_qt"]
        sample = r["sample"]
        sample_qc = r["sample_qc"]

        key = make_done_key(day, noi, vt, sample, sample_qc)
        if key in done_keys:
            print(f"⏭️ Skip (đã có done): ngày {day:02d} | {noi} | {vt}")
            continue

        # click Thêm trong popup ngày
        prev_dialogs = len(driver.find_elements(By.CSS_SELECTOR, "kendo-dialog, .k-dialog"))
        add_btn = find_add_button_in_day_dialog(driver, wait)
        safe_js_click(driver, add_btn)

        # dialog nhập liệu mới
        dialog = wait_new_dialog_open(driver, wait, prev_dialogs)

        # combobox: Nơi thực hiện (address_id)
        ok1, err1 = open_kendo_combobox_and_click_option(driver, dialog, "address_id", noi, max_retries=2)
        if not ok1:
            msg = f"address_id chọn thất bại: {err1}"
            print(f"❌ Row #{r['_rownum']}: {msg}")
            append_done_row(day, noi, vt, sample, sample_qc, status="fail", note=msg)
            done_keys.add(key)
            try:
                close_btns = dialog.find_elements(By.CSS_SELECTOR, "a.k-dialog-close")
                if close_btns:
                    safe_js_click(driver, close_btns[0])
            except Exception:
                pass
            continue

        # combobox: Vị trí quan trắc (position_id)
        ok2, err2 = open_kendo_combobox_and_click_option(driver, dialog, "position_id", vt, max_retries=2)
        if not ok2:
            msg = f"position_id chọn thất bại: {err2}"
            print(f"❌ Row #{r['_rownum']}: {msg}")
            append_done_row(day, noi, vt, sample, sample_qc, status="fail", note=msg)
            done_keys.add(key)
            try:
                close_btns = dialog.find_elements(By.CSS_SELECTOR, "a.k-dialog-close")
                if close_btns:
                    safe_js_click(driver, close_btns[0])
            except Exception:
                pass
            continue

        # numeric
        fill_kendo_numeric(dialog, "sample", sample)
        fill_kendo_numeric(dialog, "sample_qc", sample_qc)

        # save
        click_save_in_dialog(driver, wait)

        alert_text = accept_alert_if_any(driver, seconds=2)
        if alert_text:
            msg = f"Alert khi lưu: {alert_text}"
            print(f"⚠️ Row #{r['_rownum']}: {msg}")
            append_done_row(day, noi, vt, sample, sample_qc, status="fail", note=msg)
            done_keys.add(key)
            continue

        # chờ dialog nhập liệu đóng
        try:
            WebDriverWait(driver, 20).until(EC.staleness_of(dialog))
        except Exception:
            pass

        time.sleep(0.8)

        print(f"✅ OK row #{r['_rownum']} | Ngày {day:02d} | {noi} | {vt}")
        append_done_row(day, noi, vt, sample, sample_qc, status="ok", note="")
        done_keys.add(key)


def run():
    plan_by_day = load_plan_by_day(CSV_FILENAME)
    done_keys = load_done_keys()

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 45)

    try:
        login_and_go_to_program(driver, wait)

        for day in DAYS_TO_RUN:
            rows_for_day = plan_by_day.get(day, [])
            if not rows_for_day:
                print(f"⏭️ Ngày {day:02d}/02/2026: không có dữ liệu CSV -> bỏ qua")
                continue

            print(f"\n📅 Ngày {day:02d}/02/2026: {len(rows_for_day)} dòng")
            click_day_cell(driver, wait, day)

            add_rows_for_day(driver, wait, rows_for_day, done_keys)

            # đóng popup ngày
            close_outer_dialog(driver, wait)
            time.sleep(1)

            print(f"🎉 Xong ngày {day:02d}/02/2026")

        print("\n✅ Hoàn tất tạo chương trình quan trắc. Log nằm ở done.csv")

    except Exception as e:
        print("❌ Error:", e)
        driver.save_screenshot("chuong_trinh_quan_trac_error.png")
        raise
    finally:
        # driver.quit()
        pass


if __name__ == "__main__":
    run()
