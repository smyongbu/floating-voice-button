import unittest

from model_resource_groups import (
    MODEL_FILES,
    GroupedModelDownloadManager,
    build_grouped_download_specs,
)


class ModelResourceGroupTests(unittest.TestCase):
    def test_all_five_visible_models_have_download_specs(self):
        groups = build_grouped_download_specs()
        self.assertEqual(set(groups), set(MODEL_FILES))
        self.assertEqual(len(groups), 5)
        self.assertEqual(sum(len(items) for items in groups.values()), 18)
        resource_ids = [spec.resource_id for items in groups.values() for spec in items]
        self.assertEqual(len(resource_ids), len(set(resource_ids)))
        for model_id, specs in groups.items():
            self.assertTrue(specs, model_id)
            for spec in specs:
                self.assertGreater(spec.total_size, 0)
                self.assertRegex(spec.sha256, r"^[0-9a-f]{64}$")
                self.assertIn("/resolve/", spec.url)
                self.assertNotIn("/tree/", spec.url)

    def test_group_progress_is_weighted_by_exact_bytes(self):
        status = GroupedModelDownloadManager._aggregate("demo", [
            {"state": "completed", "verified": True, "total_bytes": 75, "downloaded_bytes": 75, "installed_bytes": 75},
            {"state": "downloading", "verified": False, "total_bytes": 25, "downloaded_bytes": 5, "installed_bytes": 0},
        ])
        self.assertEqual(status["state"], "downloading")
        self.assertEqual(status["percent"], 80.0)
        self.assertEqual(status["downloaded_bytes"], 80)

    def test_group_completes_only_when_every_file_is_verified(self):
        completed = GroupedModelDownloadManager._aggregate("demo", [
            {"state": "completed", "verified": True, "total_bytes": 1, "downloaded_bytes": 1, "installed_bytes": 1},
            {"state": "completed", "verified": True, "total_bytes": 2, "downloaded_bytes": 2, "installed_bytes": 2},
        ])
        self.assertEqual(completed["state"], "completed")
        self.assertTrue(completed["verified"])
