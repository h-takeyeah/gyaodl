# -*- coding: utf-8 -*-

import platform
import shlex
import subprocess
from pathlib import Path
from time import sleep

p_name = platform.system()

# Path to directory where this script is being executed
DIR = Path('.').resolve()


def cmd_exists(cmd: str) -> bool:

    if p_name == 'Windows':
        if subprocess.run(['where', '/Q', cmd]).returncode == 0:
            return True
    elif p_name == 'Darwin' or p_name == 'Linux':
        if subprocess.run(['which', cmd], stdout=subprocess.DEVNULL).returncode == 0:
            return True
    else:
        raise Exception(f'This platform( {p_name} ) is not supported')

    return False


def dl_hls_stream(pl_url: str, title: str) -> str:

    # Check command existence
    if not cmd_exists('ffmpeg'):
        raise Exception('ffmpeg not found')
    elif not cmd_exists('streamlink'):
        raise Exception('streamlink not found')

    # Replace invalid characters with '_'.
    invalid_chars = [' ', '\u3000', '\\', '/', ':', ';', '*', '?', '"', '<', '>', '|', '%', '’']
    trimed_title = title.translate(str.maketrans({k: '_' for k in invalid_chars}))

    file_path = DIR.joinpath(trimed_title)

    # Save HLS stream to mp4
    subprocess.run(args=shlex.split(
        f'ffmpeg -i {pl_url} -c copy -movflags faststart {file_path}.mp4 -loglevel fatal', posix=(p_name != 'Windows')))  # posix: Avoid stripping backslash(Windows).
    sleep(2)

    # chmod
    if p_name == 'Darwin' or p_name == 'Linux':
        for f in list(DIR.glob('*.mp4')):
            f.chmod(0o644)

    # Return the saved path
    return f'{file_path}.mp4'
