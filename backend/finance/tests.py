
from django.db import IntegrityError, transaction
from django.test import TestCase

from finance.models import Currency


class CurrencyModelTests(TestCase):
    def test_lowercase_code_is_normalized_to_uppercase(self):
        currency = Currency.objects.create(
            code="xzt",
            name="Тестовая валюта",
        )

        self.assertEqual(currency.code, "XZT")
        self.assertTrue(
            Currency.objects.filter(pk=currency.pk, code="XZT").exists()
        )

    def test_duplicate_currency_code_is_rejected_by_database(self):
        Currency.objects.create(
            code="USD",
            name="Доллар США",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Currency.objects.bulk_create([
                    Currency(code="USD", name="Дубликат доллара"),
                ])

    def test_only_one_default_currency_is_allowed(self):
        # KZT уже добавлена миграцией 0002 как валюта по умолчанию.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Currency.objects.bulk_create([
                    Currency(
                        code="USD",
                        name="Доллар США",
                        is_default=True,
                    ),
                ])

    def test_database_rejects_more_than_four_decimal_places(self):
        currency = Currency.objects.create(
            code="USD",
            name="Доллар США",
            decimal_places=2,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Currency.objects.filter(pk=currency.pk).update(
                    decimal_places=5
                )
