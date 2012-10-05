from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from plugin import BasePlugin

class HelloWorldPlugin(BasePlugin):

    @gen.engine
    def run(self, text, callback):
        http_client = AsyncHTTPClient()
        response = yield gen.Task(http_client.fetch, "http://ya.ru")
        callback(response.body)