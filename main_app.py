import streamlit as st
from modules.data_loading import cargar_datos_de_sesion, obtener_calendario
from modules.plotting import grafico_posiciones, grafico_tiempos_vuelta
from modules.utils import configurar_cache
from datetime import datetime


# Directorio de caché
cache_dir = 'cache'

configurar_cache(cache_dir)

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
    
    schedule = obtener_calendario(year)

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
        fig= grafico_posiciones(session, gp_selected, year)
        st.plotly_chart(fig)
        
elif opcion_grafico == 'Tiempos de vuelta':
    # Selección de parámetros por el usuario
    year = st.sidebar.selectbox('Selecciona el año', years, index=default_year_index)
    
    schedule = obtener_calendario(year)

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
        
        fig = grafico_tiempos_vuelta(session, selected_driver)
        
        # Mostrar el gráfico en Streamlit
        st.plotly_chart(fig)

