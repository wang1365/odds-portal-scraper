"""
crawler.py

Logic for the overall Odds Portal scraping utility focused on crawling

"""


from .models import Season
from pyquery import PyQuery as pyquery
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import WebDriverException

import logging
import time


logger = logging.getLogger(__name__)


class Crawler(object):
    """
    A class to crawl links from oddsportal.com website.
    Makes use of Selenium and BeautifulSoup modules.
    """
    WAIT_TIME = 3  # max waiting time for a page to load
    
    def __init__(self, driver=None, wait_on_page_load=3):
        """
        Constructor
        """
        if driver:
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
            self.driver.maximize_window()
            logger.info('Chrome browser opened in headless mode')
        
        # exception when no driver created
    def get_driver(self):
        return self.driver

    def go_to_link(self, link, wait=0, sleep_time=0, check_element='login'):
        """
        returns True if no error
        False whe page not found
        """
        self.driver.implicitly_wait(wait if wait > 0 else self.wait_on_page_load)
        self.driver.set_page_load_timeout(15)
        self.driver.set_script_timeout(15)
        try:
            self.driver.get(link)
        except:
            logger.info('driver load url not finished and timeout')
            self.driver.execute_script("window.stop()")
        time.sleep(sleep_time)
        logger.info('Crawler go to link: %s', link)
        # Workaround for ajax page loading issue
        try:
            # If no Login button, page not found
            # self.driver.find_element_by_css_selector('.button-dark')
            # self.driver.find_element_by_css_selector('.loginModalBtn')
            if check_element == 'login':
                self.driver.find_element_by_css_selector('.loginModalBtn')
            else:
                self.driver.find_element_by_css_selector('.pagination-link')
        except NoSuchElementException:
            logger.warning('Problem with link, crawler could not find Login button - %s', link)
            print('Page source:\n', self.driver.page_source)
            return False
        return True

    def get_html_source(self):
        return self.driver.page_source
    
    def close_browser(self):
        time.sleep(2)
        try:
            self.driver.quit()
            logger.info('Browser closed')
        except WebDriverException:
            logger.warning('WebDriverException on closing browser - maybe closed?')

    def get_seasons_for_league(self, main_league_results_url):
        """
        Params:
            (str) main_league_results_url e.g. https://www.oddsportal.com/hockey/usa/nhl/results/

        Returns:
            (list) urls to each season for given league
        """
        seasons = []
        logger.info('Getting all seasons for league via %s', main_league_results_url)
        if not self.go_to_link(main_league_results_url, wait=15, sleep_time=5):
            logger.warning('League results URL loaded might failed %s', main_league_results_url)
            # Going to send back empty list so this is not processed further
            # return seasons
        html_source = self.get_html_source()
        html_querying = pyquery(html_source)
        # season_links = html_querying.find('div.main-menu2.main-menu-gray > ul.main-filter > li > span > strong > a')
        season_links = html_querying.find('#app > div > div.w-full > div > main > div.relative.w-full.bg-white-main > div.flex.flex-col > div > div.flex.flex-wrap > a')
        logger.info('Extracted links to %d seasons', len(season_links))
        for i, season_link in enumerate(season_links):
            this_season = Season(season_link.text)
            # Start the Season's list of URLs with just the root one
            # this_season_url = self.base_url + season_link.attrib['href']
            this_season_url = season_link.attrib['href']
            this_season.urls.append(this_season_url)
            this_season.index = i
            seasons.append(this_season)
        return seasons
    
    def fill_in_season_pagination_links(self, season):
        """
        Params:
            (Season) object with just one entry in its urls field, to be modified
        """
        first_url_in_season = season.urls[0]
        self.go_to_link(first_url_in_season, wait=60, sleep_time=5, check_element='pagination')
        html_source = self.get_html_source()
        html_querying = pyquery(html_source)
        # Check if the page says "No data available"
        no_data_div = html_querying.find('div.message-info > ul > li > div.cms')
        if no_data_div != None and no_data_div.text() == 'No data available':
            # Yes, found "No data available"
            logger.warning('Found "No data available", skipping %s', first_url_in_season)
            return
        # Just need to locate the final pagination tag
        pagination_links = html_querying.find('a.pagination-link')
        if pagination_links:
            page_count = int(pagination_links[-2].attrib['data-number'])
            season.urls = [f'{first_url_in_season}#/page/{i + 1}' for i in range(page_count)]
            if page_count == 1:
                logger.info('Check page source: \n %s', html_source)

