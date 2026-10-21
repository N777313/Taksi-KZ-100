
from django.contrib import admin

from .models import Currency, DriverWallet, WalletTransaction


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "decimal_places",
        "is_active",
        "is_default",
        "created_at",
        "updated_at",
    )
    list_display_links = ("code", "name")
    list_filter = ("is_active", "is_default", "decimal_places")
    search_fields = ("code", "name")
    ordering = ("code",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Основная информация",
            {"fields": ("code", "name")},
        ),
        (
            "Настройки валюты",
            {
                "fields": (
                    "decimal_places",
                    "is_active",
                    "is_default",
                )
            },
        ),
        (
            "Системные даты",
            {"fields": ("created_at", "updated_at")},
        ),
    )


@admin.register(DriverWallet)
class DriverWalletAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver_username",
        "currency",
        "balance",
        "is_active",
        "created_at",
    )
    list_display_links = ("id", "driver_username")
    list_filter = ("is_active", "currency")
    search_fields = (
        "driver__user__username",
        "driver__user__first_name",
        "driver__user__last_name",
        "driver__license_number",
        "driver__plate_number",
    )
    list_select_related = ("driver__user", "currency")
    ordering = ("id",)
    readonly_fields = ("balance", "created_at", "updated_at")

    fieldsets = (
        (
            "Кошелёк",
            {
                "fields": (
                    "driver",
                    "currency",
                    "balance",
                    "is_active",
                )
            },
        ),
        (
            "Системные даты",
            {"fields": ("created_at", "updated_at")},
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))

        if obj is not None:
            fields.extend(("driver", "currency"))

        return tuple(fields)

    @admin.display(description="Имя пользователя", ordering="driver__user__username")
    def driver_username(self, obj):
        return obj.driver.user.username


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver_username",
        "currency_code",
        "direction",
        "kind",
        "amount",
        "balance_before",
        "balance_after",
        "created_at",
    )
    list_display_links = ("id",)
    list_filter = ("direction", "kind", "created_at")
    search_fields = (
        "wallet__driver__user__username",
        "wallet__driver__user__first_name",
        "wallet__driver__user__last_name",
        "reference",
        "idempotency_key",
    )
    list_select_related = (
        "wallet__driver__user",
        "wallet__currency",
        "created_by",
    )
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"

    readonly_fields = (
        "wallet",
        "direction",
        "kind",
        "amount",
        "balance_before",
        "balance_after",
        "idempotency_key",
        "reference",
        "description",
        "created_by",
        "created_at",
    )

    fields = (
        "wallet",
        "direction",
        "kind",
        "amount",
        "balance_before",
        "balance_after",
        "idempotency_key",
        "reference",
        "description",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Водитель", ordering="wallet__driver__user__username")
    def driver_username(self, obj):
        return obj.wallet.driver.user.username

    @admin.display(description="Валюта", ordering="wallet__currency__code")
    def currency_code(self, obj):
        return obj.wallet.currency.code
