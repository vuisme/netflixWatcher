import imaplib
import email
import re
import time
import os
import requests
import html2text
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import logging
from googleapiclient.discovery import build
from googleapiclient.discovery_cache.base import Cache
from datetime import datetime

# --- CẤU HÌNH LOGGING: DEBUG ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Tải biến môi trường ---
EMAIL_IMAP = os.environ.get('EMAIL_IMAP', 'imap.gmail.com')
EMAIL_LOGIN = os.environ['EMAIL_LOGIN']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']

NETFLIX_EMAIL_SENDERS = [s.strip() for s in os.environ.get('NETFLIX_EMAIL_SENDERS', '').split(',') if s.strip()]
CAKE_EMAIL_SENDERS = [s.strip() for s in os.environ.get('CAKE_EMAIL_SENDERS', '').split(',') if s.strip()]

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
RANGE_NAME = os.environ['RANGE_NAME']
API_KEY = os.environ['GOOGLE_SHEETS_API_KEY']
TELEGRAM_ADMIN_UID = os.environ['TELEGRAM_ADMIN_UID']

ENABLE_NETFLIX_MODULE = os.environ.get('ENABLE_NETFLIX_MODULE', 'true').lower() == 'true'
ENABLE_CAKE_MODULE = os.environ.get('ENABLE_CAKE_MODULE', 'true').lower() == 'true'

SELENIUM_HOST = os.environ.get('SELENIUM_HOST', 'localhost')
SELENIUM_PORT = os.environ.get('SELENIUM_PORT', '4444')
SELENIUM_URL = f'http://{SELENIUM_HOST}:{SELENIUM_PORT}/wd/hub'

class NoCache(Cache):
    def get(self, url): return None
    def set(self, url, content): pass

def get_selenium_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    logger.debug(f"Kết nối Selenium: {SELENIUM_URL}")
    return webdriver.Remote(command_executor=SELENIUM_URL, options=options)

def get_recipients_from_spreadsheet():
    try:
        service = build('sheets', 'v4', developerKey=API_KEY, cache_discovery=False, cache=NoCache())
        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])
        recipients = []
        if values:
            for row in values:
                if len(row) >= 2:
                    recipients.append({'email': row[0].strip(), 'telegram_id': row[1].strip()})
        logger.debug(f"Đã tải {len(recipients)} người dùng từ Sheet.")
        return recipients
    except Exception as e:
        logger.error(f"Lỗi Google Sheets: {e}")
        return []

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
        logger.info(f"✅ Đã gửi Telegram tới {chat_id}")
    except Exception as e:
        logger.error(f"❌ Gửi Telegram thất bại: {e}")

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_codes(text):
    text = re.sub(r'\s+', ' ', text)
    match = re.search(r'(?:Enter this code to sign in|Nhập mã này để đăng nhập)\s*(\d{4})', text)
    return match.group(1) if match else None

def open_link_with_selenium(link, recipient_email, chat_id):
    driver = None
    try:
        logger.info(f"Đang xử lý link update location: {link[:50]}...")
        driver = get_selenium_driver()
        driver.get(link)
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-uia="set-primary-location-action"]'))
        ).click()
        send_telegram_message(chat_id, f'✅ Đã update Hộ Gia Đình cho {recipient_email}')
    except Exception as e:
        logger.error(f"Selenium Error: {e}")
    finally:
        if driver: driver.quit()

def handle_temporary_access_code(link, recipient_email, chat_id):
    driver = None
    try:
        logger.info(f"Đang lấy mã OTP tạm thời: {link[:50]}...")
        driver = get_selenium_driver()
        driver.get(link)
        otp_element = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-uia="travel-verification-otp"]'))
        )
        send_telegram_message(chat_id, f'🔑 Mã OTP tạm thời: {otp_element.text}')
    except Exception as e:
        logger.error(f"Selenium Error: {e}")
    finally:
        if driver: driver.quit()

def process_netflix_email(body, subject, recipient_email, chat_id):
    logger.debug(f"--- BẮT ĐẦU XỬ LÝ EMAIL NETFLIX ---")
    logger.debug(f"Subject: {subject}")
    # In ra 200 ký tự đầu của body để debug
    logger.debug(f"Body snippet: {body[:200]}...") 

    action_taken = False

    # 1. Check mã OTP đăng nhập
    if 'Enter this code to sign in' in body or 'Nhập mã này để đăng nhập' in body:
        logger.debug("-> Phát hiện keyword: OTP Login")
        otp = extract_codes(body)
        if otp:
            send_telegram_message(chat_id, f'🏠 Mã OTP Login: {otp}')
            action_taken = True
        else:
            logger.warning("-> Có keyword nhưng không regex được mã 4 số!")

    # 2. Check Link
    else:
        links = extract_links(body)
        logger.debug(f"-> Tìm thấy {len(links)} links trong email.")
        
        for link in links:
            if "update-primary-location" in link:
                logger.debug("-> Phát hiện link: Update Primary Location")
                open_link_with_selenium(link, recipient_email, chat_id)
                action_taken = True
                break # Chỉ xử lý 1 link quan trọng nhất
            elif "temporary-access-code" in link or "account/travel/verify" in link:
                logger.debug("-> Phát hiện link: Temporary Access Code")
                handle_temporary_access_code(link, recipient_email, chat_id)
                action_taken = True
                break

    if not action_taken:
        logger.warning(f"⚠️ Email từ Netflix không khớp bất kỳ kịch bản nào (OTP/Update Location). Bỏ qua.")
        logger.debug(f"Full Body (check kỹ keyword): {body}")

def fetch_last_unseen_email():
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    try:
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")

        all_senders = []
        if ENABLE_NETFLIX_MODULE: all_senders.extend(NETFLIX_EMAIL_SENDERS)

        for sender in all_senders:
            if not sender: continue
            
            # Tìm email chưa đọc
            status, data = mail.search(None, f'(UNSEEN FROM "{sender}")')
            if status != 'OK' or not data[0]:
                continue
                
            email_ids = data[0].split()
            latest_email_id = email_ids[-1]
            
            logger.debug(f"Đang fetch email ID: {latest_email_id} từ {sender}")
            _, msg_data = mail.fetch(latest_email_id, "(RFC822)")
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Lấy thông tin cơ bản
            recipient_header = msg['To'] or ""
            recipient_email = email.utils.parseaddr(recipient_header)[1]
            subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
            
            logger.info(f"📩 Email mới: {sender} -> {recipient_email} | Subject: {subject}")

            # Lấy nội dung
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() in ["text/plain", "text/html"]:
                        payload = part.get_payload(decode=True)
                        if payload: 
                            body += payload.decode(errors='ignore')
            else:
                payload = msg.get_payload(decode=True)
                if payload: body = payload.decode(errors='ignore')

            # Logic tìm người nhận Telegram
            if sender in NETFLIX_EMAIL_SENDERS:
                recipients = get_recipients_from_spreadsheet()
                chat_id = next((r['telegram_id'] for r in recipients if r['email'] == recipient_email), None)
                
                if chat_id:
                    logger.debug(f"Tìm thấy Chat ID: {chat_id} cho {recipient_email}")
                    process_netflix_email(body, subject, recipient_email, chat_id)
                else:
                    logger.warning(f"⚠️ Không tìm thấy Chat ID trong Sheet cho email: {recipient_email}. Vui lòng kiểm tra file Google Sheet.")

    except Exception as e:
        logger.error(f"Lỗi xử lý email: {e}")
    finally:
        try:
            mail.close()
            mail.logout()
        except: pass

if __name__ == "__main__":
    logger.info(f'🚀 APP STARTED (DEBUG MODE)')
    while True:
        try:
            fetch_last_unseen_email()
        except Exception as e:
            logger.critical(f"CRASH: {e}")
        time.sleep(20)
