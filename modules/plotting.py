import plotly.graph_objects as go
from fastf1 import plotting
import fastf1
import numpy as np
from colour import Color
from fastf1.core import Laps
from timple.timedelta import strftimedelta


def ajustar_tonalidad_color(color_hex, ajuste_luminosidad=0.05):
    # Convertir hex a color
    color = Color(color_hex)
    
    # Ajustar la luminosidad
    luminosidad_ajustada = max(min(color.luminance + ajuste_luminosidad, 1), 0)  # Asegurar que está en el rango [0, 1]
    color.luminance = luminosidad_ajustada
    
    return color.hex_l


def grafico_posiciones(session, gp_selected, year):
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

    return fig

fastf1.plotting.setup_mpl()  # Necesario para inicializar los colores de compuestos, si no se ha llamado antes

def grafico_tiempos_vuelta(session, selected_drivers):
    fig = go.Figure()

    # Generar colores para cada piloto
    
    for selected_driver in selected_drivers:
        # Filtrar los datos para el piloto seleccionado
        driver_laps = session.laps.pick_driver(selected_driver).copy()

        # Convertir LapTime a segundos para facilitar la visualización
        driver_laps['LapTimeSeconds'] = driver_laps['LapTime'].dt.total_seconds()

        # Obtener el color del piloto
        piloto_color = fastf1.plotting.driver_color(selected_driver)

        # Añadir la línea que une todas las vueltas del piloto con color específico
        fig.add_trace(go.Scatter(x=driver_laps['LapNumber'], y=driver_laps['LapTimeSeconds'],
                                 mode='lines',
                                 name=f'{selected_driver} Line',
                                 line=dict(color=piloto_color)))

        # Superponer marcadores coloreados por compuesto de neumático
        for compound, group_data in driver_laps.groupby('Compound'):
            color = fastf1.plotting.COMPOUND_COLORS.get(compound, '#FFFFFF')  # Usa un color por defecto si el compuesto no está en el diccionario
            fig.add_trace(go.Scatter(x=group_data['LapNumber'], y=group_data['LapTimeSeconds'],
                                     mode='markers',
                                     name=f'{selected_driver} {compound}',
                                     marker=dict(color=color, size=6),
                                     legendgroup=selected_driver))  # Agrupa en la leyenda por piloto

    # Personalizar layout del gráfico
    fig.update_layout(title='Comparación de Tiempos de Vuelta por Piloto y Tipo de Neumático',
                      xaxis_title='Número de Vuelta',
                      yaxis_title='Tiempo de Vuelta (segundos)',
                      legend_title='Piloto y Neumático',
                      template='plotly_white')

    return fig

import pandas as pd
def get_best_qualifying_time(row):
    # Esta función busca el mejor tiempo de clasificación priorizando Q3, luego Q2 y finalmente Q1.
    for q in ['Q3', 'Q2', 'Q1']:
        if pd.notna(row[q]):
            return row[q]
    return pd.NaT

def grafico_clasificacion(session):
    # Asegurarse de que los datos de la sesión están cargados
    session.load()
    
    # Obtener resultados de clasificación
    results = session.results.copy()

    # Aplicar la función para obtener el mejor tiempo de clasificación
    results['BestQualifyingTime'] = results.apply(get_best_qualifying_time, axis=1)
    
    # Filtrar las filas sin tiempo de clasificación
    filtered_results = results.dropna(subset=['BestQualifyingTime'])

    # Ordenar los resultados por el mejor tiempo de clasificación
    sorted_results = filtered_results.sort_values(by='BestQualifyingTime').reset_index(drop=True)

    # La pole es el mejor tiempo entre todos los pilotos que tengan un tiempo en Q3
    if 'Q3' in sorted_results.columns:
        pole_time = sorted_results[~sorted_results['Q3'].isna()].iloc[0]['Q3']
    else:
        pole_time = sorted_results.iloc[0]['BestQualifyingTime']
    
    sorted_results['TimeDelta'] = (sorted_results['BestQualifyingTime'] - pole_time).dt.total_seconds()
    

    # Preparar datos para Plotly
    drivers = sorted_results['Abbreviation']
    time_deltas = sorted_results['TimeDelta']

    # Colores del equipo para cada piloto
    team_colors = [fastf1.plotting.team_color(lap['TeamName']) for _, lap in sorted_results.iterrows()]

    # Crear el gráfico con Plotly
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=drivers,
        x=time_deltas,
        orientation='h',
        marker_color=team_colors
    ))

    # Personalización adicional del gráfico
    pole_lap_time_str = strftimedelta(pole_time, '%m:%s.%ms')
    fig.update_layout(
        title=f"{session.event['EventName']} {session.event.year} Qualifying<br>"
              f"Fastest Pole Lap: {pole_lap_time_str}",
        xaxis_title="Delta Time (s) from Pole",
        yaxis_title="Driver",
        yaxis_autorange="reversed",
        template="plotly_white"
    )

    return fig