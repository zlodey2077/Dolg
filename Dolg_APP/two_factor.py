"""2FA через django-otp (TOTP + статические backup-коды).

Архитектура:
- Enrollment flow: user → /2fa/setup/ → показываем QR-код для секрета,
  user сканирует через Google Authenticator/Authy/1Password и вводит первый
  6-значный код → device.confirmed=True.
- Login challenge: после стандартного login если у user есть confirmed device,
  redirect на /2fa/verify/ — ввод 6-значного кода → session помечается
  как is_verified (см. OTPMiddleware).
- Backup codes: при confirm генерируем 10 одноразовых кодов (StaticDevice +
  StaticToken). User скачивает / печатает / прячет в надёжное место.
- Enforcement: см. middleware `OrgRequire2FAMiddleware` — если user — member
  org с policy_require_2fa=True И у него нет confirmed device → редирект
  на /2fa/setup/ с message «Org требует 2FA».

ВАЖНО: django-otp хранит TOTP-секреты в БД (не plain — fernet-encrypted).
SECRET_KEY проекта используется как fernet-key. Поэтому ротация SECRET_KEY
ломает все 2FA-устройства — об этом нужно знать при prod-deployment.
"""

from __future__ import annotations

from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

BACKUP_CODE_COUNT = 10
BACKUP_CODE_LENGTH = 8


def user_has_confirmed_totp(user) -> bool:
    """True если у юзера есть подтверждённое TOTP-устройство."""
    if not user or not user.is_authenticated:
        return False
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def get_or_create_unconfirmed_totp(user) -> TOTPDevice:
    """Возвращает существующее НЕподтверждённое устройство (enrollment в процессе)
    или создаёт новое. После confirm — отдельный device, старый не трогаем
    чтобы не пересоздавать секрет на каждый refresh /2fa/setup/."""
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name='default', confirmed=False)
    return device


def confirm_totp_device(device: TOTPDevice, token: str) -> bool:
    """Проверяет 6-значный TOTP-токен. Если ok — помечает device confirmed
    и создаёт StaticDevice с backup-кодами."""
    if not device.verify_token(token):
        return False
    device.confirmed = True
    device.save()
    _ensure_backup_codes(device.user)
    return True


def _ensure_backup_codes(user) -> list[str]:
    """Создаёт (или восстанавливает) набор статических backup-кодов.
    Возвращает свежий список plain-text токенов для одноразового показа."""
    # Удаляем старый device (если был) — обновляем коды
    StaticDevice.objects.filter(user=user, name='backup').delete()
    device = StaticDevice.objects.create(user=user, name='backup', confirmed=True)
    codes: list[str] = []
    for _ in range(BACKUP_CODE_COUNT):
        token = StaticToken.random_token(BACKUP_CODE_LENGTH).lower()
        StaticToken.objects.create(device=device, token=token)
        codes.append(token)
    return codes


def get_backup_codes_count(user) -> int:
    """Сколько backup-кодов осталось (не использованных)."""
    try:
        device = StaticDevice.objects.get(user=user, name='backup', confirmed=True)
    except StaticDevice.DoesNotExist:
        return 0
    return device.token_set.count()


def disable_2fa(user) -> bool:
    """Полностью отключает 2FA: удаляет ВСЕ TOTP и backup-устройства."""
    deleted_totp = TOTPDevice.objects.filter(user=user).delete()[0]
    StaticDevice.objects.filter(user=user, name='backup').delete()
    return deleted_totp > 0


def verify_login_token(user, token: str) -> bool:
    """Проверяет 6-значный TOTP ИЛИ статический backup-код. Используется
    в login-challenge view'е после введения правильного пароля."""
    token = (token or '').strip().lower().replace(' ', '').replace('-', '')
    if not token:
        return False

    # 1) Пробуем TOTP — 6 цифр, генерируется каждые 30 сек
    for device in TOTPDevice.objects.filter(user=user, confirmed=True):
        if device.verify_token(token):
            return True

    # 2) Пробуем backup-код — 8-символьный одноразовый. verify_token() сам
    # удалит токен из БД после использования.
    for device in StaticDevice.objects.filter(user=user, confirmed=True):
        if device.verify_token(token):
            return True

    return False
