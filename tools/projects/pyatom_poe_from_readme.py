from pyatom import AtomFeed
import datetime

feed = AtomFeed(title="My Blog",
                subtitle="My example blog for a feed test.",
                feed_url="http://example.org/feed",
                url="http://example.org",
                author="Me")

# Do this for each feed entry
feed.add(title="My Post",
         content="Body of my post",
         content_type="html",
         author="Me",
         url="http://example.org/entry1",
         updated=datetime.datetime.utcnow())

print feed.to_string()
