## What is ReaTiWe?

Real Time Web (Rea-Ti-We) is your playground for all cool real-time-related stuff,
which become popular recently:

 * [XMPP](http://xmpp.org/)
 * [Webhooks](http://webhooks.org/)
 * [PuSH](http://code.google.com/p/pubsubhubbub/)
 * etc.


The system have two main parts:

 * Web interface, hosted on Google AppEngine and available on URL: 
   [http://reatiwe.appspot.com/](http://reatiwe.appspot.com/)
 * XMPP bot with JID  __reatiwe@appspot.com__ , hosted also on 
   [Google AppEngine](http://code.google.com/appengine/docs/python/xmpp/overview.html)

## Features

 * Microblogging via web or via XMPP (__@me {text}__ command)
 * XMPP messages between ReaTiWe users by nickname (__@nick {text}__ command)
 * Comments on entries via web or via XMPP (__#1234 {text}__ command)
 * __/user/{username}__ URL is a valid 
  [PuSH subscriber](http://pubsubhubbub.appspot.com/subscribe) - used for external feeds
  aggregation
 *  __/user/{username}/atom__ URL is a valid
  [PuSH topic](http://pubsubhubbub.appspot.com/publish) - used by external aggregators
  for getting notifications from ReaTiWe


## Getting started

Most of the system services are available only after sign in. For that, you need a Google
account. After the sign in, go to the [Settings](/settings) page and fill your details:

 * __Nickname__ - Used mostly via XMPP (messages etc.). Will also hide your real JID
 * __Full name__ - Visible via web on all your entries.
 * __JID__ - Add  __reatiwe@appspot.com__ to that account's roster
 * __Secret__ - Used for JID validation (__AUTH__ command)
 * __TwitName__ - Used only for the avatars (service provided by http://img.tweetimag.es/ ) 

Test the connection with the bot:

    ping

Validate your JID. If for example your settings are - JID: _user@sample.com_ and secret:
_secret123_ :

 * Add __reatiwe@appspot.com__ to  _user@sample.com_ 's roster and authorize it:
 * Send:
    
    AUTH secret123

If you change your JID, you need to revalidate it.

Start microblogging, comment on entries, sending messages to other users:

    @me This is just a small test microblog message
    @dude hi, dude. I'm using ReaTiWe too
    last   (will show you last 10 entries)
    #3214  (will show you entry with ID=3214)
    #3214 interesting stuff. this is my comment
    off (no more messages coming)
    on  (messages coming again)

You can disable messages from other users or announces for new feed entries with 
__ON__ / __OFF__ commands

When subscribing you user page __/user/{username}__ to some PuSH hub, in the 
_Verify token:_ box, put the __secret__ from the _Settings_ page.

## Available XMPP commands

In order to use the ReaTiWe services via XMPP, you need to add __reatiwe@appspot.com__ JID 
to your roster and eventualy accept the authorization request.

### Commands, available for everybody

 * __help, ?__ - available commands
 * __ping__ - check the connection
 * __auth {secret}__ - validate the current JID

### Commands, available only after JID validation

In order to validate your current nick, you need to enter it on the [Settings](/settings) page.
On the same page you can enter your secret too. By default a random secret will be generated, 
when you first login to the system. From your XMPP client send

    AUTH {your secret here}

, where {your secret here} is the secret from the [Settings](/settings) page.

 * __on / off__ - enable / disable messages from the system
 * __@nick__ - send a message to another system user
 * __@me {text}__ - post an entry
 * __last__ - show last 10 entries
 * __#1234__ - show some entry and comments to it, 1234 is an entry ID
 * __#1234 {text}__ - comment on some entry, 1234 is an entry ID

## Use cases

 * Simple microblog with web and XMPP input
 * PuSH publisher
 * Push subscriber
 * SocNode (TODO, still missing _/friends/{user}_ feed)
