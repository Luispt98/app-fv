import streamlit as st
import pandas as pd
import numpy_financial as npf
import matplotlib.pyplot as plt
import requests

# --- Configuración inicial ---
st.set_page_config(page_title="Evaluador Financiero Solar Fotovoltaico", layout="wide")
st.title("☀️ Evaluador Financiero Solar Fotovoltaico")

# --- Funciones para obtener datos oficiales ---
def obtener_tarifa_aire():
    try:
        # Ejemplo: archivo oficial de tarifas Air-e (simulado)
        url = "https://www.aire.com.co/sites/default/files/2026-08/Tarifas_Aire_Agosto2026.xlsx"
        df = pd.read_excel(url)
        tarifa_promedio = df['Tarifa'].mean()
        return round(tarifa_promedio, 0)
    except:
        return 890  # valor por defecto si falla

def obtener_precio_bolsa():
    try:
        # Ejemplo: archivo oficial XM (simulado)
        url = "https://www.xm.com.co/archivos/PreciosBolsaDiaria.csv"
        df = pd.read_csv(url)
        precio_promedio = df['PrecioBolsa'].mean()
        return round(precio_promedio, 0)
    except:
        return 450  # valor por defecto si falla

# --- Parámetros interactivos ---
st.sidebar.header("Parámetros de entrada")
tarifa_red = st.sidebar.number_input("Tarifa de red ($/kWh)", value=891)
precio_bolsa = st.sidebar.number_input("Precio bolsa ($/kWh)", value=436)
tasa_descuento = st.sidebar.slider("Tasa de descuento (%)", 5.0, 20.0, 12.0)
crecimiento_tarifa = st.sidebar.slider("Crecimiento tarifario anual (%)", 0.0, 10.0, 6.7)
degradacion_1 = st.sidebar.slider("Degradación primer año (%)", 0.0, 5.0, 2.5)
degradacion_restante = st.sidebar.slider("Degradación anual (%)", 0.0, 2.0, 0.55)
porcentaje_excedentes = st.sidebar.slider("Excedentes a la red (%)", 0.0, 100.0, 20.0)
aom_pct = st.sidebar.slider("Costos O&M (% CAPEX)", 0.0, 10.0, 3.0)
paneles = st.sidebar.number_input("Número de paneles", value=20)
potencia_panel = st.sidebar.number_input("Potencia de cada panel (Wp)", value=610)
potencia_instalada = paneles * (potencia_panel / 1000)  # en kWp

# --- Bloque opcional de datos oficiales ---
usar_datos_reales = st.sidebar.checkbox("Usar datos oficiales (Air-e/XM)", value=False)

if usar_datos_reales:
    tarifa_real = obtener_tarifa_aire()
    precio_real = obtener_precio_bolsa()
else:
    tarifa_real = tarifa_red
    precio_real = precio_bolsa

# Mostrar comparación
st.sidebar.subheader("Comparación de valores")
st.sidebar.write(f"Tarifa ingresada: {tarifa_red} $/kWh")
st.sidebar.write(f"Tarifa oficial Air-e: {tarifa_real} $/kWh")
st.sidebar.write(f"Precio bolsa ingresado: {precio_bolsa} $/kWh")
st.sidebar.write(f"Precio bolsa XM: {precio_real} $/kWh")

# --- Datos base ---
vida_util = 25
capex_neto = 60615000
energia_anual_base = 8000
beneficio_ley1715 = capex_neto * 0.5 / 5
aom = capex_neto * (aom_pct/100)

# --- Cálculo de flujos de caja ---
flujos = [-capex_neto]
energia_anual = energia_anual_base

for año in range(1, vida_util+1):
    if año == 1:
        energia_anual *= (1 - degradacion_1/100)
    else:
        energia_anual *= (1 - degradacion_restante/100)
    
    tarifa_año = tarifa_real * ((1 + crecimiento_tarifa/100) ** (año-1))
    ahorro = energia_anual * tarifa_año
    excedentes = (energia_anual * (porcentaje_excedentes/100)) * precio_real
    beneficio = beneficio_ley1715 if año <= 5 else 0
    costos = aom
    
    flujo_neto = ahorro + excedentes + beneficio - costos
    flujos.append(flujo_neto)

# --- Indicadores financieros ---
vpn = npf.npv(tasa_descuento/100, flujos)
tir = npf.irr(flujos)
flujo_acumulado = pd.Series(flujos).cumsum()
payback_simple = next((i for i, v in enumerate(flujo_acumulado) if v > 0), None)
flujos_desc = [f/(1+tasa_descuento/100)**i for i,f in enumerate(flujos)]
flujo_desc_acum = pd.Series(flujos_desc).cumsum()
payback_desc = next((i for i, v in enumerate(flujo_desc_acum) if v > 0), None)
energia_total = energia_anual_base * vida_util
lcoe = capex_neto / energia_total

# --- Energía degradada ---
años = list(range(1, vida_util+1))
energia_degradada = []
energia_temp = energia_anual_base
for año in años:
    if año == 1:
        energia_temp *= (1 - degradacion_1/100)
    else:
        energia_temp *= (1 - degradacion_restante/100)
    energia_degradada.append(energia_temp)

factor_emision = 0.5
co2_ev = sum(energia_degradada) * factor_emision / 1000

# --- Mostrar métricas ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("VPN", f"{vpn:,.0f} COP")
col2.metric("TIR", f"{tir*100:.2f}%")
col3.metric("Payback simple", f"{payback_simple} años" if payback_simple else "No recupera")
if lcoe < tarifa_real:
    col4.metric("LCOE", f"{lcoe:.0f} $/kWh", "✅ competitivo")
else:
    col4.metric("LCOE", f"{lcoe:.0f} $/kWh", "⚠️ más caro que la red")
st.metric("CO₂ evitado", f"{co2_ev:,.0f} toneladas")

# --- Gráficas ---
fig, ax = plt.subplots(figsize=(8,4))
ax.plot(range(len(flujo_acumulado)), flujo_acumulado, marker="o", label="Acumulado")
ax.plot(range(len(flujo_desc_acum)), flujo_desc_acum, marker="x", label="Descontado")
ax.axhline(0, color="red", linestyle="--")
ax.set_xlabel("Años")
ax.set_ylabel("COP")
ax.legend()
st.pyplot(fig)

fig, ax = plt.subplots(figsize=(8,4))
ax.bar(range(len(flujos)), flujos, color="green")
ax.axhline(0, color="red", linestyle="--")
ax.set_xlabel("Años")
ax.set_ylabel("COP")
ax.set_title("Flujos netos por año")
st.pyplot(fig)

fig, ax = plt.subplots(figsize=(8,4))
ax.plot(años, energia_degradada, label="Energía generada (kWh)")
ax.set_xlabel("Años")
ax.set_ylabel("kWh")
ax.legend()
st.pyplot(fig)

# --- Resumen narrativo ---
st.subheader("📖 Resumen del escenario actual")
energia_temp = energia_anual_base
for i in range(1, 11):
    if i == 1:
        energia_temp *= (1 - degradacion_1/100)
    else:
        energia_temp *= (1 - degradacion_restante/100)

resumen_texto = f"""
Escenario: {'Oficial' if usar_datos_reales else 'Manual'}
- El sistema inicia con {energia_anual_base:,.0f} kWh/año y en el año 10 produce {energia_temp:,.0f} kWh/año.
- El flujo de caja acumulado alcanza {flujo_acumulado.iloc[-1]:,.0f} COP al final de la vida útil.
- La inversión inicial de {capex_neto:,.0f} COP se recupera en aproximadamente {payback_simple} años.
- El VPN calculado es de {vpn:,.0f} COP y la TIR de {tir*100:.2f}% frente a una tasa de descuento de {tasa_descuento}%.
- El LCOE es de {lcoe:,.0f} $/kWh frente a una tarifa de red de {tarifa_real} $/kWh.
- Se evitarían aproximadamente {co2_ev:,.0f} toneladas de CO₂ en 25 años.
"""
st.write(resumen_texto)

# --- Exportar resultados ---
df_resultados = pd.DataFrame({
    "Año": range(0, vida_util+1),
    "Flujo": flujos,
    "Flujo acumulado": flujo_acumulado
})
st.download_button("📥 Descargar resultados en CSV", df_resultados.to_csv(index=False), "resultados.csv", "text/csv")

# --- Conclusión automática más realista ---
st.subheader("✅ Conclusión")
st.info("Criterios de viabilidad: VPN > 0, TIR > tasa de descuento, LCOE < tarifa de red, Payback < 10 años")

if vpn > 0 and tir*100 > tasa_descuento and lcoe < tarifa_real and (payback_simple and payback_simple < 10):
    st.success("El proyecto es viable y competitivo frente a la red.")
else:
    st.warning("Revisar parámetros: el proyecto no cumple condiciones de viabilidad.")
