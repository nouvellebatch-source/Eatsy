"""Entrega de correos transaccionales mediante la API HTTPS de Brevo."""
import os
import logging

import requests

logger = logging.getLogger('eatsy.email')


class EmailDeliveryError(Exception):
    pass


def send_verification_email(recipient: str, code: str) -> None:
    key = os.getenv('BREVO_API_KEY', '').strip()
    sender = os.getenv('CORREO_REMITENTE', '').strip()
    if not key or not sender:
        logger.error('Brevo no configurado: BREVO_API_KEY=%s, CORREO_REMITENTE=%s',
                     'presente' if key else 'ausente', 'presente' if sender else 'ausente')
        raise EmailDeliveryError('Correo no configurado')
    try:
        response = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'api-key': key, 'accept': 'application/json'},
            json={
                'sender': {'name': 'Eatsy', 'email': sender},
                'to': [{'email': recipient}],
                'subject': 'Confirma tu cuenta Eatsy',
                'htmlContent': f'<p>Tu código de confirmación es <strong>{code}</strong>.</p><p>Vence en 10 minutos.</p>',
            },
            timeout=10,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        logger.error('Brevo rechazó el correo: HTTP %s', exc.response.status_code if exc.response is not None else 'desconocido')
        raise EmailDeliveryError('No se pudo entregar el correo') from exc
    except requests.Timeout as exc:
        logger.error('Brevo no respondió dentro del tiempo permitido')
        raise EmailDeliveryError('No se pudo entregar el correo') from exc
    except requests.RequestException as exc:
        logger.error('No se pudo conectar con Brevo: %s', type(exc).__name__)
        raise EmailDeliveryError('No se pudo entregar el correo') from exc
