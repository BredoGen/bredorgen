import utils
import random

def get_macroses():
    return {'random': random_int, 'translit': translit, 'file_content': file_content}

def random_int(min, max):
    return random.randint(min, max)

def translit(text, slug=False):
    return utils.translit(text.decode('utf-8'), slug)

def file_content(host, filename):
    return open(utils.get_path(host, filename)).read()