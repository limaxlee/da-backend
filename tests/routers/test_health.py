from fastapi import status


class TestHealth:

    def test_reports_ok(self, client):
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}

    def test_is_not_mounted_under_the_apps_prefix(self, client):
        assert client.get("/apps/health").status_code == status.HTTP_404_NOT_FOUND

    def test_rejects_other_methods(self, client):
        assert client.post("/health").status_code == status.HTTP_405_METHOD_NOT_ALLOWED
