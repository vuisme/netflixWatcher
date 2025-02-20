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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tải biến môi trường
EMAIL_IMAP = os.environ['EMAIL_IMAP']
EMAIL_LOGIN = os.environ['EMAIL_LOGIN']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']
NETFLIX_EMAIL_SENDERS = os.environ.get('NETFLIX_EMAIL_SENDERS', '').split(',')
CAKE_EMAIL_SENDERS = os.environ.get('CAKE_EMAIL_SENDERS', '').split(',')
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
SPREADSHEET_ID = os.environ['SPREADSHEET_ID']
RANGE_NAME = os.environ['RANGE_NAME']
API_KEY = os.environ['GOOGLE_SHEETS_API_KEY']
TELEGRAM_ADMIN_UID = os.environ['TELEGRAM_ADMIN_UID']
ENABLE_NETFLIX_MODULE = os.environ.get('ENABLE_NETFLIX_MODULE', 'true').lower() == 'true'
ENABLE_CAKE_MODULE = os.environ.get('ENABLE_CAKE_MODULE', 'true').lower() == 'true'

class NoCache(Cache):
    """Dummy cache class for disabling the cache."""
    def get(self, url):
        return None

    def set(self, url, content):
        pass

def get_recipients_from_spreadsheet():
    """Lấy danh sách email và ID nhóm Telegram từ Google Sheets công khai"""
    try:
        service = build('sheets', 'v4', developerKey=API_KEY, cache_discovery=False, cache=NoCache())
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
        values = result.get('values', [])

        recipients = []
        if not values:
            message = "No data found in the spreadsheet."
            logger.warning(message)
            send_telegram_message(TELEGRAM_ADMIN_UID, message)
        else:
            for row in values:
                if len(row) >= 2:
                    recipients.append({'email': row[0], 'telegram_id': row[1]})
        return recipients
    except Exception as e:
        message = f"Lỗi khi lấy dữ liệu từ Google Sheets: {e}"
        logger.error(message)
        send_telegram_message(TELEGRAM_ADMIN_UID, message)
        return []

def send_telegram_message(chat_id, message, retry_delay=30, max_attempts=5):
    """Gửi tin nhắn đến nhóm Telegram với khả năng thử lại sau khi gửi thất bại"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    attempt = 0
    while attempt < max_attempts:
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logger.info("Gửi tin nhắn Telegram thành công")
            return  # Thoát khỏi vòng lặp nếu gửi tin nhắn thành công
        except requests.exceptions.RequestException as e:
            logger.error("Gửi tin nhắn Telegram thất bại: %s", e)
            if attempt == max_attempts - 1:
                # Gửi tin nhắn cho admin sau khi thử max_attempts lần
                send_telegram_message(TELEGRAM_ADMIN_UID, f"Gửi tin nhắn Telegram thất bại sau {max_attempts} lần thử: {e}")
            logger.info(f"Thử lại sau {retry_delay} giây...")
            time.sleep(retry_delay)
            attempt += 1
    logger.error(f"Đã thử {max_attempts} lần, không thể gửi tin nhắn.")

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
    codes = re.search(r'(?<=Nhập mã này để đăng nhập )\d{4}', text)
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
        message = f"Lỗi: {e}"
        logger.error(message)
        send_telegram_message(TELEGRAM_ADMIN_UID, message)
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
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-uia="travel-verification-otp"]'))
        )
        otp_code = otp_element.text
        masked_email = mask_email(recipient_email)
        message = f'Mã OTP tạm thời cho {masked_email} là: {otp_code}'
        logger.info(message)
        send_telegram_message(chat_id, message)
    except TimeoutException as e:
        message = f"Lỗi: {e}"
        logger.error(message)
        send_telegram_message(TELEGRAM_ADMIN_UID, message)
    except WebDriverException as e:
        message = f"Lỗi WebDriver: {e}"
        logger.error(message)
        send_telegram_message(TELEGRAM_ADMIN_UID, message)
    finally:
        driver.quit()


def extract_transaction_details(body):
    """Trích xuất chi tiết giao dịch từ nội dung email."""
    transaction_details = {}

    # Trích xuất số tiền tăng
    amount_increased_match = re.search(r"vừa tăng ([\d,.]+) VND", body)
    if amount_increased_match:
        transaction_details["amount_increased"] = amount_increased_match.group(1)

    # Trích xuất số tiền giảm
    amount_decreased_match = re.search(r"vừa giảm ([\d,.]+) VND", body)
    if amount_decreased_match:
        transaction_details["amount_decreased"] = amount_decreased_match.group(1)

    # Lấy thời gian giao dịch
    time_match = re.search(r"vào (\d{2}/\d{2}/\d{4} \d{2}:\d{2})", body)
    if time_match:
        transaction_details["time"] = time_match.group(1)

        # Chuyển đổi sang định dạng ISO 8601
        try:
            datetime_object = datetime.strptime(transaction_details["time"], "%d/%m/%Y %H:%M") # Định dạng thời gian gốc
            transaction_details["time"] = datetime_object.isoformat() + "+07:00"  # Thêm '+07:00' cho múi giờ Việt Nam
        except ValueError:
            logger.info("Lỗi: Định dạng thời gian không hợp lệ.")

    # Trích xuất số dư hiện tại
    current_balance_match = re.search(r"Số dư hiện tại: ([\d,.]+) VND", body)
    if current_balance_match:
        transaction_details["current_balance"] = current_balance_match.group(1)

    # Trích xuất mô tả giao dịch
    description_match = re.search(r"Mô tả: (.+)", body)
    if description_match:
        transaction_details["description"] = description_match.group(1).split("</p>")[0]

    return transaction_details


def process_netflix_email(body, recipient_email, chat_id):
    """Xử lý email từ Netflix"""
    if 'Enter this code to sign in' in body or 'Nhập mã này để đăng nhập' in body:
        logger.info("Trích xuất mã đăng nhập")
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
            elif "temporary-access-code" in link or "account/travel/verify" in link:
                handle_temporary_access_code(link, recipient_email, chat_id)

def process_cake_email(body):
    """Xử lý email từ Cake"""
    if 'Tài khoản Spend Account vừa tăng' in body:
        logger.info("Trích xuất chi tiết giao dịch")
        transaction_details = extract_transaction_details(body)
        if transaction_details:
            message = (
                f"Số tiền tăng: {transaction_details.get('amount_increased', 'Không rõ')}\n"
                f"Số dư hiện tại: {transaction_details.get('current_balance', 'Không rõ')}\n"
                f"Mô tả giao dịch: {transaction_details.get('description', 'Không rõ')}\n"
                f"Thời gian giao dịch: {transaction_details.get('time', 'Không rõ')}"
            )
            logger.info(message)
            send_telegram_message(TELEGRAM_ADMIN_UID, message)
    elif 'Tài khoản Spend Account vừa giảm' in body:
        logger.info("Trích xuất chi tiết giao dịch")
        transaction_details = extract_transaction_details(body)
        if transaction_details:
            message = (
                f"Số tiền giảm: {transaction_details.get('amount_decreased', 'Không rõ')}\n"
                f"Số dư hiện tại: {transaction_details.get('current_balance', 'Không rõ')}\n"
                f"Mô tả giao dịch: {transaction_details.get('description', 'Không rõ')}\n"
                f"Thời gian giao dịch: {transaction_details.get('time', 'Không rõ')}"
            )
            logger.info(message)
            send_telegram_message(TELEGRAM_ADMIN_UID, message)

def fetch_last_unseen_email():
    """Lấy nội dung của email chưa đọc cuối cùng từ hộp thư đến"""
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    try:
        mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
        mail.select("inbox")

        # Gộp danh sách email sender
        all_senders = []
        if ENABLE_NETFLIX_MODULE:
            all_senders.extend(NETFLIX_EMAIL_SENDERS)
        if ENABLE_CAKE_MODULE:
            all_senders.extend(CAKE_EMAIL_SENDERS)

        for sender in all_senders:
            _, email_ids = mail.search(None, f'(UNSEEN FROM "{sender}")')
            email_ids = email_ids[0].split()
            if email_ids:
                email_id = email_ids[-1]
                _, msg_data = mail.fetch(email_id, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                logger.info(f'Phát hiện email mới từ {sender}')
                recipient_email = email.utils.parseaddr(msg['To'])[1]
                subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))

                # Xác định loại email
                email_type = None
                if sender in NETFLIX_EMAIL_SENDERS and ENABLE_NETFLIX_MODULE:
                    email_type = 'netflix'
                elif sender in CAKE_EMAIL_SENDERS and ENABLE_CAKE_MODULE:
                    email_type = 'cake'

                # Xử lý theo loại email
                if email_type:
                    recipients = get_recipients_from_spreadsheet()
                    chat_id = None
                    if email_type == 'netflix':
                        for recipient in recipients:
                            if recipient['email'] == recipient_email:
                                chat_id = recipient['telegram_id']
                                break
                    elif email_type == 'cake':
                        chat_id = TELEGRAM_ADMIN_UID  # Gửi thông báo Cake cho admin

                    if chat_id:
                        if msg.is_multipart():
                            for part in msg.walk():
                                content_type = part.get_content_type()
                                if "text/plain" in content_type or "text/html" in content_type:
                                    body = part.get_payload(decode=True).decode()
                                    if email_type == 'netflix':
                                        process_netflix_email(body, recipient_email, chat_id)
                                    elif email_type == 'cake':
                                        process_cake_email(body)
                        else:
                            body = msg.get_payload(decode=True).decode()
                            if email_type == 'netflix':
                                process_netflix_email(body, recipient_email, chat_id)
                            elif email_type == 'cake':
                                process_cake_email(body)
    except Exception as e:
        message = f"Lỗi khi xử lý email: {e}"
        logger.error(message)
        send_telegram_message(TELEGRAM_ADMIN_UID, message)
    finally:
        mail.logout()

if __name__ == "__main__":
    logger.info(f'KHỞI TẠO THÀNH CÔNG - ver 2.0')
    logger.info(f'NETFLIX MODULE: {"BẬT" if ENABLE_NETFLIX_MODULE else "TẮT"}')
    logger.info(f'CAKE MODULE: {"BẬT" if ENABLE_CAKE_MODULE else "TẮT"}')
    while True:
        fetch_last_unseen_email()
        time.sleep(20)
