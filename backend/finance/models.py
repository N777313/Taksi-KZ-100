import uuid

from django.conf import settings



from django.core.exceptions import ValidationError
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import Q


class Currency(models.Model):
    code = models.CharField(
        max_length=3,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{3}$",
                message="Код валюты должен состоять из 3 заглавных латинских букв.",
            )
        ],
        verbose_name="Код валюты",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Название валюты",
    )
    decimal_places = models.PositiveSmallIntegerField(
        default=2,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(4),
        ],
        verbose_name="Количество знаков после запятой",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Валюта по умолчанию",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создана",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Изменена",
    )

    class Meta:
        ordering = ["code"]
        verbose_name = "Валюта"
        verbose_name_plural = "Валюты"
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="finance_one_default_currency",
            ),
            models.CheckConstraint(
                condition=Q(decimal_places__lte=4),
                name="finance_currency_decimal_places_max_4",
            ),
        ]

    def clean(self):
        super().clean()

        if not 0 <= self.decimal_places <= 4:
            raise ValidationError({
                "decimal_places": "Допустимо от 0 до 4 знаков после запятой."
            })

        self.code = self.code.upper()

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.name}"






class DriverWallet(models.Model):
    driver = models.OneToOneField(
        "accounts.DriverProfile",
        on_delete=models.PROTECT,
        related_name="wallet",
        verbose_name="Водитель",
    )
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        related_name="wallets",
        verbose_name="Валюта",
    )
    balance = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        default=0,
        verbose_name="Баланс",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создан",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Изменён",
    )

    class Meta:
        ordering = ["id"]
        verbose_name = "Кошелёк водителя"
        verbose_name_plural = "Кошельки водителей"
        constraints = [
            models.CheckConstraint(
                condition=Q(balance__gte=0),
                name="fin_wallet_balance_nonneg",
            ),
        ]

    def clean(self):
        super().clean()

        if self._state.adding and self.currency_id:
            if not self.currency.is_active:
                raise ValidationError({
                    "currency": "Нельзя создать кошелёк в неактивной валюте."
                })

    def save(self, *args, **kwargs):
        if self._state.adding and self.balance != 0:
            raise ValidationError({
                "balance": (
                    "Новый кошелёк создаётся с нулевым балансом. "
                    "Для зачисления используйте финансовый сервис."
                )
            })

        if self.pk:
            old = type(self).objects.filter(pk=self.pk).values(
                "balance", "currency_id"
            ).first()

            if old:
                if self.balance != old["balance"]:
                    raise ValidationError({
                        "balance": (
                            "Баланс изменяется только через сервис "
                            "финансовых транзакций."
                        )
                    })

                if (
                    self.currency_id != old["currency_id"]
                    and WalletTransaction.objects.filter(
                        wallet_id=self.pk
                    ).exists()
                ):
                    raise ValidationError({
                        "currency": (
                            "Нельзя менять валюту кошелька "
                            "после появления транзакций."
                        )
                    })

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Кошелёк: {self.driver.user.username} "
            f"({self.currency.code})"
        )


class WalletTransaction(models.Model):
    class Direction(models.TextChoices):
        CREDIT = "credit", "Зачисление"
        DEBIT = "debit", "Списание"

    class Kind(models.TextChoices):
        TOP_UP = "top_up", "Пополнение"
        RIDE_PAYMENT = "ride_payment", "Оплата поездки"
        REFUND = "refund", "Возврат"
        WITHDRAWAL = "withdrawal", "Вывод средств"
        ADJUSTMENT = "adjustment", "Корректировка"

    wallet = models.ForeignKey(
        DriverWallet,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="Кошелёк",
    )
    direction = models.CharField(
        max_length=10,
        choices=Direction.choices,
        verbose_name="Направление",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        verbose_name="Тип операции",
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        verbose_name="Сумма",
    )
    balance_before = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        verbose_name="Баланс до операции",
    )
    balance_after = models.DecimalField(
        max_digits=20,
        decimal_places=4,
        verbose_name="Баланс после операции",
    )
    idempotency_key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="Ключ уникальности операции",
    )
    reference = models.CharField(
        max_length=128,
        blank=True,
        verbose_name="Внешний идентификатор",
    )
    description = models.TextField(
        blank=True,
        verbose_name="Описание",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wallet_transactions_created",
        verbose_name="Инициатор",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата операции",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Транзакция кошелька"
        verbose_name_plural = "Транзакции кошельков"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="fin_tx_amount_positive",
            ),
            models.CheckConstraint(
                condition=Q(balance_before__gte=0),
                name="fin_tx_before_nonneg",
            ),
            models.CheckConstraint(
                condition=Q(balance_after__gte=0),
                name="fin_tx_after_nonneg",
            ),
        ]
        indexes = [
            models.Index(
                fields=["wallet", "-created_at"],
                name="fin_tx_wallet_created_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Проведённую транзакцию нельзя изменять. "
                "Для исправления создайте отдельную корректирующую операцию."
            )

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Проведённую транзакцию нельзя удалять."
        )

    def __str__(self):
        return (
            f"{self.get_direction_display()}: "
            f"{self.amount} {self.wallet.currency.code}"
        )
