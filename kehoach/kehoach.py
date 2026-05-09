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
    UnexpectedAlertPresentException,
    ElementClickInterceptedException,
)

# ========= CONFIG =========
CENLAB_URL = "https://cenlab.moitruonghcm.vn/my-cenlab/login?returnUrl=%2F"
USERNAME = "0902969892"
PASSWORD = "fmahEuDuWSL^I6"

# CSV cho "Kế hoạch quan trắc"
CSV_FILENAME = "KYHIEUCS2-update.csv"

DONE_CSV = "donecs2.csv"
PROGRAM_CODE = "CS2.26-0057-03"

DAYS_RANGE_1 = list(range(1, 14))
DAYS_RANGE_2 = list(range(14, 32))

DRAWER_INDEX_KEHOACH = 5  # Kế hoạch quan trắc


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


def dismiss_alert_if_any(driver):
    try:
        alert = driver.switch_to.alert
        txt = alert.text
        alert.accept()
        return txt
    except Exception:
        return None


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
            except StaleElementReferenceException:
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
    last = None
    while time.time() < end:
        try:
            btns = detail_dialog.find_elements(
                By.XPATH,
                ".//button[@title='Thêm' and (not(@hidden) or @hidden='false')]"
            )
            btns = [b for b in btns if b.is_displayed()]
            if btns:
                safe_click(driver, btns[0])
                return
        except (StaleElementReferenceException, ElementClickInterceptedException) as e:
            last = e
        time.sleep(0.25)
    raise TimeoutException(f"Không click được nút Thêm. last={last}")


def fill_text_input(dialog_root, controls_value: str, value: str):
    inp = dialog_root.find_element(By.CSS_SELECTOR, f"input[controls='{controls_value}']")
    inp.send_keys(Keys.CONTROL, "a")
    inp.send_keys(Keys.BACKSPACE)
    inp.send_keys(str(value))


def fill_and_commit(dialog_root, controls_value: str, value: str, commit="TAB"):
    """
    Nhập xong thì chỉ TAB để commit (KHÔNG Enter).
    """
    inp = dialog_root.find_element(By.CSS_SELECTOR, f"input[controls='{controls_value}']")
    inp.send_keys(Keys.CONTROL, "a")
    inp.send_keys(Keys.BACKSPACE)
    inp.send_keys(str(value))

    # CHỈ TAB, không Enter
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
        except StaleElementReferenceException:
            dd = add_dialog.find_element(By.CSS_SELECTOR, "gc-tree-dropdown[controls='matrix_id']")
        time.sleep(0.2)
    raise TimeoutException("matrix_id vẫn bị khóa (chưa enable). Cần commit field 'name'.")


# ========= UPDATED: select matrix by typing "Nước mặt" then click item =========
def select_matrix_nuoc_mat(driver, add_dialog):
    dd = add_dialog.find_element(By.CSS_SELECTOR, "gc-tree-dropdown[controls='matrix_id']")


    # 2) Tìm đúng span (chờ nó xuất hiện)
    span = WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((
            By.XPATH,
            "//span[@kendotreeviewitemcontent and contains(@class,'k-in') "
            "and @data-treeindex='3_13' and normalize-space(.)='Nước mặt']"
        ))
    )

    # 3) Cuộn tới khi thấy span rồi mới click
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", span)
    time.sleep(0.2)

    # Chờ click được (sau scroll)
    WebDriverWait(driver, 8).until(lambda d: span.is_displayed() and span.is_enabled())
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
    except Exception:
        pass


# ========= FLOW =========
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
    print("✅ Đã click card: Lấy mẫu - Quan trắc")

    menu = wait.until(
        EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            f"li.k-drawer-item[data-kendo-drawer-index='{DRAWER_INDEX_KEHOACH}'][aria-label='Kế hoạch quan trắc']"
        ))
    )
    safe_click(driver, menu)
    print("✅ Đã click menu: Kế hoạch quan trắc")

    prog = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[normalize-space()='{PROGRAM_CODE}']/ancestor::a[1]")))
    safe_click(driver, prog)
    print(f"✅ Đã chọn chương trình: {PROGRAM_CODE}")

    time.sleep(3)
    return driver, wait


def click_day_td(driver, wait, day_num: int):
    day_str = f"{day_num:02d}"
    td = wait.until(EC.element_to_be_clickable((
        By.XPATH,
        f"//td[@monthslot and .//span[contains(@class,'k-nav-day') and normalize-space()='{day_str}']]"
    )))
    safe_click(driver, td)


def open_day_popup(driver, wait, day_num: int):
    click_day_td(driver, wait, day_num)
    print(f"📅 Click ngày {day_num:02d}/05/2026")
    time.sleep(2)
    return wait_last_visible_dialog(driver, timeout=18)


def refetch_trieu_links(day_dialog):
    return day_dialog.find_elements(By.XPATH, ".//a[normalize-space()='Triều Lên' or normalize-space()='Triều Xuống']")


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

    target = "QUANTRACNUOCMAT2026-TRIEULEN" if normalize_text(position_text) == "Triều Lên" else "QUANTRACNUOCMAT2026-TRIEUXUONG"
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
    click_visible_add_in_detail(driver, detail_dialog)

    add_dialog = wait_add_form_dialog(driver, timeout=20)

    # Tên: nhập + commit để mở khóa nền mẫu
    fill_and_commit(add_dialog, "name", "Nước mặt", commit="TAB")
    safe_click(driver, add_dialog)
    time.sleep(0.2)

    wait_matrix_enabled(add_dialog, timeout=10)
    select_matrix_nuoc_mat(driver, add_dialog)

    ky_hieu = normalize_text(csv_row.get("Ký hiệu", ""))
    fill_text_input(add_dialog, "code", ky_hieu)

    click_save_in_dialog(driver, add_dialog)

    time.sleep(0.6)
    still_open = False
    try:
        still_open = add_dialog.is_displayed()
    except Exception:
        still_open = False

    if still_open:
        dlg_text = normalize_text(add_dialog.text)
        if "Nền mẫu" in dlg_text and "bắt buộc" in dlg_text:
            click_close_dialog(driver, wait, add_dialog)
            raise Exception("Validate fail: Nền mẫu là mục bắt buộc nhập")

    append_done(DONE_CSV, {
        "key": done_key,
        "Ngày": csv_row.get("Ngày", ""),
        "idx": csv_row.get("_csv_index", ""),
        "Nơi thực hiện": csv_row.get("Nơi thực hiện", ""),
        "Vị trí quan trắc": csv_row.get("Vị trí quan trắc", ""),
        "Ký hiệu": ky_hieu,
    })


def add_kehoach_for_day(driver, wait, day_dialog, day_num: int, day_rows: list, done_keys: set):
    if not day_rows:
        print(f"ℹ️ Ngày {day_num:02d}/02 không có dữ liệu -> bỏ qua")
        click_close_dialog(driver, wait, day_dialog)
        return

    links = refetch_trieu_links(day_dialog)
    print(f"📅 Ngày {day_num:02d}/02: links={len(links)} | csv_rows={len(day_rows)}")

    max_i = min(len(links), len(day_rows))

    for i in range(max_i):
        csv_row = day_rows[i]
        done_key = f"kehoach|{csv_row.get('_csv_index','')}"
        if done_key in done_keys:
            print(f"⏭️ Skip done: csv_idx={csv_row.get('_csv_index')}")
            continue

        attempts = 0
        while attempts < 3:
            try:
                day_dialog = wait_last_visible_dialog(driver, timeout=18)
                links = refetch_trieu_links(day_dialog)
                if i >= len(links):
                    print(f"⚠️ Không có link index={i}")
                    break

                link = links[i]
                position_text = normalize_text(link.text)
                safe_click(driver, link)
                time.sleep(0.9)

                detail_dialog = wait_last_visible_dialog(driver, timeout=18)

                add_one_row_for_link(driver, wait, detail_dialog, csv_row, done_key)
                done_keys.add(done_key)
                print(f"✅ Day {day_num:02d}/02: thêm OK (row {i+1}, csv_idx={csv_row.get('_csv_index')})")

                click_nuoc_mat_row(driver, wait, detail_dialog)
                add_group_tests_in_current_popup(driver, wait, position_text)

                click_close_dialog(driver, wait, detail_dialog)
                time.sleep(1)
                break

            except (StaleElementReferenceException, ElementClickInterceptedException) as e:
                attempts += 1
                print(f"⚠️ Retry stale/intercept row#{i+1}: {e}")
                time.sleep(0.8)
            except Exception as e:
                attempts += 1
                print(f"⚠️ Retry err row#{i+1}: {e}")

                try:
                    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                    time.sleep(0.2)
                    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                    time.sleep(0.2)
                except Exception:
                    pass

                try:
                    day_dialog = open_day_popup(driver, wait, day_num)
                except Exception:
                    pass

                time.sleep(0.8)

    click_close_dialog(driver, wait, day_dialog)
    time.sleep(1)


def run():
    base_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    csv_path = os.path.join(base_dir, CSV_FILENAME)
    if not os.path.exists(csv_path):
        for fn in os.listdir(base_dir):
            if fn.upper().startswith("KYHIEU") and fn.lower().endswith(".csv"):
                csv_path = os.path.join(base_dir, fn)
                print(f"⚠️ Không thấy {CSV_FILENAME}. Dùng file: {fn}")
                break

    rows = read_csv_rows(csv_path)
    by_day = group_rows_by_day(rows)

    done_path = os.path.join(base_dir, DONE_CSV)
    done_keys = load_done_keys(done_path)
    print(f"📌 Done keys: {len(done_keys)}")

    driver, wait = login_and_go_to_kehoach()

    try:
        for day_num in DAYS_RANGE_1 + DAYS_RANGE_2:
            print(f"\n📅 Xử lý ngày {day_num:02d}/05/2026")
            day_rows = by_day.get(day_num, [])
            if not day_rows:
                print("ℹ️ CSV không có dữ liệu ngày này -> skip")
                continue

            day_dialog = open_day_popup(driver, wait, day_num)
            add_kehoach_for_day(driver, wait, day_dialog, day_num, day_rows, done_keys)

        print("\n🎉 Hoàn tất Kế hoạch quan trắc theo CSV.")
    finally:
        # driver.quit()
        pass


if __name__ == "__main__":
    run()
