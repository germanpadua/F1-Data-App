import os
import streamlit as st
import fastf1
import pandas as pd
from datetime import datetime
from modules.data_loading import cargar_datos_de_sesion, obtener_calendario, cargar_mapa_circuito
from modules.plotting import (grafico_posiciones, grafico_tiempos_vuelta, grafico_clasificacion, 
                              grafico_comparar_vueltas_en_mapa, grafico_comparar_desgaste, 
                              mostrar_mapa_circuito, grafico_vel_media_equipo)
from modules.utils import configurar_cache
import requests
from streamlit_globe import streamlit_globe
import folium
from streamlit_folium import st_folium

def obtener_coordenadas_osm(query):
    nominatim_url = "https://nominatim.openstreetmap.org/search"
    parametros = {'q': query, 'format': 'json'}
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

    circuito_por_ciudad = df_circuitos[df_circuitos['NAME'].str.contains(ciudad, case=False)]
    if not circuito_por_ciudad.empty:
        return (circuito_por_ciudad.iloc[0]['LAT'], circuito_por_ciudad.iloc[0]['LNG'])

    circuitos_en_pais = df_circuitos[df_circuitos['COUNTRY'].str.contains(pais, case=False)]
    if len(circuitos_en_pais) == 1:
        return (circuitos_en_pais.iloc[0]['LAT'], circuitos_en_pais.iloc[0]['LNG'])

    return obtener_coordenadas_osm(ubicacion_evento)

def mostrar_analisis():
    if f'mostrar_analisis_{analisis_seleccionado}' in st.session_state and st.session_state[f'mostrar_analisis_{analisis_seleccionado}']:
        if analisis_seleccionado == 'Qualy':
            session = cargar_datos_de_sesion(year, gp_selected, 'Q')
            session.load(laps=True, telemetry=True, weather=True)
            if not session.laps.empty:
                fig = grafico_clasificacion(session, year)
                st.plotly_chart(fig)
                
                drivers = session.laps['Driver'].unique()
                selected_drivers = st.multiselect('Selecciona dos pilotos para comparar', drivers, default=(drivers[:1], drivers[1:2]))
                if len(selected_drivers) == 2:
                    fig2, fig3 = grafico_comparar_vueltas_en_mapa(session, selected_drivers[0], selected_drivers[1])
                    st.pyplot(fig2)
                    st.pyplot(fig3)
                else:
                    st.warning("Por favor, selecciona dos pilotos.")
            else:
                st.error("No se encontraron datos para esta sesión.")
        elif analisis_seleccionado == 'Carrera':
            session = cargar_datos_de_sesion(year, gp_selected, 'R')
            session.load(laps=True, telemetry=True, weather=True)
            opcion_grafico = st.selectbox(
                "Elige una opción de análisis:",
                ('Evolución de las posiciones', 'Tiempos de vuelta','Velocidad en carrera'),
                key="opcion_analisis_selectbox"
            )
            if opcion_grafico == 'Evolución de las posiciones':        
                if not session.laps.empty:
                    fig = grafico_posiciones(session, gp_selected, year)
                    st.plotly_chart(fig)
                else:
                    st.error('No se encontraron datos para esta sesión.')

            elif opcion_grafico == 'Tiempos de vuelta':
                if not session.laps.empty:
                    drivers = session.laps['Driver'].unique()
                    selected_drivers = st.multiselect('Selecciona pilotos para comparar', drivers, default=drivers[:1])
                    if selected_drivers:
                        fig = grafico_tiempos_vuelta(session, year, selected_drivers)
                        st.plotly_chart(fig)
                    else:
                        st.warning("Por favor, selecciona al menos un piloto.")
                else:
                    st.error("No se encontraron datos para esta sesión.")

            elif opcion_grafico == 'Velocidad en carrera':
                if not session.laps.empty:
                    fig1, fig2 = grafico_comparar_desgaste(session, year)
                    st.pyplot(fig1)
                    st.pyplot(fig2)

                    fig3 = grafico_vel_media_equipo(session)
                    st.pyplot(fig3)
                else:
                    st.error("No se encontraron datos para esta sesión.")
        else:
            st.warning(f"Análisis de {analisis_seleccionado} no disponible.")

# Inicialización y configuración de la cache
cache_dir = 'cache'
configurar_cache(cache_dir)

st.title('Análisis de Fórmula 1')

# Paso 1: Selección del año
st.header("Selecciona el Año y el Circuito")
years = [2020, 2021, 2022, 2023, 2024]
current_year = datetime.now().year
default_year_index = years.index(current_year) if current_year in years else len(years) - 1
year = st.selectbox('Año', years, index=default_year_index)

# Paso 2: Selección del circuito
schedule = obtener_calendario(year)
gps_disponibles = schedule['EventName'].unique().tolist()
gps_disponibles = [gp for gp in gps_disponibles if "Pre-Season" not in gp]
gp_selected = st.selectbox('Gran Premio', gps_disponibles)

# Obtén la ubicación del circuito seleccionado para mostrar en el mapa
ubicacion_evento = schedule.loc[schedule['EventName'] == gp_selected, ['Location', 'Country']].apply(lambda x: f"{x['Location']}, {x['Country']}", axis=1).values[0]
coordenadas = obtener_coordenadas_circuito(ubicacion_evento)

# Información adicional del circuito
if st.checkbox("Mostrar información adicional del circuito"):
    st.write(f"Ubicación: {ubicacion_evento}")
    if coordenadas:
        latitude = coordenadas[0]
        longitude = coordenadas[1]
        col1, col2 = st.columns(2)

        with col1:
            pointsData = [{'lat': latitude, 'lng': longitude, 'size': 0.3, 'color': 'red'}]
            labelsData = [{'lat': latitude, 'lng': longitude, 'size': 0.3, 'color': 'red', 'text': ubicacion_evento}]
            streamlit_globe(pointsData=pointsData, labelsData=labelsData, daytime='day', width=400, height=400)

        with col2:
            m = folium.Map(location=[latitude, longitude], zoom_start=14)
            folium.Marker([latitude, longitude], popup=f"<i>{ubicacion_evento}</i>", tooltip=ubicacion_evento).add_to(m)
            st_folium(m, width=400, height=400)
    else:
        st.error('No se pudieron obtener las coordenadas del circuito seleccionado.')
        
    if os.path.exists("data/circuit_image/" + gp_selected + ".png"):
        circuito = cargar_mapa_circuito("data/circuit_image/" + gp_selected + ".png")
        st.pyplot(circuito)
    else:
        for years in range(2024, 2018, -1):
            funciona = False
            try:
                schedule = obtener_calendario(years)
                if gp_selected in schedule['EventName'].unique():
                    if os.path.exists("data/circuit_image/" + gp_selected + ".png"):
                        circuito = cargar_mapa_circuito("data/circuit_image/" + gp_selected + ".png")
                    else:
                        session = cargar_datos_de_sesion(years, gp_selected, 'R')
                        session.load(laps=True, telemetry=True, weather=True)
                        lap = session.laps.pick_fastest()
                        pos = lap.get_pos_data()
                        circuit_info = session.get_circuit_info()
                        circuito = mostrar_mapa_circuito(lap, pos, circuit_info, session.event['EventName'])
                    st.pyplot(circuito)
                    funciona = True
            except Exception as e:
                print(f"No se pudo cargar los datos para el año {years}: {e}")
            if funciona:
                break

if 'mostrar_analisis' not in st.session_state:
    st.session_state['mostrar_analisis'] = False

event = fastf1.get_event(year, gp_selected)
event_date = event.get_session_date('FP1', utc=True)

fechas = None

if event['EventFormat'] == 'conventional':
    prac1_date = event.get_session_date('FP1', utc=True)
    prac2_date = event.get_session_date('FP2', utc=True)
    prac3_date = event.get_session_date('FP3', utc=True)
    qualy_date = event.get_session_date('Q', utc=True)
    race_date = event.get_session_date('R', utc=True)
    fechas = {'FP1': prac1_date, 'FP2': prac2_date, 'FP3': prac3_date, 'Qualy': qualy_date, 'Carrera': race_date}

elif event['EventFormat'] == 'sprint':
    prac1_date = event.get_session_date('FP1', utc=True)
    qualy_date = event.get_session_date('Q', utc=True)
    prac2_date = event.get_session_date('FP2', utc=True)
    sprint_date = event.get_session_date('S', utc=True)
    race_date = event.get_session_date('R', utc=True)
    fechas = {'FP1': prac1_date, 'Qualy': qualy_date, 'FP2': prac2_date, 'Sprint': sprint_date, 'Carrera': race_date}

elif event['EventFormat'] == 'sprint-shootout':
    prac1_date = event.get_session_date('FP1', utc=True)
    qualy_date = event.get_session_date('Q', utc=True)
    sprint_shootout_date = event.get_session_date('SS', utc=True)
    sprint_date = event.get_session_date('S', utc=True)
    race_date = event.get_session_date('R', utc=True)
    fechas = {'FP1': prac1_date, 'Qualy': qualy_date, 'Sprint Shootout': sprint_shootout_date, 'Sprint': sprint_date, 'Carrera': race_date}

elif event['EventFormat'] == 'sprint_qualifying':
    prac1_date = event.get_session_date('FP1', utc=True)
    sprint_qualy_date = event.get_session_date('SQ', utc=True)
    sprint_date = event.get_session_date('S', utc=True)
    qualy_date = event.get_session_date('Q', utc=True)
    race_date = event.get_session_date('R', utc=True)
    fechas = {'FP1': prac1_date, 'Sprint Qualy': sprint_qualy_date, 'Sprint': sprint_date, 'Qualy': qualy_date, 'Carrera': race_date}
else:
    st.write("No se ha encontrado el formato del evento")
    st.write(event['EventFormat'])

if fechas:
    current_time = datetime.now()
    if current_time < fechas['FP1']:
        countdown = fechas['Carrera'] - current_time
        days_remaining = countdown.days
        hours_remaining = countdown.seconds // 3600
        countdown_str = f"{days_remaining} días y {hours_remaining} horas hasta la carrera. El análisis estará disponible tras la carrera"
        st.warning(countdown_str)
        st.session_state['mostrar_analisis'] = False
    else:
        analisis_opciones = [key for key, date in fechas.items() if current_time >= date]
        if analisis_opciones:
            analisis_seleccionado = st.selectbox("Selecciona una sesión para analizar", analisis_opciones, key="selectbox_sesiones")
            st.session_state[f'mostrar_analisis_{analisis_seleccionado}'] = True

    mostrar_analisis()
else:
    st.write("No se ha definido 'fechas'. Verifica el formato del evento.")