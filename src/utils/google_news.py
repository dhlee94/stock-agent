import feedparser
from urllib.parse import quote

class GoogleNews:
    def __init__(self, lang='en', country='US'):
        self.lang = lang.lower()
        self.country = country.upper()
        self.base_url = 'https://news.google.com/rss'

    def _build_url(self, path, query=None):
        url = f"{self.base_url}/{path}?hl={self.lang}&gl={self.country}&ceid={self.country}:{self.lang}"
        if query:
            url += f"&q={quote(query)}"
        return url

    def search(self, query):
        """Search for news articles via Google News RSS."""
        url = self._build_url("search", query=query)
        return feedparser.parse(url)

    def top_news(self):
        """Get top news articles via Google News RSS."""
        url = self._build_url("headlines")
        return feedparser.parse(url)

    def topic_headlines(self, topic_id):
        """Get headlines for a specific topic."""
        url = self._build_url(f"headlines/section/topic/{topic_id.upper()}")
        return feedparser.parse(url)
