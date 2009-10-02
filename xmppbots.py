# -*- coding: utf-8 -*-

import logging, datetime, urllib

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp

from templatefilters import *
from models import *

logging.getLogger().setLevel(logging.DEBUG)

class XMPPHandler(webapp.RequestHandler):
  """Handler class for all XMPP activity."""
  def post(self):
    message = xmpp.Message(self.request.POST)
    bare_jid = message.sender.split('/')[0]
    jid = db.IM("xmpp", bare_jid)
    microUser = MicroUser.gql('WHERE jid = :1', jid).get()
    # only register users
    if not microUser:
      message.reply("not authorized")
      return
    logging.debug("msg from: %s" % bare_jid)
    if message.body[0:4].lower() == u"ping":
      message.reply("PONG! :)")
    elif message.body[0:4].lower() == u"@me " and len(message.body) > 5:
      text = message.body[4:].strip().replace('\n','').replace('\r',' ').replace('\t',' ')
      micro = MicroEntry( author=microUser, content=text)
      micro.put()
      # ping the PuSH hub (current user)
      form_fields = { "hub.mode": "publish",
                        "hub.url": "http://reatiwe.appspot.com/user/%s/atom" % microUser.nick }
      response = urlfetch.fetch(url = "https://pubsubhubbub.appspot.com/",
                        payload = urllib.urlencode(form_fields),
                        method = urlfetch.POST,
                        headers = {'Content-Type': 'application/x-www-form-urlencoded'})
      message.reply("message sent #%s." % str(entityid(micro)))
    elif message.body[0:4].lower() == u"nick":
      if len(message.body) > 6:
        nick = message.body[5:].strip()
        exists = MicroUser.gql('WHERE nick = :1', nick).get()
        if exists and microUser.nick != exists.nick:
          message.reply("Nickname not available.")
        elif len(nick) > 32 or len(nick) < 4:
          message.reply("Nickname must be between 4 and 32 characters long.")
        elif re.match('^[a-z][a-z0-9]*$', nick) == None:
          message.reply("Nickname may only contain characters a-z and 0-9 (no uppercase) and must start with a-z.")
        else:
          microUser.nick = nick
          microUser.put()
      message.reply("Nickname: %s" % microUser.nick)
    # TODO: other commands - last, on, off, follow etc.  
    else:
      logging.debug("unknown msg: %s" % str(self.request.get('stanza')))
      message.reply("Error: unknown message")
