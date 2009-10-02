# -*- coding: utf-8 -*-

import cgi, os, random, re, wsgiref.handlers, urllib, base64
from google.appengine.api import urlfetch
from datetime import datetime
from django.utils import simplejson
from google.appengine.api import users
from google.appengine.ext import db, webapp
from google.appengine.ext.webapp import template

from models import *
from xmppbots import *
from templatefilters import *

pagelimit = 20


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
                    'content': content(micro.content)})
    self.response.out.write(encoder.encode(stuff))


class StreamHandler(webapp.RequestHandler):
  def get(self, nick='all'):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = MicroUser.gql("WHERE nick = :1", nick).get()
      total = pagelimit
      self.response.out.write(template.render('templates/stream.html', locals()))
    else:
      login_url = users.create_login_url('/stream')
      self.redirect(login_url) 


class HomeHandler(webapp.RequestHandler):
  def get(self, type='html'):
    if type == 'atom':
      self.response.headers['Content-Type'] = 'application/atom+xml'
    elif type == 'json':
      self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
    #micros = MicroEntry.all().order('-date').fetch(pagelimit)
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
    else:
      login_url = users.create_login_url('/')
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
        # ping the PuSH hub (current user)
        form_fields = { "hub.mode": "publish", 
                        "hub.url": "http://reatiwe.appspot.com/user/%s/atom" % microUser.nick }
        response = urlfetch.fetch(url = "https://pubsubhubbub.appspot.com/",
                        payload = urllib.urlencode(form_fields),
                        method = urlfetch.POST,
                        headers = {'Content-Type': 'application/x-www-form-urlencoded'})
      self.redirect('/')  
    else:
      login_url = users.create_login_url('/')
      self.redirect(login_url) 


class UserHandler(webapp.RequestHandler):
  def get(self, nick, type='html'):
    if type == 'atom':
      self.response.headers['Content-Type'] = 'application/atom+xml'
    elif type == 'json':
      self.response.headers['Content-Type'] = 'application/json; charset=UTF-8'
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
    else:
      login_url = users.create_login_url('/')
    microUser = MicroUser.gql("WHERE nick = :1", nick).get()
    if not microUser:
      self.redirect('/')
      return
    total = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1', microUser).count()
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
    micros = db.GqlQuery('SELECT * FROM MicroEntry WHERE author = :1 ORDER BY date DESC LIMIT ' + str(page * pagelimit) + ', ' + str(pagelimit), microUser)
    if micros.count() > 0:
      latest = micros[0].date
    else:
      latest = datetime.datetime.today()
    path = os.path.join('templates/user.' + type)
    self.response.out.write(template.render(path, locals()))


class EntryHandler(webapp.RequestHandler):
  def get(self, entryid):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
    else:
      login_url = users.create_login_url('/')
    entry = MicroEntry.get_by_id(int(entryid))  
    if not entry:
      self.redirect('/')
    else:
      self.response.out.write(template.render('templates/entry.html', locals()))


class SettingsHandler(webapp.RequestHandler):
  def get(self):
    user = users.get_current_user()
    if user:
      logout_url = users.create_logout_url("/")
      microUser = getMicroUser(user)
      if microUser.jid == None:
        microUser.jid = db.IM("xmpp", user.email())
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
      jid = self.request.get('jid').strip()
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
      # TODO: check for valid JID
      else: 
        microUser.nick = nick
        microUser.jid = db.IM("xmpp", jid)
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
    self.response.out.write(template.render('templates/about.html', locals()))


def main():
  webapp.template.register_template_library('templatefilters')
  application = webapp.WSGIApplication([
    ('/_ah/xmpp/message/chat/', XMPPHandler),
    ('/',HomeHandler),
    (r'/(atom|json)',HomeHandler),
    ('/stream',StreamHandler),
    (r'/stream/([^/]*)',StreamHandler),
    ('/items', ItemsHandler),
    (r'/items/([^/]*)',ItemsHandler),
    (r'/user/([^/]*)',UserHandler),
    (r'/user/([^/]*)/(atom|json)',UserHandler),
    (r'/entry/(.*)',EntryHandler),
    ('/about',AboutHandler),
    ('/settings',SettingsHandler)
  ], debug=True)
  wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
  main()
