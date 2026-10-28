#!/usr/bin/env python3
"""
Shared Chrome startup for all scrapers.

Locally (Windows) Selenium finds Chrome on its own.
In the Docker container (Render/Railway) Chromium and Chromedriver come from
CHROME_BIN / CHROMEDRIVER_PATH, and LOW_MEMORY=1 enables memory-saving flags.
"""

import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# Render Free: 512 MB RAM / 0.1 CPU
LOW_MEMORY_ARGS = [
    '--disable-dev-shm-usage',
    '--renderer-process-limit=1',
    '--js-flags=--max-old-space-size=256',
    '--disable-background-networking',
    '--disable-default-apps',
    '--disable-sync',
    '--no-first-run',
    '--mute-audio',
    '--window-size=1280,900',
]

# A page load must never block a search forever
PAGE_LOAD_TIMEOUT_SECONDS = int(os.environ.get('PAGE_LOAD_TIMEOUT', '90'))


def create_driver(chrome_options: Options) -> webdriver.Chrome:
    """Start Chrome with the scraper's options plus container settings"""
    chrome_bin = os.environ.get('CHROME_BIN')
    driver_path = os.environ.get('CHROMEDRIVER_PATH')

    if chrome_bin:
        chrome_options.binary_location = chrome_bin

    if os.environ.get('LOW_MEMORY') == '1':
        for arg in LOW_MEMORY_ARGS:
            if arg not in chrome_options.arguments:
                chrome_options.add_argument(arg)

        # Don't load images (saves a lot of RAM) - image URLs are still in the HTML
        prefs = chrome_options.experimental_options.get('prefs', {})
        prefs.setdefault('profile.managed_default_content_settings.images', 2)
        chrome_options.add_experimental_option('prefs', prefs)

        # Don't wait for every tracking script - scrapers wait for elements themselves
        chrome_options.page_load_strategy = 'eager'

    print(f"🌐 Starte Chrome ({chrome_bin or 'Selenium Manager'})...", flush=True)
    start = time.time()

    if driver_path:
        driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
    else:
        driver = webdriver.Chrome(options=chrome_options)

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
    # Scripts read whole result lists at once - the default 30s is tight on 0.1 CPU
    driver.set_script_timeout(PAGE_LOAD_TIMEOUT_SECONDS)

    version = driver.capabilities.get('browserVersion', '?')
    print(f"✅ Chrome {version} gestartet ({time.time() - start:.1f}s)", flush=True)
    return driver
