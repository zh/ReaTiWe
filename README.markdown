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
 * A lot of __/callback/{some_secret}__ valid 
  [PuSH subscribers](http://pubsubhubbub.appspot.com/subscribe) - used for external feeds
  aggregation
 *  __/callback/{username}/atom__ URL is a valid
  [PuSH topic](http://pubsubhubbub.appspot.com/publish) - used by external aggregators
  for getting notifications from ReaTiWe


## Getting started

### Initial registration

Most of the system services are available only after sign in. For that, you need a Google
account. After the sign in, go to the [Settings](/settings) page and fill your details:

 * __Nickname__ - Used mostly via XMPP (messages etc.). Will also hide your real JID
 * __Full name__ - Visible via web on all your entries.
 * __JID__ - Add  __reatiwe@appspot.com__ to that account's roster
 * __Secret__ - Used for JID validation (__AUTH__ command)
 * __TwitName__ - Used only for the avatars (service provided by http://img.tweetimag.es/ )
 * __Subscriptions__ - list of topics, you are subscribed to. See below (PuSH section) for details.

### Working with the bot

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

### Atom feeds

"Public timeline" Atom feed is on URL 
[http://reatiwe.appspot.com/atom](http://reatiwe.appspot.com/atom).
There is also per user Atom feed, available on URL
__http://reatiwe.appspot.com/user/{username}/atom__
Both types of feeds have PuSH reference hub URL included:

    <link rel="hub" href="https://pubsubhubbub.appspot.com/"/>

### Webhooks and PubSubHubbub (PuSH)

Everytime some user is creating a new entry via web or XMPP, the system will ping
[PubSubHubbub reference hub](http://pubsubhubbub.appspot.com/) with two topics:

 * Main Atom feed: __http://reatiwe.appspot.com/atom__
 * Entry author's feed: __http://reatiwe.appspot.com/user/{username}/atom__

If you want some external services to get real-time notifications from ReaTiWe,
ask them to [subscribe](http://pubsubhubbub.appspot.com/subscribe) to that topics.
If the external service is not getting your entries, you can try to ping the hub
from the [PuSH reference hub 'Publish' page](http://pubsubhubbub.appspot.com/publish).
On the same page, you can check when was the last time, when the hub got your feed.

If you want to aggregate some external Atom feeds with your entries, go to the
[Settings](/settings) page and enter the _topic URL_ and (optional) the _origin_ (some
string, you want to see in the _'from ...'_ part of the entries).
The system will send subscribtion request to the 
[PuSH reference hub](http://pubsubhubbub.appspot.com/): _"hub.mode"="subscribe"_,
_"hub.callback"="http://reatiwe.appspot.com/callback/{some_secret}"_

ReaTiWe subscribtion handler is checking for _'hub.challenge'_  and  _'hub.topic'_
parameters, via a GET request from the PuSH hub, and sending back _'hub.challenge'_ 
in the response body.

On POST requests, comming from the hub, only the valid Atom entries, which are still
new for the system (checking atom entries IDs and links) are aggregated.

You can also subscribe/unsubscribe from the XMPP bot (commands follows):

    list (show all your subscriptions)
    sub http://somefeed.example.com/feed SomeFeed  (origin='SomeFeed')
    unsub Xx12eW  (unsubscribe from topic with name=Xx12eW)
  
There is also an XMPP messages send webhook (__POST__ requests), available on URL:
[http://reatiwe.appspot.com/send](http://reatiwe.appspot.com/send). You can use it to
send XMPP messages via web (pure-man BOSH service ;) ) to ReaTiWe users. Needed parameters
are as follows:

 * __to__ - username, you want to send a message to
 * __from__ - your username
 * __secret__ - the __secret__ from the [Settings](/settings) page
 * __message__ - message text to send

Example code:

    curl -X POST -d"to=other" -d"from=me" -d"secret=secret123" \
                 -d"message=hello+world" http://reatiwe.appspot.com/send

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
 * __list__ - list all topic subscriptions
 * __sub {url} [alias]__ - subscribe to some topic (Atom feed) (alias is optional, default="feed")
 * __unsub {name}__ - unsubscribe from some topic

## Use cases

 * Simple microblog with web and XMPP input
 * PuSH publisher
 * Push subscriber
 * [Web-to-XMPP gateway](http://bloggitation.appspot.com/entry/using-reatiwe-like-a-web-to-xmpp-gateway)
 * [PuSH-to-XMPP gateway](http://bloggitation.appspot.com/entry/using-reatiwe-like-a-push-to-xmpp-gateway)
 * SocNode (TODO, still missing _/friends/{user}_ feed)
