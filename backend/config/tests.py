
from django.db import connection
from django.test import TestCase


class HealthEndpointTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_endpoint(self):
        response = self.client.get("/health/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")
        self.assertEqual(response.json()["database"], "ok")

    def test_database_query(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

        self.assertEqual(result[0], 1)
