import glob
import gzip
import json
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

from bs4 import BeautifulSoup


work_server = os.environ.get(
    "WORK_SERVER", "https://archive-tiktok-worker.blazelight.dev"
)

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Connection": "keep-alive",
}

r_cookies = {}


def refresh_cookies():
    global r_cookies
    print("Grabbing cookies...")
    driver = webdriver.Chrome()
    driver.get("https://tiktok.com")
    cookies = driver.get_cookies()
    for cookie in cookies:
        r_cookies[cookie["name"]] = cookie["value"]
    driver.close()


def get_user_vids(username):

    # This is a hack, curl doesn't flag detection at tiktok
    html_out = subprocess.run(
        [
            "/usr/bin/curl",
            f"https://www.tiktok.com/@{username}",
            "-H",
            "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:103.0) Gecko/20100101 Firefox/103.0",
        ],
        capture_output=True,
    ).stdout
    try:

        soup = BeautifulSoup(html_out, "html.parser")
        tt_script = soup.find("script", attrs={"id": "SIGI_STATE"})
        tt_json = json.loads(tt_script.string)
        video_ids = tt_json["ItemList"]["user-post"]["list"]
        return video_ids
    except:
        print(html_out)
        print(tt_script)
        print(traceback.format_exc())
        time.sleep(60 * 60 * 15)


def worker():
    refresh_cookies()

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

                    try:
                        vid_ids = get_user_vids(user)
                    except AttributeError:
                        refresh_cookies()
                        vid_ids = get_user_vids(user)

                    t_before_req = time.time()
                    res = requests.post(
                        work_server + "/add_work",
                        json={"video_ids": vid_ids, "priority": "requested_user"},
                    )
                    end_time = time.time()
                    print(
                        f"\r{user=}: Processed with {res=} in {end_time - start_time} seconds. {res.text}. Took {t_before_req - start_time} seconds to send request"
                        + " " * 30
                    )
                    time.sleep(15)
                except Exception as e:
                    print(traceback.format_exc())
                    time.sleep(5)
        except Exception as e:
            print(traceback.format_exc())
            time.sleep(5)


if __name__ == "__main__":

    worker()
