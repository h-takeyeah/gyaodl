# GYAO! video downloader cli

Take GYAO! video URL, try to find out HLS stream and save it as a mp4 file.

## Usage

**NOTE:** URL must be in `^https://gyao.yahoo.co.jp/(episode|title)(/[^/]+/|/)[0-9a-z-]+$` format.

```sh
python3 -m gyaodl [URL]
```

- Output file will be created where you run the command.
- No options for video quality. Always the best stream will be used.

## Installation

Following commands installs `gyaodl` as global one.

- Windows10

```pwsh
py -3 -m pip install wheel # If not installed
py -3 setup.py sdist
py -3 -m pip install .\dist\gyaodl-{version}.tar.gz
```

- Linux

```sh
pip3 install wheel # If not installed
python3 setup.py sdist
pip3 install .\dist\gyaodl-{version}.tar.gz
```

**Note:** Run these commands at the directory where `setup.py` exists. Not inside gyaodl module direcotry(which holds `__init__.py`).

### Requirements(other than Python)

- ffmpeg >= 4.1

[FFmpeg](https://ffmpeg.org/) is used for handling HLS stream.

## Note

You can try the command before `pip install`.

- Windows10

```pwsh
py -3 -m gyaodl [URL]
```

- Linux

```sh
python3 -m gyaodl [URL]
```

**Note:** Run above commands at the directory where `setup.py` exists. Not inside gyaodl module direcotry(which holds `__init__.py`).

---

To get the schema of GYAO API, you can use [get-graphql-schema](https://github.com/prisma-labs/get-graphql-schema) (Install through npm).

```sh
get-graphql-schema https://gyao.yahoo.co.jp/apis/playback/graphql?appId=dj00aiZpPUNJeDh2cU1RazU3UCZzPWNvbnN1bWVyc2VjcmV0Jng9NTk-
```

## Escape clause

I can't take responsibility or liability for any consequences resulting from use of this software.
