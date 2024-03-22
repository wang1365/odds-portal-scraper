"""
scraper.py

Logic for the overall Odds Portal scraping utility focused on scraping

"""
import json
import logging
import pathlib
import pickle
import random
import time

import requests
from pyquery import PyQuery as pyquery
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException

from oddsportal.cache import Cache
from .models import Game

logger = logging.getLogger(__name__)

class Scraper(object):
    """
    A class to scrape/parse match results from oddsportal.com website.
    Makes use of Selenium and BeautifulSoup modules.
    """

    def __init__(self, wait_on_page_load=3, driver=None):
        """
        Constructor
        """
        if not driver:
            self.driver = driver
        else:
            self.base_url = 'https://www.oddsportal.com'
            self.wait_on_page_load = wait_on_page_load
            if wait_on_page_load == None:
                self.wait_on_page_load = 3
            self.options = webdriver.ChromeOptions()
            self.options.add_argument('--headless')
            self.options.add_argument('--no-sandbox')
            self.options.add_argument('--disable-gpu')

            self.driver = webdriver.Chrome('./chromedriver/chromedriver', chrome_options=self.options)
        self.session = requests.Session()
        self.headers = {
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

        logger.info('Chrome browser opened in headless mode')

        # exception when no driver created

    def request(self, url, timeout=5):
        return self.session.get(url, headers=self.headers, timeout=timeout)

    def go_to_link(self, link, sleep_time=0):
        """
        returns True if no error
        False whe page not found
        """

        self.driver.implicitly_wait(3)
        self.driver.set_page_load_timeout(15)
        self.driver.set_script_timeout(15)
        try:
            self.driver.get(link)
            time.sleep(sleep_time)
        except:
            logger.info('driver load url not finished and timeout')
        logger.info('Go to link: %s', link)
        try:
            # if no Login button -> page not found
            # self.driver.find_element_by_css_selector('.button-dark')
            self.driver.find_element_by_css_selector('.loginModalBtn')
            # self.driver.find_element_by_partial_link_text('MY LEAGUES')
        except NoSuchElementException:
            logger.warning('Problem with link, scraper could not find Login button - %s', link)
            return False
        # Workaround for ajax page loading issue
        # time.sleep(self.wait_on_page_load)
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
        logger.info('season [%s] url count: %s', season.name, len(season.urls))
        cache = Cache(season)
        use_cache = season.index != 0

        for url in season.urls:
            if use_cache:
                cached_games = cache.get(url)
                if cached_games:
                    season.games = cached_games
                    logger.info('Load url:[%s] from cache', url)
                    continue

            st = random.randint(3, 6)
            self.go_to_link(url, sleep_time=st)
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
            url_param_dom = [s.text for s in scripts if s.text and 'pageOut' in s.text]
            if not url_param_dom:
                continue
            url_param_txt = url_param_dom[0]
            url_param_txt = url_param_txt.split("'")[1]
            url_param = json.loads(url_param_txt)
            url_pattern = f'https://www.oddsportal.com/ajax-sport-country-tournament-archive_/{url_param["sid"]}/{url_param["id"]}/X0/1/0/page/%s'

            page_url = url_pattern % url.split('/')[-1]
            ret = self.request(url_pattern % url.split('/')[-1])

            logger.info("==> Ajax [%s] request success, sleep %s", page_url, st)
            if ret.status_code != 200:
                print('Ajax request failed: %s' + url)
                logger.warning('Ajax request failed: %s', url)
                continue
            if 'globals.jsonpCallback' in ret.text:
                logger.warning('Ajax [%s] request failed: %s', page_url, ret.text)
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
                    cache.set(url, games)
                    for game in games:
                        season.add_game(game)
            except Exception as e:
                logger.error('!!! Parse game failed', e)


if __name__ == '__main__':
    s = Scraper()
    s.go_to_link('https://www.oddsportal.com/basketball/usa/nba/results/#/page/27/')
    s.close_browser()
