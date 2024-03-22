import pathlib
import pickle


class Cache(object):

    def __init__(self):
        self.base = pathlib.Path('/data/odds')
        if not self.base.exists():
            self.base.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def gen_key(url):
        key = url.replace('https://www.oddsportal.com/', '')
        return key.replace('/', '.')

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
