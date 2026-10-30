import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from push_render_env import _service_health_url, _validate_production_env  # noqa: E402


class RenderEnvironmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+asyncpg://user:pass@db.example.test/app",
            "APP_SECRET_KEY": "app-secret",
            "JWT_SECRET_KEY": "jwt-secret",
            "AES_ENCRYPTION_KEY": "aes-secret",
            "TRUSTED_HOSTS": "anti-bots.onrender.com,anti-bots-api.onrender.com",
            "REDIS_URL": "rediss://default:secret@redis.example.test:6379",
        }

    def test_accepts_complete_production_environment(self):
        _validate_production_env(self.env)

    def test_rejects_loopback_trusted_host(self):
        self.env["TRUSTED_HOSTS"] = "localhost,anti-bots-api.onrender.com"
        with self.assertRaisesRegex(ValueError, "TRUSTED_HOSTS"):
            _validate_production_env(self.env)

    def test_requires_native_redis_when_event_features_are_enabled(self):
        self.env["REDIS_URL"] = ""
        with self.assertRaisesRegex(ValueError, "REDIS_URL"):
            _validate_production_env(self.env)

    def test_allows_missing_redis_when_all_dependent_features_are_disabled(self):
        self.env["REDIS_URL"] = ""
        for feature in (
            "EVENT_PIPELINE_ENABLED",
            "EVENT_QUEUE_ENABLED",
            "EVENT_REALTIME_PUBSUB_ENABLED",
        ):
            self.env[feature] = "false"
        _validate_production_env(self.env)

    def test_rejects_non_redis_url_without_printing_its_value(self):
        self.env["REDIS_URL"] = "https://private-token.example.test"
        with self.assertRaisesRegex(ValueError, "REDIS_URL") as caught:
            _validate_production_env(self.env)
        self.assertNotIn("private-token", str(caught.exception))

    def test_worker_does_not_use_web_health_check(self):
        service = {"type": "background_worker", "name": "anti-bots-platform-monitor"}
        self.assertIsNone(_service_health_url(service, service["name"]))

    def test_web_service_uses_render_health_url(self):
        service = {
            "type": "web_service",
            "serviceDetails": {"url": "https://anti-bots-api.onrender.com"},
        }
        self.assertEqual(
            _service_health_url(service, "anti-bots-api"),
            "https://anti-bots-api.onrender.com",
        )


if __name__ == "__main__":
    unittest.main()
