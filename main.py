# -*- coding: utf-8 -*-

import cgi, os, random, re, wsgiref.handlers, urllib, base64
import logging, hashlib, feedparser, markdown

from datetime import datetime, timedelta
from google.appengine.api import urlfetch
from django.utils import simplejson
from google.appengine.api import users
from google.appengine.ext import db, webapp
from google.appengine.ext.webapp import template
from google.appengine.api.labs import taskqueue
from google.appengine.api import memcache

import settings

from templatefilters import *
from models import *
from webhooks import *
from xmppbots import *

logging.getLogger().setLevel(logging.DEBUG)


class BaseRequestHandler(webapp.RequestHandler):
  """Supplies common handlers functions"""
  def modified_since(self, timestamp):
    self.response.headers['Last-Modified'] = timestamp.strftime("%a, %d %b %Y %H:%M:%S GMT")
    expires = timestamp + timedelta(minutes=5)
    self.response.headers['Expires'] = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
    if self.request.headers.has_key('If-Modified-Since'):
      dt = self.request.headers.get('If-Modified-Since').split(';')[0]
      modsince = datetime.strptime(dt, "%a, %d %b %Y %H:%M:%S %Z")
      if (modsince + timedelta(seconds=1)) >= timestamp:
        return False  
    return True

  # Collection is db.Model 
  def show(self, collection, template_name='', vars={}, type='html'):
    if type == 'atom': 
      self.response.headers['Content-Type'] = 'application/atom+xml'
      if vars['latest'] and not self.modified_since(vars['latest']):
        self.error(304)
        return self.response.out.write("304 Not Modified")
    elif type == 'json':
      self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
    path = os.path.join("templates/%s.%s" % (template_name, type))
    hub_url = settings.HUB_URL
    pushub_url = settings.PUSHUB_URL
    site_url = settings.SITE_URL
    site_name = settings.SITE_NAME
    param = vars.copy() 
    param.update(locals())
    return self.response.out.write(template.render(path, param))


class HomeHandler(BaseRequestHandler):
  def get(self, type='html'):
    # authentication
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')

    # pagination
    total = db.GqlQuery('SELECT * FROM MicroEntry WHERE myown = True').count()
    page = self.request.get('page')
    if page:
      page = int(page)
    else:
      page = 0
    page1 = page + 1  
    if total > (page + 1) * settings.PAGELIMIT:
      page_prev = str(page + 1)
    if page > 0:
      page_next = str(page - 1)
    num_pages = int(total/settings.PAGELIMIT)
    if total % settings.PAGELIMIT > 0 or total < settings.PAGELIMIT:
      num_pages = num_pages + 1
    micros = db.GqlQuery('SELECT * FROM MicroEntry WHERE myown = True ORDER BY date DESC LIMIT ' + str(page * settings.PAGELIMIT) + ', ' + str(settings.PAGELIMIT))
    latest = datetime.now()
    if micros.count() > 0:
      latest = micros[0].date
    return self.show(micros, "home", locals(), type)  
                                                      
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
                      params={"nick":microUser.nick, "hub":settings.HUB_URL})
        taskqueue.add(url="/publish",
                      params={"nick":microUser.nick, "hub":settings.PUSHUB_URL})
      self.redirect('/')  
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 


class UserHandler(BaseRequestHandler):
  def get(self, nick, type='html'):
    nickUser = MicroUser.gql("WHERE nick = :1", nick).get()

    # authentication
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')
    if not nickUser:
      self.redirect('/')
      return
    
    # pagination
    total = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1 AND myown = True', nickUser).count()
    page = self.request.get('page')
    if page:
      page = int(page)
    else:
      page = 0
    page1 = page + 1  
    if total > (page + 1) * settings.PAGELIMIT:
      page_prev = str(page + 1)
    if page > 0:
      page_next = str(page - 1)
    num_pages = int(total/settings.PAGELIMIT)
    if total % settings.PAGELIMIT > 0 or total < settings.PAGELIMIT:
      num_pages = num_pages + 1
    
    micros = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1 AND myown = True ORDER BY date DESC LIMIT ' + str(page * settings.PAGELIMIT) + ', ' + str(settings.PAGELIMIT), nickUser)
    latest = datetime.now()
    if micros.count() > 0:
      latest = micros[0].date
    e_count = nickUser.micros.count()  
    c_count = nickUser.comments.count()  
    l_count = nickUser.likes.count()  
    return self.show(micros, "user", locals(), type)  

# Only for the current user
class PrivateHandler(BaseRequestHandler):
  def get(self, nick, type='html'):
    nickUser = MicroUser.gql("WHERE nick = :1", nick).get()

    # authentication
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      # you can see only your own feed
      if microUser.nick != nick or not nickUser:
        self.redirect('/')
        return
    else:
      login_url = users.create_login_url('/')
      return self.redirect(login_url) 
    
    # pagination
    total = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1', nickUser).count()
    page = self.request.get('page')
    if page:
      page = int(page)
    else:
      page = 0
    page1 = page + 1  
    if total > (page + 1) * settings.PAGELIMIT:
      page_prev = str(page + 1)
    if page > 0:
      page_next = str(page - 1)
    num_pages = int(total/settings.PAGELIMIT)
    if total % settings.PAGELIMIT > 0 or total < settings.PAGELIMIT:
      num_pages = num_pages + 1
    
    micros = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1 ORDER BY date DESC LIMIT ' + str(page * settings.PAGELIMIT) + ', ' + str(settings.PAGELIMIT), nickUser)
    latest = datetime.now()
    if micros.count() > 0:
      latest = micros[0].date
    return self.show(micros, "private", locals(), type)  


class LikesHandler(BaseRequestHandler):
  def get(self, nick, type='html'):
    nickUser = MicroUser.gql("WHERE nick = :1", nick).get()
    
    # authentication
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
    else:
      login_url = users.create_login_url('/')
    if not nickUser:
      self.redirect('/')
      return
    likes = nickUser.likes.order('-date')
    
    latest = datetime.now()
    if likes.count() > 0:
      latest = likes[0].date
    return self.show(likes, "likes", locals(), type)  


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
      likes = entry.impressions
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
        # send the comment to the entry owner (but not myself)
        if entry.author.validated and not entry.author.silent and microUser.nick != entry.author.nick:
          msg = "comment on entry #%d:\n" % int(entryid)
          msg += content
          msg += "\nhttp://%s/entry/%d\n" % (settings.SITE_URL, int(entryid)) 
          taskqueue.add(url="/send", params={"from":microUser.nick, 
                                             "to":entry.author.nick, 
                                             "message":msg, 
                                             "secret":microUser.secret})
      self.redirect("/entry/%d" % int(entryid))  
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
      topics = MicroTopic.all().filter('user =', microUser)  
      hub_url = settings.HUB_URL
      return self.response.out.write(template.render('templates/settings.html', locals()))
    else:
      login_url = users.create_login_url('/')
      return self.redirect(login_url) 

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
      try:
        if exists and microUser.nick != exists.nick:
          raise ReatiweError("Nickname not available.")
        elif len(full_name) > 64 or len(full_name) < 4:
          raise  ReatiweError("Full name must be between 4 and 64 characters long.")
        elif isValidNick(nick) and isValidSecret(secret):
          microUser.nick = nick
          microUser.full_name = full_name
          if microUser.jid and microUser.jid.address != jid:
            microUser.validated = False
          microUser.jid = db.IM("xmpp", jid)
          microUser.secret = secret
          microUser.twit_user = twit_user
          microUser.put()
          return self.redirect('/')  
        else:
          return self.redirect('/')  
      except Exception, e:
        error = str(e)
        pass
        return self.response.out.write(template.render('templates/settings.html', locals()))
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
    return self.response.out.write(template.render('templates/about.html', locals()))


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
    return self.response.out.write(template.render('templates/help.html', locals()))


def main():
  webapp.template.register_template_library('templatefilters')
  application = webapp.WSGIApplication([
    ('/',                          HomeHandler),
    (r'/(atom|json)',              HomeHandler),
    (r'/user/([^/]*)',             UserHandler),
    (r'/user/([^/]*)/(atom|json)', UserHandler),
    (r'/private/([^/]*)',          PrivateHandler),
    (r'/private/([^/]*)/(atom|json)', PrivateHandler),
    (r'/likes/([^/]*)',            LikesHandler),
    (r'/likes/([^/]*)/(atom|json)', LikesHandler),
    (r'/callback/([^/]*)',         CallbackHandler),
    (r'/entry/(.*)',               EntryHandler),
    (r'/comment/(.*)',             CommentHandler),
    ('/stream',                    StreamHandler),
    (r'/stream/([^/]*)',           StreamHandler),
    ('/items',                     ItemsHandler),
    (r'/items/([^/]*)',            ItemsHandler),
    ('/topic',                     TopicHandler),
    ('/publish',                   PublishHandler),
    ('/subscribe',                 SubscribeHandler),
    ('/validate',                  ValidateHandler),
    ('/send',                      SendHandler),
    ('/about',                     AboutHandler),
    ('/help',                      HelpHandler),
    ('/settings',                  SettingsHandler)
  ], debug=settings.DEBUG)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
