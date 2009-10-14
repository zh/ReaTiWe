# -*- coding: utf-8 -*-

import logging, datetime, urllib

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

from templatefilters import *
from models import *
from webhooks import *

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

list - list all subscriptions
sub {url} [alias] - subscribe to some topic (Atom feed)
unsub {name} - unsubscribe from some topic

See also: http://reatiwe.appspot.com/help
"""


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
        try:
          if exists and microUser.nick != exists.nick:
            raise ReatiweError(" Nickname not available.")
          elif isValidNick(nick):
            microUser.nick = nick
            microUser.put()
        except Exception, e:
          pass
          message.reply(str(e))
      message.reply("nickname: %s" % microUser.nick)
    elif msg[0].lower() == u"last":
      text = "Last messages:\n"
      micros = MicroEntry.all().order('-date').fetch(10)
      micros.reverse()
      for m in micros:
        content = m.content.replace('\n','').replace('\r',' ').replace('\t',' ')
        text += "@%s:\n%s\n#%s (%s ago from %s, %d replies) http://reatiwe.appspot.com/entry/%s\n\n" % (m.author.nick, content, str(entityid(m)), timestamp(m.date), origin(m.origin), int(m.comments), str(entityid(m)))
      message.reply(text)
    elif msg[0].lower() == u"list":
      topics = db.GqlQuery("SELECT * FROM MicroTopic where user = :1", microUser)
      if topics.count() > 0:
        text = "Your subscriptions:\n"
        for t in topics:
          text += "%s: %s" % (t.name, t.url)
          if t.validated:
            text += " (valid)"
          text += "\n"  
        message.reply(text)
      else:
        message.reply("No subscriptions")
    elif msg[0].lower() == u"sub":
      url = ""
      t_origin = "feed"
      if len(msg) > 1:
        t_url = msg[1]
      if len(msg) > 2:
        t_origin = msg[2]
      try:
        if isValidURL(t_url) and isValidOrigin(t_origin):
          exists = MicroTopic.gql('WHERE url = :1', t_url).get()
          if exists:
            raise ReatiweError("Already subscribed to %s - %s" % (t_url, exists.name))
          t = MicroTopic(user=microUser, url=t_url, origin=t_origin)
          t.put()
          taskqueue.add(url="/subscribe",
                        params={"name":t.name,
                                "mode":"subscribe",
                                "hub":"https://pubsubhubbub.appspot.com/"})
          message.reply("Subscribed %s: %s (%s)" % (t.name, t_url, t_origin))
      except Exception, e:
        pass
        message.reply(str(e))
    elif msg[0].lower() == u"unsub":
      topic = MicroTopic.all().filter('name =', msg[1]).get()
      if not topic:
        message.reply("Error: not authorized")
        return
      name = topic.name
      url = topic.url
      q = db.GqlQuery("SELECT * FROM MicroEntry where topic = :1", topic)
      if q.count() > 0:
        results = q.fetch(q.count())
        db.delete(results)
      topic.delete()
      taskqueue.add(url="/subscribe",
                    params={"name": name,
                            "mode": "unsubscribe",
                            "hub": "https://pubsubhubbub.appspot.com/"})
      message.reply("Unsubscribed from %s" % url)
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


def main():
  webapp.template.register_template_library('templatefilters')
  application = webapp.WSGIApplication([
    ('/_ah/xmpp/message/chat/',    XMPPHandler),
  ], debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
