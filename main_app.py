import streamlit as st
import fastf1
from fastf1 import plotting
from matplotlib import pyplot as plt
import pandas as pd

import os

# Especifica el nombre del directorio de caché
cache_dir = 'cache'

# Crea el directorio de caché si no existe
os.makedirs(cache_dir, exist_ok=True)

# Habilita el caché de FastF1
fastf1.Cache.enable_cache(cache_dir)

# Título de la aplicación
st.title('Análisis de Tiempos de Vuelta en Fórmula 1')

# Selección de año, evento y sesión
year = st.sidebar.selectbox('Selecciona el año', [2020, 2021, 2022, 2023])
gp = st.sidebar.text_input('Escribe el Gran Premio', 'Spain')
session_type = st.sidebar.selectbox('Selecciona el tipo de sesión', ['FP1', 'FP2', 'FP3', 'Q', 'R'])

# Botón para cargar los datos
if st.sidebar.button('Cargar Datos'):
    with st.spinner('Cargando datos...'):
        session = fastf1.get_session(year, gp, session_type)
        session.load()
        laps = session.laps
        st.success('¡Datos cargados con éxito!')

        # Mostrar una tabla con los tiempos de vuelta
        if not laps.empty:
            driver_ids = laps['DriverNumber'].unique()
            selected_driver = st.selectbox('Selecciona un piloto', driver_ids)
            driver_laps = laps.pick_driver(selected_driver)
            st.write(driver_laps[['LapNumber', 'LapTime', 'Position']].reset_index(drop=True))
        
            # Graficar los tiempos de vuelta del piloto seleccionado
            plt.figure(figsize=(10, 6))
            plt.plot(driver_laps['LapNumber'], driver_laps['LapTime'].dt.total_seconds(), marker='.')
            plt.title(f'Tiempos de Vuelta para el piloto {selected_driver}')
            plt.xlabel('Número de Vuelta')
            plt.ylabel('Tiempo de Vuelta (segundos)')
            st.pyplot(plt)
        else:
            st.error('No se encontraron datos para esta sesión.')

