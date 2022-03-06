# -*- coding: utf-8 -*-

import argparse
import json
import logging
from pathlib import Path
import re
from html.parser import HTMLParser
from typing import List, Tuple, Union
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from http.client import HTTPResponse

from gyaodl import dl


program_version = '0.4'

GYAO_APPID = 'dj00aiZpPUNJeDh2cU1RazU3UCZzPWNvbnN1bWVyc2VjcmV0Jng9NTk-'
BRIGHTCOVE_ID_OF_GYAO = '4235717419001'
BRIGHTCOVE_API_PK = (
    'BCpkADawqM1O4pwi3SZ75b8DE1c2l78PZ418NByBa33h737r'
    'Wv6uhPJHYkaZ6xHINTj5oOqa0-zarOEvQ6e1EqKhBcCppkAU'
    'Wuo5QSKWVC4HZjY2z-Lo_ptwEK3hxfKuvZXkdNuyOM5nNSWy'
)


class GrepVideoInfo(HTMLParser):
    '''
    GrepVideoInfo

    Original parser that parses HTML source of a GYAO! video page and find data-vid attribute.
    '''

    def __init__(self, *, convert_charrefs: bool = ...) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self.video_info = {'vid': ''}

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Union[str, None]]]) -> None:
        # It is guaranteed that the tuple in attrs has only two elements.
        d = dict(attrs)
        if tag == 'div' and 'gyao-player' in d.get('class', ''):
            self.video_info['vid'] = d.get('data-vid', '')
            if len(self.video_info) == 0:
                raise Exception('"gyao-player" div element has no data for "data-vid" attribute.')

    def feed(self, data: str) -> dict:
        super().feed(data)
        return self.video_info


class EndPointGetter(HTMLParser):
    '''
    EndPointGetter

    A parser that parses given HTML source. It searches for the `data-endpoint-url` attribute
    relating to the video series and returns its value as the feed() function's return value.
    '''

    def __init__(self, *, convert_charrefs: bool = ...) -> None:
        super().__init__(convert_charrefs=convert_charrefs)
        self.endpoint_url = ''
        self.ptn = re.compile(r'^/api/programs/[0-9a-z-]+/videos$')

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Union[str, None]]]) -> None:
        d = dict(attrs)
        endpoint_url = d.get('data-endpoint-url')
        if endpoint_url and self.ptn.match(endpoint_url):
            self.endpoint_url = endpoint_url

    def feed(self, data: str) -> str:
        super().feed(data)
        return self.endpoint_url


def gyao_url_to_video_info(url: str) -> dict:

    ptn = re.compile(r'^https://gyao.yahoo.co.jp/(episode|title)(/[^/]+/|/)[0-9a-z-]+$')

    if not ptn.match(url):
        raise TypeError('This URL is not supported.')

    # If url is already encoded, it will be decoded before re-encoding.
    # If url is not encoded, it will be encoded.
    with urlopen(quote(unquote(url), safe='/:+')) as res:
        html_content = res.read()  # bytes
        parser = GrepVideoInfo()
        return parser.feed(html_content.decode())


def get_video_metadata(gyao_videoid: str) -> dict:
    variables = json.dumps({
        'videoId': gyao_videoid,
        'logicaAgent': 'PC_WEB',
        'clientSpaceId': '1183050133',
        'os': 'UNKNOWN',
        'device': 'PC'
    })
    graphql_query = (
        'query Playback($videoId: ID!, $logicaAgent: LogicaAgent!, '
        '$clientSpaceId: String!, $os: Os!, $device: Device!) '
        '{ content( parameter: { contentId: $videoId logicaAgent: $logicaAgent '
        'clientSpaceId: $clientSpaceId os: $os device: $device view: WEB } ) '
        '{ video { id title delivery { id drm } duration gyaoUrl } } }'
    )
    query_parameters = {
        'appId': GYAO_APPID,  # appId
        'query': graphql_query,  # query string for GraphQL
        'variables': variables  # variables for GraphQL(JSON formatted string)
    }

    # urlencode(): Encode a dict or sequence of two-element tuples into a URL query string.
    req = Request(f'https://gyao.yahoo.co.jp/apis/playback/graphql?{urlencode(query_parameters)}')

    with urlopen(req) as res:
        parsed = json.loads(res.read())

        # May be not found.
        if parsed['data']['content'] is None:
            return {'delivery_id': '', 'title': ''}

        return {
            'delivery_id': parsed['data']['content']['video']['delivery']['id'],
            'title': parsed['data']['content']['video']['title']
        }


def get_playlist_url(brightcove_id: str) -> str:
    headers = {'Accept': f'application/json;pk={BRIGHTCOVE_API_PK}'}
    req = Request(
        f'https://edge.api.brightcove.com/playback/v1/accounts/{BRIGHTCOVE_ID_OF_GYAO}/videos/{brightcove_id}', headers=headers)
    with urlopen(req) as res:
        parsed = json.loads(res.read())

        # Search for a hls stream
        for v in parsed['sources']:
            if not v['type'] == 'application/x-mpegURL':
                continue
            elif ('ext_x_version' not in v) or (not v['ext_x_version'] == '4'):
                continue
            elif not str(v['src']).startswith('https'):
                continue

            return v['src']  # Found a stream URL

        return ''  # Not found


def get_available_episodes(url: str) -> list[str]:
    ptn = re.compile(r'^https://gyao.yahoo.co.jp/(episode|title)(/[^/]+/|/)[0-9a-z-]+$')

    if not ptn.match(url):
        raise TypeError('This URL is not supported.')

    res: HTTPResponse
    # If url is already encoded, it will be decoded before re-encoding.
    # If url is not encoded, it will be encoded.
    with urlopen(quote(unquote(url), safe='/:+')) as res:
        html_content = res.read()  # bytes
        parser = EndPointGetter()
        endpoint_path = parser.feed(html_content.decode())

    # replace url.path with endpoint_path
    with urlopen(url.replace(urlparse(url).path, endpoint_path)) as res:
        assert 'json' in res.headers.get_content_type()

        json_body = json.loads(res.read())
        # The loaded JSON must be "dict" type, and its property "videos" must be "list" type.
        assert type(json_body) == dict and type(json_body.get('videos')) == list

        # streamingAvailability: the episode is publicly available or not
        # shorWebUrl: link to a video page (example https://gyao.yahoo.co.jp/episode/1234)
        return [v.get('shortWebUrl') for v in json_body.get('videos') if v.get('streamingAvailability', True) and v.get('shortWebUrl')]


def main() -> None:
    # Create an argparser
    parser = argparse.ArgumentParser(prog='gyaodl', description='Download GYAO! video as mp4 file.')
    parser.add_argument('--version', action='version', version=program_version)
    parser.add_argument('url', help='GYAO! video URL')
    parser.add_argument('--series', action='store_true', default=False, help='download all available episodes')

    # Create a logger
    logger = logging.getLogger('GYAODownloader')

    # Save log file at the directory where this script is installed.
    script_installed_at = Path(__file__).parent.resolve()
    fh = logging.FileHandler(script_installed_at.joinpath('application.log'))
    fmt = logging.Formatter('%(asctime)s %(lineno)d %(levelname)s %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.setLevel(logging.ERROR)

    # Parse arguments from commandline
    args = parser.parse_args()

    # Start
    print('Start')

    # Prepare a list of video viewing page URLs.
    # By default, it downloads one episode.
    episodes: list[str] = [args.url]

    # When using the --series option, "gyaodl" downloads all episodes.
    # For example, when you give a URL representing the 3rd episode of the series
    # you want to see to "gyaodl" and that series has 12 episodes in total, "gyaodl"
    # downloads all episodes of the series. It means that you can download all of
    # the episodes from the 1st one to the 12th one at once.
    if args.series:
        episodes = get_available_episodes(args.url)

    for ep_url in episodes:
        # GYAO URL schema1: gyao.yahoo.co.jp/episode/{Japanese title(may be empty)}/{uuid}
        # GYAO URL schema2: gyao.yahoo.co.jp/title/{Japanese title(may be empty)}/{uuid}
        # Since uuid in URL path is not always same as gyao_videoid, I have to parse HTML source.
        gyao_video_info = gyao_url_to_video_info(ep_url)
        gyao_videoid = gyao_video_info['vid']
        logger.debug(f'gyao_videoid: {gyao_videoid}')

        # Convert gyao videoid to video id which is managed by brightcove.com
        # get_video_metadata returns { delivery_id, title }
        metadata = get_video_metadata(gyao_videoid)

        # Handle the condition that delivery_id is falsy.
        if not metadata.get('delivery_id') or len(metadata.get('delivery_id')) == 0:
            print(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
            logger.error(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
            return

        brightcove_id = metadata['delivery_id']
        title = metadata['title']

        print(f'Video found (Title:{title})')
        logger.debug(f'brightcove_id: {brightcove_id}')

        # Get a playlist
        playlist_url = get_playlist_url(brightcove_id)
        logger.debug(f'playlist_url: {playlist_url}')

        # Determine that function finished successfully or not.
        if len(playlist_url) == 0:
            print('Failed to get the playlist url.')
            logger.error('Failed to get the playlist url.')
            return

        if not urlparse(playlist_url).path.endswith('m3u8'):
            logger.error('The playlist URL format was different than expected.')
            print('The playlist URL format was different than expected.')
            logger.debug(f'URL: {playlist_url}')
            print(f'URL: {playlist_url}')
            return

        try:
            # Download
            saved_at = dl.dl_hls_stream(playlist_url, metadata['title'])
        except FileExistsError as eexist:
            logger.error(eexist)
            print(eexist)
            print('Skip')
        except Exception as e:
            logger.error(e)
        else:
            # Done
            print(f'The video has been saved. ({saved_at})')

    print('Done')
