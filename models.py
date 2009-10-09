# -*- coding: utf-8 -*-
import functools
import os
import os.path
import re
import time
import random
import unicodedata

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


def isValidSecret(secret):
  if len(secret) > 32 or len(secret) < 6:
    raise ReatiweError("Secret must be between 6 and 32 characters long.")
  if re.match('^[a-zA-Z][a-zA-Z0-9]*$', secret) == None:
    raise ReatiweError("Secret may only contain characters a-z, A-Z and 0-9 and must start with a letter.")
  return True


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


class MicroEntry(db.Model):
  author  = db.Reference(MicroUser, collection_name='micros')
  content = db.TextProperty()
  date    = db.DateTimeProperty(auto_now_add=True)
  link    = db.StringProperty()   # link if entry come from some feed
  uniq_id = db.StringProperty()   # uniq key
  origin  = db.StringProperty(default="web")    # web, xmpp etc.
  comments = db.IntegerProperty(default=0)


class Comment(db.Model):
  idx     = db.IntegerProperty(default=1)
  entry   = db.Reference(MicroEntry, collection_name='replies')
  author  = db.Reference(MicroUser, collection_name='comments')
  date    = db.DateTimeProperty(auto_now_add=True)
  content = db.TextProperty()
  origin  = db.StringProperty(default="web")    # web, xmpp etc.


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
    microUser.secret = baseN(abs(hash(time.time())), 36)
    microUser.put()
  return microUser
