"""Module providing confirmation for Netflix Household update"""
import imaplib
import email
import re
import time
import os
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
            except TimeoutException as exception:
                print("Error:", exception)

            time.sleep(3)
            driver.quit()


def fetch_last_unseen_email():
    """Gets body of last unseen mail from inbox"""
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP)
    mail.login(EMAIL_LOGIN, EMAIL_PASSWORD)
    mail.select("inbox")
    print(mail)
    _, email_ids = mail.search(None, '(UNSEEN FROM ' + NETFLIX_EMAIL_SENDER + ')')
    tmp, data = mail.search(None, 'ALL')
    for num in data[0].split():
    	tmp, data = mail.fetch(num, '(RFC822)')
    	print('Message: {0}\n'.format(num))
    	pprint.pprint(data[0][1])
    	break
    print(mail.search(None, 'ALL')
    
    mail.logout()


if __name__ == "__main__":
    while True:
        fetch_last_unseen_email()
        time.sleep(20)
