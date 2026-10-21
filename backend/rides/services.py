
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Ride


ALLOWED_TRANSITIONS = {
    Ride.Status.REQUESTED: {
        Ride.Status.SEARCHING,
        Ride.Status.CANCELLED,
    },
    Ride.Status.SEARCHING: {
        Ride.Status.ACCEPTED,
        Ride.Status.CANCELLED,
    },
    Ride.Status.ACCEPTED: {
        Ride.Status.DRIVER_ARRIVED,
        Ride.Status.CANCELLED,
    },
    Ride.Status.DRIVER_ARRIVED: {
        Ride.Status.IN_PROGRESS,
        Ride.Status.CANCELLED,
    },
    Ride.Status.IN_PROGRESS: {
        Ride.Status.COMPLETED,
    },
    Ride.Status.COMPLETED: set(),
    Ride.Status.CANCELLED: set(),
}


@transaction.atomic
def transition_ride(ride, new_status):
    ride = Ride.objects.select_for_update().get(pk=ride.pk)

    if new_status not in ALLOWED_TRANSITIONS.get(ride.status, set()):
        raise ValidationError(
            f"Недопустимый переход заказа: "
            f"{ride.status} -> {new_status}"
        )

    now = timezone.now()

    if new_status == Ride.Status.ACCEPTED:
        if not ride.driver_id:
            raise ValidationError(
                "Перед принятием заказа необходимо назначить водителя."
            )
        ride.accepted_at = now

    elif new_status == Ride.Status.IN_PROGRESS:
        ride.started_at = now

    elif new_status == Ride.Status.COMPLETED:
        ride.completed_at = now

    elif new_status == Ride.Status.CANCELLED:
        ride.cancelled_at = now

    ride.status = new_status
    ride.save()

    return ride
