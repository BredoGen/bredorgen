class Page(object):
    def __init__(self, route, key=None):
        self.route = route
        self.keyword = key
        self.life_time = tuple()

    def __str__(self):
        return self.route

class PageCollection(list):
    def __contains__(self, item):
        return any(filter(lambda x: x.route == item, self))

    def get_page(self, route):
        filtered = filter(lambda x: x.route == route, self)
        if filtered:
            return filtered[0]

    def get_all_keywords(self):
        return [page.keyword for page in self]

    def actual(self):
        def life_time(x):
            if not x.life_time:
                return True
        return filter(life_time, self)
