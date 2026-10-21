
from django.contrib import admin
from django.db import DatabaseError, connection
from django.http import JsonResponse
from django.urls import path


def health(request):
    return JsonResponse({
        "status": "ok",
        "service": "taxi-kz",
    })


def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse(
            {
                "status": "unavailable",
                "database": "error",
            },
            status=503,
        )

    return JsonResponse({
        "status": "ready",
        "database": "ok",
    })


urlpatterns = [
    path("health/", health, name="health"),
    path("health/ready/", readiness, name="readiness"),
    path("admin/", admin.site.urls),
]
