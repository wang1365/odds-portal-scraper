"""
scraper.py

Logic for the overall Odds Portal scraping utility focused on scraping

"""
import json
import pickle

from .models import Game
from .models import Season
from pyquery import PyQuery as pyquery
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import requests

import datetime
import logging
import os
import re
import time
import hashlib
import pathlib

logger = logging.getLogger(__name__)

class Cache(object):

    def __init__(self):
        self.base = pathlib.Path('/data/odds')
        if not self.base.exists():
            self.base.mkdir(parents=True, exist_ok=True)

    def get(self, url):
        key = hashlib.md5(url.encode()).hexdigest()
        f = self.base.joinpath(key)
        if not f.exists():
            return []
        # return f.read_text(encoding='utf8')
        b = f.read_bytes()
        return pickle.loads(b)
    def set(self, url, obj):
        key = hashlib.md5(url.encode()).hexdigest()
        f = self.base.joinpath(key)
        b = pickle.dumps(obj)
        f.write_bytes(b)

class Scraper(object):
    """
    A class to scrape/parse match results from oddsportal.com website.
    Makes use of Selenium and BeautifulSoup modules.
    """

    def __init__(self, wait_on_page_load=3):
        """
        Constructor
        """
        self.base_url = 'https://www.oddsportal.com'
        self.wait_on_page_load = wait_on_page_load
        if wait_on_page_load == None:
            self.wait_on_page_load = 3
        self.options = webdriver.ChromeOptions()
        self.options.add_argument('headless')

        self.driver = webdriver.Chrome('./chromedriver/chromedriver', chrome_options=self.options)
        self.cache = Cache()

        logger.info('Chrome browser opened in headless mode')

        # exception when no driver created

    def go_to_link(self, link):
        """
        returns True if no error
        False whe page not found
        """
        self.driver.get(link)
        try:
            # if no Login button -> page not found
            # self.driver.find_element_by_css_selector('.button-dark')
            self.driver.find_element_by_css_selector('.loginModalBtn')
        except NoSuchElementException:
            logger.warning('Problem with link, could not find Login button - %s', link)
            return False
        # Workaround for ajax page loading issue
        time.sleep(self.wait_on_page_load)
        return True

    def get_html_source(self):
        return self.driver.page_source

    def close_browser(self):
        time.sleep(5)
        try:
            self.driver.quit()
            logger.info('Browser closed')
        except WebDriverException:
            logger.warning('WebDriverException on closing browser - maybe closed?')

    def populate_games_into_season(self, season):
        """
        Params:
            season (Season) with urls but not games populated, to modify
        """
        for url in season.urls:
            cached_games = self.cache.get(url)
            if cached_games:
                season.games = cached_games
                continue

            self.go_to_link(url)
            html_source = self.get_html_source()
            html_querying = pyquery(html_source)
            # Check if the page says "No data available"
            no_data_div = html_querying.find('div.message-info > ul > li > div.cms')
            if no_data_div != None and no_data_div.text() == 'No data available':
                # Yes, found "No data available"
                logger.warning('Found "No data available", skipping %s', url)
                continue
            retrieval_time_for_reference = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            scripts = html_querying.find('script')
            url_param_txt = [s.text for s in scripts if s.text and 'pageOut' in s.text][0]
            url_param_txt = url_param_txt.split("'")[1]
            url_param = json.loads(url_param_txt)
            url_pattern = f'https://www.oddsportal.com/ajax-sport-country-tournament-archive_/{url_param["sid"]}/{url_param["id"]}/X0/1/0/page/%s'
            headers = {
                'authority': 'www.oddsportal.com',
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'content-type': 'application/json',
                'referer': 'https://www.oddsportal.com/basketball/usa/nba/results/',
                'sec-ch-ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': "Windows",
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'x-requested-with': 'XMLHttpRequest',
            }
            session = requests.Session()

            page_url = url_pattern % url.split('/')[-1]
            ret = session.get(page_url, headers=headers)

            logger.info("==> Ajax [%s] request result: %s", page_url, ret.text)
            if ret.status_code != 200:
                print('Ajax request failed: %s' + url)
                logger.warning('Ajax request failed: %s', url)
                continue
            if 'globals.jsonpCallback' in ret.text:
                logger.warning('Ajax request failed: %s', ret.text)
                logger.warning('Ajax request failed: %s', page_url)
                continue

            def parse_game(response):
                result = json.loads(response.text)
                items = result['d']['rows']
                games = []
                for item in items:
                    game = Game()
                    games.append(game)

                    game.game_datetime = time.strftime("%Y-%m-%d %H:%M:%S",
                                                       time.localtime(item['date-start-timestamp']))
                    game.retrieval_datetime = retrieval_time_for_reference
                    game.retrieval_url = url
                    game.num_possible_outcomes = season.possible_outcomes
                    game.team_home = item['home-name']
                    game.team_away = item['away-name']
                    game.game_url = self.base_url + item['url']

                    sh, sa = item['homeResult'], item['awayResult']
                    game.score_home = int(sh) if sh else None
                    game.score_away = int(sa) if sa else None

                    if item['home-winner'] == 'win':
                        game.outcome = 'HOME'
                    elif item['home-winner'] == 'lost':
                        game.outcome = 'AWAY'
                    else:
                        game.outcome = 'DRAW'
                    odds = item['odds']
                    if odds:
                        game.odds_home = odds[0]['avgOdds']
                        game.odds_away = odds[1]['avgOdds']
                        game.odds_draw = None if len(odds) < 3 else odds[2]['avgOdds']

                return games

            try:
                games = parse_game(ret)
                if games:
                    self.cache.set(url, games)
                    for game in games:
                        season.add_game(game)
            except Exception as e:
                logger.error('!!! Parse game failed', e)


if __name__ == '__main__':
    s = Scraper()
    s.go_to_link('https://www.oddsportal.com/basketball/usa/nba/results/#/page/27/')
    s.close_browser()
