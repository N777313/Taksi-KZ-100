# Create your models here.


from django.conf import settings
from django.db import models


class Ride(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Создан"
        SEARCHING = "searching", "Поиск водителя"
        ACCEPTED = "accepted", "Водитель назначен"
        DRIVER_ARRIVED = "driver_arrived", "Водитель прибыл"
        IN_PROGRESS = "in_progress", "В поездке"
        COMPLETED = "completed", "Завершён"
        CANCELLED = "cancelled", "Отменён"

    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="passenger_rides",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="driver_rides",
        null=True,
        blank=True,
    )

    pickup_address = models.CharField(max_length=255)
    destination_address = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )

    fare_estimate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    fare_final = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.CharField(max_length=3, default="KZT")

    requested_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    cancel_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["passenger", "status"]),
            models.Index(fields=["driver", "status"]),
        ]

    def __str__(self):
        return f"Заказ #{self.pk}: {self.get_status_display()}"
