import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

# Datos base de paneles
potencia_panel_on = 610   # Wp
potencia_panel_off = 600  # Wp
area_panel = 2.82         # m²

# Datos eléctricos
voc_on = 55.31; vmpp_on = 45.6; imp_on = 13.38
voc_off = 55.0; vmpp_off = 45.25; imp_off = 13.26

# Datos baterías Off-Grid
cap_bateria = 12.5     # kWh
autonomia_dias = 1.8   # días

# Costos aproximados (COP)
costo_panel_on = 1_325_000
costo_panel_off = 1_300_000
costo_inversor_on = 15_000_000
costo_inversor_off = 4_450_000   # cada Must
costo_bateria = 2_000_000
tarifa_kwh = 850

st.title("Comparación de Sistemas Fotovoltaicos On-Grid vs Off-Grid")

# Entradas
n_paneles_on = st.number_input("Paneles On-Grid", value=20, min_value=1)
n_paneles_off = st.number_input("Paneles Off-Grid", value=50, min_value=1)
consumo_diario_on = st.number_input("Consumo diario On-Grid (kWh)", value=22.0)
consumo_diario_off = st.number_input("Consumo diario Off-Grid (kWh)", value=131.0)

# Cálculos On-Grid
pdc_on = n_paneles_on * potencia_panel_on / 1000
costo_total_on = n_paneles_on * costo_panel_on + costo_inversor_on
produccion_anual_on = consumo_diario_on * 365
ahorro_anual_on = produccion_anual_on * tarifa_kwh
retorno_on = costo_total_on / ahorro_anual_on

# Cálculos Off-Grid
pdc_off = n_paneles_off * potencia_panel_off / 1000
energia_util = consumo_diario_off * autonomia_dias
n_bat = round(energia_util / cap_bateria)
costo_total_off = n_paneles_off * costo_panel_off + (3 * costo_inversor_off) + (n_bat * costo_bateria)
produccion_anual_off = consumo_diario_off * 365

# Mostrar resultados
st.subheader("Resultados On-Grid")
st.write(f"Potencia FV: {pdc_on:.2f} kWp")
st.write(f"Inversión inicial: {costo_total_on:,.0f} COP")
st.write(f"Producción anual: {produccion_anual_on:,.0f} kWh")
st.write(f"Ahorro anual: {ahorro_anual_on:,.0f} COP")
st.write(f"Retorno: {retorno_on:.1f} años")

st.subheader("Resultados Off-Grid")
st.write(f"Potencia FV: {pdc_off:.2f} kWp")
st.write(f"Inversión inicial: {costo_total_off:,.0f} COP")
st.write(f"Producción anual: {produccion_anual_off:,.0f} kWh")
st.write(f"Banco de baterías: {n_bat} x LiFePO4 de 12.5 kWh (~{energia_util:.1f} kWh útiles)")
st.write(f"Autonomía: {autonomia_dias} días")

# Gráfico comparativo
fig, ax = plt.subplots()
labels = ["On-Grid", "Off-Grid"]
costos = [costo_total_on, costo_total_off]
produccion = [produccion_anual_on, produccion_anual_off]

ax.bar(labels, costos, color="red", alpha=0.6, label="Inversión inicial (COP)")
ax.bar(labels, produccion, color="blue", alpha=0.6, label="Producción anual (kWh)")
ax.set_title("Comparación On-Grid vs Off-Grid")
ax.legend()
st.pyplot(fig)

# Exportación a Excel (corregida con BytesIO)
datos = {
    "Tipo": ["On-Grid", "Off-Grid"],
    "Paneles": [n_paneles_on, n_paneles_off],
    "Potencia FV (kWp)": [pdc_on, pdc_off],
    "Inversión inicial (COP)": [costo_total_on, costo_total_off],
    "Producción anual (kWh)": [produccion_anual_on, produccion_anual_off],
    "Ahorro anual (COP)": [ahorro_anual_on, None],
    "Retorno (años)": [retorno_on, None],
    "Baterías": [None, n_bat],
    "Autonomía (días)": [None, autonomia_dias]
}
df = pd.DataFrame(datos)

# Crear archivo Excel en memoria
output = io.BytesIO()
with pd.ExcelWriter(output, engine="openpyxl") as writer:
    df.to_excel(writer, index=False, sheet_name="Comparación")

output.seek(0)

st.download_button(
    label="📥 Descargar comparación en Excel",
    data=output,
    file_name="comparacion_fv.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
