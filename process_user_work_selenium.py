import glob
import gzip
import json
from lib2to3.pgen2 import driver
import requests
import random
import time
import tempfile
import os
import re
from datetime import datetime
import multiprocessing
import traceback
from io import BytesIO
import subprocess
from selenium import webdriver

from selenium.webdriver.common.by import By


work_server = os.environ.get(
    "WORK_SERVER", "https://archive-tiktok-worker.blazelight.dev"
)


def get_user_vids(driver, username, full_scrape=True):
    driver.get(f"https://www.tiktok.com/@{username}")

    # Scroll down a little
    last_height = driver.execute_script("return document.body.scrollHeight")
    if full_scrape:
        flag_complete = 0
        for _ in range(300):
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # Wait to load page
            time.sleep(1)

            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            print(f"{last_height=} {new_height=}")

            # Skip out if we don't have anything new for 3 cycles
            if new_height == last_height:
                flag_complete += 1
            else:
                flag_complete = 0
            if flag_complete >= 3:
                break

            last_height = new_height
    vid_ids = []
    #link_elements = driver.find_elements(By.TAG_NAME, "a")
    link_elements = driver.find_elements(By.XPATH, '//a[contains(@href, "/video/")]')

    t1 = time.time()
    for element in link_elements:
        if "/video/" in element.get_attribute("href"):
            vid_ids.append(element.get_attribute("href").split("/")[-1])
    t2 = time.time()

    print(f"Scrape complete. Link scrape took {t2-t1} seconds")
    return vid_ids


def worker():
    driver = webdriver.Chrome()
    driver.get("https://tiktok.com/@therock")
    time.sleep(10)

    while True:
        try:
            # Get work
            r = requests.post(
                work_server + "/get_work",
                json={"job_type": "user", "max_items": 1},
            )
            for user in r.json()["users"]:
                try:
                    start_time = time.time()
                    print(f"Processing {user}")

                    vid_ids = get_user_vids(driver, user)

                    t_before_req = time.time()
                    res = requests.post(
                        work_server + "/add_work",
                        json={"video_ids": vid_ids, "priority": "requested_user"},
                    )
                    end_time = time.time()
                    print(
                        f"\r{user=}: Processed with {res=} in {end_time - start_time} seconds. {res.text}. Took {end_time - t_before_req} seconds to send request"
                        + " " * 30
                    )
                except Exception as e:
                    print(traceback.format_exc())
                    time.sleep(5)
        except Exception as e:
            print(traceback.format_exc())
            time.sleep(5)


if __name__ == "__main__":

    worker()
