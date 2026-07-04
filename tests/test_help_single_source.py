import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACK_HTML_PATH = PROJECT_ROOT / "track.html"
HELP_DOC_PATH = PROJECT_ROOT / "docs" / "脉图帮助说明.md"
SPEC_PATH = PROJECT_ROOT / "HikingTrackAnalyzer.spec"


class TestHelpSingleSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TRACK_HTML_PATH.read_text(encoding="utf-8")
        cls.help_doc = HELP_DOC_PATH.read_text(encoding="utf-8")
        cls.spec = SPEC_PATH.read_text(encoding="utf-8")

    def test_help_markdown_doc_is_the_full_user_help_source(self):
        self.assertIn("# 脉图帮助说明", self.help_doc)
        self.assertIn("## 前言", self.help_doc)
        self.assertIn("[请博主喝杯咖啡](../assets/social/alipay-donate.jpg)", self.help_doc)
        self.assertNotIn("![支付宝赞助二维码]", self.help_doc)
        self.assertIn("## 一、软件简介", self.help_doc)
        self.assertIn("### 大模型连接配置说明", self.help_doc)
        self.assertIn("账号授权与数据同步说明", self.help_doc)
        self.assertIn("AI 洞察一直加载或失败怎么办？", self.help_doc)

    def test_track_html_loads_help_from_backend_instead_of_hardcoding_full_copy(self):
        self.assertIn("<title>脉图 - FitVault V1.2.0</title>", self.html)
        for token in (
            'id="help-preface-content"',
            'id="help-usage-content"',
            "async function loadHelpContent()",
            "window.pywebview.api.get_help_markdown",
            "splitHelpMarkdown",
            "renderHelpMarkdown",
            "renderHelpPrefaceMarkdown",
            "help-preface-layout",
            "help-donate-toggle",
            "helpContentLoadPromise",
        ):
            self.assertIn(token, self.html)

        self.assertNotIn("OpenClaw 配置说明", self.html)
        self.assertNotIn("AI 洞察一直加载或失败怎么办？", self.html)
        self.assertNotIn("Garmin 同步按钮不可用怎么办？", self.html)

    def test_readme_garmin_sync_no_longer_requires_openclaw_prompt(self):
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Garmin 和 COROS 同步能力随应用提供，普通用户不需要准备外部 skill 包。", readme)
        self.assertIn("正式安装包会随应用内置 COROS 授权所需的 Node.js 运行时", readme)
        self.assertIn("COROS MCP 的 FIT 下载单次最多返回 10 个活动", readme)
        self.assertIn("每次最多下载 10 个 FIT 文件", readme)
        self.assertIn("[请博主喝杯咖啡](assets/social/alipay-donate.jpg)", readme)
        self.assertNotIn("![支付宝赞助二维码]", readme)
        self.assertIn("Garmin 活动同步不依赖这一步", readme)
        self.assertNotIn("Garmin 同步仍依赖 OpenClaw / QClaw skill、账号授权和存储规范", readme)
        self.assertNotIn("当前版本支持通过 OpenClaw 同步活动", readme)
        self.assertNotIn("Skill 下载：", readme)

        self.assertIn("Garmin 和 COROS 同步能力随应用提供，普通用户不需要准备外部 skill 包。", self.help_doc)
        self.assertIn("正式安装包会随应用内置 COROS 授权所需的 Node.js 运行时", self.help_doc)
        self.assertIn("COROS MCP 的 FIT 下载单次最多返回 10 个活动", self.help_doc)
        self.assertIn("每次最多下载 10 个 FIT 文件", self.help_doc)
        self.assertIn("[请博主喝杯咖啡](../assets/social/alipay-donate.jpg)", self.help_doc)
        self.assertIn("Garmin 活动同步不依赖这一步", self.help_doc)
        self.assertNotIn("Garmin 同步仍依赖 OpenClaw / QClaw skill、账号授权和存储规范", self.help_doc)
        self.assertNotIn("等待 OpenClaw 下载 FIT 文件", self.help_doc)
        self.assertNotIn("当前版本支持通过 OpenClaw 同步活动", self.help_doc)
        self.assertNotIn("Skill 下载：", self.help_doc)

    def test_help_renderer_does_not_expose_skill_download_actions(self):
        self.assertNotIn("function helpDownloadButtonHtml", self.html)
        self.assertNotIn("saveSkillZip('garmin-stats')", self.html)
        self.assertNotIn("saveSkillZip('coros-stats')", self.html)
        self.assertNotIn("skills/garmin-stats.zip", self.html)
        self.assertNotIn("skills/coros-stats.zip", self.html)

    def test_backend_exposes_help_markdown_with_contract_response(self):
        res = main.Api().get_help_markdown()

        self.assertTrue(res["ok"])
        self.assertEqual(res["code"], main.API_CODE_OK)
        self.assertEqual(res["data"]["source"], "docs/脉图帮助说明.md")
        self.assertIn("大模型连接配置说明", res["data"]["markdown"])

    def test_packaging_includes_help_markdown(self):
        self.assertIn('("docs/脉图帮助说明.md", "docs")', self.spec)

    def test_packaging_uses_fitvault_english_name(self):
        self.assertIn("name='FitVault'", self.spec)
        self.assertIn("bundle_identifier='com.mrfang.fitvault'", self.spec)
        self.assertNotIn("name='MaiTu'", self.spec)
        self.assertNotIn("com.mrfang.maitu", self.spec)

    def test_packaging_includes_garmin_auth_dependencies(self):
        requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn('collect_submodules("garminconnect")', self.spec)
        self.assertIn('collect_submodules("garth")', self.spec)
        self.assertIn("garminconnect", requirements)
        self.assertIn("garth", requirements)

    def test_packaging_includes_unpacked_provider_skill_dirs(self):
        self.assertIn('("skills/garmin-stats", "skills/garmin-stats")', self.spec)
        self.assertIn('("skills/coros-stats", "skills/coros-stats")', self.spec)
        self.assertIn('("skills/garmin-stats.zip", "skills")', self.spec)
        self.assertIn('("skills/coros-stats.zip", "skills")', self.spec)

    def test_windows_packaging_does_not_require_console_cli_helper_by_default(self):
        self.assertIn("FITVAULT_INCLUDE_LEGACY_CONSOLE_HELPER", self.spec)
        self.assertIn("_include_legacy_console_helper", self.spec)
        self.assertIn("name='FitVaultCLI'", self.spec)
        self.assertIn("console=True", self.spec)
        self.assertIn('platform.system().lower() == "windows" and _include_legacy_console_helper', self.spec)
        self.assertNotIn('platform.system().lower() == "windows":\n    cli_exe = EXE', self.spec)

    def test_app_base_dir_prefers_bundle_resources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "脉图.app" / "Contents"
            frameworks = bundle / "Frameworks"
            resources = bundle / "Resources"
            resources.mkdir(parents=True)
            (resources / "track.html").write_text("<html></html>", encoding="utf-8")
            exe = bundle / "MacOS" / "FitVault"
            exe.parent.mkdir(parents=True)
            exe.write_text("", encoding="utf-8")

            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", str(frameworks), create=True), \
                 mock.patch.object(sys, "executable", str(exe)):
                self.assertEqual(main.app_base_dir(), resources)

    def test_garmin_login_cli_runs_login_script_without_starting_gui(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            login = root / "skills" / "garmin-stats" / "scripts" / "login.py"
            login.parent.mkdir(parents=True)
            login.write_text("# login\n", encoding="utf-8")
            old_argv = sys.argv[:]

            with mock.patch.object(main, "app_base_dir", return_value=root), \
                 mock.patch.object(main.runpy, "run_path") as run_path:
                code = main.run_garmin_login_cli(["--garmin-login", "--region", "cn"])

            self.assertEqual(code, 0)
            run_path.assert_called_once_with(str(login), run_name="__main__")
            self.assertEqual(sys.argv, old_argv)


if __name__ == "__main__":
    unittest.main()
