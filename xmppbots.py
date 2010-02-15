# -*- coding: utf-8 -*-

import logging, datetime, urllib, urllib2

from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from django.utils import simplejson

import settings

from templatefilters import *
from models import *
from webhooks import *

logging.getLogger().setLevel(logging.DEBUG)

xmpp_help = """
Available commands:

help, ?       - available commands
ping          - check the connection
auth {secret} - validate the current JID


Available only after JID validation:

on / off      - enable / disable messages from the system

@nick         - send a message to another system user
@me           - post an entry

last          - show last 10 entries from everybody
mine          - show your own last 10 entries
#1234         - show some entry and comments to it
#1234 {text}  - comment on some entry
like #1234    - like some entry

list          - list all subscriptions
sub {url} [alias] [hub] - subscribe to some topic (Atom feed)
unsub {name}  - unsubscribe from some topic

See also: %s/help
""" % settings.SITE_URL


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
    ### ON ### --------------------------------------------------------
    if msg[0].lower() == u"on":
      microUser.silent = False
      microUser.put()
      message.reply("Messages: ON")
    ### OFF ### --------------------------------------------------------
    elif msg[0].lower() == u"off":
      microUser.silent = True
      microUser.put()
      message.reply("Messages: OFF")
    ### NICK ### --------------------------------------------------------
    elif msg[0].lower() == u"nick":
      if len(msg) > 1:
        nick = msg[1]
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
    ### LAST ### --------------------------------------------------------
    elif msg[0].lower() == u"last":
      text = "Last messages:\n"
      micros = MicroEntry.all().filter('myown =', True).order('-date').fetch(10)
      micros.reverse()
      for m in micros:
        content = m.content.replace('\n','').replace('\r',' ').replace('\t',' ')
        text += "@%s:\n%s\n#%s" % (m.author.nick, content, str(entityid(m))) 
        text += " (%s ago from %s" % (timestamp(m.date), origin(m.origin))
        text += ", %d replies, %d likes)" % (int(m.comments), int(m.likes))
        text += " %s/entry/%s\n\n" % (settings.SITE_URL, str(entityid(m)))
      message.reply(text)
    ### MINE ### --------------------------------------------------------
    elif msg[0].lower() == u"mine":
      text = "My own last messages:\n"
      micros = MicroEntry.all().filter("author = ", microUser).order('-date').fetch(10)
      micros.reverse()
      for m in micros:
        content = m.content.replace('\n','').replace('\r',' ').replace('\t',' ')
        text += "@%s:\n%s\n#%s" % (m.author.nick, content, str(entityid(m))) 
        text += " (%s ago from %s" % (timestamp(m.date), origin(m.origin))
        text += ", %d replies, %d likes)" % (int(m.comments), int(m.likes))
        text += " %s/entry/%s\n\n" % (settings.SITE_URL, str(entityid(m)))
      message.reply(text)
    ### LIKE ### --------------------------------------------------------
    elif msg[0].lower() == u"like":
      if len(msg) > 1:
        text = "@%s liked " % microUser.nick
        epattern = re.compile('^#([0-9]*)$')
        em = epattern.match(msg[1])
        if em and em.group(1):
          entryid = int(em.group(1))
          entry = MicroEntry.get_by_id(entryid)
          if not entry or not entry.myown or entry.myown == False:
            text += "non existing entry"
          else:
            exists = Like.gql('WHERE author = :1 AND entry = :2', microUser, entry).get()
            if exists:
              text += "AGAIN entry #%d" % entryid
            else:  
              addLikeEntry(entry, Like(author=microUser))
              text += "entry #%d" % entryid
              # send the comment to the entry author
              if entry.author.validated and not entry.author.silent and microUser.nick != entry.author.nick:
                taskqueue.add(url="/send", params={"from":microUser.nick,
                                                   "to":entry.author.nick,
                                                   "message":text,
                                                   "secret":microUser.secret})
        else:  
         text += msg[1]
      else:
        text = "What you like?"
      message.reply(text)
    ### LIST ### --------------------------------------------------------
    elif msg[0].lower() == u"list":
      topics = db.GqlQuery("SELECT * FROM MicroTopic where user = :1", microUser)
      if topics.count() > 0:
        text = "Your subscriptions:\n"
        for t in topics:
          text += "%s: %s [ %s ]" % (t.name, t.url, t.hub)
          if t.validated:
            text += " (valid)"
          text += "\n"  
        message.reply(text)
      else:
        message.reply("No subscriptions")
    ### SUB ### --------------------------------------------------------
    elif msg[0].lower() == u"sub":
      url = ""
      t_origin = "feed"
      if len(msg) > 1:
        t_url = msg[1]
      if len(msg) > 2:
        t_origin = msg[2]
      if len(msg) > 3:
        t_hub = msg[3]
      else:
        t_hub = settings.HUB_URL
      try:
        if isValidURL(t_url) and isValidOrigin(t_origin) and isValidURL(t_hub):
          exists = MicroTopic.gql('WHERE url = :1', t_url).get()
          if exists:
            raise ReatiweError("Already subscribed to %s - %s" % (t_url, exists.name))
          t = MicroTopic(user=microUser, url=t_url, origin=t_origin, hub=t_hub)
          t.put()
          taskqueue.add(url="/subscribe",
                        params={"name":t.name, "mode":"subscribe", "hub":t.hub})
          message.reply("Subscribed %s: %s (%s), hub: %s" % (t.name, t.url, t.origin, t.hub))
      except Exception, e:
        pass
        message.reply(str(e))
    ### UNSUB ### --------------------------------------------------------
    elif msg[0].lower() == u"unsub":
      topic = MicroTopic.all().filter('name =', msg[1]).get()
      if not topic:
        message.reply("Error: not authorized")
        return
      taskqueue.add(url="/subscribe",
                    params={"name": topic.name, "mode": "unsubscribe", "hub": topic.hub})
      message.reply("Unsubscribed from %s" % topic.url)
    else:
      # regular expressions, heavy stuff
      pattern = re.compile('^@([a-z][a-z0-9]*)\s*(.*)')
      pattern1 = re.compile('^#([0-9]*)\s*(.*)')
      m = pattern.match(message.body)
      m1 = pattern1.match(message.body)
    ### @nick ### --------------------------------------------------------
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
                        params={"nick":microUser.nick, "hub":settings.HUB_URL})
          message.reply("message sent: %s/entry/%s" % (settings.SITE_URL,str(entityid(micro))))
        # message to another user  
        elif to_nick == u"img" or to_nick == u"image":
          #message.reply("img published: %s/entry/%s" % (settings.SITE_URL,str(entityid(micro))))
          try:
            args = [x.strip() for x in text.split() if x != None]
            if len(args) > 1:
              t_link = args[1]
            else:
              t_link = args[0]
            form_fields = { "key": settings.IMG_KEY, "image" : args[0] }
            result = urlfetch.fetch(url = settings.IMG_URL,
                                    payload = urllib.urlencode(form_fields),
                                    method = urlfetch.POST)
            logging.debug("upload %s to %s" % (args[0], settings.IMG_URL))
            if result.status_code == 200:
              decoder = simplejson.JSONDecoder()
              jdata = decoder.decode(result.content)
              logging.debug("upload result: %s" % repr(jdata))
              if jdata["rsp"]["stat"] == "fail":
                raise "Upload error: %s" % jdata["rsp"]["error_msg"]
              imgtext = jdata["rsp"]["image"]["small_thumbnail"]
              micro = MicroEntry(author=microUser, type=u"image", content=imgtext, origin=resource, link=t_link)
              micro.put()
              message.reply("image published: %s (delete - %s)" % (jdata["rsp"]["image"]["small_thumbnail"], 
                                                                  jdata["rsp"]["image"]["delete_page"]))
              return
            else:
              raise "Upload error: code %d" % result.status_code
          except urllib2.HTTPError, e:
            result = int(e.code)
            if result < 200 or result >= 300:
              logging.error('urllib2 problem: %s' % repr(e))
            pass
            return
          except Exception, e:
            logging.error('problem: %s' % repr(e))
            pass
            return
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
    ### #1234 ### --------------------------------------------------------
      elif m1 and m1.group(1):
        to_entry = m1.group(1)
        entry = MicroEntry.get_by_id(int(to_entry))
        # you cannot see private entries
        if not entry or not entry.myown or entry.myown == False:
          message.reply("Error: no such entry or not authorized.")
          return
        else:
          if m1.group(2): # Comment to some entry
            msg = m1.group(2)
            text = msg.strip().replace('\n','').replace('\r',' ').replace('\t',' ')
            comment = Comment(author=microUser, content=text, origin=resource)
            addCommentEntry(entry, comment)
            message.reply("Comment on entry #%s sent." % entityid(entry))
            # send the comment to the entry author
            if entry.author.validated and not entry.author.silent and microUser.nick != entry.author.nick:
              text  = "comment on entry #%s:\n%s\n" % (entityid(entry), text)
              text += "%s/entry/%s\n" % (settings.SITE_URL, entityid(entry))
              taskqueue.add(url="/send", params={"from":microUser.nick,
                                                 "to":entry.author.nick,
                                                 "message":text,
                                                 "secret":microUser.secret})
          else:  # display the entry itself
            text = "@%s:\n%s\n" % (entry.author.nick, entry.content)
            if int(entry.comments) > 0:
              text += "\nRepiles:\n"
              replies = Comment.all().filter('entry = ', entry).order('idx')
              for r in replies:
                text += "#%d @%s:\n%s " % (int(r.idx), r.author.nick, r.content)
                text += "(%s ago from %s)\n" % (timestamp(r.date), origin(r.origin))
            if int(entry.likes) > 0:
              text += "\nLikes: "
              for l in entry.impressions:
                text += "%s, " % l.author.nick
            text += "\n#%s (%s ago from %s) " % (str(entityid(entry)), timestamp(entry.date), origin(entry.origin)) 
            text += "%s/entry/%s\n" % (settings.SITE_URL, str(entityid(entry)))
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
