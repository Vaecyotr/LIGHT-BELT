import json
import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from host_services import engine_adapter as host
from host_services.real_engine_adapter import RealEngineAdapter


class ReplySocket:
    def __init__(self, replies):
        self.replies = replies

    def settimeout(self, value):
        pass

    def connect(self, path):
        pass

    def sendall(self, payload):
        request = json.loads(payload)
        self.chunks = iter(self.replies(request['request_id']))

    def recv(self, size):
        return next(self.chunks, b'')

    def close(self):
        pass


def test_ipc_matches_fragmented_reply_after_unrelated_messages():
    def replies(request_id):
        response = json.dumps({'request_id': request_id, 'error': 'success', 'data': 17}).encode()
        return [b'{"event":"pause"}\n{"request_id":999,"error":"success"}\n' + response[:9],
                response[9:] + b'\n{"event":"idle"}\n']

    client = host.MpvClient('socket', socket_factory=lambda: ReplySocket(replies))
    assert client._send(['get_property', 'volume'])['data'] == 17


def test_ipc_command_rejection_is_not_silently_successful():
    client = host.MpvClient('socket', socket_factory=lambda: ReplySocket(
        lambda rid: [json.dumps({'request_id': rid, 'error': 'command failed'}).encode() + b'\n']))
    with pytest.raises(host.MpvUnavailableError, match='command failed'):
        client.pause()


def test_ipc_eof_before_matching_reply_is_an_error():
    client = host.MpvClient('socket', socket_factory=lambda: ReplySocket(
        lambda _: [b'{"event":"idle"}\n']))
    result = client._send(['stop'])
    assert 'closed' in result['error']


def test_ipc_ignores_unmatched_reply_before_eof():
    client = host.MpvClient('socket', socket_factory=lambda: ReplySocket(
        lambda _: [b'{"request_id":22,"error":"success"}\n']))
    assert 'closed' in client._send(['stop'])['error']


def test_failed_pause_does_not_change_playback_state(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    mpv = MagicMock()
    mpv.pause.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    data, error = host.playback_pause()
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['playback_state'] == 'playing'


def test_failed_reset_resume_does_not_report_playing(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'paused')
    monkeypatch.setattr(host, '_real_adapter', None)
    mpv = MagicMock()
    mpv.resume.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_mpv', mpv)
    data, error = host.playback_reset()
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['playback_state'] == 'paused'


def test_failed_termination_refuses_new_output_process():
    adapter = RealEngineAdapter('profile', 'socket')
    proc = MagicMock()
    proc.poll.return_value = None
    proc.terminate.side_effect = OSError('denied')
    adapter._playback_proc = proc
    with patch('host_services.real_engine_adapter.subprocess.Popen') as popen:
        with pytest.raises(RuntimeError, match='playback engine'):
            adapter.on_playback_start({'show_yaml': 'show.yaml'}, None)
    popen.assert_not_called()


def test_play_preserves_manual_ownership_if_old_engine_cannot_stop(monkeypatch):
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 1000, 'media_path': 'movie.mp4'})
    monkeypatch.setattr(host, '_refresh_wled_profile', lambda **_: None)
    monkeypatch.setattr(host, '_manual_targets', {'strip': {'target_id': 'strip'}})
    real = MagicMock()
    real.on_playback_stop.side_effect = RuntimeError('cannot stop')
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_play('show', None)
    assert data is None and error == 'ENGINE_UNAVAILABLE'
    assert host._manual_targets == {'strip': {'target_id': 'strip'}}


def test_stale_socket_is_not_removed_if_owned_mpv_cannot_stop(monkeypatch):
    monkeypatch.setattr(host.socket, 'AF_UNIX', 123, raising=False)
    probe = MagicMock()
    probe.connect.side_effect = ConnectionRefusedError('stale')
    monkeypatch.setattr(host.socket, 'socket', lambda *_: probe)
    monkeypatch.setattr(host.os.path, 'exists', lambda _: True)
    unlink = MagicMock()
    monkeypatch.setattr(host.os, 'unlink', unlink)
    proc = MagicMock()
    proc.poll.return_value = None
    proc.terminate.side_effect = OSError('denied')
    monkeypatch.setattr(host, '_mpv_proc', proc)
    with pytest.raises(host.MpvUnavailableError):
        host._ensure_mpv()
    unlink.assert_not_called()


def test_missing_socket_does_not_start_second_mpv_when_old_process_will_not_stop(monkeypatch):
    monkeypatch.setattr(host.os.path, 'exists', lambda _: False)
    monkeypatch.setattr(host.os, 'makedirs', MagicMock())
    monkeypatch.setattr(host, '_wait_until', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(host, 'MpvClient', lambda _path: MagicMock())
    proc = MagicMock()
    proc.poll.return_value = None
    proc.terminate.side_effect = OSError('denied')
    monkeypatch.setattr(host, '_mpv_proc', proc)
    popen = MagicMock()
    monkeypatch.setattr(host.subprocess, 'Popen', popen)
    with pytest.raises(host.MpvUnavailableError):
        host._ensure_mpv()
    popen.assert_not_called()


def test_video_media_is_passed_to_engine_on_start_and_resume(monkeypatch):
    adapter = RealEngineAdapter('profile', 'socket')
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stderr = iter([])
    monkeypatch.setattr('host_services.real_engine_adapter.time.sleep', lambda _: None)
    monkeypatch.setattr('host_services.real_engine_adapter._await_engine_ready', lambda *_args, **_kwargs: True)
    with patch('host_services.real_engine_adapter.subprocess.Popen', return_value=proc) as popen:
        adapter.on_playback_start({'show_yaml': 'show.yaml', 'media_path': 'movie.mp4'}, None)
        assert '--video' in popen.call_args.args[0]
        adapter.on_playback_resume_yaml()
        assert '--video' in popen.call_args.args[0]


def test_play_failure_does_not_report_playing(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'stopped')
    monkeypatch.setattr(host, '_find_show', lambda _: {'media_path': 'movie.mp4', 'duration_ms': 1000})
    monkeypatch.setattr(host, '_real_adapter', None)
    mpv = MagicMock()
    mpv.play_file.side_effect = host.MpvUnavailableError('load rejected')
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    data, error = host.playback_play('show', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['playback_state'] == 'stopped'


def test_new_mpv_replays_desired_audio(monkeypatch):
    monkeypatch.setitem(host._state, 'volume', 0.17)
    monkeypatch.setitem(host._state, 'muted', True)
    monkeypatch.setattr(host, '_mpv', None)
    monkeypatch.setattr(host.os.path, 'exists', lambda _: True)
    probe = MagicMock()
    monkeypatch.setattr(host.socket, 'AF_UNIX', 123, raising=False)
    monkeypatch.setattr(host.socket, 'socket', lambda *_: probe)
    client = MagicMock()
    monkeypatch.setattr(host, 'MpvClient', lambda _: client)
    assert host._ensure_mpv() is client
    client.set_volume.assert_called_once_with(0.17)
    client.set_mute.assert_called_once_with(True)


def test_audio_rejection_reports_error_and_retains_desired_value(monkeypatch):
    client = MagicMock()
    client.set_volume.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_mpv', client)
    data, error = host.audio_set(0.17, None, 0)
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['volume'] == 0.17


def test_play_reports_engine_launch_failure_without_playing_state(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'stopped')
    monkeypatch.setattr(host, '_find_show', lambda _: {'media_path': None, 'duration_ms': 1000})
    monkeypatch.setattr(host, '_mpv', None)
    monkeypatch.setattr(host, '_refresh_wled_profile', lambda **_: None)
    real = MagicMock()
    real.on_playback_start.side_effect = RuntimeError('engine launch failed')
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_play('show', None)
    assert data is None and error == 'ENGINE_UNAVAILABLE'
    assert host._state['playback_state'] == 'stopped'


def test_stale_watchdog_result_does_not_stop_new_session(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setitem(host._state, 'show_id', 'new')
    monkeypatch.setattr(host, '_session_generation', 2)
    host._finalize_natural_end(expected_generation=1)
    assert host._state['show_id'] == 'new'
    assert host._state['playback_state'] == 'playing'


def test_real_play_rejects_missing_media_before_replacing_session(monkeypatch, tmp_path):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setattr(host, '_find_show', lambda _: {
        'show_id': 'bad', 'duration_ms': 1000, 'media_path': str(tmp_path / 'missing.mp4')})
    real = MagicMock()
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_play('bad', None)
    assert data is None and error == 'CONTENT_NOT_READY'
    real.on_playback_stop.assert_not_called()
    assert host._state['playback_state'] == 'playing'


def test_real_yaml_only_is_rejected_before_replacing_session(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setattr(host, '_find_show', lambda _: {
        'show_id': 'yaml-only', 'duration_ms': 0, 'show_yaml': 'show.yaml'})
    real = MagicMock()
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_play('yaml-only', None)
    assert data is None and error == 'CONTENT_NOT_READY'
    real.on_playback_stop.assert_not_called()
    assert host._state['playback_state'] == 'playing'


def test_content_validation_accepts_video_only_and_rejects_invalid_yaml(monkeypatch, tmp_path):
    from host_services import shows_loader
    media = tmp_path / 'movie.mp4'
    media.write_bytes(b'fixture')
    monkeypatch.setattr(shows_loader, '_probe_duration_ms', lambda _: 1000)
    assert host._validate_playback_content({'media_path': str(media)}) is None
    bad_yaml = tmp_path / 'bad.yaml'
    bad_yaml.write_text('schema_version: [', encoding='utf-8')
    assert 'invalid show' in host._validate_playback_content({
        'media_path': str(media), 'show_yaml': str(bad_yaml)})


def test_media_is_stopped_when_post_load_command_fails(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'mock')
    monkeypatch.setattr(host, '_find_show', lambda _: {
        'duration_ms': 1000, 'media_path': 'movie.mp4', 'audio_path': 'track.wav'})
    monkeypatch.setattr(host, '_real_adapter', None)
    monkeypatch.setattr(host, '_wait_until', lambda *_args, **_kwargs: True)
    mpv = MagicMock()
    mpv.add_audio_track.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    data, error = host.playback_play('show', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    mpv.stop.assert_called_once()


def test_replay_failure_during_switch_stops_previous_media(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'mock')
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 1000, 'media_path': 'new.mp4'})
    monkeypatch.setattr(host, '_real_adapter', None)
    old_mpv = MagicMock()
    monkeypatch.setattr(host, '_mpv', old_mpv)
    def fail_replay():
        raise host.MpvUnavailableError('volume rejected')
    monkeypatch.setattr(host, '_ensure_mpv', fail_replay)
    data, error = host.playback_play('new', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    old_mpv.stop.assert_called_once()


def test_ensure_failure_cleans_client_created_during_attempt(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'mock')
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 1000, 'media_path': 'new.mp4'})
    monkeypatch.setattr(host, '_real_adapter', None)
    monkeypatch.setattr(host, '_mpv', None)
    created = MagicMock()
    def fail_replay():
        host._mpv = created
        raise host.MpvUnavailableError('volume rejected')
    monkeypatch.setattr(host, '_ensure_mpv', fail_replay)
    data, error = host.playback_play('new', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    created.stop.assert_called_once()


def test_shutdown_still_stops_owned_mpv_if_engine_cleanup_fails(monkeypatch):
    monkeypatch.setattr(host, '_watchdog_thread', None)
    monkeypatch.setattr(host, '_watchdog_stop', threading.Event())
    monkeypatch.setattr(host, '_mpv_observer', None)
    real = MagicMock()
    real.on_playback_stop.side_effect = RuntimeError('engine did not stop')
    monkeypatch.setattr(host, '_real_adapter', real)
    proc = MagicMock()
    proc.poll.return_value = None
    monkeypatch.setattr(host, '_mpv_proc', proc)
    with pytest.raises(RuntimeError, match='engine did not stop'):
        host.shutdown()
    proc.terminate.assert_called_once()


def test_active_session_does_not_recreate_missing_mpv(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(host, '_mpv', None)
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    ensure = MagicMock()
    monkeypatch.setattr(host, '_ensure_mpv', ensure)
    data, error = host.playback_pause()
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['playback_state'] == 'error'
    ensure.assert_not_called()


def test_start_resume_rejection_reports_mpv_error_and_stops_outputs(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 1000, 'media_path': 'movie.mp4'})
    monkeypatch.setattr(host, '_validate_playback_content', lambda _: None)
    monkeypatch.setattr(host, '_refresh_wled_profile', lambda **_: None)
    real = MagicMock()
    monkeypatch.setattr(host, '_real_adapter', real)
    mpv = MagicMock()
    mpv.resume.side_effect = host.MpvUnavailableError('resume rejected')
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    ready = MagicMock()
    ready.wait.return_value = True
    observer = {'loaded': ready, 'load_error': None, 'stop': MagicMock(), 'socket': MagicMock()}
    monkeypatch.setattr(host, '_start_mpv_observer', lambda *_: setattr(host, '_mpv_observer', observer))
    data, error = host.playback_play('show', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert real.on_playback_stop.call_count == 2
    mpv.stop.assert_called_once()


def test_real_start_waits_for_seek_before_starting_engine(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 10000, 'media_path': 'movie.mp4'})
    monkeypatch.setattr(host, '_validate_playback_content', lambda _: None)
    monkeypatch.setattr(host, '_refresh_wled_profile', lambda **_: None)
    monkeypatch.setattr(host, '_push_brightness_scale', lambda: None)
    monkeypatch.setattr(host, '_mark_devices_output', lambda: None)
    calls = []
    real = MagicMock()
    real.on_playback_start.side_effect = lambda *_: calls.append('engine')
    monkeypatch.setattr(host, '_real_adapter', real)
    mpv = MagicMock()
    mpv.pause.side_effect = lambda: calls.append('pause')
    mpv.seek.side_effect = lambda _: calls.append('seek')
    mpv.resume.side_effect = lambda: calls.append('resume')
    mpv.get_duration.return_value = 10
    mpv._send.return_value = {'error': 'success', 'data': 2.0}
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    ready = MagicMock()
    ready.wait.return_value = True
    observer = {'loaded': ready, 'load_error': None, 'stop': MagicMock(), 'socket': MagicMock()}
    monkeypatch.setattr(host, '_start_mpv_observer', lambda *_: setattr(host, '_mpv_observer', observer))
    data, error = host.playback_play('show', 2000)
    assert error is None and data['playback_state'] == 'playing'
    assert calls == ['pause', 'seek', 'engine', 'resume']
    host._close_mpv_observer()


def test_mpv_end_error_is_reported_only_for_current_entry(monkeypatch):
    events = []
    import host_services.ws as ws
    monkeypatch.setattr(ws, 'publish_error', events.append, raising=False)
    monkeypatch.setattr(host, '_session_generation', 3)
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setitem(host._state, 'show_id', 'new')
    monkeypatch.setattr(host, '_real_adapter', None)
    monkeypatch.setattr(host, '_mpv_proc', None)
    monkeypatch.setattr(host, '_mpv', None)
    observer = {'entry_id': None}
    host._handle_mpv_event({'event': 'start-file', 'playlist_entry_id': 8}, 3, observer)
    host._handle_mpv_event({'event': 'end-file', 'playlist_entry_id': 7, 'reason': 'error'}, 3, observer)
    assert host._state['playback_state'] == 'playing'
    host._handle_mpv_event({'event': 'end-file', 'playlist_entry_id': 8, 'reason': 'error', 'file_error': 'decode failed'}, 3, observer)
    assert host._state['playback_state'] == 'error'
    assert events and events[0]['code'] == 'MEDIA_ERROR'


def test_observer_reads_fragmented_events_and_reports_async_error(monkeypatch):
    import host_services.ws as ws
    delivered = threading.Event()
    messages = []
    monkeypatch.setattr(ws, 'publish_error', lambda value: (messages.append(value), delivered.set()))
    monkeypatch.setattr(host, '_session_generation', 31)
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setattr(host, '_real_adapter', None)
    monkeypatch.setattr(host, '_mpv_proc', None)
    monkeypatch.setattr(host, '_mpv', None)
    monkeypatch.setattr(host.socket, 'AF_UNIX', 123, raising=False)
    sock = ReplySocket(lambda _: [])
    sock.chunks = iter([b'{"event":"start-file","playlist_entry_id":8}\n{"event":"file-',
                        b'loaded"}\n{"event":"end-file","playlist_entry_id":8,"reason":"error","file_error":"decode"}\n'])
    monkeypatch.setattr(host.socket, 'socket', lambda *_: sock)
    observer = host._start_mpv_observer('socket', 31)
    assert observer['loaded'].wait(2)
    assert delivered.wait(2)
    assert messages[0]['message'] == 'decode'
    assert host._state['playback_state'] == 'error'
    host._close_mpv_observer()
    observer['thread'].join(2)


def test_engine_health_distinguishes_early_exit_and_completed_show(monkeypatch):
    adapter = RealEngineAdapter('profile', 'socket')
    proc = MagicMock()
    proc.poll.return_value = 0
    adapter._playback_proc = proc
    adapter._active_show = {'duration_ms': 305000}
    adapter._playback_started_at = 100.0
    monkeypatch.setattr('host_services.real_engine_adapter.time.monotonic', lambda: 110.0)
    assert adapter.process_failure() is not None
    monkeypatch.setattr('host_services.real_engine_adapter.time.monotonic', lambda: 405.0)
    assert adapter.process_failure() is None
    proc.poll.return_value = 1
    assert adapter.process_failure() is not None


def test_media_engine_completion_uses_current_position_after_seek_or_pause():
    adapter = RealEngineAdapter('profile', 'socket')
    adapter._playback_proc = MagicMock()
    adapter._playback_proc.poll.return_value = 0
    adapter._active_show = {'duration_ms': 305000, 'media_path': 'movie.mp4'}
    adapter._playback_started_at = 100.0
    assert adapter.process_failure(position_ms=304500) is None
    assert adapter.process_failure(position_ms=200000) is not None
    assert adapter.process_failure(position_ms=None) is None


def test_manual_engine_exit_is_reported(monkeypatch):
    adapter = RealEngineAdapter('profile', 'socket')
    adapter._manual_proc = MagicMock()
    adapter._manual_proc.poll.return_value = 0
    assert 'manual' in adapter.process_failure()


def test_immediate_engine_exit_is_reported(monkeypatch):
    adapter = RealEngineAdapter('profile', 'socket')
    proc = MagicMock()
    proc.poll.return_value = 1
    proc.returncode = 1
    proc.stderr = iter([])
    monkeypatch.setattr('host_services.real_engine_adapter.time.sleep', lambda _: None)
    monkeypatch.setattr('host_services.real_engine_adapter._await_engine_ready', lambda *_args, **_kwargs: True)
    with patch('host_services.real_engine_adapter.subprocess.Popen', return_value=proc):
        with pytest.raises(RuntimeError, match='exited'):
            adapter.on_playback_start({'show_yaml': 'show.yaml'}, None)


def test_engine_readiness_requires_marker_and_continues_draining(monkeypatch):
    from host_services import real_engine_adapter as real
    proc = MagicMock()
    drained = threading.Event()
    def output():
        yield b'initializing\n'
        yield b'LIGHT_BELT_ENGINE_READY\n'
        yield b'after-ready\n'
        drained.set()
    proc.stdout = output()
    assert real._await_engine_ready(proc, timeout=1)
    assert drained.wait(1)


def test_engine_eof_before_ready_is_failure():
    from host_services import real_engine_adapter as real
    proc = MagicMock()
    proc.stdout = iter([b'initializing\n'])
    assert not real._await_engine_ready(proc, timeout=1)


def test_engine_without_ready_marker_is_stopped_before_failure():
    adapter = RealEngineAdapter('profile', 'socket')
    proc = MagicMock()
    proc.poll.return_value = None
    proc.stdout = iter([b'no readiness marker\n'])
    proc.stderr = iter([])
    with patch('host_services.real_engine_adapter.subprocess.Popen', return_value=proc):
        with pytest.raises(RuntimeError, match='before ready'):
            adapter.on_playback_start({'show_yaml': 'show.yaml'}, None)
    proc.terminate.assert_called_once()


def test_real_play_does_not_report_ready_without_file_loaded(monkeypatch):
    monkeypatch.setattr(host, 'ENGINE_ADAPTER', 'real')
    monkeypatch.setitem(host._state, 'playback_state', 'stopped')
    monkeypatch.setattr(host, '_find_show', lambda _: {'duration_ms': 1000, 'media_path': 'movie.mp4'})
    monkeypatch.setattr(host, '_validate_playback_content', lambda _: None)
    monkeypatch.setattr(host, '_refresh_wled_profile', lambda **_: None)
    monkeypatch.setattr(host, '_real_adapter', MagicMock())
    monkeypatch.setattr(host, '_ensure_mpv', lambda: MagicMock())
    ready = MagicMock()
    ready.wait.return_value = False
    observer = {'loaded': ready, 'load_error': None, 'stop': MagicMock(), 'socket': MagicMock()}
    monkeypatch.setattr(host, '_start_mpv_observer', lambda *_: setattr(host, '_mpv_observer', observer))
    data, error = host.playback_play('show', None)
    assert data is None and error == 'MEDIA_NOT_READY'
    assert host._state['playback_state'] == 'stopped'


def test_stop_reports_failure_when_engine_does_not_exit(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setattr(host, '_mpv', None)
    real = MagicMock()
    real.on_playback_stop.side_effect = RuntimeError('cannot stop')
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_stop()
    assert data is None and error == 'ENGINE_UNAVAILABLE'
    assert host._state['playback_state'] == 'error'


def test_stop_media_failure_preserves_error_state_for_retry(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    monkeypatch.setitem(host._state, 'show_id', 'show')
    real = MagicMock()
    monkeypatch.setattr(host, '_real_adapter', real)
    mpv = MagicMock()
    mpv.stop.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_mpv', mpv)
    data, error = host.playback_stop()
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['playback_state'] == 'error'
    assert host._state['show_id'] == 'show'


def test_seek_pauses_and_restarts_lighting_around_media_seek(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'playing')
    calls = []
    mpv = MagicMock()
    mpv.pause.side_effect = lambda: calls.append('pause')
    mpv.seek.side_effect = lambda _: calls.append('seek')
    mpv.resume.side_effect = lambda: calls.append('resume')
    mpv._send.return_value = {'error': 'success', 'data': 1.234}
    monkeypatch.setattr(host, '_ensure_mpv', lambda: mpv)
    real = MagicMock()
    real.on_playback_seek_prepare.side_effect = lambda: calls.append('stop-engine')
    real.on_playback_resume_yaml.side_effect = lambda: calls.append('start-engine') or True
    monkeypatch.setattr(host, '_real_adapter', real)
    data, error = host.playback_seek(1234)
    assert error is None and data['position_ms'] == 1234
    assert calls == ['pause', 'stop-engine', 'seek', 'start-engine', 'resume']


def test_scene_audio_failure_does_not_report_scene_applied(monkeypatch):
    monkeypatch.setitem(host._state, 'playback_state', 'stopped')
    monkeypatch.setattr(host, '_scenes', {'scene': {'entries': [], 'audio': {'volume': 0.17}}})
    client = MagicMock()
    client.set_volume.side_effect = host.MpvUnavailableError('rejected')
    monkeypatch.setattr(host, '_mpv', client)
    data, error = host.scene_apply('scene', None)
    assert data is None and error == 'MPV_UNAVAILABLE'
    assert host._state['scene_id'] != 'scene'
