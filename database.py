import tvshows.manager as manager
from tvshows.exceptions import TVShowsDBError, TVShowsDBErrorInteractive
from pydblite import Base
from datetime import datetime
from itertools import groupby
from operator import itemgetter


class DBManager:

    has_changes = False
    list_template = '{:<7}  {:<9}  {:<27}  {:<27}  {}'
    topics_sort_fields = ['id', 'tracker', 'last_update',
                          'next_update', 'title']

    def __init__(self):
        self.credentials = self.open_db('credentials')
        self.topics = self.open_db('topics')
        self.now = datetime.now()

    def open_db(self, db_name):
        _db = Base(manager.app_dir.joinpath('db', f'{db_name}.pdl'))
        if _db.exists():
            return _db.open()
        raise TVShowsDBError(f'Couldn\'t connect to DB: {db_name}')

    def get_cookies(self, tracker):
        return self.credentials(tracker=tracker)[0]['cookies']

    def get_auth_params(self, tracker):
        return self.credentials(tracker=tracker)[0]['auth_params']

    def get_topic(self, field):
        try:
            if field.isdigit():
                return self.topics(id=field)[0]
            else:
                for topic in self.topics:
                    if field.upper() in topic['title'].upper():
                        return topic
                raise IndexError
        except IndexError:
            raise TVShowsDBErrorInteractive(
                f'Couldn\'t find topic with: {field}')

    def get_topics(self, force):
        return groupby(
            (self.topics if force else self.topics('next_update') < self.now),
            key=lambda x: x['tracker'])

    def check_sort_field(self, field):
        if field not in self.topics_sort_fields:
            raise TVShowsDBErrorInteractive(
                (f'Couldn\'t sort by field: {field}.\n'
                 f'Must be one of: {", ".join(self.topics_sort_fields)}'))

    def get_list_topics(self, sortby):
        if not self.topics:
            raise TVShowsDBErrorInteractive(
                (f'There are no topics to track right now.\n'
                 f'Type `tvshows --help` to learn how to add one'))

        return sorted(self.topics, key=itemgetter(sortby), reverse=True)

    def format_list_header(self):
        return self.list_template.format(
            *[i.upper() for i in self.topics_sort_fields])

    def format_list_item(self, item):
        return self.list_template.format(
            item['id'],
            item['tracker'],
            item['last_update'].strftime('%d.%m.%y %H:%M, %A'),
            item['next_update'].strftime('%d.%m.%y %H:%M, %A'),
            item['title'])
