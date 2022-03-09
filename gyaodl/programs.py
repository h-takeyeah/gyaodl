# -*- coding: utf-8 -*-

import json
import re
from dataclasses import asdict, dataclass, fields
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen


@dataclass
class Video:
    '''
    Video

    Part of resource comes from program API
    (gyao.yahoo.co.jp/api/programs/<program_id>/videos)
    '''
    id: str
    title: str
    shortTitle: str
    streamingAvailability: str
    startDate: str
    endDate: str
    shortWebUrl: str

    def __post_init__(self):
        me=asdict(self)
        for f in fields(self):
            assert type(me[f.name]) == f.type, f'Cannot assign {me[f.name]} to {f.name}({f.type})'


class VideoIdGetter(HTMLParser):
    '''
    VideoIdGetter

    Original parser that parses HTML source of a GYAO! video page and find data-vid attribute.
    '''

    def __init__(self, *, convert_charrefs=True) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self.vid = ''

    def handle_starttag(self, _tag: str, attrs: list[tuple]) -> None:
        # It is guaranteed that the tuple in attrs has only two elements.
        d = dict(attrs)
        if 'gyao-player' in d.get('class', ''):
            self.vid = d.get('data-vid', '')

    def feed(self, data: str) -> str:
        super().feed(data)
        return self.vid


class EndPointGetter(HTMLParser):
    '''
    EndPointGetter

    A parser that parses given HTML source. It searches for the `data-endpoint-url` attribute
    relating to the video series and returns its value as the feed() function's return value.
    '''

    def __init__(self, *, convert_charrefs=True) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self.endpoint_url = ''
        self.ptn = re.compile(r'^/api/programs/[0-9a-z-]+/videos$')

    def handle_starttag(self, _tag: str, attrs: list[tuple]) -> None:
        d = dict(attrs)
        endpoint_url = d.get('data-endpoint-url')
        if endpoint_url and self.ptn.match(endpoint_url):
            self.endpoint_url = endpoint_url

    def feed(self, data: str) -> str:
        super().feed(data)
        return self.endpoint_url


def get_episodes(url: str, series: bool) -> list[Video]:
    try:
        # If url is already encoded, it will be decoded before re-encoding.
        # If url is not encoded, it will be encoded.
        with urlopen(quote(unquote(url), safe='/:+')) as res:
            html_content = res.read()  # bytes
            if res.headers.get_content_charset():
                charset = res.headers.get_content_charset()
            else:
                charset = 'utf8'
            endpoint_path = EndPointGetter().feed(html_content.decode(charset))
            assert len(endpoint_path) > 0, 'Endpoint not found from HTML source'

        # replace url.path with endpoint_path
        with urlopen(url.replace(urlparse(url).path, endpoint_path)) as res:
            assert 'json' in res.headers.get_content_type(), f'Unexpected Content-Type ({res.headers.get_content_type()})'

            json_body = json.loads(res.read())
            # The loaded JSON must be "dict" type, and its property "videos" must be "list" type.
            assert isinstance(json_body, dict) and isinstance(json_body.get('videos'), list), 'Unexpected JSON schema'

            episodes: list[Video] = []
            video_fields = [f.name for f in fields(Video)]
            if series:
                for v in json_body.get('videos'):
                    assert isinstance(v, dict), 'Unexpected item found'
                    # Drop unnecessary properties from response json
                    filtered_v = dict([p for p in v.items() if p[0] in video_fields])
                    episodes.append(Video(**filtered_v))
            else:
                if url.find('title') > 0:
                    # Since uuid in URL path is not gyao_videoid when URL includes 'title', so parse HTML
                    vid = VideoIdGetter().feed(html_content.decode(charset))
                else:
                    # Otherwise, the last element of url.path is gyao_videoid
                    vid = urlparse(url).path.split('/')[-1]
                assert len(vid) > 0, 'Failed to get videoid'

                for v in json_body.get('videos'):
                    assert isinstance(v, dict), 'Unexpected item found'
                    if v.get('id') == vid:
                        filtered_v = dict([p for p in v.items() if p[0] in video_fields])
                        episodes.append(Video(**filtered_v))
                        break
                    else:
                        pass
                # len(episodes) must be 1
            assert len(episodes) != 0, 'episode list is empty why???'
            return episodes

    except HTTPError:
        raise
