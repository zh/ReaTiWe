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
      message.reply("Error: not authorized")
      return
    msg = [x.strip() for x in message.body.split() if x != None]
    if msg[0].lower() == u"ping":
      message.reply("PONG! :)")
    elif msg[0].lower() == u"nick":
      if len(message.body) > 6:
        nick = message.body[5:].strip()
        exists = MicroUser.gql('WHERE nick = :1', nick).get()
        if exists and microUser.nick != exists.nick:
          message.reply("Error: Nickname not available.")
        elif len(nick) > 32 or len(nick) < 4:
          message.reply("Error: Nickname must be between 4 and 32 characters long.")
        elif re.match('^[a-z][a-z0-9]*$', nick) == None:
          message.reply("Error: Nickname may only contain characters a-z and 0-9 (no uppercase) and must start with a-z.")
        else:
          microUser.nick = nick
          microUser.put()
      message.reply("nickname: %s" % microUser.nick)
    # TODO: other commands - last, on, off, follow etc.
    elif msg[0].lower() == u"last":
      text = "Last messages:\n"
      micros = MicroEntry.all().order('-date').fetch(10)
      micros.reverse()
      for m in micros:
        text += "@%s:\n%s\n#%s (%s ago) http://reatiwe.appspot.com/entry/%s\n\n" % (m.author.nick, m.content, str(entityid(m)), timestamp(m.date), str(entityid(m)))
      message.reply(text)
    else:
      # regular expressions, heavy stuff
      pattern = re.compile('^@([a-z][a-z0-9]*)\s*(.*)')
      m = pattern.match(message.body)
      if m and m.group(2):
        to_nick = m.group(1)
        msg = m.group(2)
        text = msg.strip().replace('\n','').replace('\r',' ').replace('\t',' ')
        # if message is to myself, blog it
        if to_nick == u"me":
          micro = MicroEntry( author=microUser, content=text)
          micro.put()
          # ping the PuSH hub (current user)
          form_fields = { "hub.mode": "publish",
                          "hub.url": "http://reatiwe.appspot.com/user/%s/atom" % microUser.nick }
          response = urlfetch.fetch(url = "https://pubsubhubbub.appspot.com/",
                          payload = urllib.urlencode(form_fields),
                          method = urlfetch.POST,
                          headers = {'Content-Type': 'application/x-www-form-urlencoded'})
          message.reply("message sent: http://reatiwe.appspot.com/entry/%s" % str(entityid(micro)))
        # message to another user  
        else:  
          toUser = MicroUser.gql('WHERE nick = :1', to_nick).get()
          if not toUser:
            message.reply("Error: not implemented.")
            return
          else:
            to_jid = toUser.jid.address
            #chat_message_sent = False
            #if xmpp.get_presence(to_jid):
            #  status_code = xmpp.send_message(to_jid, "message from @%s:\n%s" % (bare_jid, msg))
            xmpp.send_message(to_jid, "message from @%s:\n%s" % (microUser.nick, msg))
            #  chat_message_sent = (status_code != xmpp.NO_ERROR)
            #if not chat_message_sent:  
            #  logging.debug("msg (%s -> %s) not sent." % (bare_jid, to_jid))
            message.reply("message to %s sent." % to_nick)
      else:  
        logging.debug("unknown msg: %s" % str(self.request.get('stanza')))
        message.reply("Error: not implemented.")
