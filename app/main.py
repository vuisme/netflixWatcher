import imaplib
import email
import re
import time
import os
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import logging
import gspread

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tải biến môi trường
EMAIL_IMAP = os.environ['EMAIL_IMAP']
EMAIL_LOGIN = os.environ['EMAIL_LOGIN']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']
NETFLIX_EMAIL_SENDER = os.environ['NETFLIX_EMAIL_SENDER']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
SPREADSHEET_URL = os.environ['SPREADSHEET_URL']

def get_recipients_from_spreadsheet():
    """Lấy danh sách email và ID nhóm Telegram từ Google Sheets công khai"""
    try:
        gc = gspread.service_account_from_dict({
            "type": "service_account",
            "project_id": "dummy",
            "private_key_id": "dummy",
            "private_key": "dummy",
            "client_email": "dummy@dummy.iam.gserviceaccount.com",
            "client_id": "dummy",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/dummy%40dummy.iam.gserviceaccount.com"
        })
        spreadsheet = gc.open_by_url(SPREADSHEET_URL)
        worksheet = spreadsheet.sheet1
        recipients = worksheet.get_all_records()
        return recipients
    except Exception as e:
        logger.error("Lỗi khi lấy dữ liệu từ Google Sheets: %s", e)
        return []

def send_telegram_message(chat_id, message):
    """Gửi tin nhắn đến nhóm Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("Gửi tin nhắn Telegram thành công")
    except requests.exceptions.RequestException as e:
        logger.error("Gửi tin nhắn Telegram thất bại: %s", e)

def extract_links(text):
    """Tìm tất cả các liên kết https"""
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls

def extract_codes(text):
    """Tìm mã 4 chữ số sau 'Enter this code to sign in'"""
    text = re.sub(r'\s+', ' ', text)
    codes = re.search(r'(?<=Enter this code to sign in )\d{4}', text)
    if codes:
        return codes.group()
    return None

def mask_email(email_address):
    """Che địa chỉ email để chỉ hiện 2 ký tự đầu và 5 ký tự cuối"""
    username, domain = email_address.split('@')
    if len(username) > 7:
        masked_username = username[:2] + '****' + username[-1:]
    else:
        masked_username = username[:2] + '****'
    masked_email = masked_username + '@' + domain
    return masked_email

def open_link_with_selenium(link, recipient_email, chat_id):
    """Mở Selenium và nhấp nút để xác nhận kết nối"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Remote(
        command_executor='http://netflix_watcher_selenium:4444/wd/hub',
        options=options
    )

    try:
        driver.get(link)
        WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-uia="set-primary-location-action"]'))
        ).click()
        masked_email = mask_email(recipient_email)
        message = f'Đã tự động cập nhật Hộ Gia Đình thành công cho {masked_email}'
        logger.info(message)
        send_telegram_message(chat_id, message)
    except TimeoutException as e:
        logger.error("Lỗi: %s", e)
    finally:
        driver.quit()

def handle_temporary_access_code(link, recipient_email, chat_id):
    """Mở Selenium và lấy mã OTP từ liên kết"""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Remote(
        command_executor='http://netflix_watcher_selenium:4444/wd/hub',
        options=options
    )

    try:
        driver.get(link)
        otp_element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-uia="otp-code-element"]'))
        )
        otp_code = otp_element.text
        masked_email = mask_email(recipient_email)
        message = f'Mã OTP tạm thời cho {masked_email} là: {otp_code}'
        logger.info(message)
        send_telegram_message(chat_id, message)
    except TimeoutException as e:
        logger.error("Lỗi: %s", e)
    finally:
        driver.quit()

def process_email_body(body, recipient_email, chat_id):
    """Xử lý nội dung email"""
    if 'Enter this code to sign in' in body:
        otpcode = extract_codes(body)
        if otpcode:
            masked_email = mask_email(recipient_email)
            message = f'Mã OTP cho {masked_email} là: {otpcode}'
            logger.info(message)
            send_telegram_message(chat_id, message)
    else:
        links = extract_links(body)
        for link in links:
            if "update-primary-location" in link:
                open_link_with_selenium(link, recipient_email, chat_id)
            elif "temporary-access-code" in link:
                handle_temporary_access_code(link, recipient_email, chat_id)

def fetch_last_unseen_email():
    """Lấy nội dung của email chưa đọc cuối cùng từ hộp thư đến"""
    recipients = get_recipients_from_spreadsheet()
    if not recipients:
        logger.error("Không có danh sách người nhận từ Google Sheets")
        return
    
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    try:
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")
        _, email_ids = mail.search(None, '(UNSEEN FROM ' + NETFLIX_EMAIL_SENDER + ')')
        email_ids = email_ids[0].split()
        if email_ids:
            email_id = email_ids[-1]
            _, msg_data = mail.fetch(email_id, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            logger.info('Phát hiện yêu cầu xác thực mới')

            recipient_email = email.utils.parseaddr(msg['To'])[1]
            chat_id = next((item['telegram_id'] for item in recipients if item['email'] == recipient_email), None)
            if not chat_id:
                logger.error(f"Không tìm thấy chat ID cho email {recipient_email}")
                return
            
            subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
            if 'sign-in code' in subject:
                logger.info('Email chứa tiêu đề "sign-in code"')
            elif 'temporary access code' in subject:
                logger.info('Email chứa tiêu đề "temporary access code"')

            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if "text/plain" in content_type:
                        body = part.get_payload(decode=True).decode()
                        process_email_body(body, recipient_email, chat_id)
            else:
                body = msg.get_payload(decode=True).decode()
                process_email_body(body, recipient_email, chat_id)
    except Exception as e:
        logger.error("Lỗi khi xử lý email: %s", e)
    finally:
        mail.logout()

if __name__ == "__main__":
    logger.info('KHỞI TẠO THÀNH CÔNG')
    while True:
        fetch_last_unseen_email()
        time.sleep(20)
