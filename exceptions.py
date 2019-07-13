class TVShowsError(Exception):
    pass


class TVShowsErrorInteractive(Exception):
    pass


class TVShowsDBError(TVShowsError):
    pass


class TVShowsDBErrorInteractive(TVShowsErrorInteractive):
    pass


class TVShowsTrackerError(TVShowsError):
    pass


class TVShowsSkipTopicError(TVShowsError):
    def __init__(self, message, title):
        self.message = message
        self.title = title

    def __str__(self):
        return f'{self.message}. Skip topic: {self.title}'
