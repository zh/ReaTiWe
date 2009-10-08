# -*- coding: utf-8 -*-

import logging, datetime, urllib

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.api.labs import taskqueue

from templatefilters import *
from models import *

logging.getLogger().setLevel(logging.DEBUG)

xmpp_help = """
Available commands:

help, ? - available commands
ping - check the connection
auth {secret} - validate the current JID


Available only after JID validation:

on / off - enable / disable messages from the system

@nick - send a message to another system user
@me - post an entry

last - show last 10 entries
#1234 - show some entry and comments to it
#1234 {text} - comment on some entry

See also: http://reatiwe.appspot.com/help
"""

class SendHandler(webapp.RequestHandler):
  def post(self):
    try:
      from_nick = self.request.POST['from']
      to_nick = self.request.POST['to']
      fromUser = MicroUser.gql('WHERE nick = :1', from_nick).get()
      toUser = MicroUser.gql('WHERE nick = :1', to_nick).get()
      if not fromUser or not toUser:
        raise ReatiweError("User does not exists.")
      
      secret = self.request.POST['secret']
      if fromUser.secret != secret:
        raise ReatiweError("Not authorized")

      message = self.request.POST['message']
      if not message or message == "":
        raise ReatiweError("Empty message")

      xmpp.send_message(toUser.jid.address, "message from @%s:\n%s" % (from_nick, message))
    except Exception, e:
      logging.error('problem: %s' % repr(e))
      pass


class XMPPHandler(webapp.RequestHandler):
  """Handler class for all XMPP activity."""
  def post(self):
    message = xmpp.Message(self.request.POST)
    bare_jid = message.sender.split('/')[0]
    resource = message.sender.split('/')[1]
    if not resource:
      resource = "xmpp"
    jid = db.IM("xmpp", bare_jid)
    microUser = MicroUser.gql('WHERE jid = :1', jid).get()
    # only register users
    if not microUser:
      message.reply("Error: not authorized")
      return
    msg = [x.strip() for x in message.body.split() if x != None]
    # only ping, auth (and maybe help?) commands are allowed for non-validated JIDs
    if msg[0].lower() == u"ping":
      message.reply("PONG! :)")
      return
    elif msg[0].lower() == u"help" or  msg[0].lower() == "?":
      message.reply(xmpp_help)
      return
    elif msg[0].lower() == u"auth":
      token = None
      if len(msg) > 1:
        token = msg[1]
      if token and microUser.secret == token:
        microUser.validated = True
        microUser.put()
        message.reply("JID %s is validated" % bare_jid)
        return
      else:
        message.reply("Error: not authorized")
        return
    if not microUser.validated:
      message.reply("Error: not authorized")
      return
    # validated JID    
    if msg[0].lower() == u"on":
      microUser.silent = False
      microUser.put()
      message.reply("Messages: ON")
    elif msg[0].lower() == u"off":
      microUser.silent = True
      microUser.put()
      message.reply("Messages: OFF")
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
    elif msg[0].lower() == u"last":
      text = "Last messages:\n"
      micros = MicroEntry.all().order('-date').fetch(10)
      micros.reverse()
      for m in micros:
        text += "@%s:\n%s\n#%s (%s ago from %s, %d replies) http://reatiwe.appspot.com/entry/%s\n\n" % (m.author.nick, m.content, str(entityid(m)), timestamp(m.date), origin(m.origin), int(m.comments), str(entityid(m)))
      message.reply(text)
    else:
      # regular expressions, heavy stuff
      pattern = re.compile('^@([a-z][a-z0-9]*)\s*(.*)')
      pattern1 = re.compile('^#([0-9]*)\s*(.*)')
      m = pattern.match(message.body)
      m1 = pattern1.match(message.body)
      if m and m.group(2):
        to_nick = m.group(1)
        msg = m.group(2)
        text = msg.strip().replace('\n','').replace('\r',' ').replace('\t',' ')
        # if message is to myself, blog it
        if to_nick == u"me":
          micro = MicroEntry(author=microUser, content=text, origin=resource)
          micro.put()
          # ping the PuSH hub (current user).
          taskqueue.add(url="/publish", 
                        params={"nick":microUser.nick, "hub":"https://pubsubhubbub.appspot.com/"})
          message.reply("message sent: http://reatiwe.appspot.com/entry/%s" % str(entityid(micro)))
        # message to another user  
        else:  
          toUser = MicroUser.gql('WHERE nick = :1', to_nick).get()
          if not toUser:
            message.reply("Error: not implemented.")
            return
          else:
            if toUser.silent:
              message.reply("%s does not accept messages." % to_nick)
            else:
              taskqueue.add(url="/send", params={"from":microUser.nick, 
                                                 "to":to_nick, 
                                                 "message":msg, 
                                                 "secret":microUser.secret})
              message.reply("message to %s sent." % to_nick)
      elif m1 and m1.group(1):
        to_entry = m1.group(1)
        entry = MicroEntry.get_by_id(int(to_entry))
        if not entry:
          message.reply("Error: no such entry.")
          return
        else:
          if m1.group(2): # Comment to some entry
            msg = m1.group(2)
            text = msg.strip().replace('\n','').replace('\r',' ').replace('\t',' ')
            comment = Comment(author=microUser, content=text, origin=resource)
            addCommentEntry(entry, comment)
            message.reply("Comment to entry #%s sent." % entityid(entry))
          else:  # display the entry itself
            text = "@%s:\n%s\n" % (entry.author.nick, entry.content)
            if int(entry.comments) > 0:
              text += "\nRepiles:\n\n"
              replies = Comment.all().filter('entry = ', entry).order('idx')
              for r in replies:
                text += "#%d @%s:\n%s (%s ago from %s)\n\n" % (int(r.idx), r.author.nick, r.content, timestamp(r.date), origin(r.origin))
            text += "\n#%s (%s ago from %s, %d replies) http://reatiwe.appspot.com/entry/%s\n\n" % (str(entityid(entry)), timestamp(entry.date), origin(entry.origin), int(entry.comments), str(entityid(entry)))
            message.reply(text)
      else:  
        logging.debug("unknown msg: %s" % str(self.request.get('stanza')))
        message.reply("Error: not implemented.")
