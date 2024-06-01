"""Module providing confirmation for Netflix Household update"""
import imaplib
import email
import re
import time
import os
import requests
from selenium import webdriver
from selenium.webdriver import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

EMAIL_IMAP = os.environ['EMAIL_IMAP']
EMAIL_LOGIN = os.environ['EMAIL_LOGIN']
EMAIL_PASSWORD = os.environ['EMAIL_PASSWORD']
NETFLIX_EMAIL_SENDER = os.environ['NETFLIX_EMAIL_SENDER']
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']


def send_telegram_message(message):
    """Sends a message to the Telegram group"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("Gửi tin nhắn Telegram thành công")
    else:
        print("Gửi tin nhắn Telegram thất bại")


def extract_links(text):
    """Finds all https links"""
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls


def extract_codes(text):
    """Finds the 4-digit code after 'Enter this code to sign in'"""
    # Loại bỏ các ký tự xuống dòng và khoảng trắng thừa
    text = re.sub(r'\s+', ' ', text)
    codes = re.search(r'(?<=Enter this code to sign in )\d{4}', text)
    if codes:
        return codes.group()
    return None


def mask_email(email_address):
    """Masks the email address to show only the first 2 and last 5 characters"""
    username, domain = email_address.split('@')
    if len(username) > 7:
        masked_username = username[:2] + '****' + username[-1:]
    else:
        masked_username = username[:2] + '****'
    masked_email = masked_username + '@' + domain
    return masked_email


def open_link_with_selenium(body, recipient_email):
    """Opens Selenium and clicks a button to confirm connection"""
    links = extract_links(body)
    for link in links:
        if "update-primary-location" in link:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            driver = webdriver.Remote(
                command_executor='http://netflix_watcher_selenium:4444/wd/hub',
                options=options
            )

            driver.get(link)
            time.sleep(3)

            try:
                element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.CSS_SELECTOR, '[data-uia="set-primary-location-action"]'
                    ))
                )

                element.click()
                masked_email = mask_email(recipient_email)
                message = f'Đã tự động cập nhật Hộ Gia Đình thành công cho {masked_email}'
                print(message)
                send_telegram_message(message)
            except TimeoutException as exception:
                print("Error:", exception)

            time.sleep(3)
            driver.quit()


def fetch_last_unseen_email():
    """Gets body of last unseen mail from inbox"""
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
    mail.select("inbox")
    _, email_ids = mail.search(None, '(UNSEEN FROM ' + NETFLIX_EMAIL_SENDER + ')')
    email_ids = email_ids[0].split()
    if email_ids:
        email_id = email_ids[-1]
        _, msg_data = mail.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        print('Phát hiện yêu cầu xác thực mới')

        # Lấy địa chỉ email người nhận
        recipient_email = email.utils.parseaddr(msg['To'])[1]

        # Kiểm tra tiêu đề của email
        subject = str(email.header.make_header(email.header.decode_header(msg['Subject'])))
        if 'sign-in code' in subject:
            print('Email chứa tiêu đề "Sign-in code"')
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if "text/plain" in content_type:
                        body = part.get_payload(decode=True).decode()
                        otpcode = extract_codes(body)
                        if otpcode:
                            masked_email = mask_email(recipient_email)
                            message = f'Mã OTP cho {masked_email} là: {otpcode}'
                            print(message)
                            send_telegram_message(message)
            else:
                body = msg.get_payload(decode=True).decode()
                otpcode = extract_codes(body)
                if otpcode:
                    masked_email = mask_email(recipient_email)
                    message = f'Mã OTP cho {masked_email} là: {otpcode}'
                    print(message)
                    send_telegram_message(message)
        else:
            print('Email không chứa tiêu đề "Sign-in code", trích xuất liên kết')
            if msg.is_multipart():
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if "text/plain" in content_type:
                        body = part.get_payload(decode=True).decode()
                        open_link_with_selenium(body, recipient_email)
            else:
                body = msg.get_payload(decode=True).decode()
                open_link_with_selenium(body, recipient_email)

    mail.logout()


if __name__ == "__main__":
    while True:
        fetch_last_unseen_email()
        time.sleep(20)
