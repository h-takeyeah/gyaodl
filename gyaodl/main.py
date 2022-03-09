# -*- coding: utf-8 -*-

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from html.parser import HTMLParser
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from http.client import HTTPResponse

from gyaodl import dl


program_version = '0.5'

GYAO_APPID = 'dj00aiZpPUNJeDh2cU1RazU3UCZzPWNvbnN1bWVyc2VjcmV0Jng9NTk-'
BRIGHTCOVE_ID_OF_GYAO = '4235717419001'
BRIGHTCOVE_API_PK = (
    'BCpkADawqM1O4pwi3SZ75b8DE1c2l78PZ418NByBa33h737r'
    'Wv6uhPJHYkaZ6xHINTj5oOqa0-zarOEvQ6e1EqKhBcCppkAU'
    'Wuo5QSKWVC4HZjY2z-Lo_ptwEK3hxfKuvZXkdNuyOM5nNSWy'
)


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


def gyao_url_to_video_info(url: str) -> str:
    res: HTTPResponse
    # If url is already encoded, it will be decoded before re-encoding.
    # If url is not encoded, it will be encoded.
    with urlopen(quote(unquote(url), safe='/:+')) as res:
        html_content = res.read()  # bytes
        if res.headers.get_content_charset():
            charset = res.headers.get_content_charset()
        else:
            charset = 'utf8'
        parser = VideoIdGetter()
        return parser.feed(html_content.decode(charset))


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
        assert 'json' in res.headers.get_content_type(), f'Unexpected Content-Type ({res.headers.get_content_type()})'
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
        assert 'json' in res.headers.get_content_type(), f'Unexpected Content-Type ({res.headers.get_content_type()})'
        parsed = json.loads(res.read())
        assert type(parsed) == dict and type(parsed.get('sources')) == list, 'Unexpected JSON schema'

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
    res: HTTPResponse
    # If url is already encoded, it will be decoded before re-encoding.
    # If url is not encoded, it will be encoded.
    with urlopen(quote(unquote(url), safe='/:+')) as res:
        html_content = res.read()  # bytes
        if res.headers.get_content_charset():
            charset = res.headers.get_content_charset()
        else:
            charset = 'utf8'
        parser = EndPointGetter()
        endpoint_path = parser.feed(html_content.decode(charset))

    # replace url.path with endpoint_path
    with urlopen(url.replace(urlparse(url).path, endpoint_path)) as res:
        assert 'json' in res.headers.get_content_type(), f'Unexpected Content-Type ({res.headers.get_content_type()})'

        json_body = json.loads(res.read())
        # The loaded JSON must be "dict" type, and its property "videos" must be "list" type.
        assert type(json_body) == dict and type(json_body.get('videos')) == list, 'Unexpected JSON schema'

        def _filter(v: dict) -> bool:
            # ensure "shortWebUrl" key exists
            if type(v) != dict or not v.get('shortWebUrl'):
                return False
            # streamingAvailability: the episode is publicly available or not yet
            elif str(v.get('streamingAvailability', "available")).lower() != "available":
                return False
            else:
                # The following blocks are meaningless if "streamingAvailabilty" was
                # determined based on the period from the start date to the end date.
                try:
                    start_date = datetime.fromisoformat(v.get('startDate', ''))
                    end_date = datetime.fromisoformat(v.get('endDate', ''))
                    if start_date.utcoffset():
                        now = datetime.now(timezone(start_date.utcoffset()))
                    else:
                        now = datetime.now()
                    return now >= start_date and now < end_date
                except ValueError: # Invalid isoformat string
                    pass

                # unknown rule
                return True

        # shorWebUrl: link to a video page (example https://gyao.yahoo.co.jp/episode/1234)
        return [v.get('shortWebUrl') for v in json_body.get('videos') if _filter(v)]


def is_expected_url(url: str) -> bool:
    if not re.match(r'^https://gyao.yahoo.co.jp/(episode|title)(/[^/]+/|/)[0-9a-z-]+$', url):
        return False

    return True


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
    fh = logging.FileHandler(script_installed_at.joinpath('application.log'), encoding='utf8', delay=True)
    fmt = logging.Formatter('%(asctime)s %(lineno)d %(levelname)s %(message)s')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.setLevel(logging.ERROR)

    # Parse arguments from commandline
    args = parser.parse_args()

    # Start
    print('Start')

    # Throws an error if the given URL does not follow a supported format
    if not is_expected_url(args.url):
        raise ValueError('Unexpected URL')

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
        try:
            # GYAO URL schema1: gyao.yahoo.co.jp/episode/{Japanese title(may be empty)}/{uuid}
            # GYAO URL schema2: gyao.yahoo.co.jp/title/{Japanese title(may be empty)}/{uuid}
            # Since uuid in URL path is not always same as gyao_videoid, I have to parse HTML source.
            gyao_videoid = gyao_url_to_video_info(ep_url)

            # Without --series option, the episode may be unavailable
            # because we skipped check by get_available_episodes().
            if len(gyao_videoid) == 0:
                print('This episode is not available yet or vid not found')
                continue

            logger.debug(f'gyao_videoid: {gyao_videoid}')

            # Convert gyao videoid to video id which is managed by brightcove.com
            # get_video_metadata returns { delivery_id, title }
            metadata = get_video_metadata(gyao_videoid)

            # Handle the condition that delivery_id is falsy.
            if not metadata.get('delivery_id') or len(metadata.get('delivery_id')) == 0:
                print(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
                logger.error(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
                continue

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
                continue

            if not urlparse(playlist_url).path.endswith('m3u8'):
                logger.error('The playlist URL format was different than expected.')
                print('The playlist URL format was different than expected.')
                logger.debug(f'URL: {playlist_url}')
                print(f'URL: {playlist_url}')
                continue

            try:
                # Download
                saved_at = dl.dl_hls_stream(playlist_url, metadata['title'])
            except FileExistsError as eexist:
                print(eexist)
                print('Skip')
            except Exception as e:
                logger.error(e)
            else:
                # Done
                print(f'The video has been saved. ({saved_at})')

        except AssertionError as ae:
            print(ae)
            continue

    print('Done')
