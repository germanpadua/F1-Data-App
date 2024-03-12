import os
import streamlit as st
import fastf1
import pandas as pd
from datetime import datetime
from modules.data_loading import cargar_datos_de_sesion, obtener_calendario
from modules.plotting import grafico_posiciones, grafico_tiempos_vuelta
from modules.utils import configurar_cache
import requests
from streamlit_globe import streamlit_globe
import folium
from streamlit_folium import st_folium



def obtener_coordenadas_osm(query):
    """Obtiene las coordenadas (latitud y longitud) de una consulta dada usando OpenStreetMap Nominatim API.
    
    Args:
        query (str): La consulta de búsqueda, por ejemplo, el nombre de un circuito de Fórmula 1.
    
    Returns:
        tuple: Un par de coordenadas (latitud, longitud).
    """
    nominatim_url = "https://nominatim.openstreetmap.org/search"
    parametros = {
        'q': query,
        'format': 'json'
    }
    response = requests.get(nominatim_url, params=parametros)
    if response.status_code == 200:
        resultados = response.json()
        if resultados:
            latitud = resultados[0]['lat']
            longitud = resultados[0]['lon']
            return (latitud, longitud)
        else:
            return None
    else:
        return None

# Inicialización y configuración de la cache
cache_dir = 'cache'
configurar_cache(cache_dir)

st.title('Análisis en Fórmula 1')



# Paso 1: Selección del año
st.header("Selecciona el Año y el Circuito")
years = [2020, 2021, 2022, 2023, 2024]
current_year = datetime.now().year
default_year_index = years.index(current_year) if current_year in years else len(years) - 1
year = st.selectbox('Año', years, index=default_year_index)

# Paso 2: Selección del circuito
schedule = obtener_calendario(year)
gps_disponibles = schedule['EventName'].unique().tolist()
gp_selected = st.selectbox('Gran Premio', gps_disponibles)

# Obtén la ubicación del circuito seleccionado para mostrar en el mapa
# Suponiendo que puedes obtener la ubicación del evento así
ubicacion_evento = schedule.loc[schedule['EventName'] == gp_selected, ['Location', 'Country']].apply(lambda x: f"{x['Location']}, {x['Country']}", axis=1).values[0]
# Obtener coordenadas del circuito seleccionado
coordenadas = obtener_coordenadas_osm(ubicacion_evento)



# Información adicional del circuito
if st.checkbox("Mostrar información adicional del circuito"):
    st.write(f"Ubicación: {ubicacion_evento}")
    # Aquí puedes agregar más información relevante sobre el circuito
    if coordenadas:
        latitude = coordenadas[0]
        longitude = coordenadas[1]
        pointsData=[{'lat': coordenadas[0], 'lng': coordenadas[1], 'size': 0.3, 'color': 'red'}]
        labelsData=[{'lat': coordenadas[0], 'lng': coordenadas[1], 'size': 0.3, 'color': 'red', 'text': ubicacion_evento}]
        streamlit_globe(pointsData=pointsData, labelsData=labelsData, daytime='day', width=800, height=600)
        
        # Crear un mapa de Folium centrado en las coordenadas
        m = folium.Map(location=[latitude, longitude], zoom_start=12)

        # Añadir un marcador para el circuito
        folium.Marker(
            [latitude, longitude],
            popup=f"<i>{ubicacion_evento}</i>",
            tooltip=ubicacion_evento
        ).add_to(m)

        # Mostrar el mapa en Streamlit
        st_folium(m, width=725, height=500)

    else:
        st.error('No se pudieron obtener las coordenadas del circuito seleccionado.')

    
if 'mostrar_analisis' not in st.session_state:
    st.session_state['mostrar_analisis'] = False
    
# Botón para ocultar información y mostrar las opciones de análisis
# Botón para cambiar el estado de mostrar_analisis
if st.button("Explorar análisis de Fórmula 1"):
    st.session_state['mostrar_analisis'] = True
    
if st.session_state['mostrar_analisis']:
    st.header("Análisis en Fórmula 1")
    opcion_grafico = st.selectbox(
        "Elige una opción de análisis:",
        ('Evolución de las posiciones', 'Tiempos de vuelta')
    )

    # Lógica para mostrar el gráfico basado en la elección
    if opcion_grafico == 'Evolución de las posiciones':
        session_type = 'R'  # Para análisis de carrera
        session = cargar_datos_de_sesion(year, gp_selected, session_type)
        if not session.laps.empty:
            fig = grafico_posiciones(session, gp_selected, year)
            st.plotly_chart(fig)
        else:
            st.error('No se encontraron datos para esta sesión.')

    elif opcion_grafico == 'Tiempos de vuelta':
        session_type = 'R'
        session = cargar_datos_de_sesion(year, gp_selected, session_type)
        if not session.laps.empty:
            drivers = session.laps['Driver'].unique()
            selected_driver = st.selectbox('Selecciona un piloto', drivers)
            fig = grafico_tiempos_vuelta(session, selected_driver)
            st.plotly_chart(fig)
        else:
            st.error("No se encontraron datos para esta sesión.")
