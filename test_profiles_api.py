#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from planner.profiles import validate_profile


class ProfileValidationTests(unittest.TestCase):
    def test_validate_profile_rejects_invalid_metadata(self):
        bad_profile = {
            "id": "bad_profile",
            "name": "Bad Profile",
            "description": "invalid metadata values",
            "icon": "🧩",
            "scope_labels": {
                "global_organize": "Global",
                "preserve_parent_boundaries": "Boundary",
                "project_safe_mode": "Safe",
            },
            "categories": ["all"],
            "rule_bundle": [],
            "allowed_scope_modes": [
                "global_organize",
                "preserve_parent_boundaries",
                "project_safe_mode",
            ],
            "default_scope_mode": "preserve_parent_boundaries",
            "workflow_type": "not_real",
            "safety_level": "unsafe",
            "profile_origin": "alien",
        }
        errors = validate_profile(bad_profile)
        self.assertTrue(any("workflow_type" in e for e in errors))
        self.assertTrue(any("safety_level" in e for e in errors))
        self.assertTrue(any("profile_origin" in e for e in errors))


class ProfileApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)

        self.original_settings_path = app_module.SETTINGS_PATH
        self.original_base_dir = app_module.BASE_DIR

        app_module.SETTINGS_PATH = self.tmp_path / "settings.json"
        app_module.BASE_DIR = self.tmp_path

        with open(app_module.SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "parent_folders": [],
                    "rules": [],
                    "exclude_patterns": [],
                    "user_profiles": [],
                },
                f,
                indent=2,
            )

        with open(self.tmp_path / "rules.json", "w", encoding="utf-8") as f:
            json.dump({"rules": []}, f, indent=2)

        self.client = TestClient(app_module.app)

    def tearDown(self):
        app_module.SETTINGS_PATH = self.original_settings_path
        app_module.BASE_DIR = self.original_base_dir
        self.tmpdir.cleanup()

    def _new_profile_payload(self, name: str = "UserProfileA") -> dict:
        return {
            "name": name,
            "description": "user-created profile",
            "icon": "🧪",
            "scope_labels": {
                "global_organize": "Global",
                "preserve_parent_boundaries": "Boundary",
                "project_safe_mode": "Safe",
            },
            "categories": ["all"],
            "rule_bundle": [],
            "allowed_scope_modes": [
                "global_organize",
                "preserve_parent_boundaries",
                "project_safe_mode",
            ],
            "default_scope_mode": "preserve_parent_boundaries",
            "workflow_type": "custom",
            "safety_level": "safe",
        }

    def test_get_profiles_includes_extended_metadata(self):
        res = self.client.get("/api/profiles")
        self.assertEqual(res.status_code, 200)
        profiles = res.json()
        self.assertGreaterEqual(len(profiles), 1)
        sample = profiles[0]
        self.assertIn("description", sample)
        self.assertIn("workflow_type", sample)
        self.assertIn("safety_level", sample)
        self.assertIn("profile_origin", sample)
        self.assertTrue(any(p.get("profile_origin") == "builtin" for p in profiles))

    def test_user_profile_crud_persists_and_builtin_delete_fails(self):
        create_res = self.client.post("/api/profiles", json=self._new_profile_payload())
        self.assertEqual(create_res.status_code, 200)
        created = create_res.json()
        self.assertEqual(created["profile_origin"], "user")

        with open(app_module.SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings = json.load(f)
        self.assertEqual(len(settings.get("user_profiles", [])), 1)

        update_res = self.client.put(
            "/api/profiles/UserProfileA",
            json={"description": "updated desc", "safety_level": "standard"},
        )
        self.assertEqual(update_res.status_code, 200)
        self.assertEqual(update_res.json()["description"], "updated desc")
        self.assertEqual(update_res.json()["safety_level"], "standard")

        builtin_delete = self.client.delete("/api/profiles/Generic")
        self.assertEqual(builtin_delete.status_code, 403)

        delete_res = self.client.delete("/api/profiles/UserProfileA")
        self.assertEqual(delete_res.status_code, 200)

        list_res = self.client.get("/api/profiles")
        self.assertEqual(list_res.status_code, 200)
        user_names = [p["name"] for p in list_res.json() if p.get("profile_origin") == "user"]
        self.assertNotIn("UserProfileA", user_names)

    def test_generate_rules_route_keeps_working_for_builtin_profile(self):
        res = self.client.post("/api/profiles/generic/generate-rules")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("count"), 0)
        self.assertEqual(body.get("added"), [])


if __name__ == "__main__":
    unittest.main()
