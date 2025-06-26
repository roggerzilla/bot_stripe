# database.py
from supabase import create_client, Client
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user(user_id: int):
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    data = response.data
    return data[0] if data else None

def add_user(user_id: int, referred_by=None, initial_points=0):
    user = get_user(user_id)
    if user:
        logging.warning(f"Usuario {user_id} ya existe.")
        return False

    created_at = datetime.utcnow().isoformat()
    data = {
        "user_id": user_id,
        "points": initial_points,
        "referred_by": referred_by,
        "created_at": created_at
    }
    supabase.table("users").insert(data).execute()
    logging.info(f"Usuario {user_id} añadido a Supabase.")
    return True

def update_user_points(user_id: int, amount: int):
    user = get_user(user_id)
    if not user:
        logging.warning(f"Usuario {user_id} no encontrado.")
        return

    new_points = user["points"] + amount
    supabase.table("users").update({"points": new_points}).eq("user_id", user_id).execute()
    logging.info(f"Puntos de usuario {user_id} actualizados en {amount} (total: {new_points}).")

def get_user_points(user_id: int):
    user = get_user(user_id)
    return user["points"] if user else 0
