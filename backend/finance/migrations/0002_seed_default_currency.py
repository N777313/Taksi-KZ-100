from django.db import migrations


def create_default_currency(apps, schema_editor):
    Currency = apps.get_model("finance", "Currency")
    db_alias = schema_editor.connection.alias

    currency, created = Currency.objects.using(db_alias).get_or_create(
        code="KZT",
        defaults={
            "name": "Казахстанский тенге",
            "decimal_places": 2,
            "is_active": True,
            "is_default": True,
        },
    )

    # Если KZT уже существует, не перезаписываем его настройки.
    # Назначаем валютой по умолчанию только если основной валюты ещё нет.
    has_default = Currency.objects.using(db_alias).filter(
        is_default=True
    ).exists()

    if not has_default:
        Currency.objects.using(db_alias).filter(pk=currency.pk).update(
            is_default=True
        )


def reverse_seed(apps, schema_editor):
    # Не удаляем валюту при откате: она могла быть использована.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_default_currency,
            reverse_seed,
        ),
    ]
