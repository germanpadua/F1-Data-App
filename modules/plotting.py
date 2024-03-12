import plotly.graph_objects as go
from fastf1 import plotting

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

def grafico_tiempos_vuelta(session, selected_driver):
    fig = go.Figure()
    
    # Filtrar los datos para el piloto seleccionado
    driver_laps = session.laps.pick_driver(selected_driver)

    # Convertir LapTime a segundos para facilitar la visualización
    driver_laps['LapTimeSeconds'] = driver_laps['LapTime'].dt.total_seconds()

    # Encuentra la vuelta más rápida para destacarla
    vuelta_rapida = driver_laps.loc[driver_laps['LapTimeSeconds'].idxmin()]

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

    

    return fig