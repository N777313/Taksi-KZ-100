
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Currency, DriverWallet, WalletTransaction


class FinanceOperationError(ValidationError):
    """Базовая ошибка финансовой операции."""


class InvalidAmount(FinanceOperationError):
    """Недопустимая сумма или точность суммы."""


class InvalidIdempotencyKey(FinanceOperationError):
    """Отсутствует или некорректен ключ идемпотентности."""


class IdempotencyConflict(FinanceOperationError):
    """Ключ уже использован для другой операции."""


class WalletInactive(FinanceOperationError):
    """Кошелёк отключён."""


class InsufficientFunds(FinanceOperationError):
    """На кошельке недостаточно средств."""


class InvalidTransactionKind(FinanceOperationError):
    """Тип операции не соответствует её направлению."""


def _normalize_key(value):
    if value is None:
        raise InvalidIdempotencyKey(
            "Передайте уникальный UUID ключ операции."
        )

    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise InvalidIdempotencyKey(
            "Ключ операции должен быть корректным UUID."
        ) from exc


def _normalize_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidAmount("Укажите корректную сумму.") from exc

    if not amount.is_finite() or amount <= 0:
        raise InvalidAmount("Сумма должна быть больше нуля.")

    # В модели финансовых операций допускается не более 4 знаков
    # после запятой. Нормализуем представление, не округляя сумму.
    try:
        normalized = amount.quantize(Decimal("0.0001"))
    except InvalidOperation as exc:
        raise InvalidAmount(
            "Сумма выходит за допустимый диапазон."
        ) from exc

    if amount != normalized:
        raise InvalidAmount(
            "Допускается не более 4 знаков после запятой."
        )

    try:
        return WalletTransaction._meta.get_field("amount").clean(
            normalized, None
        )
    except ValidationError as exc:
        raise InvalidAmount(
            "Сумма превышает допустимый диапазон."
        ) from exc


def _check_idempotent_replay(
    existing,
    *,
    wallet_id,
    direction,
    kind,
    amount,
    reference,
    description,
    created_by_id,
):
    same_request = (
        existing.wallet_id == wallet_id
        and existing.direction == direction
        and existing.kind == kind
        and existing.amount == amount
        and existing.reference == reference
        and existing.description == description
        and existing.created_by_id == created_by_id
    )

    if not same_request:
        raise IdempotencyConflict(
            "Этот ключ уже использован для другой операции. "
            "Для новой операции передайте новый UUID."
        )

    return existing


def _execute_wallet_operation(
    *,
    wallet_id,
    amount,
    idempotency_key,
    direction,
    kind,
    reference="",
    description="",
    created_by=None,
):
    key = _normalize_key(idempotency_key)
    amount = _normalize_amount(amount)

    # Разрешённые сочетания направления и типа операции.
    allowed_kinds = {
        WalletTransaction.Direction.CREDIT: {
            WalletTransaction.Kind.TOP_UP,
            WalletTransaction.Kind.REFUND,
            WalletTransaction.Kind.ADJUSTMENT,
        },
        WalletTransaction.Direction.DEBIT: {
            WalletTransaction.Kind.RIDE_PAYMENT,
            WalletTransaction.Kind.WITHDRAWAL,
            WalletTransaction.Kind.ADJUSTMENT,
        },
    }

    kind = str(kind)
    if kind not in allowed_kinds.get(direction, set()):
        raise InvalidTransactionKind(
            "Тип операции не соответствует направлению."
        )

    reference = reference or ""
    description = description or ""
    created_by_id = getattr(created_by, "pk", None)

    try:
        with transaction.atomic():
            # Все операции одного кошелька выполняются последовательно.
            wallet = (
                DriverWallet.objects
                .select_for_update()
                .select_related("currency")
                .get(pk=wallet_id)
            )

            # Проверяем ключ после блокировки кошелька:
            # повторное списание того же кошелька не пройдёт дважды.
            existing = WalletTransaction.objects.filter(
                idempotency_key=key
            ).first()

            if existing:
                return _check_idempotent_replay(
                    existing,
                    wallet_id=wallet.pk,
                    direction=direction,
                    kind=kind,
                    amount=amount,
                    reference=reference,
                    description=description,
                    created_by_id=created_by_id,
                )

            if not wallet.is_active:
                raise WalletInactive("Кошелёк неактивен.")

            # Учитываем точность конкретной валюты:
            # для KZT с decimal_places=0 сумма 10.50 недопустима.
            currency_quantum = Decimal(1).scaleb(
                -wallet.currency.decimal_places
            )
            try:
                currency_amount = amount.quantize(currency_quantum)
            except InvalidOperation as exc:
                raise InvalidAmount(
                    "Недопустимая точность суммы для валюты."
                ) from exc

            if amount != currency_amount:
                raise InvalidAmount(
                    f"Для валюты {wallet.currency.code} допускается "
                    f"{wallet.currency.decimal_places} знаков "
                    "после запятой."
                )

            balance_before = wallet.balance

            if direction == WalletTransaction.Direction.CREDIT:
                balance_after = balance_before + amount
            else:
                if balance_before < amount:
                    raise InsufficientFunds(
                        "Недостаточно средств на кошельке."
                    )
                balance_after = balance_before - amount

            if balance_after < 0:
                raise InsufficientFunds(
                    "Баланс кошелька не может быть отрицательным."
                )

            # Проверяем пределы DecimalField до обновления БД.
            try:
                balance_after = DriverWallet._meta.get_field(
                    "balance"
                ).clean(balance_after, None)
            except ValidationError as exc:
                raise InvalidAmount(
                    "Итоговый баланс превышает допустимый диапазон."
                ) from exc

            # ВАЖНО: DriverWallet.save() намеренно запрещает менять
            # баланс напрямую. Обновляем его здесь через QuerySet.update()
            # под блокировкой и внутри transaction.atomic().
            DriverWallet.objects.filter(pk=wallet.pk).update(
                balance=balance_after,
                updated_at=timezone.now(),
            )

            wallet.balance = balance_after

            # Если создание записи журнала не удастся, atomic()
            # откатит и обновление баланса.
            return WalletTransaction.objects.create(
                wallet=wallet,
                direction=direction,
                kind=kind,
                amount=amount,
                balance_before=balance_before,
                balance_after=balance_after,
                idempotency_key=key,
                reference=reference,
                description=description,
                created_by=created_by,
            )

    except IntegrityError:
        # Дополнительная защита при одновременном использовании
        # одного глобально уникального ключа для разных кошельков.
        existing = WalletTransaction.objects.filter(
            idempotency_key=key
        ).first()

        if existing is None:
            raise

        return _check_idempotent_replay(
            existing,
            wallet_id=wallet_id,
            direction=direction,
            kind=kind,
            amount=amount,
            reference=reference,
            description=description,
            created_by_id=created_by_id,
        )


def credit_wallet(
    *,
    wallet_id,
    amount,
    idempotency_key,
    kind=WalletTransaction.Kind.TOP_UP,
    reference="",
    description="",
    created_by=None,
):
    """Пополнить кошелёк и записать операцию в журнал."""
    return _execute_wallet_operation(
        wallet_id=wallet_id,
        amount=amount,
        idempotency_key=idempotency_key,
        direction=WalletTransaction.Direction.CREDIT,
        kind=kind,
        reference=reference,
        description=description,
        created_by=created_by,
    )


def debit_wallet(
    *,
    wallet_id,
    amount,
    idempotency_key,
    kind=WalletTransaction.Kind.RIDE_PAYMENT,
    reference="",
    description="",
    created_by=None,
):
    """Списать средства и записать операцию в журнал."""
    return _execute_wallet_operation(
        wallet_id=wallet_id,
        amount=amount,
        idempotency_key=idempotency_key,
        direction=WalletTransaction.Direction.DEBIT,
        kind=kind,
        reference=reference,
        description=description,
        created_by=created_by,
    )
