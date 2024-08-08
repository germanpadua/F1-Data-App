import plotly.graph_objects as go
from fastf1 import plotting
import fastf1
import numpy as np
from colour import Color
from fastf1.core import Laps
from timple.timedelta import strftimedelta
from matplotlib.collections import LineCollection
import matplotlib as mpl
from matplotlib import pyplot as plt
import pandas as pd
import itertools
import seaborn as sns
import streamlit as st
import datetime
from matplotlib.colors import to_hex
from itertools import cycle
from modules.utils import rotate
from matplotlib.ticker import FuncFormatter
from scipy.signal import savgol_filter


import pickle
import os

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
def format_func(value, tick_number):
        minutes = int(value // 60)
        seconds = int(value % 60)
        return f"{minutes}:{seconds:02d}"
    
def grafico_tiempos_vuelta(session, selected_drivers, year):
    fig = go.Figure()
    # Definir una paleta de colores para los pilotos
    paleta_colores_pilotos = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
    
    # Ciclar a través de la paleta de colores si hay más pilotos que colores
    ciclo_colores_pilotos = itertools.cycle(paleta_colores_pilotos)
    
    # Variable para almacenar el tiempo máximo de vuelta
    max_lap_time = 0  
    
    for selected_driver in selected_drivers:
        # Filtrar los datos para el piloto seleccionado
        driver_laps = session.laps.pick_driver(selected_driver).pick_quicklaps().copy()
        # Convertir LapTime a segundos para facilitar la visualización
        driver_laps['LapTimeSeconds'] = driver_laps['LapTime'].dt.total_seconds()
        # Actualizar el tiempo máximo de vuelta si es necesario
        max_lap_time = max(max_lap_time, driver_laps['LapTimeSeconds'].max())
        # Obtener el color del piloto de la paleta
        piloto_color = next(ciclo_colores_pilotos)
        # Añadir la línea que une todas las vueltas del piloto con color específico
        fig.add_trace(go.Scatter(x=driver_laps['LapNumber'], y=driver_laps['LapTimeSeconds'],
                                 mode='lines',
                                 name=f'{selected_driver} Line',
                                 line=dict(color=piloto_color)))
        # Superponer marcadores coloreados por compuesto de neumático
        for compound, group_data in driver_laps.groupby('Compound'):
            color = fastf1.plotting.COMPOUND_COLORS.get(compound, '#FFFFFF')
            fig.add_trace(go.Scatter(x=group_data['LapNumber'], y=group_data['LapTimeSeconds'],
                                     mode='markers',
                                     name=f'{selected_driver} {compound}',
                                     marker=dict(color=color, size=6),
                                     legendgroup=selected_driver))
    # Definir la función de formato de tiempo
    def format_time(seconds):
        minutes = int(seconds // 60)
        seconds_remainder = seconds % 60
        return f"{minutes}:{seconds_remainder:02.0f}"
    # Generar ticks cada 15 segundos hasta el tiempo máximo de vuelta, más un buffer
    tickvals = np.arange(0, max_lap_time + 1, 1)
    ticktext = [format_time(val) for val in tickvals]
    # Personalizar layout del gráfico
    fig.update_layout(title='Comparación de Tiempos de Vuelta por Piloto y Tipo de Neumático',
                      xaxis_title='Número de Vuelta',
                      yaxis=dict(title='Tiempo de Vuelta (min:seg)', tickvals=tickvals, ticktext=ticktext),
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
def grafico_clasificacion(session, year):
    # Asegúrate de cargar los datos de la sesión
    session.load()
    
    # Obtén los resultados de clasificación y calcula el mejor tiempo
    results = session.results.copy()
    results['BestQualifyingTime'] = results.apply(get_best_qualifying_time, axis=1)
    filtered_results = results.dropna(subset=['BestQualifyingTime'])
    sorted_results = filtered_results.sort_values(by='BestQualifyingTime').reset_index(drop=True)
    pole_time = sorted_results.iloc[0]['BestQualifyingTime']
    sorted_results['TimeDelta'] = (sorted_results['BestQualifyingTime'] - pole_time).dt.total_seconds()
     # Genera colores para cada equipo utilizando una paleta más grande para evitar duplicados
    fallback_colors = cycle(sns.color_palette("tab20", n_colors=20))
    
    team_colors_map = {}
    for _, lap in sorted_results.iterrows():
        team_name = lap['TeamName']
        if team_name not in team_colors_map:
            try:
                color = fastf1.plotting.team_color(team_name)
            except KeyError:
                color = next(fallback_colors)
                color = to_hex(color)
            # Verifica que el color no haya sido utilizado ya
            while color in team_colors_map.values():
                color = next(fallback_colors)
                color = to_hex(color)
            team_colors_map[team_name] = color
    team_colors = [team_colors_map[lap['TeamName']] for _, lap in sorted_results.iterrows()]
    # Construye el gráfico
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=sorted_results['Abbreviation'],
        x=sorted_results['TimeDelta'],
        orientation='h',
        marker=dict(color=team_colors)
    ))
    # Personaliza el layout
    fig.update_layout(
        title=f"{session.event['EventName']} {session.event.year} Qualifying Comparison",
        xaxis_title="Time Delta (s) from Pole",
        yaxis=dict(autorange="reversed"),
        template="plotly_white"
    )
    return fig
def grafico_delta_vs_distancia(comparacion):
    # Crear la figura y el eje
    fig, ax = plt.subplots(figsize=(15, 5))
    # Aplicar un filtro de media móvil
    #comparacion['DeltaSuavizado'] = (comparacion['DeltaTiempo'].dt.total_seconds()).rolling(window=5, center=True).mean()
    # O aplicar un filtro Savitzky-Golay para suavizar los datos
    comparacion['DeltaSuavizado'] = savgol_filter(comparacion['DeltaTiempo'].dt.total_seconds(), 51, 3) # window_size 51, polynomial order 3
    # Dibujar el gráfico de línea con la diferencia de tiempo
    ax.plot(comparacion['Distance'], comparacion['DeltaSuavizado'], label='Delta Tiempo')
    # Establecer etiquetas y título
    ax.set_xlabel('Distancia (m)')
    ax.set_ylabel('Delta (s)')
    ax.set_title('Delta de Tiempo (Suavizado) a lo largo de la Vuelta')
    # Opcional: establecer límites para el eje Y si es necesario
    # ax.set_ylim(-1, 1)
    # Opcional: añadir una línea horizontal en y=0 para claridad
    ax.axhline(0, color='black', linewidth=0.5, linestyle='--')
    # Añadir leyenda
    ax.legend()
    # Añadir una rejilla
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    # Ajustar la trama y guardar o mostrar el gráfico
    plt.tight_layout()
    # plt.show()  # Mostrar la imagen en un entorno interactivo
    return fig
def grafico_comparar_vueltas_en_mapa(session, piloto1, piloto2):
    # Configurar el esquema de colores para la trama
    fastf1.plotting.setup_mpl()
    colormap = mpl.cm.PiYG
    # Seleccionar los pilotos y obtener sus mejores vueltas de telemetría
    # Obtener los resultados de la clasificación y los tiempos finales de clasificación para cada piloto
    results = session.results.copy()
    results['BestQualifyingTime'] = results.apply(get_best_qualifying_time, axis=1)
    tiempo_final_piloto1 = results.loc[results['Abbreviation'] == piloto1, 'BestQualifyingTime'].iloc[0]
    tiempo_final_piloto2 = results.loc[results['Abbreviation'] == piloto2, 'BestQualifyingTime'].iloc[0]
    # Identificar la vuelta que corresponde a este mejor tiempo de clasificación
    vuelta_final_piloto1 = session.laps.pick_driver(piloto1)[session.laps['LapTime'] == tiempo_final_piloto1].iloc[0]
    vuelta_final_piloto2 = session.laps.pick_driver(piloto2)[session.laps['LapTime'] == tiempo_final_piloto2].iloc[0]
    # Obtener telemetría para las vueltas finales de clasificación
    tel_piloto1 = vuelta_final_piloto1.get_telemetry().add_distance()
    tel_piloto2 = vuelta_final_piloto2.get_telemetry().add_distance()
    # Realizar una unión asof para comparar las vueltas basándose en la distancia
    comparacion = pd.merge_asof(tel_piloto1, tel_piloto2, on='Distance', suffixes=('_piloto1', '_piloto2'), direction='nearest')
    # Calcular la diferencia de tiempo en cada punto de la vuelta
    comparacion['DeltaTiempo'] = comparacion['Time_piloto1'] - comparacion['Time_piloto2']
    x = comparacion['X_piloto1']              # values for x-axis
    y = comparacion['Y_piloto1']              # values for y-axis
    color = comparacion['DeltaTiempo'].dt.total_seconds()     # value to base color gradient on
    points = np.array([x, y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points[:-1], points[1:]], axis=1)
    # Formato del título con nombres de los pilotos y la sesión
    titulo = f'Comparativa de Qualy: {piloto1} (Fucsia) vs {piloto2} (Verde)'
    # Configuración del título del gráfico
    fig, ax = plt.subplots(sharex=True, sharey=True, figsize=(12, 6.75))
    fig.suptitle(titulo, size=24, y=0.97)
    # Adjust margins and turn of axis
    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.12)
    ax.axis('off')
    
    # After this, we plot the data itself.
    # Create background track line
    ax.plot(x, y,
            color='black', linestyle='-', linewidth=16, zorder=0)
    ax.set_aspect('equal')
    
    # Create a continuous norm to map from data points to colors
    
    #norm = mpl.colors.TwoSlopeNorm(vmin=-absmax, vcenter=0.0, vmax=absmax)
    norm = mpl.colors.TwoSlopeNorm(vmin=color.min(), vcenter=0.0, vmax=color.max())
    #norm = mpl.colors.SymLogNorm(linthresh=0.05, vmin=-absmax, vmax=absmax)
    lc = LineCollection(segments, cmap=colormap, norm=norm,
                        linestyle='-', linewidth=5)
    # Set the values used for colormapping
    lc.set_array(color)
    # Merge all line segments together
    ax.add_collection(lc)
    # Calcular la dirección de la flecha
    dx = x.iloc[1] - x.iloc[0]  # Diferencia en X entre el segundo y primer punto
    dy = y.iloc[1] - y.iloc[0]  # Diferencia en Y entre el segundo y primer punto
    # Añadir la flecha indicando el comienzo de la vuelta
    ax.annotate('', xy=(x.iloc[1], y.iloc[1]), xytext=(x.iloc[0], y.iloc[0]),
                arrowprops=dict(facecolor='gold', edgecolor='gold', arrowstyle='simple', lw=5),
                annotation_clip=False)
    # Añadir texto explicativo para la flecha
    # Ajusta la posición (x, y) según sea necesario para evitar la superposición con otros elementos
    ax.text(x.iloc[0] - 300, y.iloc[0], 'Inicio de la vuelta', color='gold', ha='right', va='top')
    
    # Finally, we create a color bar as a legend.
    cbaxes = fig.add_axes([0.25, 0.05, 0.5, 0.05])
    
    #normlegend = mpl.colors.TwoSlopeNorm(vmin=-absmax, vcenter=0.0, vmax=absmax)
    normlegend = mpl.colors.TwoSlopeNorm(vmin=color.min(), vcenter=0.0, vmax=color.max())
    #normlegend = mpl.colors.SymLogNorm(linthresh=0.003, vmin=-absmax, vmax=absmax)
    legend = mpl.colorbar.ColorbarBase(cbaxes, norm=normlegend, cmap=colormap,
                                    orientation="horizontal")
    
    # Añadir texto explicativo cerca de la barra de colores
    plt.text(0.25, 0.11, piloto1 + ' por delante', transform=fig.transFigure, color='fuchsia', ha='left')
    plt.text(0.75, 0.11, piloto2 + ' por delante', transform=fig.transFigure, color='green', ha='right')
    
    fig2 = grafico_delta_vs_distancia(comparacion)
    return fig, fig2
def grafico_comparar_vueltas():
    # Configurar el esquema de colores para la trama
    fastf1.plotting.setup_mpl()
    # Cargar la sesión
    session = fastf1.get_session(2023, 'Bahrain Grand Prix', 'Q')
    session.load()
    # Seleccionar los pilotos y obtener sus mejores vueltas de telemetría
    piloto1 = 'HAM'
    piloto2 = 'VER'
    vuelta_piloto1 = session.laps.pick_driver(piloto1).pick_fastest()
    vuelta_piloto2 = session.laps.pick_driver(piloto2).pick_fastest()
    tel_piloto1 = vuelta_piloto1.get_telemetry().add_distance()
    tel_piloto2 = vuelta_piloto2.get_telemetry().add_distance()
    # Asegurar que los datos están ordenados por distancia antes de intentar cualquier operación
    tel_piloto1 = tel_piloto1.sort_values(by='Distance')
    tel_piloto2 = tel_piloto2.sort_values(by='Distance')
    # Realizar una unión asof para comparar las vueltas basándose en la distancia
    comparacion = pd.merge_asof(tel_piloto1, tel_piloto2, on='Distance', suffixes=('_piloto1', '_piloto2'), direction='nearest')
    # Calcular la diferencia de tiempo en cada punto de la vuelta
    comparacion['DeltaTiempo'] = comparacion['Time_piloto1'] - comparacion['Time_piloto2']
    # Visualización
    fig, ax = plt.subplots()
    # Trazar la diferencia de tiempo como una función de la distancia recorrida
    ax.plot(comparacion['Distance'], comparacion['DeltaTiempo'].dt.total_seconds(), label='Diferencia de tiempo')
    # Establecer el eje y para mostrar las diferencias de tiempo en segundos
    ax.set_xlabel('Distancia recorrida (m)')
    ax.set_ylabel('Diferencia de tiempo (s)')
    # Establecer leyenda y título
    ax.legend()
    ax.set_title(f'Diferencia de tiempo entre {piloto1} y {piloto2}')
    return fig
def grafico_comparar_desgaste(session, year):
    # Preparación del entorno de matplotlib
    #fastf1.plotting.setup_mpl(mpl_timedelta_support=False, misc_mpl_mods=False)
    # Obtener los pilotos que terminaron en los puntos y sus vueltas rápidas, excluyendo vueltas lentas
    point_finishers = session.results[:10]['Abbreviation'].tolist()
    driver_laps = session.laps.pick_drivers(point_finishers).pick_quicklaps()
    driver_laps = driver_laps.reset_index(drop=True)
    # Colores de los pilotos basados en sus abreviaciones
    driver_colors = {}
    fallback_colors = cycle(sns.color_palette("tab20", n_colors=20))
    for abv in point_finishers:
        try:
            # Intenta obtener el color del piloto desde la configuración de fastf1
            color = fastf1.plotting.DRIVER_COLORS[fastf1.plotting.DRIVER_TRANSLATE[abv]]
        except KeyError:
            # Si el piloto no tiene un color asignado, genera uno aleatorio
            color = next(fallback_colors)
            color = to_hex(color)
            # Asegúrate de que el color generado no esté ya utilizado
            while color in driver_colors.values():
                color = next(fallback_colors)
                color = to_hex(color)
        driver_colors[abv] = color
    # Creación de la figura
    fig, ax = plt.subplots(figsize=(10, 5))
    # Conversión de timedelta a segundos para compatibilidad con Seaborn
    driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()
    # Gráfico de violin para mostrar las distribuciones de los tiempos de vuelta
    sns.violinplot(data=driver_laps, x="Driver", y="LapTime(s)", hue="Driver",
                   inner=None, palette=driver_colors, order=point_finishers)
    # Gráfico de swarm para mostrar los tiempos de vuelta individuales, diferenciados por compuesto de neumático
    sns.swarmplot(data=driver_laps, x="Driver", y="LapTime(s)",
                  hue="Compound", palette=fastf1.plotting.COMPOUND_COLORS,
                  hue_order=["SOFT", "MEDIUM", "HARD"],
                  order=point_finishers, linewidth=0, size=4)
    # Ajustes estéticos del gráfico
    ax.set_xlabel("Driver")
    ax.set_ylabel("Lap Time (s)")
    plt.suptitle("Lap Time Distributions by Driver and Tyre Compound")
    # Mejora de la estética con despine
    sns.despine(left=True, bottom=True)
    plt.tight_layout()
    
    
    # Obtener los pilotos que terminaron en los puntos y sus vueltas rápidas, excluyendo vueltas lentas
    no_point_finishers = session.results[10:]['Abbreviation'].tolist()
    driver_laps = session.laps.pick_drivers(no_point_finishers).pick_quicklaps()
    driver_laps = driver_laps.reset_index(drop=True)
    # Colores de los pilotos basados en sus abreviaciones
    driver_colors = {}
    fallback_colors = cycle(sns.color_palette("tab20", n_colors=20))
    for abv in no_point_finishers:
        try:
            # Intenta obtener el color del piloto desde la configuración de fastf1
            color = fastf1.plotting.DRIVER_COLORS[fastf1.plotting.DRIVER_TRANSLATE[abv]]
        except KeyError:
            # Si el piloto no tiene un color asignado, genera uno aleatorio
            color = next(fallback_colors)
            color = to_hex(color)
            # Asegúrate de que el color generado no esté ya utilizado
            while color in driver_colors.values():
                color = next(fallback_colors)
                color = to_hex(color)
        driver_colors[abv] = color
    # Creación de la figura
    fig2, ax = plt.subplots(figsize=(10, 5))
    # Conversión de timedelta a segundos para compatibilidad con Seaborn
    driver_laps["LapTime(s)"] = driver_laps["LapTime"].dt.total_seconds()
    # Gráfico de violin para mostrar las distribuciones de los tiempos de vuelta
    sns.violinplot(data=driver_laps, x="Driver", y="LapTime(s)", hue="Driver",
                   inner=None, palette=driver_colors, order=no_point_finishers)
    # Gráfico de swarm para mostrar los tiempos de vuelta individuales, diferenciados por compuesto de neumático
    sns.swarmplot(data=driver_laps, x="Driver", y="LapTime(s)",
                  hue="Compound", palette=fastf1.plotting.COMPOUND_COLORS,
                  hue_order=["SOFT", "MEDIUM", "HARD"],
                  order=no_point_finishers, linewidth=0, size=4)
    # Ajustes estéticos del gráfico
    ax.set_xlabel("Driver")
    ax.set_ylabel("Lap Time (s)")
    # Mejora de la estética con despine
    sns.despine(left=True, bottom=True)
    plt.tight_layout()
    
    return fig, fig2


def mostrar_mapa_circuito(lap, pos, circuit_info, name):

    # Get an array of shape [n, 2] where n is the number of points and the second
    # axis is x and y.
    track = pos.loc[:, ('X', 'Y')].to_numpy()
    # Convert the rotation angle from degrees to radian.
    track_angle = circuit_info.rotation / 180 * np.pi
    fig, ax = plt.subplots()
    
    # Rotate and plot the track map.
    rotated_track = rotate(track, angle=track_angle)
    ax.plot(rotated_track[:, 0], rotated_track[:, 1])
    
    offset_vector = [500, 0]  # offset length is chosen arbitrarily to 'look good'
    # Iterate over all corners.
    for _, corner in circuit_info.corners.iterrows():
        # Create a string from corner number and letter
        txt = f"{corner['Number']}{corner['Letter']}"
        # Convert the angle from degrees to radian.
        offset_angle = corner['Angle'] / 180 * np.pi
        # Rotate the offset vector so that it points sideways from the track.
        offset_x, offset_y = rotate(offset_vector, angle=offset_angle)
        # Add the offset to the position of the corner
        text_x = corner['X'] + offset_x
        text_y = corner['Y'] + offset_y
        # Rotate the text position equivalently to the rest of the track map
        text_x, text_y = rotate([text_x, text_y], angle=track_angle)
        # Rotate the center of the corner equivalently to the rest of the track map
        track_x, track_y = rotate([corner['X'], corner['Y']], angle=track_angle)
        # Draw a circle next to the track.
        ax.scatter(text_x, text_y, color='grey', s=140)
        # Draw a line from the track to this circle.
        ax.plot([track_x, text_x], [track_y, text_y], color='grey')
        # Finally, print the corner number inside the circle.
        ax.text(text_x, text_y, txt,
                va='center_baseline', ha='center', size='small', color='white')
        
    plt.title(name + ' Circuit')
    plt.xticks([])
    plt.yticks([])
    plt.axis('equal')
    plt.savefig('data/circuit_image/'+name + '.png')

    return fig


def grafico_vel_media_equipo(session):
    laps = session.laps.pick_quicklaps()
    
    transformed_laps = laps.copy()
    transformed_laps.loc[:, "LapTime (s)"] = laps["LapTime"].dt.total_seconds()
    
    # order the team from the fastest (lowest median lap time) tp slower
    team_order = (
        transformed_laps[["Team", "LapTime (s)"]]
        .groupby("Team")
        .median()["LapTime (s)"]
        .sort_values()
        .index
    )
    # Iniciar la paleta de colores de fallback
    fallback_colors = cycle(sns.color_palette("tab20", n_colors=20))
    # Inicializar el mapa de colores del equipo
    team_colors_map = {}
    for team in team_order:
        try:
            # Intenta obtener el color del equipo usando fastf1
            color = fastf1.plotting.team_color(team)
            if color == "none":  # Verificar si el color es "none"
                raise KeyError  # Forzar el uso del color de fallback
        except KeyError:
            # Si el equipo no está en la lista de colores de fastf1 o el color es "none", usa un color de la paleta de fallback
            color = next(fallback_colors)
            color = to_hex(color)  # Convertir el color a formato hexadecimal
        
        # Verificar si el color ya está en uso y buscar un color alternativo si es necesario
        while color in team_colors_map.values():
            color = next(fallback_colors)
            color = to_hex(color)
        
        team_colors_map[team] = color
    
    
    fig, ax = plt.subplots(figsize=(15, 10))
    sns.boxplot(
        data=transformed_laps,
        x="Team",
        y="LapTime (s)",
        hue="Team",
        order=team_order,
        palette=team_colors_map,
        whiskerprops=dict(color="white"),
        boxprops=dict(edgecolor="white"),
        medianprops=dict(color="grey"),
        capprops=dict(color="white"),
    )
    plt.title("Distribución de los tiempos de vuelta por equipo")
    plt.grid(visible=False)
    # x-label is redundant
    ax.set(xlabel=None)
    plt.tight_layout()
    return fig