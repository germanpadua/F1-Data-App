from fastf1 import get_session
from fastf1 import get_event_schedule
import streamlit as st

@st.cache_data
def cargar_datos_de_sesion(year, gp, session_type):
    session = get_session(year, gp, session_type)
    session.load(telemetry=True, weather=False)
    return session

def obtener_calendario(year):
    return get_event_schedule(year)