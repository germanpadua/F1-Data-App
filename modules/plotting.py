import plotly.graph_objects as go
from fastf1 import plotting
import fastf1
import numpy as np
from colour import Color


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