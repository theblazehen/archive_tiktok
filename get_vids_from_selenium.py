from seleniumwire import webdriver
from selenium.webdriver.common.keys import Keys
import json
import gzip
import time
import redis
import requests


def request_interceptor(request):
    if (
        "/video/tos/" in request.url
        or ".jpeg" in request.url
        or "x-expires" in request.url
    ):
        request.abort()


def response_interceptor(request, response):
    if "api/recommend/item_list" in request.url:
        plaintext_response = gzip.decompress(response.body).decode("utf-8")
        ret_data = json.loads(plaintext_response)
        ids = [x["id"] for x in ret_data["itemList"]]
        r = requests.post(
            "https://archive-tiktok-worker.blazelight.dev/add_work",
            json={"ids": ids},
        )
        print(r.text)


options = {"request_storage": "memory", "request_storage_max_size": 100}

driver = webdriver.Chrome(seleniumwire_options=options)
driver.request_interceptor = request_interceptor
driver.response_interceptor = response_interceptor
driver.get("https://tiktok.com")
input("Log in and hit enter")

last_height = driver.execute_script("return document.body.scrollHeight")
while True:
    try:
        driver.get("https://tiktok.com")
        for _ in range(600):
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            time.sleep(3)

            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    except:
        time.sleep(10)
