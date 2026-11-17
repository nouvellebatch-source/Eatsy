"""Entrega de correos transaccionales mediante la API HTTPS de Brevo."""
import os

import requests


class EmailDeliveryError(Exception):
    pass


def send_verification_email(recipient: str, code: str) -> None:
    key = os.getenv('BREVO_API_KEY', '').strip()
    sender = os.getenv('CORREO_REMITENTE', '').strip()
    if not key or not sender:
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
    except requests.RequestException as exc:
        raise EmailDeliveryError('No se pudo entregar el correo') from exc
