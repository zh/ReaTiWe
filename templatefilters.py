# -*- coding: utf-8 -*-

import time, re
from time import strftime
from google.appengine.ext import db, webapp
from google.appengine.api.datastore_types import Key
from models import MicroEntry

def timestamp(date):
	seconds = time.time() - time.mktime(date.timetuple())
	
	days = int(seconds / 86400)
	if days == 1:
		return '1 day'
	if days > 1:
		return '%d days' % days
	
	hours = int(seconds / 3600)
	if hours == 1:
		return '1 hour'
	if hours > 1:
		return '%d hours' % hours
	
	minutes = int(seconds / 60)
	if minutes == 1:
		return '1 minute'
	if minutes > 1:
		return '%d minutes' % minutes
	
	if seconds == 1:
		return '1 second'
	return '%d seconds' % seconds

def entityid(entity):
	# return db.get(Key.from_path(entity.kind(), 4)).content
	return entity.key().id()

def rfc822datetime(datetime):
	return datetime.strftime('%a, %d %b %Y %H:%M:%S') + ' GMT'

def rfc3339datetime(datetime):
	return datetime.replace(microsecond = 0).isoformat() + 'Z'

def content(content):
	content = re.sub(r'@([a-z0-9]*)', r'<a href="/user/\1">@\1</a>', content)
	content = re.sub(r'(http://[^ ]*)', r'<a href="\1">\1</a>', content)
	return content

register = webapp.template.create_template_register()
register.filter(timestamp)
register.filter(entityid)
register.filter(rfc822datetime)
register.filter(rfc3339datetime)
register.filter(content)
