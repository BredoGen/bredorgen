import os
import trans

def get_path(host, path):
    return os.path.join(os.path.dirname(__file__), 'sites/%s/%s' % (host, path))

def translit(text, slug=True):
    return text.encode('trans/slug' if slug else 'trans')