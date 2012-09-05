import sys
import os

class BasePlugin(object):

    def __init__(self):
        pass

    def run(self, *args, **kwards):
        raise NotImplementedError()

class PluginManager(object):

    def __init__(self, plugin_folder):
        self.plugins = dict()

        folder = os.path.abspath(plugin_folder)
        sys.path.append(folder)

        modules = [ module for module in os.listdir(folder) if os.path.isdir(os.path.join(folder, module))]
        for module in modules:
            try:
                imported = __import__(module)
                for macros, c in imported._macroses.items():
                    if issubclass(c, BasePlugin):
                        self.plugins[macros] = c().run
            except Exception:
                pass # TODO: inform about exc

    def get_plugins(self):
        return self.plugins