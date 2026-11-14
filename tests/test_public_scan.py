import json
import os
import subprocess
import tempfile
import unittest

SCAN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "public-scan")
STATE = {
    "roadmap.json": {"items": [{"title": "Secret partner launch in the north region"}, {"title": "Northwind rollout"}]},
    "inbox.json": {"items": [{"title": "Quiet vendor price hike", "context": "see the docs about the agents box",
                              "short": ["Rename the staging cluster"]}]},
}


class PublicScanTest(unittest.TestCase):
    def run_scan(self, files, ignore=None, state=STATE, home=None):
        with tempfile.TemporaryDirectory() as h, tempfile.TemporaryDirectory() as repo:
            os.makedirs(os.path.join(h, "products", "acme"))
            for name, data in state.items():
                with open(os.path.join(h, name), "w") as f:
                    json.dump(data, f)
            for path, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(repo, path)) or repo, exist_ok=True)
                with open(os.path.join(repo, path), "w") as f:
                    f.write(text)
            if ignore:
                with open(os.path.join(repo, ".public-scan-ignore"), "w") as f:
                    f.write(ignore)
            subprocess.run(["git", "init", "-q", repo], check=True)
            subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
            env = dict(os.environ, FACTORY_HOME=home or h)
            return subprocess.run([SCAN, repo], capture_output=True, text=True, env=env)

    def test_copied_title_in_a_fixture_fails(self):
        r = self.run_scan({"tests/fixture.py": 'TITLE = "Secret partner launch in the north"\n'})
        self.assertEqual(r.returncode, 1)
        self.assertIn("tests/fixture.py: secret partner launch in the", r.stdout)

    def test_short_title_and_inbox_title_fail(self):
        self.assertEqual(self.run_scan({"a.md": "the Northwind rollout\n"}).returncode, 1)
        self.assertEqual(self.run_scan({"a.md": "a quiet vendor price hike\n"}).returncode, 1)
        self.assertEqual(self.run_scan({"a.md": "rename the staging cluster\n"}).returncode, 1)  # list value

    def test_nested_and_jsonl_state_are_read(self):
        r = self.run_scan({"a.md": "Hidden merger codename project\n"},
                          state={"products/acme/p.json": {"name": "Hidden merger codename project"}})
        self.assertEqual(r.returncode, 1)
        with tempfile.TemporaryDirectory() as h:
            with open(os.path.join(h, "updates.jsonl"), "w") as f:
                f.write('{"note": "Board meeting moved"}\n{"note": "Quarterly payroll vendor swap"}\n')
            r = self.run_scan({"a.md": "Quarterly payroll vendor swap\n"}, state={}, home=h)
            self.assertEqual(r.returncode, 1)

    def test_clean_tree_inbox_bodies_and_code_text_pass(self):
        self.assertEqual(self.run_scan({"tests/fixture.py": 'TITLE = "Dark mode"\n'}).returncode, 0)
        self.assertEqual(self.run_scan({"a.md": "see the docs about the agents box\n"}).returncode, 0)
        r = self.run_scan({"factory/x.py": 'MSG = "secret partner launch in the north region"\n',
                           "README.md": "secret partner launch in the north region\n"})
        self.assertEqual(r.returncode, 0)

    def test_ignore_matches_whole_hits_only(self):
        files = {"a.md": "the Northwind rollout\n"}
        self.assertEqual(self.run_scan(files, ignore="northwind rollout\n").returncode, 0)
        self.assertEqual(self.run_scan(files, ignore="northwind\n").returncode, 1)

    def test_skipped_places_and_bad_jsonl_lines(self):
        # the ignore file itself is not scanned (its lines join into state 5-word runs)
        r = self.run_scan({"a.md": "Dark mode\n"}, ignore="secret partner launch\nin the north region\n")
        self.assertEqual(r.returncode, 0)
        with tempfile.TemporaryDirectory() as h:
            os.makedirs(os.path.join(h, "secrets"))
            with open(os.path.join(h, "secrets", "x.json"), "w") as f:
                json.dump({"v": "Northwind rollout plan"}, f)
            with open(os.path.join(h, "u.jsonl"), "w") as f:
                f.write('{"note": "Quarterly payroll vendor swap"}\n{"cut off')
            self.assertEqual(self.run_scan({"a.md": "Northwind rollout plan\n"}, state={}, home=h).returncode, 0)
            self.assertEqual(self.run_scan({"a.md": "Quarterly payroll vendor swap\n"}, state={}, home=h).returncode, 1)

    def test_not_a_git_checkout_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(subprocess.run([SCAN, d], capture_output=True).returncode, 2)

    def test_missing_state_folder_passes(self):
        r = self.run_scan({"a.md": "Northwind rollout\n"}, home="/nonexistent-factory-home")
        self.assertEqual(r.returncode, 0)
        self.assertIn("no state folder", r.stderr)


if __name__ == "__main__":
    unittest.main()
