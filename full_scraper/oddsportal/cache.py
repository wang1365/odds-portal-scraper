import pathlib
import pickle

from oddsportal import Season


class Cache(object):

    def __init__(self, season: Season):
        self.base = pathlib.Path('/data/odds')
        self.season = season
        if not self.base.exists():
            self.base.mkdir(parents=True, exist_ok=True)

    def gen_key(self, url):
        key = url.replace('https://www.oddsportal.com/', '')
        return f"{key.replace('/', '.')}-{len(self.season.urls)}"

    def get(self, url):
        f = self.base.joinpath(self.gen_key(url))
        if not f.exists():
            return []
        b = f.read_bytes()
        return pickle.loads(b)
    def set(self, url, obj):
        f = self.base.joinpath(self.gen_key(url))
        b = pickle.dumps(obj)
        f.write_bytes(b)
