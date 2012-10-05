import os
import sys
from tornado import web, gen
import hacks

class AsyncRequestHandler(web.RequestHandler):

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
        with web.RequestHandler._template_loader_lock:
            if template_path not in web.RequestHandler._template_loaders:
                loader = self.create_template_loader(template_path)
                web.RequestHandler._template_loaders[template_path] = loader
            else:
                loader = web.RequestHandler._template_loaders[template_path]
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
