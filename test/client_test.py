import pytest
import responses
import json
from copy import deepcopy
from matrix_client.client import MatrixClient, Room, User
from matrix_client.api import MATRIX_V2_API_PATH
from . import response_examples

HOSTNAME = "http://example.com"


def test_create_client():
    MatrixClient("http://example.com")


def test_sync_token():
    client = MatrixClient("http://example.com")
    assert client.get_sync_token() is None
    client.set_sync_token("FAKE_TOKEN")
    assert client.get_sync_token() is "FAKE_TOKEN"


def test__mkroom():
    client = MatrixClient("http://example.com")

    roomId = "!UcYsUzyxTGDxLBEvLz:matrix.org"
    goodRoom = client._mkroom(roomId)

    assert isinstance(goodRoom, Room)
    assert goodRoom.room_id is roomId

    with pytest.raises(ValueError):
        client._mkroom("BAD_ROOM:matrix.org")
        client._mkroom("!BAD_ROOMmatrix.org")
        client._mkroom("!BAD_ROOM::matrix.org")


def test_get_rooms():
    client = MatrixClient("http://example.com")
    rooms = client.get_rooms()
    assert isinstance(rooms, dict)
    assert len(rooms) == 0

    client = MatrixClient("http://example.com")

    client._mkroom("!abc:matrix.org")
    client._mkroom("!def:matrix.org")
    client._mkroom("!ghi:matrix.org")

    rooms = client.get_rooms()
    assert isinstance(rooms, dict)
    assert len(rooms) == 3


def test_bad_state_events():
    client = MatrixClient("http://example.com")
    room = client._mkroom("!abc:matrix.org")

    ev = {
        "tomato": False
    }

    client._process_state_event(ev, room)


def test_state_event():
    client = MatrixClient("http://example.com")
    room = client._mkroom("!abc:matrix.org")

    room.name = False
    room.topic = False
    room.aliases = False

    ev = {
        "type": "m.room.name",
        "content": {}
    }

    client._process_state_event(ev, room)
    assert room.name is None

    ev["content"]["name"] = "TestName"
    client._process_state_event(ev, room)
    assert room.name is "TestName"

    ev["type"] = "m.room.topic"
    client._process_state_event(ev, room)
    assert room.topic is None

    ev["content"]["topic"] = "TestTopic"
    client._process_state_event(ev, room)
    assert room.topic is "TestTopic"

    ev["type"] = "m.room.aliases"
    client._process_state_event(ev, room)
    assert room.aliases is None

    aliases = ["#foo:matrix.org", "#bar:matrix.org"]
    ev["content"]["aliases"] = aliases
    client._process_state_event(ev, room)
    assert room.aliases is aliases

    # test member join event
    ev["type"] = "m.room.member"
    ev["content"] = {'membership': 'join', 'displayname': 'stereo'}
    ev["state_key"] = "@stereo:xxx.org"
    client._process_state_event(ev, room)
    assert len(room._members) == 1
    assert room._members[0].user_id == "@stereo:xxx.org"
    # test member leave event
    ev["content"]['membership'] = 'leave'
    client._process_state_event(ev, room)
    assert len(room._members) == 0


def test_get_user():
    client = MatrixClient("http://example.com")

    assert isinstance(client.get_user("@foobar:matrix.org"), User)

    with pytest.raises(ValueError):
        client.get_user("badfoobar:matrix.org")
        client.get_user("@badfoobarmatrix.org")
        client.get_user("@badfoobar:::matrix.org")


def test_get_download_url():
    client = MatrixClient("http://example.com")
    real_url = "http://example.com/_matrix/media/r0/download/foobar"
    assert client.api.get_download_url("mxc://foobar") == real_url

    with pytest.raises(ValueError):
        client.api.get_download_url("http://foobar")


def test_remove_listener():
    def dummy_listener():
        pass

    client = MatrixClient("http://example.com")
    handler = client.add_listener(dummy_listener)

    found_listener = False
    for listener in client.listeners:
        if listener["uid"] == handler:
            found_listener = True
            break

    assert found_listener, "listener was not added properly"

    client.remove_listener(handler)
    found_listener = False
    for listener in client.listeners:
        if listener["uid"] == handler:
            found_listener = True
            break

    assert not found_listener, "listener was not removed properly"


class TestClientRegister:
    cli = MatrixClient(HOSTNAME)

    @responses.activate
    def test_register_as_guest(self):
        cli = self.cli

        def _sync(self):
            self._sync_called = True
        cli.__dict__[_sync.__name__] = _sync.__get__(cli, cli.__class__)
        register_guest_url = HOSTNAME + MATRIX_V2_API_PATH + "/register"
        response_body = json.dumps({
            'access_token': 'EXAMPLE_ACCESS_TOKEN',
            'device_id': 'guest_device',
            'home_server': 'example.com',
            'user_id': '@455:example.com'
        })
        responses.add(responses.POST, register_guest_url, body=response_body)
        cli.register_as_guest()
        assert cli.token == cli.api.token == 'EXAMPLE_ACCESS_TOKEN'
        assert cli.hs == 'example.com'
        assert cli.user_id == '@455:example.com'
        assert cli._sync_called


def test_get_rooms_display_name():

    def add_members(api, room, num):
        for i in range(num):
            room._mkmembers(User(api, '@frho%s:matrix.org' % i, 'ho%s' % i))

    client = MatrixClient("http://example.com")
    client.user_id = "@frho0:matrix.org"
    room1 = client._mkroom("!abc:matrix.org")
    add_members(client.api, room1, 1)
    room2 = client._mkroom("!def:matrix.org")
    add_members(client.api, room2, 2)
    room3 = client._mkroom("!ghi:matrix.org")
    add_members(client.api, room3, 3)
    room4 = client._mkroom("!rfi:matrix.org")
    add_members(client.api, room4, 30)

    rooms = client.get_rooms()
    assert len(rooms) == 4
    assert room1.display_name == "Empty room"
    assert room2.display_name == "ho1"
    assert room3.display_name == "ho1 and ho2"
    assert room4.display_name == "ho1 and 28 others"


@responses.activate
def test_presence_listener():
    client = MatrixClient("http://example.com")
    accumulator = []

    def dummy_callback(event):
        accumulator.append(event)
    presence_events = [
        {
            "content": {
                "avatar_url": "mxc://localhost:wefuiwegh8742w",
                "currently_active": False,
                "last_active_ago": 2478593,
                "presence": "online",
                "user_id": "@example:localhost"
            },
            "event_id": "$WLGTSEFSEF:localhost",
            "type": "m.presence"
        },
        {
            "content": {
                "avatar_url": "mxc://localhost:weaugwe742w",
                "currently_active": True,
                "last_active_ago": 1478593,
                "presence": "online",
                "user_id": "@example2:localhost"
            },
            "event_id": "$CIGTXEFREF:localhost",
            "type": "m.presence"
        },
        {
            "content": {
                "avatar_url": "mxc://localhost:wefudweg13742w",
                "currently_active": False,
                "last_active_ago": 24795,
                "presence": "offline",
                "user_id": "@example3:localhost"
            },
            "event_id": "$ZEGASEDSEF:localhost",
            "type": "m.presence"
        },
    ]
    sync_response = deepcopy(response_examples.example_sync)
    sync_response["presence"]["events"] = presence_events
    response_body = json.dumps(sync_response)
    sync_url = HOSTNAME + MATRIX_V2_API_PATH + "/sync"

    responses.add(responses.GET, sync_url, body=response_body)
    callback_uid = client.add_presence_listener(dummy_callback)
    client._sync()
    assert accumulator == presence_events

    responses.add(responses.GET, sync_url, body=response_body)
    client.remove_presence_listener(callback_uid)
    accumulator = []
    client._sync()
    assert accumulator == []
