import subprocess
import unittest
from unittest import mock

import subprocess_utils


class FakeStartupInfo:
    def __init__(self):
        self.dwFlags = 0
        self.wShowWindow = None


class TestSubprocessUtils(unittest.TestCase):
    def test_windows_hidden_kwargs_adds_create_no_window(self):
        with mock.patch.object(subprocess_utils.os, "name", "nt"), \
             mock.patch.object(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "STARTUPINFO", FakeStartupInfo, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "STARTF_USESHOWWINDOW", 1, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "SW_HIDE", 0, create=True):
            kwargs = subprocess_utils.windows_hidden_startup_kwargs()

        self.assertEqual(kwargs["creationflags"], 0x08000000)
        self.assertIsInstance(kwargs["startupinfo"], FakeStartupInfo)
        self.assertEqual(kwargs["startupinfo"].dwFlags, 1)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)

    def test_windows_hidden_kwargs_merges_existing_creationflags(self):
        with mock.patch.object(subprocess_utils.os, "name", "nt"), \
             mock.patch.object(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True), \
             mock.patch.object(subprocess_utils.subprocess, "STARTUPINFO", None, create=True):
            kwargs = subprocess_utils.windows_hidden_startup_kwargs(
                creationflags=0x00000008,
                extra_creationflags=0x00000200,
            )

        self.assertEqual(kwargs["creationflags"], 0x08000208)

    def test_run_hidden_requires_argument_array_and_shell_false(self):
        completed = subprocess.CompletedProcess(args=["tool"], returncode=0, stdout="ok", stderr="")
        with mock.patch.object(subprocess_utils.subprocess, "run", return_value=completed) as run_mock:
            result = subprocess_utils.run_hidden(["C:\\Program Files\\Tool\\tool.exe", "--version"], text=True)

        self.assertIs(result, completed)
        self.assertEqual(run_mock.call_args.args[0], ["C:\\Program Files\\Tool\\tool.exe", "--version"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])

        with self.assertRaises(TypeError):
            subprocess_utils.run_hidden("tool --version")
        with self.assertRaises(ValueError):
            subprocess_utils.run_hidden(["tool"], shell=True)


if __name__ == "__main__":
    unittest.main()
