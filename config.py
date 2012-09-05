import ConfigParser

class Config(object):
    def __init__(self, filename):
        self.config = ConfigParser.RawConfigParser()
        self.config.read(filename)

    def get(self, section, key, default=None):
        try:
            return self.config.get(section, key)
        except ConfigParser.Error:
            return default