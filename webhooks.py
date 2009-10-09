# -*- coding: utf-8 -*-

import cgi, os, random, re, wsgiref.handlers, urllib, base64
import logging, hashlib, feedparser, markdown

from urlparse import urlparse
from datetime import datetime
from django.utils import simplejson
from google.appengine.api import urlfetch
from google.appengine.api import memcache
from google.appengine.api import xmpp
from google.appengine.api import users
from google.appengine.api.labs import taskqueue
from google.appengine.ext import db, webapp
from google.appengine.ext.webapp import template

from models import *
from templatefilters import *

logging.getLogger().setLevel(logging.DEBUG)

pagelimit = 20


class PublishHandler(webapp.RequestHandler):
  def post(self):
    try:
      nick = self.request.POST['nick']
      microUser = MicroUser.gql("WHERE nick = :1", nick).get()
      if not microUser:
        raise ReatiweError("User %s does not exists." % nick)
      # ping the PuSH hub
      form_fields = { "hub.mode": "publish",
                      "hub.url": "http://reatiwe.appspot.com/atom" }
      urlfetch.fetch(url = self.request.POST['hub'],
                     payload = urllib.urlencode(form_fields),
                     method = urlfetch.POST,
                     headers = {'Content-Type': 'application/x-www-form-urlencoded'})
      form_fields = { "hub.mode": "publish",
                      "hub.url": "http://reatiwe.appspot.com/user/%s/atom" % nick }
      urlfetch.fetch(url = self.request.POST['hub'],
                     payload = urllib.urlencode(form_fields),
                     method = urlfetch.POST,
                     headers = {'Content-Type': 'application/x-www-form-urlencoded'})
    except Exception, e:
      logging.error('problem: %s' % repr(e))
      pass


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


class ItemsHandler(webapp.RequestHandler):
  def get(self, nick='all'):
    encoder = simplejson.JSONEncoder()
    stuff = []
    microUser = MicroUser.gql("WHERE nick = :1", nick).get()
    if not microUser or nick == 'all':
      micros = MicroEntry.all().order('-date').fetch(pagelimit)
    else:  
      micros = MicroEntry.all().filter('author = ', microUser).order('-date').fetch(pagelimit)
    for micro in micros:
      stuff.append({'id': entityid(micro),
                    'date': timestamp(micro.date),
                    'author': micro.author.nick,
                    'name': micro.author.full_name,
                    'origin': origin(micro.origin),
                    'avatar': micro.author.twit_user,
                    'replies': micro.comments,
                    'content': content(micro.content)})
    self.response.out.write(encoder.encode(stuff))


class StreamHandler(webapp.RequestHandler):
  def get(self, nick='all'):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      nickUser = MicroUser.gql("WHERE nick = :1", nick).get()
      total = pagelimit
      self.response.out.write(template.render('templates/stream.html', locals()))
    else:
      login_url = users.create_login_url('/stream')
      self.redirect(login_url)


class CallbackHandler(webapp.RequestHandler):
  def get(self, nick):
    challenge = self.request.get('hub.challenge')
    topic = self.request.get('hub.topic')
    vtoken = self.request.get('hub.verify_token')

    if challenge and topic and vtoken:
      microUser = MicroUser.gql("WHERE nick = :1", nick).get()
      if microUser and vtoken == microUser.secret:
        self.response.set_status(200)
        return self.response.out.write(challenge)
    self.response.set_status(400)
    return self.response.out.write("Bad request")
  # PuSH subscriber  
  def post(self, nick):
    # handle only requests from the PuSH reference hub
    microUser = MicroUser.gql("WHERE nick = :1", nick).get()
    if not microUser:
      self.response.set_status(400)
      return self.response.out.write("Bad request")

    body = self.request.body.decode('utf-8')
    data = feedparser.parse(self.request.body)
    if not data:
      self.response.set_status(400)
      return self.response.out.write("Bad request: Invalid Atom feed")
    
    update_list = []
    xmpp_text = "New entries: \n\n"
    logging.info('Found %d entries', len(data.entries))
    for entry in data.entries:
      if hasattr(entry, 'content'):
        # This is Atom.
        entry_id = entry.id
        content = entry.content[0].value
        link = entry.get('link', '')
        title = entry.get('title', '')
      else:
        content = entry.get('description', '')
        title = entry.get('title', '')
        link = entry.get('link', '')
        entry_id = (entry.get('id', '') or link or title or content)
      
      content = stripTags(content)
      uniq_id='key_' + hashlib.sha1(link + '\n' + entry_id).hexdigest()
      exists = MicroEntry.gql("WHERE uniq_id = :1", uniq_id).get()
      if not exists:
        logging.info('New entry with title = "%s", id = "%s", '
                     'link = "%s", content = "%s"',
                     title, entry_id, link, content)
        text = "[%s] \n" % title
        text += "%s ...\n" % content[:200]
        text += "%s" % link
        update_list.append(MicroEntry(
          title=title,
          content=text,
          origin="feed",
          link=link,
          uniq_id=uniq_id,
          author=microUser))
        xmpp_text += "%s\n\n" % text
    db.put(update_list)
    if len(update_list) > 0 and not microUser.silent:
      taskqueue.add(url="/send", params={"from":microUser.nick, 
                                         "to":microUser.nick, 
                                         "message":xmpp_text, 
                                         "secret":microUser.secret})
    # TODO: maybe also send xmpp message. to who?
    self.response.set_status(200)
    return self.response.out.write("OK")
