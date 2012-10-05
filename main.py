import codecs
import os
import cPickle
import sys
from tornado import gen, web

import tornado.ioloop
import tornado.template
import tornado.web

import hacks.template
import utils
import macroses
from config import Config
from plugin import PluginManager
from page import Page, PageCollection

class AsyncRequestHandler(tornado.web.RequestHandler):

    def create_template_loader(self, template_path):
        settings = self.application.settings
        if "template_loader" in settings:
            return settings["template_loader"]
        kwargs = {}
        if "autoescape" in settings:
            # autoescape=None means "no escaping", so we have to be sure
            # to only pass this kwarg if the user asked for it.
            kwargs["autoescape"] = settings["autoescape"]
        return hacks.template.Loader(template_path, **kwargs)

    @gen.engine
    def render_string(self, template_name, callback, **kwargs):
        """Generate the given template with the given arguments.

        We return the generated string. To generate and write a template
        as a response, use render() above.
        """
        # If no template_path is specified, use the path of the calling file
        template_path = self.get_template_path()
        if not template_path:
            frame = sys._getframe(0)
            web_file = frame.f_code.co_filename
            while frame.f_code.co_filename == web_file:
                frame = frame.f_back
            template_path = os.path.dirname(frame.f_code.co_filename)
        with tornado.web.RequestHandler._template_loader_lock:
            if template_path not in tornado.web.RequestHandler._template_loaders:
                loader = self.create_template_loader(template_path)
                tornado.web.RequestHandler._template_loaders[template_path] = loader
            else:
                loader = tornado.web.RequestHandler._template_loaders[template_path]
        t = loader.load(template_name)
        args = dict(
            handler=self,
            request=self.request,
            current_user=self.current_user,
            locale=self.locale,
            _=self.locale.translate,
            static_url=self.static_url,
            xsrf_form_html=self.xsrf_form_html,
            reverse_url=self.reverse_url
        )
        args.update(self.ui)
        args.update(kwargs)
        result = yield gen.Task(t.generate,**args)
        callback(result)

    @gen.engine
    def render(self, template_name, **kwargs):
        result = yield gen.Task(self.render_string, template_name, **kwargs)
        self.finish(result)


class MainHandler(AsyncRequestHandler):

    @property
    def template_args(self):
        args = {'pages': self.routing, 'current_key': self.current_key, 'host': self.request.host}
        args.update(self.plugin_manager.get_plugins())
        args.update(macroses.get_macroses())
        return args

    @property
    def plugin_manager(self):
        if not hasattr(self.application, 'plugin_manager'):
            self.application.plugin_manager = PluginManager('plugins')
        return self.application.plugin_manager

    def get_path(self, path):
        return utils.get_path(self.request.host, path)

    # overriding parent method
    def get_template_path(self):
        return self.get_path('templates')

    def render(self, template_name):
        super(MainHandler, self).render(template_name, **self.template_args)

    #def render_from_string(self, tmpl, **kwargs):
    #    return tornado.template.Template(tmpl).generate(**kwargs)

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
        except IOError, e:
            raise tornado.web.HTTPError(500, str(e))

        route_format = self.config.get('routes', 'route_format', '{{current_page}}')

        for keyword in self.keys:
            args = self.template_args # copy template args to 
            args.update({'current_key': keyword, 'current_page': utils.translit(keyword)})
            page = Page(self.render_from_string(route_format, **args), keyword)
            self.routing.append(page)

        try:
            with open(self.get_path('cached/routing.pkl'), 'wb') as f:
                cPickle.dump(self.routing, f)
        except IOError:
            raise tornado.web.HTTPError(500)

    @web.asynchronous
    def get(self, path):

        if os.path.isfile(self.get_path('templates/custom/%s' % path)):
            self.render('custom/%s' % path)
            return

        if not path:
            self.render('_index.html')
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