
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.models import UserProfile
from rides.models import Ride
from rides.services import transition_ride


User = get_user_model()


class RideLifecycleTests(TestCase):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username="test_passenger",
            password="test-password-not-for-production",
        )
        self.driver = User.objects.create_user(
            username="test_driver",
            password="test-password-not-for-production",
        )

        UserProfile.objects.create(
            user=self.passenger,
            role=UserProfile.Role.PASSENGER,
        )
        UserProfile.objects.create(
            user=self.driver,
            role=UserProfile.Role.DRIVER,
        )

        self.ride = Ride.objects.create(
            passenger=self.passenger,
            pickup_address="Актобе, точка отправления",
            destination_address="Актобе, точка назначения",
        )

    def test_new_ride_is_requested(self):
        self.assertEqual(self.ride.status, Ride.Status.REQUESTED)

    def test_ride_can_enter_searching(self):
        ride = transition_ride(
            self.ride,
            Ride.Status.SEARCHING,
        )
        self.assertEqual(ride.status, Ride.Status.SEARCHING)

    def test_ride_cannot_complete_before_trip(self):
        with self.assertRaises(ValidationError):
            transition_ride(
                self.ride,
                Ride.Status.COMPLETED,
            )

    def test_ride_requires_driver_to_be_accepted(self):
        transition_ride(self.ride, Ride.Status.SEARCHING)

        with self.assertRaises(ValidationError):
            transition_ride(
                self.ride,
                Ride.Status.ACCEPTED,
            )

    def test_assigned_driver_can_be_accepted(self):
        self.ride.driver = self.driver
        self.ride.save(update_fields=["driver"])

        transition_ride(self.ride, Ride.Status.SEARCHING)
        ride = transition_ride(self.ride, Ride.Status.ACCEPTED)

        self.assertEqual(ride.status, Ride.Status.ACCEPTED)
        self.assertIsNotNone(ride.accepted_at)
