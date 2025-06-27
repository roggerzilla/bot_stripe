from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import stripe
import os
import database  # Asegúrate de que este módulo maneje una DB en la nube (ej. Firestore)
from dotenv import load_dotenv
from telegram import Bot # Importamos Bot para enviar mensajes de confirmación

app = FastAPI()

# Cargar variables de entorno (útil para desarrollo local, Render las inyecta directamente)
load_dotenv() 

# Configuración Stripe con variables de entorno
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
BOT_TOKEN = os.environ.get("BOT_TOKEN") # Asegúrate de tener este valor en Render

# Instancia del bot para enviar confirmaciones (si el BOT_TOKEN está disponible)
# Esto solo se inicializa si hay un token disponible, evitando errores si no lo hay.
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

# Define tus paquetes de puntos aquí con precio en centavos (USD)
# NOTA: Asegúrate de que esta definición de POINT_PACKAGES esté sincronizada con la de points_handlers.py en tu bot
POINT_PACKAGES = {
    "p1": {"label": "1 puntos", "amount": 50, "points": 1},
    "p200": {"label": "500 puntos", "amount": 399, "points": 500},
    "p500": {"label": "2000 puntos", "amount": 999, "points": 2000},
    "p1000": {"label": "5000 puntos", "amount": 1999, "points": 5000}
}

@app.post("/crear-sesion")
async def crear_sesion(request: Request):
    """
    Endpoint para crear una sesión de checkout de Stripe.
    Llamado desde tu bot de Telegram en Vast.ai.
    """
    data = await request.json()
    user_id = str(data.get("telegram_user_id"))
    paquete_id = data.get("paquete_id")

    # Validación
    if not user_id or paquete_id not in POINT_PACKAGES:
        return JSONResponse(status_code=400, content={"error": "Datos inválidos: user_id o paquete_id incorrecto."})

    paquete = POINT_PACKAGES[paquete_id]

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "unit_amount": paquete["amount"],
                    "product_data": {
                        "name": paquete["label"]
                    }
                },
                "quantity": 1
            }],
            mode="payment",
            success_url="https://t.me/monkeyvideosbot",  # Revisa esta URL. Podrías usar una genérica o el bot mismo.
            cancel_url="https://t.me/monkeyvideosbot",   # Revisa esta URL.
            metadata={
                "telegram_user_id": user_id,
                "package_id": paquete_id
            }
        )
        return {"url": session.url}
    except Exception as e:
        print(f"Error creando sesión de Stripe: {e}")
        return JSONResponse(status_code=500, content={"error": f"Error interno al crear sesión: {str(e)}"})

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None, alias="Stripe-Signature")):
    """
    Endpoint que recibe los webhooks de Stripe.
    Es llamado por Stripe cuando ocurren eventos como 'checkout.session.completed'.
    """
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as e:
        print(f"Error de verificación de firma del webhook de Stripe: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except ValueError as e:
        print(f"Error de procesamiento de payload del webhook de Stripe: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    
    # Manejar el evento de sesión de checkout completada
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id_str = metadata.get("telegram_user_id") # Lo leemos como string
        package_id = metadata.get("package_id")

        # Convertir user_id a int de forma segura
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            print(f"Webhook: user_id inválido o ausente en metadata: {user_id_str}")
            return {"status": "error", "message": "Invalid user_id in metadata"}

        if user_id is not None and package_id in POINT_PACKAGES:
            points = POINT_PACKAGES[package_id]["points"]
            try:
                database.update_user_points(user_id, points)
                print(f"Usuario {user_id} recibió {points} puntos por compra en Stripe.")

                # Enviar mensaje de confirmación al usuario de Telegram
                if bot: # Solo intenta enviar si el bot se inicializó correctamente
                    try:
                        await bot.send_message(
                            chat_id=user_id,
                            text=f"🎉 ¡Recarga exitosa! Se han añadido <b>{points}</b> puntos a tu cuenta.",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        print(f"Error enviando mensaje de confirmación a Telegram para {user_id}: {e}")
                else:
                    print("Advertencia: Bot de Telegram no inicializado en el backend de Stripe (TOKEN ausente?). No se pudo enviar confirmación.")
            except Exception as e:
                print(f"Error actualizando puntos o enviando confirmación para {user_id}: {e}")
        else:
            print(f"Webhook recibido pero metadatos incompletos o inválidos: user_id={user_id_str}, package_id={package_id}")

    # Aquí puedes manejar otros tipos de eventos de Stripe si es necesario
    # elif event["type"] == "payment_intent.succeeded":
    #     print("Payment Intent succeeded!")

    return {"status": "ok"}
