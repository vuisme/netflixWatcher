"""Module providing confirmation for Netflix Household update"""
import imaplib
import email
import re
import time
import os
import pprint
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


def extract_links(text):
    """Finds all https links"""
    url_pattern = r'https?://\S+'
    urls = re.findall(url_pattern, text)
    return urls


def extract_codes(text):
    code = re.search(r'(?<=Enter this code to sign in\s)\d{4}', text)
    return codes


def open_link_with_selenium(body):
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
                print('Đã xác thực thành công')
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
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if "text/plain" in content_type:
                    body = part.get_payload(decode=True).decode()
                    bodyraw = part.get_payload()
                    print(bodyraw)
                    otpcode = extract_codes(body)
                    print(otpcode)
                    open_link_with_selenium(body)
        else:
            body = msg.get_payload(decode=True).decode()
            print('body')
            print(body)
            open_link_with_selenium(body)

    mail.logout()


if __name__ == "__main__":
    while True:
        fetch_last_unseen_email()
        time.sleep(20)
