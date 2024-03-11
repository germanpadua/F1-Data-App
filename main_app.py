import streamlit as st
import fastf1
from fastf1 import plotting
from matplotlib import pyplot as plt
import pandas as pd

# Configuración inicial, como habilitar el caché si es necesario
fastf1.Cache.enable_cache('cache')

# Función para cargar los datos (posiblemente usando st.cache)
@st.cache_data
def cargar_datos(year, gp, session_type):
    session = fastf1.get_session(year, gp, session_type)
    session.load()
    laps = session.laps
    return laps

st.title('Análisis de Tiempos de Vuelta en Fórmula 1')

# Selección de parámetros por el usuario
year = st.sidebar.selectbox('Selecciona el año', [2020, 2021, 2022, 2023])
gp = st.sidebar.text_input('Escribe el Gran Premio', 'Spain')
session_type = st.sidebar.selectbox('Selecciona el tipo de sesión', ['FP1', 'FP2', 'FP3', 'Q', 'R'])

laps = cargar_datos(year, gp, session_type)

if not laps.empty:
    drivers = laps['Driver'].unique()
    selected_driver = st.selectbox('Selecciona un piloto', drivers)
    
    # Filtra los datos para el piloto seleccionado
    driver_laps = laps.loc[laps['Driver'] == selected_driver]
    
    # Genera el gráfico para el piloto seleccionado
    fig, ax = plt.subplots()
    ax.plot(driver_laps['LapNumber'], driver_laps['LapTime'], marker='o')
    ax.set_title(f'Tiempos de vuelta de {selected_driver}')
    ax.set_xlabel('Número de vuelta')
    ax.set_ylabel('Tiempo de vuelta')
    st.pyplot(fig)
else:
    st.error('No se encontraron datos para esta sesión.')