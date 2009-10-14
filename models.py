# -*- coding: utf-8 -*-
import functools, os, re, time, random, string, urlparse, unicodedata
import os.path

from google.appengine.api import users
from google.appengine.ext import db

def baseN(num,b,numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
  return ((num == 0) and  "0" ) or (baseN(num // b, b).lstrip("0") + numerals[num % b])


def stripTags(s):
# this list is neccesarry because chk() would otherwise not know
# that intag in stripTags() is ment, and not a new intag variable in chk().
  intag = [False]
  def chk(c):
    if intag[0]:
      intag[0] = (c != '>')
      return False
    elif c == '<':
      intag[0] = True
      return False
    return True
  return ''.join(c for c in s if chk(c))


def isValidNick(nick):
  if len(nick) > 32 or len(nick) < 4:
    raise ReatiweError("Nickname must be between 4 and 32 characters long.")
  if re.match('^[a-z][a-z0-9]*$', nick) == None:
    raise ReatiweError("Nickname may only contain chars a-z and 0-9 (no uppercase) and must start with a-z.")
  return True


def isValidOrigin(origin):
  if len(origin) > 32 or len(origin) < 4:
    raise ReatiweError("Origin must be between 4 and 32 characters long.")
  if re.match('^[a-zA-Z][a-zA-Z0-9_]*$', origin) == None:
    raise ReatiweError("Origin may only contain chars, digits and _ and must start with a char.")
  return True


def isValidSecret(secret):
  if len(secret) > 32 or len(secret) < 6:
    raise ReatiweError("Secret must be between 6 and 32 characters long.")
  if re.match('^[a-zA-Z][a-zA-Z0-9]*$', secret) == None:
    raise ReatiweError("Secret may only contain chars and digits and must start with a char.")
  return True


def isValidURL(url):
  pieces = urlparse.urlparse(url)
  if all([pieces.scheme, pieces.netloc]) and set(pieces.netloc) <= set(string.letters + string.digits + '-.:') and pieces.scheme in ['http', 'https', 'ftp']:
    return True
  else:
    raise ReatiweError("Invalid URL")


class ReatiweError(Exception):
  def __init__(self, value):
    self.value = value
  def __str__(self):
    return repr(self.value)


class MicroUser(db.Model):
  user = db.UserProperty()
  nick = db.StringProperty()
  full_name = db.StringProperty()
  jid = db.IMProperty()
  secret = db.StringProperty() 
  twit_user = db.StringProperty(default="default") 
  twit_pass = db.StringProperty()
  silent = db.BooleanProperty(default=False)
  validated = db.BooleanProperty(default=False)

  def __init__(self, *args, **kwargs):
    kwargs['secret'] = kwargs.get('secret', baseN(abs(hash(time.time())), 36))
    super(MicroUser, self).__init__(*args, **kwargs)

  def __str__(self):
    return self.nick


class MicroTopic(db.Model):
  user     = db.Reference(MicroUser, collection_name='topics')
  name     = db.StringProperty(required=True)
  url      = db.StringProperty(required=True)
  origin   = db.StringProperty(default="feed")
  validated = db.BooleanProperty(default=False)
  created  = db.DateTimeProperty(auto_now_add=True)
  updated  = db.DateTimeProperty(auto_now=True)

  def __init__(self, *args, **kwargs):
    kwargs['name'] = kwargs.get('name', baseN(abs(hash(time.time())), 36))
    super(MicroTopic, self).__init__(*args, **kwargs)

  def __str__(self):
    return self.name


class MicroEntry(db.Model):
  author  = db.Reference(MicroUser, collection_name='micros')
  content = db.TextProperty(required=True)
  date    = db.DateTimeProperty(auto_now_add=True)
  topic   = db.Reference(MicroTopic, collection_name='topics')
  link    = db.StringProperty()   # link if entry come from some feed
  uniq_id = db.StringProperty()   # uniq key
  origin  = db.StringProperty(default="web")    # web, xmpp etc.
  comments = db.IntegerProperty(default=0)

  def __str__(self):
    return self.content


class Comment(db.Model):
  idx     = db.IntegerProperty(default=1)
  entry   = db.Reference(MicroEntry, collection_name='replies')
  author  = db.Reference(MicroUser, collection_name='comments')
  date    = db.DateTimeProperty(auto_now_add=True)
  content = db.TextProperty(required=True)
  origin  = db.StringProperty(default="web")    # web, xmpp etc.

  def __str__(self):
    return self.content


def addCommentEntry(entry, comment):
  entry.comments = entry.comments + 1
  entry.put()
  comment.entry = entry
  comment.idx = entry.comments
  comment.put()
  return comment


def getMicroUser(user):
  microUser = MicroUser.gql('WHERE user = :1', user).get()
  if not microUser:
    nick = re.match('[a-z0-9]*', user.nickname())
    nick = nick.string[nick.start(0):nick.end(0)]
    while MicroUser.gql('WHERE name = :1', nick).get():
      nick += str(random.randint(1000, 9999))
    microUser = MicroUser(user=user, nick=nick, full_name=nick)
    microUser.jid = db.IM("xmpp", user.email())
    microUser.put()
  return microUser
