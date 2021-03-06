# -*- coding: utf-8 -*-

import argparse
import logging
import re
from datetime import datetime, timezone
from http.client import NOT_FOUND
from pathlib import Path
from urllib.error import HTTPError

from gyaodl import dl, playback, programs

program_version = '0.5'


def is_available_episode(v: programs.Video) -> bool:
    # streamingAvailability: the episode is publicly available or not yet
    if v.streamingAvailability.lower() == 'available':
        return True
    else:
        # The following blocks are meaningless if "streamingAvailabilty" was
        # determined based on the period from the start date to the end date.
        try:
            start_date = datetime.fromisoformat(v.startDate)
            end_date = datetime.fromisoformat(v.endDate)
            if start_date.utcoffset():
                now = datetime.now(timezone(start_date.utcoffset()))
            else:
                now = datetime.now()
            return now >= start_date and now < end_date
        except ValueError: # Invalid isoformat string
            pass

        # unknown rule
        return False


def is_valid_url(url: str) -> bool:
    '''
    Validate URL format

    GYAO URL schema1: gyao.yahoo.co.jp/episode/{Japanese title(may be empty)}/{uuid}
    GYAO URL schema2: gyao.yahoo.co.jp/title/{Japanese title(may be empty)}/{uuid}
    '''
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
    if not is_valid_url(args.url):
        raise ValueError('Unexpected URL')

    # Prepare a list of video viewing page URLs.
    # By default, it downloads one episode.
    try:
        episodes: list[programs.Video] = programs.get_episodes(args.url, args.series)
    except HTTPError as e:
        if e.code == NOT_FOUND:
            print('Requested episode or series not found')
        else:
            print(e.reason)
            logger.error(e.reason)
        return

    # When using the --series option, "gyaodl" downloads all episodes.
    # For example, when you give a URL representing the 3rd episode of the series
    # you want to see to "gyaodl" and that series has 12 episodes in total, "gyaodl"
    # downloads all episodes of the series. It means that you can download all of
    # the episodes from the 1st one to the 12th one at once.

    for ep in episodes:
        try:
            if not is_available_episode(ep):
                print(f'{ep.title} [availability: {ep.streamingAvailability}] [{ep.startDate} ~ {ep.endDate}]')
                continue

            gyao_videoid = ep.id
            logger.debug(f'gyao_videoid: {gyao_videoid}')

            # Convert gyao videoid to video id which is managed by brightcove.com
            metadata: playback.Video = playback.get_video_metadata(gyao_videoid)

            # Handle the condition that metadata is None
            if metadata is None:
                print(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
                logger.error(f'Failed to get the metadata with gyao_videoid({gyao_videoid})')
                continue

            brightcove_id = metadata.delivery.id
            title = metadata.title

            print(f'Video found (Title:{title})')
            logger.debug(f'brightcove_id: {brightcove_id}')

            # Get a playlist
            playlist_url = playback.get_playlist_url(brightcove_id)
            logger.debug(f'playlist_url: {playlist_url}')

            # Determine that function finished successfully or not.
            if len(playlist_url) == 0:
                print('Failed to get the playlist url.')
                logger.error('Failed to get the playlist url.')
                continue


            try:
                # Download
                saved_at = dl.dl_hls_stream(playlist_url, metadata.title)
            except FileExistsError as eexist:
                print(eexist)
                print('Skip')
            except Exception as e:
                logger.error(e)
            else:
                # Done
                print(f'The video has been saved. ({saved_at})')

        except HTTPError as e:
            if e.code == NOT_FOUND:
                print('Requested episode or series not found')
            else:
                print(e.reason)
                logger.error(e.reason)

        except AssertionError as ae:
            print(ae)

    print('Done')
