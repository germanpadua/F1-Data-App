from fastf1 import get_session
from fastf1 import get_event_schedule
import streamlit as st
import pickle
from PIL import Image
import matplotlib.pyplot as plt

@st.cache_data
def cargar_datos_de_sesion(year, gp, session_type):
    session = get_session(year, gp, session_type)
    session.load(telemetry=True, weather=False)
    return session

def obtener_calendario(year):
    return get_event_schedule(year)

def guardar_datos_mapa(lap, pos, circuit_info, filepath):
    with open(filepath, 'wb') as f:
        pickle.dump((lap, pos, circuit_info), f)


def cargar_mapa_circuito(filepath):
    """
    Loads and returns a matplotlib figure object from an image file.

    Parameters:
    - filepath: Path to the image file.

    Returns:
    - fig: A matplotlib figure object containing the loaded image.
    """
    img = Image.open(filepath)
    fig, ax = plt.subplots()
    ax.imshow(img)
    ax.axis('off')  # Hide the axis
    return fig
