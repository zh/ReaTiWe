# -*- coding: utf-8 -*-

import cgi, os, random, re, wsgiref.handlers, urllib, base64
import logging, hashlib, feedparser, markdown

from google.appengine.api import urlfetch
from datetime import datetime
from django.utils import simplejson
from google.appengine.api import users
from google.appengine.ext import db, webapp
from google.appengine.ext.webapp import template
from google.appengine.api.labs import taskqueue
from google.appengine.api import memcache

from models import *
from xmppbots import *
from templatefilters import *

logging.getLogger().setLevel(logging.DEBUG)

pagelimit = 20


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


class HomeHandler(webapp.RequestHandler):
  def get(self, type='html'):
    total = db.GqlQuery('SELECT * FROM MicroEntry').count()
    # pagination
    page = self.request.get('page')
    if page:
      page = int(page)
    else:
      page = 0
    page1 = page + 1  
    if total > (page + 1) * pagelimit:
      page_prev = str(page + 1)
    if page > 0:
      page_next = str(page - 1)
    num_pages = int(total/pagelimit)
    if total%pagelimit > 0 or total < pagelimit:
      num_pages = num_pages + 1
    micros = db.GqlQuery('SELECT * FROM MicroEntry ORDER BY date DESC LIMIT ' + str(page * pagelimit) + ', ' + str(pagelimit))  
    if micros.count() > 0:
      latest = micros[0].date
    else:
      latest = datetime.datetime.today()
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')
    if type == 'atom':
      if self.request.headers.has_key('If-Modified-Since'):
        self.response.headers['Content-Type'] = 'application/atom+xml'
        dt = self.request.headers.get('If-Modified-Since').split(';')[0]
        modsince = datetime.datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %Z")
        if (modsince + datetime.timedelta(seconds=1)) >= latest:
          self.error(304)
          return self.response.out.write("304 Not Modified")

      self.response.headers['Last-Modified'] = latest.strftime("%a, %d %b %Y %H:%M:%S GMT")
      expires=latest + datetime.timedelta(minutes=5)
      self.response.headers['Expires'] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
    elif type == 'json':
      self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
    path = os.path.join('templates/home.' + type)
    self.response.out.write(template.render(path, locals()))
                                                      
  def post(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      content = self.request.get('content').strip()
      if content:
        content = content.replace('\n','').replace('\r',' ').replace('\t',' ')
        microUser = getMicroUser(user)
        micro = MicroEntry(author=microUser, content=content)
        micro.put()
        # ping the PuSH hub (current user).
        # TODO: users can have different hubs
        taskqueue.add(url="/publish",
                      params={"nick":microUser.nick, "hub":"https://pubsubhubbub.appspot.com/"})
      self.redirect('/')  
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 


class UserHandler(webapp.RequestHandler):
  def get(self, nick, type='html'):
    nickUser = MicroUser.gql("WHERE nick = :1", nick).get()
    # check if it is PuSH check request
    challenge = self.request.get('hub.challenge')
    topic = self.request.get('hub.topic')
    vtoken = self.request.get('hub.verify_token')

    if challenge:
      if not nickUser or not topic or not vtoken or vtoken != nickUser.secret:
        self.response.out.write("Bad request: Expected 'hub.challenge' and 'hub.verify_token'")
        self.response.set_status(400)
        return
      else:
        self.response.out.write(challenge)
        self.response.set_status(200)
        return

    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')
    if not nickUser:
      self.redirect('/')
      return
    
    total = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1', nickUser).count()
    # pagination
    page = self.request.get('page')
    if page:
      page = int(page)
    else:
      page = 0
    page1 = page + 1  
    if total > (page + 1) * pagelimit:
      page_prev = str(page + 1)
    if page > 0:
      page_next = str(page - 1)
    num_pages = int(total/pagelimit)
    if total%pagelimit > 0 or total < pagelimit:
      num_pages = num_pages + 1
    micros = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1 ORDER BY date DESC LIMIT ' + str(page * pagelimit) + ', ' + str(pagelimit), nickUser)
    if micros.count() > 0:
      latest = micros[0].date
    else:
      latest = datetime.datetime.today()
    if type == 'atom': 
      if self.request.headers.has_key('If-Modified-Since'):
        self.response.headers['Content-Type'] = 'application/atom+xml'
        dt = self.request.headers.get('If-Modified-Since').split(';')[0]
        modsince = datetime.datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %Z")
        if (modsince + datetime.timedelta(seconds=1)) >= latest:
          self.error(304)
          return self.response.out.write("304 Not Modified")

      self.response.headers['Last-Modified'] = latest.strftime("%a, %d %b %Y %H:%M:%S GMT")
      expires=latest + datetime.timedelta(minutes=5)
      self.response.headers['Expires'] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
    path = os.path.join('templates/user.' + type)
    self.response.out.write(template.render(path, locals()))
  # PuSH subscriber  
  def post(self, nick):
    microUser = MicroUser.gql("WHERE nick = :1", nick).get()
    if not microUser:
      self.response.out.write("Bad request")
      self.response.set_status(400)
      return
    body = self.request.body.decode('utf-8')
    logging.info('Post body is %d characters', len(body))
    data = feedparser.parse(self.request.body)
    if not data:
      self.response.out.write("Bad request: Invalid Atom feed")
      self.response.set_status(400)
      return
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
    self.response.out.write("OK")
    self.response.set_status(200)


class EntryHandler(webapp.RequestHandler):
  def get(self, entryid):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')
    entry = MicroEntry.get_by_id(int(entryid))  
    if not entry:
      self.redirect('/')
    else:
      replies = Comment.all().filter('entry = ', entry).order('idx')
      self.response.out.write(template.render('templates/entry.html', locals()))


class CommentHandler(webapp.RequestHandler):
  def post(self, entryid):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      entry = MicroEntry.get_by_id(int(entryid))  
      if not entry:
        self.redirect('/')
      content = self.request.get('content').strip()
      if content:
        content = content.replace('\n','').replace('\r',' ').replace('\t',' ')
        comment = Comment(author=microUser, content=content)
        addCommentEntry(entry, comment)
      self.redirect("/entry/%s" % str(entryid))  
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 


class SettingsHandler(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      if microUser.jid == None:
        microUser.jid = db.IM("xmpp", user.email())
      if microUser.secret == None:
        microUser.secret = baseN(abs(hash(time.time())), 36)  
      if microUser.twit_user == None:
        microUser.twit_user = "default"
      if microUser.full_name == None:
        microUser.full_name = microUser.nick
      self.response.out.write(template.render('templates/settings.html', locals()))
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 
  def post(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      nick = self.request.get('nick').strip()
      full_name = self.request.get('full_name').strip()
      jid = self.request.get('jid').strip()
      secret = self.request.get('secret').strip()
      twit_user = self.request.get('twit_user').strip()
      # input validation
      exists = MicroUser.gql('WHERE nick = :1', nick).get()
      if exists and microUser.nick != exists.nick:
        error = "Nickname not available."
        self.response.out.write(template.render('templates/settings.html', locals()))
        return
      elif len(nick) > 32 or len(nick) < 4:
        error = "Nickname must be between 4 and 32 characters long."
        self.response.out.write(template.render('templates/settings.html', locals()))
        return
      elif re.match('^[a-z][a-z0-9]*$', nick) == None:
        error = "Nickname may only contain characters a-z and 0-9 (no uppercase) and must start with a-z."
        self.response.out.write(template.render('templates/settings.html', locals()))
        return
      # TODO: check for valid JID, secret etc.
      elif len(full_name) > 64 or len(full_name) < 4:
        error = "Full name must be between 4 and 64 characters long."
        self.response.out.write(template.render('templates/settings.html', locals()))
        return
      elif len(secret) > 32 or len(secret) < 6:
        error = "Secret must be between 6 and 32 characters long."
        self.response.out.write(template.render('templates/settings.html', locals()))
        return
      elif re.match('^[a-zA-Z][a-zA-Z0-9]*$', secret) == None:
        error = "Secret may only contain characters a-z, A-Z and 0-9 and must start with a letter."
        self.response.out.write(template.render('templates/settings.html', locals()))
      else: 
        microUser.nick = nick
        microUser.full_name = full_name
        if microUser.jid and microUser.jid.address != jid:
          microUser.validated = False
        microUser.jid = db.IM("xmpp", jid)
        microUser.secret = secret
        microUser.twit_user = twit_user
        microUser.put()
        self.redirect('/')  
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 


class AboutHandler(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
    else:
      login_url = users.create_login_url('/about')
    memcache.delete("reatiwe_help")  
    self.response.out.write(template.render('templates/about.html', locals()))


class HelpHandler(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
    else:
      login_url = users.create_login_url('/help')
    #help_text = markdown.markdown_path("README.markdown")
    help_text = memcache.get("reatiwe_help")
    if not help_text:
      help_text = markdown.markdown_path("README.markdown")
      memcache.add("reatiwe_help", help_text, 600)
    self.response.out.write(template.render('templates/help.html', locals()))


def main():
  webapp.template.register_template_library('templatefilters')
  application = webapp.WSGIApplication([
    ('/_ah/xmpp/message/chat/',    XMPPHandler),
    ('/',                          HomeHandler),
    (r'/(atom|json)',              HomeHandler),
    ('/stream',                    StreamHandler),
    (r'/stream/([^/]*)',           StreamHandler),
    ('/items',                     ItemsHandler),
    (r'/items/([^/]*)',            ItemsHandler),
    (r'/user/([^/]*)',             UserHandler),
    (r'/user/([^/]*)/(atom|json)', UserHandler),
    (r'/entry/(.*)',               EntryHandler),
    (r'/comment/(.*)',             CommentHandler),
    ('/publish',                   PublishHandler),
    ('/send',                      SendHandler),
    ('/about',                     AboutHandler),
    ('/help',                      HelpHandler),
    ('/settings',                  SettingsHandler)
  ], debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
