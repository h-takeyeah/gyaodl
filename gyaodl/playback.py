from dataclasses import asdict, dataclass, fields, is_dataclass
import json
from typing import Union
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GYAO_APPID = "dj00aiZpPUNJeDh2cU1RazU3UCZzPWNvbnN1bWVyc2VjcmV0Jng9NTk-"


@dataclass
class Delivery:
    id: str
    drm: bool

    def __post_init__(self):
        me=asdict(self)
        for f in fields(self):
            assert type(me[f.name]) == f.type, f'Cannot assign {me[f.name]} to {f.name}({f.type})'


@dataclass
class Video:
    id: str
    title: str
    delivery: Delivery

    def __post_init__(self):
        if not is_dataclass(self.delivery) and isinstance(self.delivery, dict):
            self.delivery = Delivery(**self.delivery)

        me=asdict(self)
        for f in fields(self):
            if f.name == 'delivery': # Skip type check
                continue
            assert type(me[f.name]) == f.type, f'Cannot assign {me[f.name]} to {f.name}({f.type})'


def get_video_metadata(gyao_videoid: str) -> Union[Video, None]:
    variables = json.dumps({
        "videoId": gyao_videoid,
        "logicaAgent": "PC_WEB",
        "clientSpaceId": "1183050133",
        "os": "UNKNOWN",
        "device": "PC",
    })
    graphql_query = (
        "query Playback($videoId: ID!, $logicaAgent: LogicaAgent!, "
        "$clientSpaceId: String!, $os: Os!, $device: Device!) "
        "{ content( parameter: { contentId: $videoId logicaAgent: $logicaAgent "
        "clientSpaceId: $clientSpaceId os: $os device: $device view: WEB } ) "
        "{ video { id title delivery { id drm } } } }"
    )
    query_parameters = {
        "appId": GYAO_APPID,  # appId
        "query": graphql_query,  # query string for GraphQL
        "variables": variables,  # variables for GraphQL(JSON formatted string)
    }

    # urlencode(): Encode a dict or sequence of two-element tuples into a URL query string.
    req = Request(f"https://gyao.yahoo.co.jp/apis/playback/graphql?{urlencode(query_parameters)}")

    with urlopen(req) as res:
        assert "json" in res.headers.get_content_type(), f"Unexpected Content-Type ({res.headers.get_content_type()})"
        parsed = json.loads(res.read())
        assert isinstance(parsed, dict), "Unexpected JSON schema"

        video = parsed.get("data", {}).get("content", {}).get("video")
        if isinstance(video, dict):
            return Video(**video)
        else:
            return None  # Not found.
