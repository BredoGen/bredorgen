from plugin import BasePlugin

class HelloWorldPlugin(BasePlugin):

    def run(self, text, callback):
        callback(text)