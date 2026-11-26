"""Persistent operating preferences for the Host."""

import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
from threading import RLock


def control_dir():
    return Path(
        os.getenv("LIGHT_BELT_CONTROL_DIR", "~/.config/light-belt/control")
    ).expanduser()


class ControlConflict(ValueError):
    pass


class ControlPreferences:
    def __init__(self, directory):
        self.path = directory / "preferences.json" if directory is not None else None
        self.lock = RLock()
        self.token = secrets.token_urlsafe(16)
        self._unsaved = False
        self.recovery_error = None
        self.persistence_error = None
        self.data = {
            "mode": "auto",
            "intent": "follow",
            "volume": 0.5,
            "muted": False,
            "brightness": 0.5,
            "targets": {},
        }
        if self.path is None:
            return
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("preference document must be an object")
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            self.recovery_error = f"无法读取控制设置: {exc}"
            self.data.update(intent="off", muted=True)
            self._unsaved = True
        else:
            self._restore_valid_fields(stored)

    @property
    def saved(self):
        return not self._unsaved

    def _restore_valid_fields(self, stored):
        invalid = []
        for key in self.data.keys() & stored.keys():
            try:
                self.data[key] = self._normalize_field(key, stored[key])
            except ValueError:
                invalid.append(key)
                if key == "intent":
                    self.data[key] = "off"
                elif key == "muted":
                    self.data[key] = True
        if self.data["intent"] == "manual" and not self.data["targets"]:
            self.data["intent"] = "off"
            if "targets" not in invalid:
                invalid.append("targets")
        if invalid:
            self.recovery_error = f"控制设置字段无效: {', '.join(sorted(invalid))}"
            self._unsaved = True

    @staticmethod
    def _normalize_field(key, value):
        if key == "mode":
            value = "auto" if value == "device" else value
            valid = value in ("auto", "mic")
        elif key == "intent":
            valid = value in ("off", "follow", "manual", "music")
        elif key in ("volume", "brightness"):
            valid = type(value) in (int, float) and 0 <= value <= 1
        elif key == "muted":
            valid = type(value) is bool
        elif key == "targets":
            if not isinstance(value, dict):
                raise ValueError("Invalid control preference: targets")
            from . import engine_adapter
            targets = {}
            for strip, target in value.items():
                if (not isinstance(strip, str) or not strip or not isinstance(target, dict)
                        or target.get("target_id") != strip
                        or strip not in engine_adapter._valid_target_ids):
                    raise ValueError(f"Invalid stored target: {strip}")
                effect_type = target.get("effect_type", "static")
                raw_params = target.get("effect_params", {})
                if not isinstance(effect_type, str) or not isinstance(raw_params, dict):
                    raise ValueError(f"Invalid stored effect for target: {strip}")
                try:
                    params, error = engine_adapter._validate_effect_request(
                        strip, effect_type, raw_params
                    )
                except OverflowError as exc:
                    raise ValueError(f"Invalid stored effect for target: {strip}") from exc
                color = target.get("color", [1, 1, 1])
                speed, intensity = target.get("speed", 1.0), target.get("intensity", 1.0)
                if (error or not isinstance(color, list) or len(color) != 3
                        or any(type(channel) not in (int, float) or not 0 <= channel <= 1
                               for channel in color)
                        or type(speed) not in (int, float) or not 0 <= speed <= sys.float_info.max
                        or type(intensity) not in (int, float) or not 0 <= intensity <= sys.float_info.max):
                    raise ValueError(f"Invalid stored effect for target: {strip}")
                targets[strip] = {
                    "target_id": strip, "effect_type": effect_type, "effect_params": params,
                    "color": list(color), "speed": speed, "intensity": intensity,
                }
            value = targets
            valid = True
        else:
            valid = False
        if not valid:
            raise ValueError(f"Invalid control preference: {key}")
        return value

    def save(self, **changes):
        with self.lock:
            data = dict(self.data)
            data.update({key: self._normalize_field(key, value) for key, value in changes.items()})
            if data["intent"] == "manual" and not data["targets"]:
                raise ValueError("Manual lighting requires at least one target")
            if data == self.data and not self._unsaved:
                return
            if self.path is None:
                self.data = data
                return
            temporary = None
            try:
                self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                fd, temporary = tempfile.mkstemp(dir=self.path.parent)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, allow_nan=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            except OSError as exc:
                self.persistence_error = str(exc)
                self._unsaved = True
                raise
            finally:
                if temporary is not None:
                    Path(temporary).unlink(missing_ok=True)
            self.data = data
            self._unsaved = False
            self.persistence_error = None
            self.recovery_error = None

    def emergency_off(self):
        with self.lock:
            self.data = dict(self.data, intent="off")
            self._unsaved = True
            self.token = secrets.token_urlsafe(16)

    def set_mode(self, mode):
        self.save(mode=mode)

    def set_intent(self, intent, expected, **changes):
        if intent not in ("follow", "music", "manual", "off"):
            raise ValueError("未知的灯光设置")
        with self.lock:
            previous = self.data["intent"]
            if (intent != "off" and (previous == "off" or expected is not None)
                    and expected != self.token):
                raise ControlConflict("灯光设置已改变，请刷新")
            self.save(intent=intent, **changes)
            if intent == "off" or intent != previous:
                self.token = secrets.token_urlsafe(16)

