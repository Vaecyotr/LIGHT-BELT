import json

import pytest

from host_services import wled_brightness as wled


class Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode()


def test_scale_zero_uses_positive_brightness_and_confirms(monkeypatch):
    calls = []

    def open_url(request, timeout):
        calls.append(request)
        if isinstance(request, str):
            return Response({"on": True, "bri": 1})
        return Response({})

    monkeypatch.setattr(wled.urllib.request, "urlopen", open_url)
    result = wled.apply_managed([{"id": "strip", "host": "lamp"}], 0, 0.5)
    payload = json.loads(calls[0].data)
    assert payload == {"v": False, "on": True, "bri": 1}
    assert result[0]["submitted"] and result[0]["confirmed"]


def test_keep_off_stores_brightness_and_checks_both_off_signals(monkeypatch):
    calls = []

    def open_url(request, timeout):
        calls.append(request)
        if isinstance(request, str):
            return Response({"state": {"on": False, "bri": 128},
                             "info": {"live": False}})
        return Response({})

    monkeypatch.setattr(wled.urllib.request, "urlopen", open_url)
    result = wled.apply_managed([{"id": "strip", "host": "lamp"}], 0.5,
                                0.5, keep_off=True)
    assert json.loads(calls[0].data) == {"v": False, "on": False, "bri": 128}
    assert calls[1] == "http://lamp/json/si"
    assert result[0]["confirmed"] is True


@pytest.mark.parametrize("snapshot", [
    {"state": {"on": True, "bri": 128}, "info": {"live": False}},
    {"state": {"on": False, "bri": 128}, "info": {"live": True}},
])
def test_off_confirmation_requires_state_and_live_false(monkeypatch, snapshot):
    def open_url(request, timeout):
        return Response(snapshot if isinstance(request, str) else {})

    monkeypatch.setattr(wled.urllib.request, "urlopen", open_url)
    with pytest.raises(wled.ManagedStateError) as exc:
        wled.apply_managed([{"id": "strip", "host": "lamp"}], None, 0.5)
    assert exc.value.attempts[0]["submitted"] is True
    assert exc.value.attempts[0]["confirmed"] is False
    assert exc.value.attempts[0]["mismatch"]


def test_post_and_get_failures_are_distinguished(monkeypatch):
    calls = 0

    def open_url(request, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return Response({})
        raise OSError("readback unavailable")

    monkeypatch.setattr(wled.urllib.request, "urlopen", open_url)
    with pytest.raises(wled.ManagedStateError) as exc:
        wled.apply_managed([{"id": "strip", "host": "lamp"}], 0.5, 0.5)
    assert exc.value.attempts[0]["submitted"] is True
    assert exc.value.attempts[0]["readback_error"] == "readback unavailable"
    assert exc.value.attempts[0]["post_error"] is None

