import csv
import os
import time
import re
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
)

# ========= CONFIG =========
CENLAB_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"
USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"

CSV_FILENAME = "KYHIEUCS3.csv"
DONE_CSV = "donecs3.csv"
PROGRAM_CODE = "CS2.26-0068-02"

DAYS_RANGE_1 = list(range(1, 14))
DAYS_RANGE_2 = list(range(14, 32))

DRAWER_INDEX_KEHOACH = 5


# ========= HELPERS =========
def normalize_text(s) -> str:
    if s is None:
        return ""
    s = str(s)
    if s.strip().lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", s.strip())


def detect_delimiter(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
    return ";" if sample.count(";") >= sample.count(",") else ","


def safe_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)


def load_done_keys(done_csv_path: str) -> set:
    keys = set()
    if not os.path.exists(done_csv_path):
        return keys
    with open(done_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            k = row.get("key")
            if k:
                keys.add(k)
    return keys


def append_done(done_csv_path: str, row_dict: dict):
    file_exists = os.path.exists(done_csv_path)
    fieldnames = ["key", "Ngày", "idx", "Nơi thực hiện", "Vị trí quan trắc", "Ký hiệu", "ts"]
    with open(done_csv_path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            w.writeheader()
        w.writerow({
            "key": row_dict["key"],
            "Ngày": row_dict.get("Ngày", ""),
            "idx": row_dict.get("idx", ""),
            "Nơi thực hiện": row_dict.get("Nơi thực hiện", ""),
            "Vị trí quan trắc": row_dict.get("Vị trí quan trắc", ""),
            "Ký hiệu": row_dict.get("Ký hiệu", ""),
            "ts": datetime.now().isoformat(timespec="seconds"),
        })


def read_csv_rows(csv_path: str) -> list:
    delim = detect_delimiter(csv_path)
    print(f"📌 KYHIEU CSV: {csv_path}")
    print(f"📌 Delimiter: '{delim}'")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delim)
        rows = []
        for row in reader:
            fixed = {k.strip(): normalize_text(v) for k, v in row.items()}
            rows.append(fixed)
    print(f"📄 CSV rows: {len(rows)}")
    return rows


def group_rows_by_day(rows: list) -> dict:
    by_day = {}
    for i, r in enumerate(rows):
        ngay_raw = normalize_text(r.get("Ngày", ""))
        day_num = None
        if re.fullmatch(r"\d{1,2}", ngay_raw):
            day_num = int(ngay_raw)
        else:
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", ngay_raw)
            if m:
                day_num = int(m.group(1))
        if not day_num:
            continue
        r["_csv_index"] = i
        by_day.setdefault(day_num, []).append(r)
    return by_day


def wait_dialog_with_predicate(driver, predicate, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        dialogs = driver.find_elements(By.CSS_SELECTOR, "kendo-dialog, .k-dialog")
        for dlg in reversed(dialogs):
            try:
                if dlg.is_displayed() and predicate(dlg):
                    return dlg
            except:
                continue
        time.sleep(0.2)
    raise TimeoutException("Không tìm thấy dialog phù hợp")


def wait_last_visible_dialog(driver, timeout=15):
    return wait_dialog_with_predicate(driver, lambda d: True, timeout=timeout)


def wait_add_form_dialog(driver, timeout=18):
    return wait_dialog_with_predicate(
        driver,
        lambda dlg: (
            len(dlg.find_elements(By.CSS_SELECTOR, "input[controls='name']")) > 0
            and len(dlg.find_elements(By.CSS_SELECTOR, "gc-tree-dropdown[controls='matrix_id']")) > 0
        ),
        timeout=timeout
    )


def click_visible_add_in_detail(driver, detail_dialog):
    end = time.time() + 12
    while time.time() < end:
        try:
            btns = detail_dialog.find_elements(
                By.XPATH, ".//button[@title='Thêm' and (not(@hidden) or @hidden='false')]"
            )
            btns = [b for b in btns if b.is_displayed()]
            if btns:
                safe_click(driver, btns[0])
                return
        except:
            pass
        time.sleep(0.25)
    raise TimeoutException("Không click được nút Thêm")


def fill_text_input(dialog_root, controls_value: str, value: str):
    inp = dialog_root.find_element(By.CSS_SELECTOR, f"input[controls='{controls_value}']")
    inp.send_keys(Keys.CONTROL, "a")
    inp.send_keys(Keys.BACKSPACE)
    inp.send_keys(str(value))


def fill_and_commit(dialog_root, controls_value: str, value: str):
    inp = dialog_root.find_element(By.CSS_SELECTOR, f"input[controls='{controls_value}']")
    inp.send_keys(Keys.CONTROL, "a")
    inp.send_keys(Keys.BACKSPACE)
    inp.send_keys(str(value))
    inp.send_keys(Keys.TAB)
    time.sleep(0.6)


def wait_matrix_enabled(add_dialog, timeout=10):
    dd = add_dialog.find_element(By.CSS_SELECTOR, "gc-tree-dropdown[controls='matrix_id']")
    end = time.time() + timeout
    while time.time() < end:
        try:
            aria = (dd.get_attribute("aria-disabled") or "").lower()
            cls = (dd.get_attribute("class") or "").lower()
            if aria != "true" and "disabled" not in cls:
                return dd
        except:
            dd = add_dialog.find_element(By.CSS_SELECTOR, "gc-tree-dropdown[controls='matrix_id']")
        time.sleep(0.2)
    raise TimeoutException("matrix_id vẫn bị khóa")


def select_matrix_nuoc_mat(driver, add_dialog):
    span = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//span[@kendotreeviewitemcontent and contains(@class,'k-in') and @data-treeindex='3_13' and normalize-space(.)='Nước mặt']"
        ))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", span)
    time.sleep(0.2)
    safe_click(driver, span)
    time.sleep(0.25)


def click_save_in_dialog(driver, dialog_root):
    btn = dialog_root.find_element(
        By.XPATH,
        ".//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')]"
    )
    safe_click(driver, btn)
    time.sleep(0.9)


def click_close_dialog(driver, wait, dialog_root=None):
    try:
        if dialog_root:
            close_btns = dialog_root.find_elements(By.CSS_SELECTOR, "a.k-dialog-close, a[title='Close']")
            close_btns = [b for b in close_btns if b.is_displayed()]
            if close_btns:
                safe_click(driver, close_btns[0])
                time.sleep(0.6)
                return
        close_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.k-dialog-close, a[title='Close']")))
        safe_click(driver, close_btn)
        time.sleep(0.6)
    except:
        pass


# ========= CLICK NGÀY =========
def click_day_td(driver, wait, day_num: int):
    day_str = f"{day_num:02d}"
    td = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        f"//td[@monthslot and .//span[contains(@class,'k-nav-day') and normalize-space()='{day_str}']]"
    )))
    safe_click(driver, td)


def open_day_popup(driver, wait, day_num: int):
    click_day_td(driver, wait, day_num)
    print(f"📅 Đã click ngày {day_num:02d}/05/2026")
    time.sleep(3.5)
    return wait_last_visible_dialog(driver, timeout=25)


# ========= TÌM EVENT — ĐÃ TỐI ƯU MẠNH HƠN =========
def find_position_link(day_dialog, position_text: str):
    normalized = normalize_text(position_text)
    print(f"🔍 Tìm event: {normalized}")

    # Tìm rất rộng để debug + hoạt động
    xpaths = [
        f".//div[contains(@title, '{normalized}')]",
        f".//div[contains(., '{normalized}') and contains(@class, 'ng-star-inserted')]",
        f".//div[contains(@class, 'k-event-template') and contains(., '{normalized}')]",
        f".//a[contains(., '{normalized}')]",
        f".//td[contains(., '{normalized}')]",
    ]

    for xpath in xpaths:
        try:
            els = day_dialog.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    title = el.get_attribute("title") or ""
                    text = normalize_text(el.text)
                    print(f"✅ TÌM THẤY: {title or text}")
                    return el
        except:
            continue

    # Fallback cực mạnh: in ra tất cả events đang có để debug
    print("   → Không tìm thấy, đang liệt kê tất cả events...")
    try:
        all_events = day_dialog.find_elements(By.XPATH, ".//div[contains(@class,'ng-star-inserted')] | .//div[contains(@class,'k-event-template')] | .//a")
        print(f"   → Tìm thấy {len(all_events)} elements khả dụng:")
        for i, el in enumerate(all_events[:30]):   # chỉ in 30 cái đầu
            txt = normalize_text(el.text or el.get_attribute("title") or "")
            if txt and len(txt) > 3:
                print(f"      {i+1:2d}: {txt[:80]}")
    except:
        pass

    raise Exception(f"❌ Không tìm thấy event: {position_text}")


def click_position_row(driver, detail_dialog, position_text: str):
    normalized = normalize_text(position_text)
    xpaths = [
        f".//a[normalize-space(.)='{normalized}' or contains(normalize-space(.), '{normalized}')]",
        f".//gc-field//a[contains(., '{normalized}')]",
        f".//td[contains(., '{normalized}')]//a",
    ]
    for xpath in xpaths:
        try:
            els = detail_dialog.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    safe_click(driver, el)
                    time.sleep(0.8)
                    return True
        except:
            continue
    print(f"⚠️ Không click được vị trí '{position_text}' trong detail")
    return False


def click_nuoc_mat_row(driver, wait, detail_dialog):
    el = WebDriverWait(detail_dialog, 10).until(
        lambda d: d.find_element(By.XPATH, ".//span[normalize-space()='Nước mặt']/ancestor::a[1]")
    )
    safe_click(driver, el)
    time.sleep(0.6)


def add_group_tests_in_current_popup(driver, wait, position_text: str):
    btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(normalize-space(.),'Nhóm phép thử')]")))
    safe_click(driver, btn)

    dlg = wait_last_visible_dialog(driver, timeout=18)
    ms_input = dlg.find_element(By.CSS_SELECTOR, "kendo-multiselect input.k-input")
    safe_click(driver, ms_input)

    target = "QUANTRACNUOCMAT2026-TRIEULEN" if "Triều Lên" in position_text else "QUANTRACNUOCMAT2026-TRIEUXUONG"
    ms_input.send_keys(target)
    time.sleep(0.4)

    opt = wait.until(EC.element_to_be_clickable((By.XPATH, f"//li[@role='option' and normalize-space()='{target}']")))
    safe_click(driver, opt)
    time.sleep(0.25)

    save_btn = dlg.find_element(By.XPATH, ".//button[.//span[contains(@class,'k-i-save')] and contains(normalize-space(.),'Lưu')]")
    safe_click(driver, save_btn)
    time.sleep(2)
    click_close_dialog(driver, wait, dlg)
    time.sleep(1)


def add_one_row_for_link(driver, wait, detail_dialog, csv_row: dict, done_key: str):
    position_text = normalize_text(csv_row.get("Vị trí quan trắc", ""))
    click_position_row(driver, detail_dialog, position_text)
    click_visible_add_in_detail(driver, detail_dialog)

    add_dialog = wait_add_form_dialog(driver, timeout=20)
    fill_and_commit(add_dialog, "name", "Nước mặt")
    safe_click(driver, add_dialog)
    time.sleep(0.3)

    wait_matrix_enabled(add_dialog, timeout=10)
    select_matrix_nuoc_mat(driver, add_dialog)

    ky_hieu = normalize_text(csv_row.get("Ký hiệu", ""))
    fill_text_input(add_dialog, "code", ky_hieu)

    click_save_in_dialog(driver, add_dialog)
    time.sleep(0.8)

    append_done(DONE_CSV, {
        "key": done_key,
        "Ngày": csv_row.get("Ngày", ""),
        "idx": csv_row.get("_csv_index", ""),
        "Nơi thực hiện": csv_row.get("Nơi thực hiện", ""),
        "Vị trí quan trắc": position_text,
        "Ký hiệu": ky_hieu,
    })


def add_kehoach_for_day(driver, wait, day_num: int, day_rows: list, done_keys: set):
    """Mỗi lần xử lý xong 1 event sẽ mở lại popup ngày"""
    if not day_rows:
        print(f"ℹ️ Ngày {day_num:02d} không có dữ liệu")
        return

    print(f"📅 Xử lý ngày {day_num:02d}/05/2026 — {len(day_rows)} events")

    for csv_row in day_rows:
        position_text = normalize_text(csv_row.get("Vị trí quan trắc", ""))
        done_key = f"kehoach|{csv_row.get('_csv_index','')}"

        if done_key in done_keys:
            print(f"⏭️ Skip: {position_text}")
            continue

        success = False
        for attempt in range(3):
            try:
                # === MỞ LẠI NGÀY MỖI LẦN (quan trọng) ===
                print(f"🔄 Mở lại popup ngày {day_num:02d} để xử lý: {position_text}")
                day_dialog = open_day_popup(driver, wait, day_num)

                event_div = find_position_link(day_dialog, position_text)

                safe_click(driver, event_div)
                time.sleep(1.5)

                detail_dialog = wait_last_visible_dialog(driver, timeout=20)

                add_one_row_for_link(driver, wait, detail_dialog, csv_row, done_key)
                done_keys.add(done_key)

                # click_nuoc_mat_row(driver, wait, detail_dialog)        # uncomment nếu cần
                # add_group_tests_in_current_popup(driver, wait, position_text)

                click_close_dialog(driver, wait, detail_dialog)
                time.sleep(2.0)

                print(f"✅ Hoàn thành: {position_text}")
                success = True
                break

            except Exception as e:
                print(f"⚠️ Lần {attempt+1}/3 lỗi {position_text}: {e}")
                time.sleep(2.5)
                try:
                    click_close_dialog(driver, wait)  # close tất cả dialog đang mở
                except:
                    pass

        if not success:
            print(f"❌ Bỏ qua sau 3 lần: {position_text}")

    print(f"🏁 Hoàn tất ngày {day_num:02d}/05/2026")
    time.sleep(2)


# ========= LOGIN =========
def login_and_go_to_kehoach():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)

    driver.get(CENLAB_URL)
    wait.until(EC.visibility_of_element_located((By.ID, "user-name"))).send_keys(USERNAME)
    wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "input[formcontrolname='password']"))).send_keys(PASSWORD)
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn-login[type='submit']"))).click()

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.grid-layout-container")))

    monitoring_card = wait.until(
        EC.element_to_be_clickable((
            By.XPATH,
            "//div[contains(@class,'title') and normalize-space()='Lấy mẫu - Quan trắc']/ancestor::kendo-card[1]"
        ))
    )
    safe_click(driver, monitoring_card)

    menu = wait.until(
        EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            f"li.k-drawer-item[data-kendo-drawer-index='{DRAWER_INDEX_KEHOACH}'][aria-label='Kế hoạch quan trắc']"
        ))
    )
    safe_click(driver, menu)

    prog = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[normalize-space()='{PROGRAM_CODE}']/ancestor::a[1]")))
    safe_click(driver, prog)
    time.sleep(3)
    return driver, wait


def run():
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    csv_path = os.path.join(base_dir, CSV_FILENAME)

    if not os.path.exists(csv_path):
        for fn in os.listdir(base_dir):
            if fn.upper().startswith("KYHIEU") and fn.lower().endswith(".csv"):
                csv_path = os.path.join(base_dir, fn)
                print(f"⚠️ Dùng file: {fn}")
                break

    rows = read_csv_rows(csv_path)
    by_day = group_rows_by_day(rows)

    done_path = os.path.join(base_dir, DONE_CSV)
    done_keys = load_done_keys(done_path)
    print(f"📌 Đã hoàn thành trước: {len(done_keys)} records")

    driver, wait = login_and_go_to_kehoach()

    try:
        for day_num in DAYS_RANGE_1 + DAYS_RANGE_2:
            print(f"\n{'='*80}")
            print(f"📅 ĐANG XỬ LÝ NGÀY {day_num:02d}/05/2026")
            print(f"{'='*80}")

            day_rows = by_day.get(day_num, [])
            if not day_rows:
                print("ℹ️ Không có dữ liệu ngày này")
                continue

            add_kehoach_for_day(driver, wait, day_num, day_rows, done_keys)

        print("\n🎉 HOÀN TẤT TOÀN BỘ!")
    finally:
        pass


if __name__ == "__main__":
    run()