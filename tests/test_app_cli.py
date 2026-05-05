from __future__ import annotations

import whisper_turbo_desktop.app as app_module


def test_version_flag_returns_without_creating_qapplication(monkeypatch, capsys) -> None:
    def fail_qapplication(_argv):
        raise AssertionError("version flag must not create QApplication")

    monkeypatch.setattr(app_module, "__version__", "1.2.3")
    monkeypatch.setattr(app_module, "QApplication", fail_qapplication)

    assert app_module.main(["--version"]) == 0

    assert capsys.readouterr().out.strip() == "Whisper Turbo Desktop 1.2.3"


def test_unknown_cli_argument_returns_without_creating_qapplication(monkeypatch, capsys) -> None:
    def fail_qapplication(_argv):
        raise AssertionError("unknown CLI argument must not create QApplication")

    monkeypatch.setattr(app_module, "QApplication", fail_qapplication)

    assert app_module.main(["-c", "print('diagnostics')"]) == 2

    captured = capsys.readouterr()
    assert "Unsupported argument" in captured.err


def test_second_instance_returns_without_creating_main_window(monkeypatch) -> None:
    class FakeApplication:
        def __init__(self, _argv):
            pass

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setStyle(self, _style_name):
            pass

    class LockedInstanceGuard:
        def already_running(self) -> bool:
            return True

    def fail_main_window(*args, **kwargs):
        raise AssertionError("second instance must not create MainWindow")

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "SingleInstanceGuard", lambda: LockedInstanceGuard())
    monkeypatch.setattr(app_module, "MainWindow", fail_main_window)

    assert app_module.main([]) == 0


def test_main_applies_fusion_desktop_style(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeApplication:
        def __init__(self, _argv):
            pass

        def setApplicationName(self, _name):
            pass

        def setOrganizationName(self, _name):
            pass

        def setStyle(self, style_name):
            calls["style"] = style_name

        def exec(self):
            return 0

    class UnlockedInstanceGuard:
        def already_running(self) -> bool:
            return False

    class FakeWindow:
        def __init__(self, *args, **kwargs):
            pass

        def show(self):
            calls["shown"] = True

    monkeypatch.setattr(app_module, "QApplication", FakeApplication)
    monkeypatch.setattr(app_module, "SingleInstanceGuard", lambda: UnlockedInstanceGuard())
    monkeypatch.setattr(app_module, "MainWindow", FakeWindow)

    assert app_module.main([]) == 0

    assert calls["style"] == "Fusion"
    assert calls["shown"] is True
