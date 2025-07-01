
import time
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd

BASE_URL = "https://www.ecms.penndot.pa.gov/ECMS/"

source_configs = {
    "Executed Legal Agreements": {
        "url_suffix": "SVLGLSearch?action=SearchPublicAgr",
        "agreement_label": "Project Specific Agreement",
        "cost_label": "Maximum Agreement Cost",
        "has_supplement": False,
        "has_work_order": False,
        "has_amendment": False
    },
    "Executed Legal Supplements": {
        "url_suffix": "SVLGLSearch?action=SearchPublicSuppl",
        "agreement_label": "Project Specific Agreement",
        "cost_label": "Supplemental Agreement Cost",
        "has_supplement": True,
        "has_work_order": False,
        "has_amendment": False
    },
    "Executed Legal Work Orders": {
        "url_suffix": "SVLGLSearch?action=SearchPublicWO",
        "agreement_label": "Open End / Project Specific Agreement",
        "cost_label": "Maximum Work Order Cost",
        "has_supplement": False,
        "has_work_order": True,
        "has_amendment": False
    },
    "Executed Legal Work Order Amendments": {
        "url_suffix": "SVLGLSearch?action=SearchPublicWOA",
        "agreement_label": "Open End / Project Specific Agreement",
        "cost_label": "Work Order Amendment Cost",
        "has_supplement": False,
        "has_work_order": True,
        "has_amendment": True
    }
}

def extract_detail_fields(detail_soup, config):
    record = {}
    text_all = detail_soup.get_text(separator="\n")
    agreement_match = re.search(r"E\d{5}", text_all)
    record["Agreement No."] = agreement_match.group(0) if agreement_match else ""

    def extract_line_above(label):
        label_elem = detail_soup.find(string=re.compile(re.escape(label), re.I))
        if not label_elem:
            return ""
        parent = label_elem.find_parent()
        prev_sibling = parent.find_previous_sibling()
        while prev_sibling and not prev_sibling.get_text(strip=True):
            prev_sibling = prev_sibling.find_previous_sibling()
        return prev_sibling.get_text(strip=True) if prev_sibling else ""

    if config["has_supplement"]:
        sup_match = re.search(r"Supplement #\s*(\d+)", text_all)
        record["Supplement No."] = sup_match.group(1) if sup_match else ""
    if config.get("has_work_order"):
        work_order_match = re.search(r"Work Order #\s*(\d+)", text_all)
        record["Work Order No."] = work_order_match.group(1) if work_order_match else ""
    if config.get("has_amendment"):
        amend_match = re.search(r"Amendment #\s*(\d+)", text_all)
        record["Amendment No."] = amend_match.group(1) if amend_match else ""

    org_text = extract_line_above("Initiating Organization")
    record["Initiating Org/BP"] = re.sub(r"^Engineering\s*", "", org_text, flags=re.I)
    record["Cost"] = extract_line_above(config["cost_label"])
    consultant_line = extract_line_above("Consultant - FID")
    consultant_clean = re.sub(r"\b\d{2}-\d{7}\b|\b\d{9}\b", "", consultant_line).strip()
    record["Consultant - FID"] = consultant_clean

    def extract_method_between_labels(detail_soup):
        fid_label = detail_soup.find(string=re.compile(r"Consultant.*FID", re.I))
        method_label = detail_soup.find(string=re.compile(r"Method\(s\) of Payment", re.I))
        if not fid_label or not method_label:
            return ""
        fid_block = fid_label.find_parent()
        while fid_block and fid_block.name != "tr":
            fid_block = fid_block.find_parent()
        method_block = method_label.find_parent()
        while method_block and method_block.name != "tr":
            method_block = method_block.find_parent()
        if not fid_block or not method_block:
            return ""
        texts_between = []
        current = fid_block.find_next_sibling()
        while current and current != method_block:
            text = current.get_text(separator=" ", strip=True)
            if text:
                texts_between.append(text)
            current = current.find_next_sibling()
        return " ".join(texts_between).strip()

    record["Method(s) of Payment"] = extract_method_between_labels(detail_soup)
    return record

def handle_session_timeout_popup(driver):
    try:
        buttons = driver.find_elements(By.NAME, "timeoutContinue")
        for btn in buttons:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(2)
                print("✅ Clicked 'Yes' on session timeout popup.")
                return True
    except Exception:
        pass
    return False

def click_next_page(driver):
    handle_session_timeout_popup(driver)
    try:
        next_img = driver.find_element(By.CSS_SELECTOR, "img[alt='Go to next page']")
        next_link = next_img.find_element(By.XPATH, "./parent::a")
        if next_link.is_displayed() and next_link.is_enabled():
            next_link.click()
            time.sleep(5)
            return True
    except Exception as e:
        print(f"Next page error: {e}")
    return False

def get_total_pages(driver):
    try:
        page_info = driver.find_element(By.CSS_SELECTOR, "td.paging.center.middle")
        text = page_info.text.strip()
        match = re.search(r"Page \d+ of (\d+)", text)
        if match:
            return int(match.group(1))
    except NoSuchElementException:
        pass
    return 1

def run_scraper(start_year, end_year, selected_sources):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.get(BASE_URL)
    guest_link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'anonymous=true')]"))
    )
    guest_link.click()

    try:
        WebDriverWait(driver, 10).until(EC.alert_is_present())
        driver.switch_to.alert.accept()
    except TimeoutException:
        pass

    time.sleep(3)
    all_dfs = []

    for source_name in selected_sources:
        config = source_configs[source_name]
        url = BASE_URL + config["url_suffix"]
        driver.get(url)
        time.sleep(3)

        all_records = []
        page_num = 1
        total_pages = get_total_pages(driver)

        while page_num <= total_pages:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//table//tr"))
                )
            except TimeoutException:
                break

            rows = driver.find_elements(By.XPATH, "//table//tr")
            detail_urls = []

            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) < 5:
                    continue
                exec_date_text = cols[3].text.strip()
                try:
                    exec_date = datetime.strptime(exec_date_text, "%m/%d/%Y")
                except ValueError:
                    continue
                if exec_date.year < start_year or exec_date.year > end_year:
                    continue
                try:
                    link_tag = cols[0].find_element(By.TAG_NAME, "a")
                    detail_url = link_tag.get_attribute("href")
                    if not detail_url.startswith("http"):
                        detail_url = BASE_URL + detail_url
                    detail_urls.append((exec_date, detail_url))
                except Exception:
                    continue

            for exec_date, detail_url in detail_urls:
                try:
                    driver.get(detail_url)
                    time.sleep(2)
                    detail_soup = BeautifulSoup(driver.page_source, "html.parser")
                    record = {
                        "Link": detail_url,
                        "Executed Date": exec_date.strftime("%Y-%m-%d"),
                        "Source": source_name
                    }
                    record.update(extract_detail_fields(detail_soup, config))
                    all_records.append(record)
                    driver.back()
                    time.sleep(2)
                except Exception:
                    continue

            if page_num < total_pages:
                if not click_next_page(driver):
                    break
                time.sleep(5)
                page_num += 1
            else:
                break

        df = pd.DataFrame(all_records)
        df.rename(columns={"Consultant - FID": "Consultant"}, inplace=True)
        all_dfs.append((source_name, df))

    driver.quit()
    return all_dfs
