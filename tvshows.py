#!/usr/bin/env python3

import tvshows.trackers as trackers
import tvshows.manager as manager
from tvshows.database import DBManager
from tvshows.exceptions import TVShowsError, TVShowsErrorInteractive
from ucli import ucli


def get_tracker_instance(tracker_name, db_obj):
    return getattr(trackers, tracker_name.capitalize())(tracker_name, db_obj)


def with_db(action):
    def wrapper(args):
        try:
            db = DBManager()
            action(args, db)
        except TVShowsError as message:
            manager.event_log(message, log_level='exception')
        except TVShowsErrorInteractive as message:
            ucli.info(message)
        except KeyboardInterrupt:
            ucli.drop('Interrupted by user')
        finally:
            # Commit changes to DB even if exeption occured
            if db.has_changes:
                db.topics.commit()
    return wrapper


@with_db
def add(args, db):
    ucli.info('Adding the new topic to tracking')
    tracker = trackers.Tracker(None, db)
    topic = tracker.add(args)
    tracker = get_tracker_instance(topic['tracker'], db)
    tracker.update(topic)


@with_db
def update(args, db):
    if args['TOPIC']:
        topic = db.get_topic(args['TOPIC'])
        ucli.info('Updating specified topic:', topic['title'])
        tracker = get_tracker_instance(topic['tracker'], db)
        tracker.update(topic)
    else:
        ucli.info(
            f"Updating {'all the' if args['all'] else 'scheduled'} topics")
        for tracker_name, topics in db.get_topics(args['all']):
            tracker = get_tracker_instance(tracker_name, db)
            for topic in topics:
                tracker.update(topic)


@with_db
def list(args, db):
    db.check_sort_field(args['--sortby'])
    topics = db.get_list_topics(args['--sortby'])

    from locale import setlocale, LC_TIME
    setlocale(LC_TIME, 'en_US.UTF-8')

    ucli.header(db.format_list_header())
    for topic in topics:
        print(db.format_list_item(topic))
