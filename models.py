# -*- coding: utf-8 -*-

import functools
import os
import os.path
import re
import random
import unicodedata

from google.appengine.api import users
from google.appengine.ext import db

class MicroUser(db.Model):
  user = db.UserProperty()
  nick = db.StringProperty()
  jid = db.IMProperty()

class MicroEntry(db.Model):
  author  = db.Reference(MicroUser, collection_name='micros')
  content = db.StringProperty()
  date    = db.DateTimeProperty(auto_now_add=True)

def getMicroUser(user):
  microUser = MicroUser.gql('WHERE user = :1', user).get()
  if not microUser:
    nick = re.match('[a-z0-9]*', user.nickname())
    nick = nick.string[nick.start(0):nick.end(0)]
    while MicroUser.gql('WHERE name = :1', nick).get():
      nick += str(random.randint(1000, 9999))
    microUser = MicroUser()
    microUser.nick = nick
    microUser.user = user
    microUser.jid = db.IM("xmpp", user.email())
    microUser.put()
  return microUser
