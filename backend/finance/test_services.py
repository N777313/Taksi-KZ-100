
import uuid
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections
from django.test import TestCase, TransactionTestCase

# from django.test.utils import skipUnlessDBFeature
from django.test import skipUnlessDBFeature

from accounts.models import DriverProfile
from finance.models import (
    Currency,
    DriverWallet,
    WalletTransaction,
)
from finance.services import (
    IdempotencyConflict,
    InsufficientFunds,
    InvalidAmount,
    debit_wallet,
    credit_wallet,
)


from django.core.exceptions import ValidationError
from unittest.mock import patch

def make_wallet(balance=Decimal("100.0000")):
    suffix = uuid.uuid4().hex[:12]
    user = get_user_model().objects.create_user(
        username=f"test-driver-{suffix}"
    )

    driver = DriverProfile.objects.create(
        user=user,
        license_number=f"LIC-{suffix}",
        vehicle_make="Toyota",
        vehicle_model="Corolla",
        vehicle_year=2020,
        plate_number=f"T{suffix[:7]}",
    )

    currency = Currency.objects.get(code="KZT")

    wallet = DriverWallet.objects.create(
        driver=driver,
        currency=currency,
    )

    # Начальный баланс формируется настоящей финансовой операцией.
    if balance > 0:
        credit_wallet(
            wallet_id=wallet.pk,
            amount=balance,
            idempotency_key=uuid.uuid4(),
            kind=WalletTransaction.Kind.TOP_UP,
            description="Начальное пополнение в тесте",
        )

    return wallet



class WalletServiceTests(TestCase):
    def setUp(self):
        self.wallet = make_wallet()
        self.key = uuid.uuid4()

    def test_credit_updates_balance_and_creates_journal(self):
        tx = credit_wallet(
            wallet_id=self.wallet.pk,
            amount="25",
            idempotency_key=self.key,
        )

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, Decimal("125.0000"))
        self.assertEqual(tx.balance_before, Decimal("100.0000"))
        self.assertEqual(tx.balance_after, Decimal("125.0000"))
        self.assertEqual(
            WalletTransaction.objects.filter(
                idempotency_key=self.key
            ).count(),
            1,
        )

    def test_repeated_request_does_not_credit_twice(self):
        first = credit_wallet(
            wallet_id=self.wallet.pk,
            amount="25",
            idempotency_key=self.key,
        )
        second = credit_wallet(
            wallet_id=self.wallet.pk,
            amount="25",
            idempotency_key=self.key,
        )

        self.wallet.refresh_from_db()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.wallet.balance, Decimal("125.0000"))
        self.assertEqual(
            WalletTransaction.objects.filter(
                idempotency_key=self.key
            ).count(),
            1,
        )

    def test_reusing_key_with_different_amount_is_rejected(self):
        credit_wallet(
            wallet_id=self.wallet.pk,
            amount="25",
            idempotency_key=self.key,
        )

        with self.assertRaises(IdempotencyConflict):
            credit_wallet(
                wallet_id=self.wallet.pk,
                amount="30",
                idempotency_key=self.key,
            )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("125.0000"))

    def test_insufficient_funds_does_not_change_balance(self):
        with self.assertRaises(InsufficientFunds):
            debit_wallet(
                wallet_id=self.wallet.pk,
                amount="150",
                idempotency_key=self.key,
            )

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, Decimal("100.0000"))
        self.assertFalse(
            WalletTransaction.objects.filter(
                idempotency_key=self.key
            ).exists()
        )


    def test_amount_must_match_currency_precision(self):
        currency = self.wallet.currency
        places = currency.decimal_places

        # Формируем сумму с одним лишним десятичным знаком
        # относительно точности валюты.
        invalid_amount = (
            Decimal("10")
            + Decimal(1).scaleb(-(places + 1))
        )

        with self.assertRaises(InvalidAmount):
            credit_wallet(
                wallet_id=self.wallet.pk,
                amount=str(invalid_amount),
                idempotency_key=self.key,
            )

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.0000"))
        self.assertFalse(
            WalletTransaction.objects.filter(
                idempotency_key=self.key
            ).exists()
        )

    def test_balance_rolls_back_if_journal_creation_fails(self):
        self.wallet.refresh_from_db()
        balance_before = self.wallet.balance
        operation_key = uuid.uuid4()

        with patch(
            "finance.services.WalletTransaction.objects.create",
            side_effect=RuntimeError("Simulated journal failure"),
        ):
            with self.assertRaises(RuntimeError):
                credit_wallet(
                    wallet_id=self.wallet.pk,
                    amount="25",
                    idempotency_key=operation_key,
                )

        self.wallet.refresh_from_db()

        self.assertEqual(self.wallet.balance, balance_before)
        self.assertFalse(
            WalletTransaction.objects.filter(
                idempotency_key=operation_key,
            ).exists()
        )


@skipUnlessDBFeature("has_select_for_update")
class ConcurrentWalletDebitTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.wallet = make_wallet(Decimal("100.0000"))

    def test_two_concurrent_debits_cannot_overdraw_wallet(self):
        barrier = Barrier(2)

        def attempt_debit(key):
            close_old_connections()
            try:
                barrier.wait(timeout=10)

                try:
                    debit_wallet(
                        wallet_id=self.wallet.pk,
                        amount="80",
                        idempotency_key=key,
                    )
                    return "success"
                except InsufficientFunds:
                    return "insufficient_funds"
            finally:
                connections.close_all()

        keys = [uuid.uuid4(), uuid.uuid4()]

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt_debit, keys))

        self.wallet.refresh_from_db()

        self.assertCountEqual(
            results,
            ["success", "insufficient_funds"],
        )
        self.assertEqual(self.wallet.balance, Decimal("20.0000"))
        transactions = WalletTransaction.objects.filter(
            wallet=self.wallet
        )

        # Одна запись пополнения + одно успешное списание.
        self.assertEqual(transactions.count(), 2)

        # Из двух конкурентных списаний успешно прошло только одно.
        self.assertEqual(
            transactions.filter(
                direction=WalletTransaction.Direction.DEBIT
            ).count(),
            1,
        )


class WalletModelProtectionTests(TestCase):
    def setUp(self):
        self.wallet = make_wallet()
        self.key = uuid.uuid4()

    def test_direct_balance_change_is_rejected(self):
        self.wallet.balance = Decimal("999.0000")

        with self.assertRaises(ValidationError):
            self.wallet.save()

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("100.0000"))

    def test_wallet_cannot_be_created_with_nonzero_balance(self):
        with self.assertRaises(ValidationError):
            DriverWallet.objects.create(
                driver=self.wallet.driver,
                currency=self.wallet.currency,
                balance=Decimal("50.0000"),
            )

    def test_transaction_cannot_be_modified(self):
        tx = credit_wallet(
            wallet_id=self.wallet.pk,
            amount="10",
            idempotency_key=self.key,
        )

        tx.description = "Попытка изменить проведённую операцию"

        with self.assertRaises(ValidationError):
            tx.save()

    def test_transaction_cannot_be_deleted(self):
        tx = credit_wallet(
            wallet_id=self.wallet.pk,
            amount="10",
            idempotency_key=self.key,
        )

        with self.assertRaises(ValidationError):
            tx.delete()

        self.assertTrue(
            WalletTransaction.objects.filter(pk=tx.pk).exists()
        )
