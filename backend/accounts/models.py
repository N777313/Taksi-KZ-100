# Create your models here.



from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    class Role(models.TextChoices):
        PASSENGER = "passenger", "Пассажир"
        DRIVER = "driver", "Водитель"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="taxi_profile",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PASSENGER,
    )
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class DriverProfile(models.Model):
    class Availability(models.TextChoices):
        OFFLINE = "offline", "Не на линии"
        AVAILABLE = "available", "Свободен"
        BUSY = "busy", "Выполняет заказ"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="driver_profile",
    )
    license_number = models.CharField(max_length=64, blank=True)
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model = models.CharField(max_length=60, blank=True)
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    plate_number = models.CharField(
        max_length=16,
        unique=True,
        null=True,
        blank=True,
    )
    availability = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.OFFLINE,
    )
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Водитель: {self.user.username}"
