import codecs
import os
import cPickle

import tornado.ioloop
import tornado.template
import tornado.web
import trans

from config import Config
from plugin import PluginManager
from page import Page, PageCollection


class MainHandler(tornado.web.RequestHandler):

    @property
    def template_args(self):
        args = {'pages': self.routing, 'current_key': self.current_key}
        args.update(self.plugin_manager.get_plugins())
        return args

    @property
    def plugin_manager(self):
        if not hasattr(self.application, 'plugin_manager'):
            self.application.plugin_manager = PluginManager('plugins')
        return self.application.plugin_manager

    # overriding parent method
    def get_template_path(self):
        return self.get_path('templates')

    def render(self, template_name):
        super(MainHandler, self).render(template_name, **self.template_args)

    def render_from_string(self, tmpl, **kwargs):
        return tornado.template.Template(tmpl).generate(**kwargs)

    def get_path(self, path):
        return os.path.join(os.path.dirname(__file__), 'sites/%s/%s' % (self.request.host, path))

    def prepare(self):

        self.config  = Config(self.get_path('config.ini'))

        self.routing = PageCollection()
        self.keys = list()
        self.current_page = None
        self.current_key = None

        try:
            os.makedirs(self.get_path('cached'))
        except OSError:
            pass

        try:
            with open(self.get_path('cached/routing.pkl')) as routing:
                self.routing = cPickle.load(routing)
                self.keys = self.routing.get_all_keywords()
        except IOError:
            self.generate_routing()

    def generate_routing(self):

        try:
            with codecs.open(self.get_path('keys.txt'), 'r', 'utf-8') as keys:
                self.keys = keys.readlines()
        except IOError:
            raise tornado.web.HTTPError(500)

        route_format = self.config.get('routes', 'route_format', '{{current_page}}')

        for keyword in self.keys:
            args = self.template_args
            args.update({'current_key': keyword, 'current_page': keyword.encode('trans/slug')})
            page = Page(self.render_from_string(route_format, **args), keyword)
            self.routing.append(page)

        try:
            with open(self.get_path('cached/routing.pkl'), 'wb') as f:
                cPickle.dump(self.routing, f)
        except IOError:
            raise tornado.web.HTTPError(500)

    def get(self, path):

        print self.routing

        if os.path.isfile(self.get_path('templates/custom/%s' % path)):
            self.render('custom/%s' % path)
            return

        if path not in self.routing:
            raise tornado.web.HTTPError(404)

        self.current_page = self.routing.get_page(path)
        self.current_key = self.current_page.keyword

        self.render('_page.html')

    def on_finish(self):
        print self.request.request_time()

application = tornado.web.Application([
    (r"/(.*)", MainHandler),
], debug=True)

if __name__ == "__main__":
    application.listen(8000)
    tornado.ioloop.IOLoop.instance().start()