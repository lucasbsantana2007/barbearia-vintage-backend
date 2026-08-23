import httpx
from app.config import settings
from app.models import Appointment


async def send_appointment_to_n8n(appointment: Appointment) -> None:
    if not settings.n8n_webhook_url:
        return

    payload = {
        "appointment_id": appointment.id,
        "client_name": appointment.client.name,
        "client_email": appointment.client.email,
        "service": appointment.service.name,
        "date": appointment.date.isoformat(),
        "time": appointment.start_time.strftime("%H:%M"),
        "status": appointment.status,
    }

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(settings.n8n_webhook_url, json=payload)
            response.raise_for_status()
    except httpx.HTTPError:
        # A falha do e-mail não pode impedir o agendamento.
        # Em produção, este erro deveria ser enviado a logs/monitoramento.
        return
