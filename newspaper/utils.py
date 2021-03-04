# -*- coding: utf-8 -*-
"""
Holds misc. utility methods which prove to be
useful throughout this library.
"""
__title__ = 'newspaper'
__author__ = 'Lucas Ou-Yang'
__license__ = 'MIT'
__copyright__ = 'Copyright 2014, Lucas Ou-Yang'

import codecs
import hashlib
import logging
import os
import pickle
import random
import re
import string
import sys
import threading
import time

from configparser import ConfigParser

from hashlib import sha1

from bs4 import BeautifulSoup

from . import settings

from psycopg2 import connect, DatabaseError
from urllib.parse import urlparse

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def db(filename='database.ini', section='postgresql'):
    parser = ConfigParser()
    parser.read(f'{os.getcwd()}/{filename}')

    output = {}

    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            output[param[0]] = param[1]
    else:
        raise Exception('Section {0} not found in the {1} file'.format(section, filename))

    return output

def db_connect():
    c = None

    try:
        params = db()

        c = connect(**params)
    except (Exception, DatabaseError) as e:
        print(e)

    return c

conn = db_connect()

class FileHelper(object):
    @staticmethod
    def loadResourceFile(filename):
        if not os.path.isabs(filename):
            dirpath = os.path.abspath(os.path.dirname(__file__))
            path = os.path.join(dirpath, 'resources', filename)
        else:
            path = filename
        try:
            f = codecs.open(path, 'r', 'utf-8')
            content = f.read()
            f.close()
            return content
        except IOError:
            raise IOError("Couldn't open file %s" % path)


class ParsingCandidate(object):

    def __init__(self, url, link_hash):
        self.url = url
        self.link_hash = link_hash


class RawHelper(object):
    @staticmethod
    def get_parsing_candidate(url, raw_html):
        if isinstance(raw_html, str):
            raw_html = raw_html.encode('utf-8', 'replace')
        link_hash = '%s.%s' % (hashlib.md5(raw_html).hexdigest(), time.time())
        return ParsingCandidate(url, link_hash)


class URLHelper(object):
    @staticmethod
    def get_parsing_candidate(url_to_crawl):
        # Replace shebang in urls
        final_url = url_to_crawl.replace('#!', '?_escaped_fragment_=') \
            if '#!' in url_to_crawl else url_to_crawl
        link_hash = '%s.%s' % (hashlib.md5(final_url).hexdigest(), time.time())
        return ParsingCandidate(final_url, link_hash)


class StringSplitter(object):
    def __init__(self, pattern):
        self.pattern = re.compile(pattern)

    def split(self, string):
        if not string:
            return []
        return self.pattern.split(string)


class StringReplacement(object):
    def __init__(self, pattern, replaceWith):
        self.pattern = pattern
        self.replaceWith = replaceWith

    def replaceAll(self, string):
        if not string:
            return ''
        return string.replace(self.pattern, self.replaceWith)


class ReplaceSequence(object):
    def __init__(self):
        self.replacements = []

    def create(self, firstPattern, replaceWith=None):
        result = StringReplacement(firstPattern, replaceWith or '')
        self.replacements.append(result)
        return self

    def append(self, pattern, replaceWith=None):
        return self.create(pattern, replaceWith)

    def replaceAll(self, string):
        if not string:
            return ''

        mutatedString = string
        for rp in self.replacements:
            mutatedString = rp.replaceAll(mutatedString)
        return mutatedString


class TimeoutError(Exception):
    pass


def timelimit(timeout):
    """Borrowed from web.py, rip Aaron Swartz
    """
    def _1(function):
        def _2(*args, **kw):
            class Dispatch(threading.Thread):
                def __init__(self):
                    threading.Thread.__init__(self)
                    self.result = None
                    self.error = None

                    self.setDaemon(True)
                    self.start()

                def run(self):
                    try:
                        self.result = function(*args, **kw)
                    except:
                        self.error = sys.exc_info()
            c = Dispatch()
            c.join(timeout)
            if c.isAlive():
                raise TimeoutError()
            if c.error:
                raise c.error[0](c.error[1])
            return c.result
        return _2
    return _1


def domain_to_filename(domain):
    """All '/' are turned into '-', no trailing. schema's
    are gone, only the raw domain + ".txt" remains
    """
    filename = domain.replace('/', '-')
    if filename[-1] == '-':
        filename = filename[:-1]
    filename += ".txt"
    return filename


def filename_to_domain(filename):
    """[:-4] for the .txt at end
    """
    return filename.replace('-', '/')[:-4]


def is_ascii(word):
    """True if a word is only ascii chars
    """
    def onlyascii(char):
        if ord(char) > 127:
            return ''
        else:
            return char
    for c in word:
        if not onlyascii(c):
            return False
    return True


def extract_meta_refresh(html):
    """ Parses html for a tag like:
    <meta http-equiv="refresh" content="0;URL='http://sfbay.craigslist.org/eby/cto/5617800926.html'" />
    Example can be found at: https://www.google.com/url?rct=j&sa=t&url=http://sfbay.craigslist.org/eby/cto/
    5617800926.html&ct=ga&cd=CAAYATIaYTc4ZTgzYjAwOTAwY2M4Yjpjb206ZW46VVM&usg=AFQjCNF7zAl6JPuEsV4PbEzBomJTUpX4Lg
    """
    soup = BeautifulSoup(html, 'html.parser')
    element = soup.find('meta', attrs={'http-equiv': 'refresh'})
    if element:
        try:
            wait_part, url_part = element['content'].split(";")
        except ValueError:
            # In case there are not enough values to unpack
            # for instance: <meta http-equiv="refresh" content="600" />
            return None
        else:
            # Get rid of any " or ' inside the element
            # for instance:
            # <meta http-equiv="refresh" content="0;URL='http://sfbay.craigslist.org/eby/cto/5617800926.html'" />
            if url_part.lower().startswith("url="):
                return url_part[4:].replace('"', '').replace("'", '')


def to_valid_filename(s):
    """Converts arbitrary string (for us domain name)
    into a valid file name for caching
    """
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    return ''.join(c for c in s if c in valid_chars)


def print_duration(method):
    """Prints out the runtime duration of a method in seconds
    """
    def timed(*args, **kw):
        ts = time.time()
        result = method(*args, **kw)
        te = time.time()
        print('%r %2.2f sec' % (method.__name__, te - ts))
        return result
    return timed


def chunks(l, n):
    """Yield n successive chunks from l
    """
    newn = int(len(l) / n)
    for i in range(0, n - 1):
        yield l[i * newn:i * newn + newn]
    yield l[n * newn - newn:]


def purge(fn, pattern):
    """Delete files in a dir matching pattern
    """
    for f in os.listdir(fn):
        if re.search(pattern, f):
            os.remove(os.path.join(fn, f))


def clear_memo_cache(source):
    """Clears the memoization cache for this specific news domain
    """
    d_pth = os.path.join(settings.MEMO_DIR, domain_to_filename(source.domain))
    if os.path.exists(d_pth):
        os.remove(d_pth)
    else:
        print('memo file for', source.domain, 'has already been deleted!')


def memoize_articles(source, articles):
    """When we parse the <a> links in an <html> page, on the 2nd run
    and later, check the <a> links of previous runs. If they match,
    it means the link must not be an article, because article urls
    change as time passes. This method also uniquifies articles.
    """

    if len(articles) == 0:
        return []

    current_articles = {article.url: article for article in articles}

    for url, article in list(current_articles.items()):
        with conn.cursor() as c:
            u = urlparse(url)
            c.execute('SELECT id FROM urls WHERE href = %s', (f'{u.netloc}{u.path}',))
            existing_id = c.fetchone()

            if existing_id != None:
                del current_articles[url]

    return list(current_articles.values())


def get_useragent():
    """Uses generator to return next useragent in saved file
    """
    with open(settings.USERAGENTS, 'r') as f:
        agents = f.readlines()
        selection = random.randint(0, len(agents) - 1)
        agent = agents[selection]
        return agent.strip()


def get_available_languages():
    """Returns a list of available languages and their 2 char input codes
    """
    stopword_files = os.listdir(os.path.join(settings.STOPWORDS_DIR))
    two_dig_codes = [f.split('-')[1].split('.')[0] for f in stopword_files]
    for d in two_dig_codes:
        assert len(d) == 2
    two_dig_codes.sort()
    return two_dig_codes


def print_available_languages():
    """Prints available languages with their full names
    """
    language_dict = {
        'ar': 'Arabic',
        'be': 'Belarusian',
        'bg': 'Bulgarian',
        'da': 'Danish',
        'de': 'German',
        'el': 'Greek',
        'en': 'English',
        'es': 'Spanish',
        'et': 'Estonian',
        'fa': 'Persian',
        'fi': 'Finnish',
        'fr': 'French',
        'he': 'Hebrew',
        'hi': 'Hindi',
        'hr': 'Croatian',
        'hu': 'Hungarian',
        'id': 'Indonesian',
        'it': 'Italian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'lt': 'Lithuanian',
        'mk': 'Macedonian',
        'nb': 'Norwegian (Bokmål)',
        'nl': 'Dutch',
        'no': 'Norwegian',
        'pl': 'Polish',
        'pt': 'Portuguese',
        'ro': 'Romanian',
        'ru': 'Russian',
        'sl': 'Slovenian',
        'sr': 'Serbian',
        'sv': 'Swedish',
        'sw': 'Swahili',
        'th': 'Thai',
        'tr': 'Turkish',
        'uk': 'Ukrainian',
        'vi': 'Vietnamese',
        'zh': 'Chinese',
    }

    codes = get_available_languages()
    print('\nYour available languages are:')
    print('\ninput code\t\tfull name')
    for code in codes:
        print('  %s\t\t\t  %s' % (code, language_dict[code]))
    print()


def extend_config(config, config_items):
    """
    We are handling config value setting like this for a cleaner api.
    Users just need to pass in a named param to this source and we can
    dynamically generate a config object for it.
    """
    for key, val in list(config_items.items()):
        if hasattr(config, key):
            setattr(config, key, val)

    return config
