import re
import requests
# import socks
# import socket
import hashlib
import tvshows.manager as manager
from bencoding import bdecode, bencode
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from tvshows.database import DBManager
from tvshows.exceptions import TVShowsTrackerError, TVShowsSkipTopicError
from locale import setlocale, LC_TIME
from ucli import ucli


# socks.set_default_proxy(socks.SOCKS5, 'localhost', 9050)
# socket.socket = socks.socksocket
setlocale(LC_TIME, 'ru_RU.UTF-8')


class Tracker:

    LINK_REGEX = re.compile(r'(?<=\b)(\s|\s\[.*\]\s)(?=\()')
    TITLE_LINK_REGEX = re.compile(r'\[\w\]\s(.*)\s\(')
    URL_REGEX = re.compile(r':\/\/(.*?)\..*\?(?:t|id)\=(\d+)')

    def __init__(self, name, db_obj: DBManager):
        self.NAME = name
        self.session = requests.Session()
        self.session.proxies = {'http':  'socks5h://127.0.0.1:9050',
                                'https': 'socks5h://127.0.0.1:9050'}
        self.db = db_obj

        if not name:
            return

        _cookies = self.db.get_cookies(self.NAME)
        if _cookies:
            self.session.cookies.update(_cookies)
        else:
            self.auth(self.db.get_auth_params(self.NAME))

    def auth(self, params):
        auth_response = self.session.post(self.LOGIN_URL, params)
        if auth_response.url.startswith(self.LOGIN_URL):
            raise TVShowsTrackerError(
                f'Invalid login or password. Tracker: [{self.NAME}]')
        else:
            self.db.credentials.update(
                tracker=self.NAME, cookies=self.session.cookies.get_dict())

    def get_web_page(self):
        response = self.session.get(f"{self.PAGE_URL}{self.topic['id']}")
        if not response.ok:
            raise TVShowsTrackerError(
                f"Couldn\'t connect to tracker: {self.topic['tracker']}")
        return BeautifulSoup(response.text, 'html.parser')

    def get_info_hash(self):
        torrent_bytes = self.session.get(
            f"{self.DOWNLOAD_URL}{self.topic['id']}")
        if not torrent_bytes.ok:
            raise TVShowsSkipTopicError(
                'Couldn\t get torrent file', self.topic['title'])
            return

        torrent_bytes = torrent_bytes.content
        _decoded = bdecode(torrent_bytes)[b'info']
        info_hash = hashlib.sha1(bencode(_decoded)).hexdigest().upper()

        if not info_hash:
            raise TVShowsSkipTopicError(
                'Couldn\t calculate torrent hash', self.topic['title'])
            return

        if info_hash == self.topic['info_hash']:
            raise TVShowsSkipTopicError(
                'Hashes are equal', self.topic['title'])
            return

        manager.update_file(self.topic, torrent_bytes)
        return info_hash

    def try_get_datetime(self, web_page):
        try:
            return self.get_datetime(web_page)
        except AttributeError:
            raise TVShowsSkipTopicError(
                'Couldn\'t find datetime soup', self.topic['title'])
            return
        except ValueError:
            raise TVShowsSkipTopicError(
                'Couldn\'t parse datetime string', self.topic['title'])
            return

    def get_episodes_range(self, web_page):
        try:
            return (self.EPISODES_RANGE_REGEX
                    .search(web_page.h1.a.text).groups())
        except AttributeError:
            return

    def correct_link_name(self, ep_range):
        try:
            return manager.rename_link(
                self.topic['link'],
                self.LINK_REGEX.sub(
                    f' [{ep_range[0]}\u2215{ep_range[1]}] ',
                    self.topic['link'].name))
        except TypeError:
            return

    def stop_tracking(self, ep_range):
        try:
            if ep_range[1].isdigit() and int(ep_range[0]) == int(ep_range[1]):
                manager.event_log(f"Stop tracking: {self.topic['title']}")
                return True
        except TypeError:
            return False

    def make_schedule(self, web_page_update, this_week):
        delta = {'days': 6, 'hours': 22}
        if self.topic['air'] == 'daily':
            delta['days'] = 0
            this_week += 1
            _weekday = web_page_update.isoweekday()
            # If this topic updated four times this week
            if (this_week == 4
                    # Or It's Friday
                    or _weekday == 5
                    # Or It's Thursday late night
                    or (_weekday == 4 and web_page_update.hour > 21)):
                delta['days'] = 7 - _weekday
                this_week = 0
        return (web_page_update + timedelta(**delta), this_week)

    def add(self, args):
        _fields = {}

        if 'link' in args:
            try:
                args['title'] = self.TITLE_LINK_REGEX.search(
                    args['link']).group(1)
            except AttributeError:
                raise TVShowsTrackerError((
                    f"Couldn't find {self.TITLE_LINK_REGEX} pattern "
                    f"in {args['link']} string"))
        for field_name in ['topic URL', 'title', 'air', 'link']:
            if field_name == 'air':
                _candidates = ['daily', 'weekly']
                ucli.header('Air:')
                ucli.print_candidates(_candidates)
                _fields['air'] = ucli.parse_selection(_candidates)
                continue
            _field = ucli.get_field(
                field_name,
                prefill=args[field_name] if field_name in args else False,
                necessary=True)
            if field_name == 'topic URL':
                _fields['tracker'], _fields['id'] = self.URL_REGEX.search(
                    _field).groups()
                continue
            if field_name == 'link':
                _fields['link'] = manager.get_path(_field)
                continue
            _fields[field_name] = _field

        topic = self.db.topics.insert(**_fields)
        return self.db.topics[topic]

    def update(self, topic):

        self.topic = topic

        web_page = self.get_web_page()
        web_page_update = self.try_get_datetime(web_page)
        if web_page_update <= topic['last_update']:
            return

        info_hash = self.get_info_hash()
        if not info_hash:
            return

        ep_range = self.get_episodes_range(web_page)
        link_name = self.correct_link_name(ep_range)

        if self.stop_tracking(ep_range):
            self.db.topics.delete(topic)
        else:
            _nu, _tw = self.make_schedule(web_page_update, topic['this_week'])
            self.db.topics.update(
                topic,
                info_hash=info_hash,
                last_update=web_page_update,
                next_update=_nu,
                this_week=_tw,
                link=link_name)

        self.db.has_changes = True


class Rutracker(Tracker):

    LOGIN_URL = 'http://rutracker.org/forum/login.php'
    PAGE_URL = 'http://rutracker.org/forum/viewtopic.php?t='
    DOWNLOAD_URL = 'http://rutracker.org/forum/dl.php?t='
    EPISODES_RANGE_REGEX = re.compile(
        r'Серии:? (?:\d+-)?(\d+) (?:из |\()(\d+|\?+)')

    def get_datetime(self, soup):
        return datetime.strptime(
            (soup.find('table', 'attach bordered med')
                 .find_all('tr', limit=2)[1]
                 # .find('li').text),  # .replace('Май', 'Мая') Dirty hack
                 .find('li').text).replace('Май', 'Мая'),
            '%d-%b-%y %H:%M')


class Kinozal(Tracker):

    LOGIN_URL = 'http://kinozal.tv/takelogin.php'
    PAGE_URL = 'http://kinozal.tv/details.php?id='
    DOWNLOAD_URL = 'http://dl.kinozal.tv/download.php?id='
    EPISODES_RANGE_REGEX = re.compile(r'\d+-(\d+) серии из (\d+|\?+)')
    LAST_UPDATE_REGEX = re.compile(r'(\d+\s\w+\s\d+|\w+)\sв\s(\d+):(\d+)')

    def get_datetime(self, soup):
        _relative_days = {u'сегодня': 0, u'вчера': -1}

        try:
            datetime_soup = (soup.find('div', 'mn1_content')
                             .find('div', 'bx1 justify')
                             .find('b', recursive=False).string)
        except AttributeError:
            datetime_soup = (soup.find('div', 'mn1_menu')
                             .find('ul', 'men w200')
                             .find_all('li')[-1]
                             .find('span', 'floatright green n').string)

        _date, _hours, _minutes = (self.LAST_UPDATE_REGEX
                                       .search(datetime_soup).groups())

        if _date in _relative_days:
            return (self.db.now.replace(
                hour=int(_hours), minute=int(_minutes))
                + timedelta(days=_relative_days[_date]))
        else:
            return datetime.strptime(
                f'{_date} {_hours}:{_minutes}', '%d %B %Y %H:%M')
