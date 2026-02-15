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

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Tải biến môi trường ---
EMAIL_IMAP = os.environ.get('EMAIL_IMAP', 'imap.gmail.com')
EMAIL_LOGIN = os.environ['EMAIL_LOGIN']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']

# Xử lý danh sách sender, lọc bỏ chuỗi rỗng
NETFLIX_EMAIL_SENDERS = [s.strip() for s in os.environ.get('NETFLIX_EMAIL_SENDERS', '').split(',') if s.strip()]
CAKE_EMAIL_SENDERS = [s.strip() for s in os.environ.get('CAKE_EMAIL_SENDERS', '').split(',') if s.strip()]

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
RANGE_NAME = os.environ['RANGE_NAME']
API_KEY = os.environ['GOOGLE_SHEETS_API_KEY']
TELEGRAM_ADMIN_UID = os.environ['TELEGRAM_ADMIN_UID']

ENABLE_NETFLIX_MODULE = os.environ.get('ENABLE_NETFLIX_MODULE', 'true').lower() == 'true'
ENABLE_CAKE_MODULE = os.environ.get('ENABLE_CAKE_MODULE', 'true').lower() == 'true'

# Cấu hình Selenium từ biến môi trường (Quan trọng cho K8s)
SELENIUM_HOST = os.environ.get('SELENIUM_HOST', 'localhost')
SELENIUM_PORT = os.environ.get('SELENIUM_PORT', '4444')
SELENIUM_URL = f'http://{SELENIUM_HOST}:{SELENIUM_PORT}/wd/hub'

class NoCache(Cache):
    """Dummy cache class for disabling the cache."""
    def get(self, url):
        return None
    def set(self, url, content):
        pass

def get_selenium_driver():
    """Khởi tạo Selenium Driver với cấu hình dynamic"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    logger.info(f"Đang kết nối tới Selenium tại: {SELENIUM_URL}")
    return webdriver.Remote(
        command_executor=SELENIUM_URL,
        options=options
    )

def get_recipients_from_spreadsheet():
    """Lấy danh sách email và ID nhóm Telegram từ Google Sheets"""
    try:
        service = build('sheets', 'v4', developerKey=API_KEY, cache_discovery=False, cache=NoCache())
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        recipients = []
        if not values:
            logger.warning("No data found in the spreadsheet.")
        else:
            for row in values:
                if len(row) >= 2:
                    recipients.append({'email': row[0].strip(), 'telegram_id': row[1].strip()})
        return recipients
    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu từ Google Sheets: {e}")
        return []

def send_telegram_message(chat_id, message, retry_delay=10, max_attempts=3):
    """Gửi tin nhắn Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message}
    
    for attempt in range(max_attempts):
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Đã gửi Telegram tới {chat_id}")
            return
        except Exception as e:
            logger.error(f"Gửi Telegram thất bại (Lần {attempt+1}): {e}")
            time.sleep(retry_delay)
    
    logger.error(f"Bỏ cuộc gửi tin nhắn tới {chat_id} sau {max_attempts} lần.")

def extract_links(text):
    return re.findall(r'https?://\S+', text)

def extract_codes(text):
    text = re.sub(r'\s+', ' ', text)
    # Pattern tìm mã 4 số
    match = re.search(r'(?:Enter this code to sign in|Nhập mã này để đăng nhập)\s*(\d{4})', text)
    return match.group(1) if match else None

def mask_email(email_address):
    try:
        username, domain = email_address.split('@')
        if len(username) > 7:
            return f"{username[:2]}****{username[-1]}@{domain}"
        return f"{username[:2]}****@{domain}"
    except:
        return email_address

def open_link_with_selenium(link, recipient_email, chat_id):
    driver = None
    try:
        driver = get_selenium_driver()
        driver.get(link)
        
        # Chờ nút xác nhận
        WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-uia="set-primary-location-action"]'))
        ).click()
        
        masked = mask_email(recipient_email)
        msg = f'✅ Đã tự động cập nhật Hộ Gia Đình cho {masked}'
        logger.info(msg)
        send_telegram_message(chat_id, msg)
        
    except Exception as e:
        msg = f"❌ Lỗi Selenium (Update Primary Location): {e}"
        logger.error(msg)
        send_telegram_message(TELEGRAM_ADMIN_UID, msg)
    finally:
        if driver: driver.quit()

def handle_temporary_access_code(link, recipient_email, chat_id):
    driver = None
    try:
        driver = get_selenium_driver()
        driver.get(link)
        
        otp_element = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-uia="travel-verification-otp"]'))
        )
        otp_code = otp_element.text
        
        masked = mask_email(recipient_email)
        msg = f'🔑 Mã OTP tạm thời cho {masked} là: {otp_code}'
        logger.info(msg)
        send_telegram_message(chat_id, msg)
        
    except Exception as e:
        msg = f"❌ Lỗi Selenium (Get Temp Code): {e}"
        logger.error(msg)
        send_telegram_message(TELEGRAM_ADMIN_UID, msg)
    finally:
        if driver: driver.quit()

def extract_transaction_details(body):
    details = {}
    # Regex tìm tiền
    inc = re.search(r"vừa tăng ([\d,.]+) VND", body)
    if inc: details["amount_increased"] = inc.group(1)
    
    dec = re.search(r"vừa giảm ([\d,.]+) VND", body)
    if dec: details["amount_decreased"] = dec.group(1)
    
    # Regex tìm thời gian
    time_match = re.search(r"vào (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", body)
    if time_match: details["time"] = time_match.group(1)
    
    curr = re.search(r"Số dư hiện tại: ([\d,.]+) VND", body)
    if curr: details["current_balance"] = curr.group(1)
    
    desc = re.search(r"Mô tả: (.+)", body)
    if desc: details["description"] = desc.group(1).split("</p>")[0]
    
    return details

def process_netflix_email(body, recipient_email, chat_id):
    if 'Enter this code to sign in' in body or 'Nhập mã này để đăng nhập' in body:
        otp = extract_codes(body)
        if otp:
            masked = mask_email(recipient_email)
            msg = f'🏠 Mã OTP Login cho {masked}: {otp}'
            logger.info(msg)
            send_telegram_message(chat_id, msg)
    else:
        links = extract_links(body)
        for link in links:
            if "update-primary-location" in link:
                open_link_with_selenium(link, recipient_email, chat_id)
            elif "temporary-access-code" in link or "account/travel/verify" in link:
                handle_temporary_access_code(link, recipient_email, chat_id)

def process_cake_email(body):
    details = extract_transaction_details(body)
    if not details: return

    msg = ""
    if 'amount_increased' in details:
        msg = f"💰 CAKE TĂNG: {details['amount_increased']}\n"
    elif 'amount_decreased' in details:
        msg = f"💸 CAKE GIẢM: {details['amount_decreased']}\n"
    
    if msg:
        msg += f"Số dư: {details.get('current_balance', '?')}\n"
        msg += f"ND: {details.get('description', '?')}\n"
        msg += f"Lúc: {details.get('time', '?')}"
        send_telegram_message(TELEGRAM_ADMIN_UID, msg)

def fetch_last_unseen_email():
    """Lấy email chưa đọc và xử lý"""
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    try:
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")

        all_senders = []
        if ENABLE_NETFLIX_MODULE: all_senders.extend(NETFLIX_EMAIL_SENDERS)
        if ENABLE_CAKE_MODULE: all_senders.extend(CAKE_EMAIL_SENDERS)

        for sender in all_senders:
            if not sender: continue # Bỏ qua sender rỗng

            # Tìm kiếm email chưa đọc
            status, data = mail.search(None, f'(UNSEEN FROM "{sender}")')
            
            # --- FIX QUAN TRỌNG: Kiểm tra dữ liệu trả về ---
            if status != 'OK' or not data or not data[0]:
                continue
                
            email_ids = data[0].split()
            if not email_ids:
                continue
            # -----------------------------------------------

            # Lấy email mới nhất
            latest_email_id = email_ids[-1]
            status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
            
            if status != 'OK' or not msg_data:
                logger.error(f"Không thể fetch email ID: {latest_email_id}")
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Parse thông tin
            recipient_header = msg['To'] or ""
            recipient_email = email.utils.parseaddr(recipient_header)[1]
            logger.info(f"📩 Email mới từ: {sender} -> {recipient_email}")

            # Lấy Body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() in ["text/plain", "text/html"]:
                        payload = part.get_payload(decode=True)
                        if payload: body = payload.decode(errors='ignore')
            else:
                payload = msg.get_payload(decode=True)
                if payload: body = payload.decode(errors='ignore')

            # Xử lý Logic
            if sender in NETFLIX_EMAIL_SENDERS and ENABLE_NETFLIX_MODULE:
                recipients = get_recipients_from_spreadsheet()
                chat_id = next((r['telegram_id'] for r in recipients if r['email'] == recipient_email), None)
                
                if chat_id:
                    process_netflix_email(body, recipient_email, chat_id)
                else:
                    logger.warning(f"Không tìm thấy Chat ID cho email: {recipient_email}")

            elif sender in CAKE_EMAIL_SENDERS and ENABLE_CAKE_MODULE:
                process_cake_email(body)

    except imaplib.IMAP4.error as e:
        logger.error(f"Lỗi IMAP: {e}")
    except Exception as e:
        logger.error(f"Lỗi không mong muốn: {e}")
    finally:
        try:
            mail.close()
            mail.logout()
        except:
            pass

if __name__ == "__main__":
    logger.info(f'🚀 APP STARTED - Selenium Host: {SELENIUM_HOST}')
    logger.info(f'NETFLIX MODULE: {"ON" if ENABLE_NETFLIX_MODULE else "OFF"}')
    logger.info(f'CAKE MODULE: {"ON" if ENABLE_CAKE_MODULE else "OFF"}')
    
    while True:
        try:
            fetch_last_unseen_email()
        except Exception as e:
            logger.critical(f"Lỗi vòng lặp chính: {e}")
        time.sleep(20)
