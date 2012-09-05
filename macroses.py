import utils
import random

def get_macroses():
    return {'random': random_int, 'translit': translit}

def random_int(min, max):
    return random.randint(min, max)

def translit(text, slug=False):
    return utils.translit(text.decode('utf-8'), slug)