import os
import streamlit as st
import fastf1
from fastf1 import plotting
from matplotlib import pyplot as plt
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from fastf1 import get_event_schedule
from datetime import datetime


# Directorio de caché
cache_dir = 'cache'

# Verifica si el directorio de caché existe, si no, créalo
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

# Configuración inicial de FastF1 y matplotlib para la aplicación
fastf1.Cache.enable_cache(cache_dir)  # Habilita la caché de FastF1
plotting.setup_mpl(misc_mpl_mods=False)  # Configuración de matplotlib para FastF1

# Función para cargar los datos de la sesión
@st.cache_data
def cargar_datos_de_sesion(year, gp, session_type):
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=False, weather=False)
    return session

st.title('Análisis en Fórmula 1')

# Menú / Página principal con opciones de gráficos
opcion_grafico = st.sidebar.selectbox(
    'Elige una opción de gráfico:',
    ('Evolución de las posiciones', 'Tiempos de vuelta')
)

# Lista de años disponibles para la selección
years = [2020, 2021, 2022, 2023, 2024]
current_year = datetime.now().year
default_year_index = years.index(current_year) if current_year in years else len(years) - 1

# Lógica para mostrar el gráfico basado en la elección
if opcion_grafico == 'Evolución de las posiciones':
    # Cargar datos específicos si es necesario
    # Código para mostrar el gráfico de evolución de las posiciones
    # Selección de parámetros por el usuario
    
    year = st.sidebar.selectbox('Selecciona el año', years, index=default_year_index)
    
    schedule = get_event_schedule(year)

    # Extrae los nombres de los Grandes Premios de la programación
    gps_disponibles = schedule['EventName'].tolist()

    # Crea un selectbox para que el usuario seleccione el GP
    default_gp_index = gps_disponibles.index('Bahrain Grand Prix') if 'Bahrain Grand Prix' in gps_disponibles else 0

    # Crea un selectbox para que el usuario seleccione el GP, con un valor por defecto
    gp_selected = st.sidebar.selectbox('Selecciona el Gran Premio', gps_disponibles, index=default_gp_index)

    session_type = 'R'  # Para análisis de carrera

    session = cargar_datos_de_sesion(year, gp_selected, session_type)

    # Verifica si hay datos cargados para la sesión
    if session.laps.empty:
        st.error('No se encontraron datos para esta sesión.')
    else:
        # Inicializa una figura de Plotly
        fig = go.Figure()

        for drv in session.drivers:
            drv_laps = session.laps.pick_driver(drv)
            abb = drv_laps['Driver'].iloc[0]

            try:
                color = plotting.driver_color(abb)
            except KeyError:
                color = 'gray'  # Color predeterminado para pilotos sin color específico

            # Añade una línea al gráfico por cada piloto, ajustando el tamaño de los marcadores
            fig.add_trace(go.Scatter(x=drv_laps['LapNumber'], y=drv_laps['Position'],
                                    mode='lines+markers',
                                    name=abb,
                                    line=dict(color=color),
                                    marker=dict(color=color, size=2)))  # Ajusta el tamaño aquí

        # Configura el layout del gráfico
        fig.update_layout(title=f'Evolución de las Posiciones - {gp_selected} {year}',
                        xaxis_title='Número de Vuelta',
                        yaxis_title='Posición',
                        yaxis=dict(autorange="reversed"),  # Invierte el eje Y para que la posición 1 esté arriba
                        legend_title='Piloto',
                        template='plotly_white')

        # Muestra el gráfico en Streamlit
        st.plotly_chart(fig)
elif opcion_grafico == 'Tiempos de vuelta':
    # Selección de parámetros por el usuario
    year = st.sidebar.selectbox('Selecciona el año', years, index=default_year_index)
    
    schedule = get_event_schedule(year)

    # Extrae los nombres de los Grandes Premios de la programación
    gps_disponibles = schedule['EventName'].tolist()

    # Crea un selectbox para que el usuario seleccione el GP
    default_gp_index = gps_disponibles.index('Bahrain Grand Prix') if 'Bahrain Grand Prix' in gps_disponibles else 0

    # Crea un selectbox para que el usuario seleccione el GP, con un valor por defecto
    gp_selected = st.sidebar.selectbox('Selecciona el Gran Premio', gps_disponibles, index=default_gp_index)


    session_type = st.sidebar.selectbox('Selecciona el tipo de sesión', ['FP1', 'FP2', 'FP3', 'Q', 'R'])

    session = cargar_datos_de_sesion(year, gp_selected, session_type)

    if session.laps.empty:
        st.error("No se encontraron datos para esta sesión.")
    else:
        # Lista de pilotos en la sesión
        drivers = session.laps['Driver'].unique()
        selected_driver = st.selectbox('Selecciona un piloto', drivers)

        # Filtrar los datos para el piloto seleccionado
        driver_laps = session.laps.pick_driver(selected_driver)

        # Convertir LapTime a segundos para facilitar la visualización
        driver_laps['LapTimeSeconds'] = driver_laps['LapTime'].dt.total_seconds()

        # Encuentra la vuelta más rápida para destacarla
        vuelta_rapida = driver_laps.loc[driver_laps['LapTimeSeconds'].idxmin()]

        # Crear el gráfico para el piloto seleccionado usando Plotly
        fig = go.Figure()

        # Añadir la línea de tiempos de vuelta
        fig.add_trace(go.Scatter(x=driver_laps['LapNumber'], y=driver_laps['LapTimeSeconds'],
                                mode='lines+markers',
                                name='Tiempo de vuelta',
                                line=dict(color='dodgerblue'),
                                marker=dict(color='dodgerblue', size=6)))

        # Destacar la vuelta más rápida
        fig.add_trace(go.Scatter(x=[vuelta_rapida['LapNumber']], y=[vuelta_rapida['LapTimeSeconds']],
                                mode='markers',
                                name='Vuelta más rápida',
                                marker=dict(color='red', size=10)))

        # Añadir texto de vuelta más rápida
        fig.add_annotation(x=vuelta_rapida['LapNumber'], y=vuelta_rapida['LapTimeSeconds'],
                        text=f"Vuelta más rápida: {vuelta_rapida['LapTimeSeconds']:.2f}s",
                        showarrow=True,
                        arrowhead=1,
                        ax=0,
                        ay=-40)

        # Personalizar layout del gráfico
        fig.update_layout(title=f'Tiempos de vuelta de {selected_driver}',
                        xaxis_title='Número de Vuelta',
                        yaxis_title='Tiempo de Vuelta (segundos)',
                        legend_title='Leyenda',
                        template='plotly_white')

        # Mostrar el gráfico en Streamlit
        st.plotly_chart(fig)


