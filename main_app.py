import streamlit as st
import fastf1
from fastf1 import plotting
from matplotlib import pyplot as plt
import pandas as pd

# Configuración inicial de FastF1 y matplotlib para la aplicación
fastf1.Cache.enable_cache('cache')  # Habilita la caché de FastF1
plotting.setup_mpl(misc_mpl_mods=False)  # Configuración de matplotlib para FastF1

# Función para cargar los datos de la sesión
@st.cache_data
def cargar_datos_de_sesion(year, gp, session_type):
    session = fastf1.get_session(year, gp, session_type)
    session.load(telemetry=False, weather=False)
    return session

st.title('Análisis de Posiciones en Carrera en Fórmula 1')

# Selección de parámetros por el usuario
year = st.sidebar.selectbox('Selecciona el año', [2020, 2021, 2022, 2023])
gp = st.sidebar.text_input('Escribe el Gran Premio', 'Spain')
session_type = 'R'  # Para análisis de carrera

session = cargar_datos_de_sesion(year, gp, session_type)

# Crear el gráfico de posiciones de los pilotos
fig, ax = plt.subplots(figsize=(8.0, 4.9))

for drv in session.drivers:
    drv_laps = session.laps.pick_driver(drv)

    abb = drv_laps['Driver'].iloc[0]
    try:
        color = plotting.driver_color(abb)
    except KeyError:
        color = 'gray'  # Color predeterminado para pilotos sin color específico
    
    ax.plot(drv_laps['LapNumber'], drv_laps['Position'], label=abb, color=color)


# Finalizar el gráfico
ax.set_ylim([20.5, 0.5])
ax.set_yticks([1, 5, 10, 15, 20])
ax.set_xlabel('Vuelta')
ax.set_ylabel('Posición')

# Añadir la leyenda fuera del área del gráfico
ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
plt.tight_layout()

# Mostrar el gráfico en Streamlit
st.pyplot(fig)
