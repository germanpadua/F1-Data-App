import os
import streamlit as st
import fastf1
import pandas as pd
from datetime import datetime
from modules.data_loading import cargar_datos_de_sesion, obtener_calendario
from modules.plotting import grafico_posiciones, grafico_tiempos_vuelta, grafico_clasificacion, grafico_comparar_vueltas, grafico_comparar_vueltas_en_mapa
from modules.utils import configurar_cache
import requests
from streamlit_globe import streamlit_globe
import folium
from streamlit_folium import st_folium
import matplotlib.pyplot as plt
from fastf1 import plotting
import numpy as np


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
    
    
def obtener_coordenadas_circuito(ubicacion_evento, archivo_circuitos='data/circuitos_f1.csv'):
    df_circuitos = pd.read_csv(archivo_circuitos)
    ciudad, pais = ubicacion_evento.split(', ')

    # Primero intenta encontrar un circuito por la ciudad
    circuito_por_ciudad = df_circuitos[df_circuitos['NAME'].str.contains(ciudad, case=False)]
    if not circuito_por_ciudad.empty:
        return (circuito_por_ciudad.iloc[0]['LAT'], circuito_por_ciudad.iloc[0]['LNG'])

    # Si no encuentra por ciudad, verifica si hay un único circuito en el país
    circuitos_en_pais = df_circuitos[df_circuitos['COUNTRY'].str.contains(pais, case=False)]
    if len(circuitos_en_pais) == 1:
        return (circuitos_en_pais.iloc[0]['LAT'], circuitos_en_pais.iloc[0]['LNG'])

    # Si no hay un único circuito en el país, busca las coordenadas de la ciudad y país
    return obtener_coordenadas_ciudad(ubicacion_evento)


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
coordenadas = obtener_coordenadas_circuito(ubicacion_evento)



# Información adicional del circuito
if st.checkbox("Mostrar información adicional del circuito"):
    st.write(f"Ubicación: {ubicacion_evento}")
    # Aquí puedes agregar más información relevante sobre el circuito
    if coordenadas:
        latitude = coordenadas[0]
        longitude = coordenadas[1]
        # Utiliza st.columns para adaptar el tamaño de los widgets y mapas
        col1, col2 = st.columns(2)

        # En la columna de la izquierda, puedes colocar el globo terráqueo o cualquier otro contenido
        with col1:
            pointsData=[{'lat': latitude, 'lng': longitude, 'size': 0.3, 'color': 'red'}]
            labelsData=[{'lat': latitude, 'lng': longitude, 'size': 0.3, 'color': 'red', 'text': ubicacion_evento}]
            # Ajusta el tamaño basado en el ancho de la columna
            streamlit_globe(pointsData=pointsData, labelsData=labelsData, daytime='day', width=200, height=400)

        # En la columna de la derecha, puedes mostrar el mapa de Folium
        with col2:
            # Crear un mapa de Folium centrado en las coordenadas
            m = folium.Map(location=[latitude, longitude], zoom_start=14)
            # Añadir un marcador para el circuito
            folium.Marker([latitude, longitude], popup=f"<i>{ubicacion_evento}</i>", tooltip=ubicacion_evento).add_to(m)
            # Ajusta el tamaño basado en el ancho de la columna
            st_folium(m, width=200, height=400)

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
        ('Evolución de las posiciones', 'Tiempos de vuelta', 'Tiempos en clasificación')
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
            selected_drivers = st.multiselect('Selecciona pilotos para comparar', drivers, default=drivers[:1])
            if selected_drivers:
                fig = grafico_tiempos_vuelta(session, selected_drivers)
                st.plotly_chart(fig)
            else:
                st.warning("Por favor, selecciona al menos un piloto.")
        else:
            st.error("No se encontraron datos para esta sesión.")
            
    
    elif opcion_grafico == 'Tiempos en clasificación':
        session_type = 'Q'
        session = cargar_datos_de_sesion(year, gp_selected, session_type)
        if not session.laps.empty:
            fig = grafico_clasificacion(session)
            st.plotly_chart(fig)
            
            drivers = session.laps['Driver'].unique()
            selected_drivers = st.multiselect('Selecciona dos pilotos para comparar', drivers, default=(drivers[:1], drivers[1:2]))
            if len(selected_drivers)==2:
                fig2 = grafico_comparar_vueltas_en_mapa(session, selected_drivers[0], selected_drivers[1])
                st.pyplot(fig2)

            else:
                st.warning("Por favor, selecciona dos pilotos.")
                
        else:
            st.error("No se encontraron datos para esta sesión.")