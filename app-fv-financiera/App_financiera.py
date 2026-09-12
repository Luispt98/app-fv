import streamlit as st
import pandas as pd
import numpy_financial as npf
import matplotlib.pyplot as plt

# --- Configuración inicial ---
st.set_page_config(page_title="Evaluador Financiero Solar Fotovoltaico", layout="wide")
st.title("☀️ Evaluador Financiero Solar Fotovoltaico")

# --- Parámetros interactivos ---
st.sidebar.header("Parámetros de entrada")
paneles = st.sidebar.number_input("Número de paneles", value=20)
tarifa_red = st.sidebar.number_input("Tarifa de red ($/kWh)", value=891)
tasa_descuento = st.sidebar.slider("Tasa de descuento (%)", 5.0, 20.0, 12.0)
crecimiento_tarifa = st.sidebar.slider("Crecimiento tarifario anual (%)", 0.0, 10.0, 6.7)
degradacion_1 = st.sidebar.slider("Degradación primer año (%)", 0.0, 5.0, 2.5)
degradacion_restante = st.sidebar.slider("Degradación anual (%)", 0.0, 2.0, 0.55)
precio_bolsa = st.sidebar.number_input("Precio bolsa ($/kWh)", value=436)
porcentaje_excedentes = st.sidebar.slider("Excedentes a la red (%)", 0.0, 100.0, 20.0)
aom_pct = st.sidebar.slider("Costos O&M (% CAPEX)", 0.0, 10.0, 3.0)

# Escenarios
escenario = st.sidebar.selectbox("Escenario", ["Optimista", "Conservador", "Pesimista"])
if escenario == "Optimista":
    crecimiento_tarifa = 8.0
    degradacion_restante = 0.3
elif escenario == "Conservador":
    crecimiento_tarifa = 6.7
    degradacion_restante = 0.55
else:  # Pesimista
    crecimiento_tarifa = 5.0
    degradacion_restante = 1.0

# --- Datos base ---
vida_util = 25
capex_neto = 60615000
energia_anual_base = 8000
beneficio_ley1715 = capex_neto * 0.5 / 5  # ahorro tributario distribuido en 5 años
aom = capex_neto * (aom_pct/100)

# --- Cálculo detallado de flujos de caja ---
flujos = [-capex_neto]  # inversión inicial
energia_anual = energia_anual_base

for año in range(1, vida_util+1):
    # aplicar degradación
    if año == 1:
        energia_anual *= (1 - degradacion_1/100)
    else:
        energia_anual *= (1 - degradacion_restante/100)
    
    # aplicar crecimiento tarifario
    tarifa_año = tarifa_red * ((1 + crecimiento_tarifa/100) ** (año-1))
    
    # ahorro por autoconsumo
    ahorro = energia_anual * tarifa_año
    
    # ingreso por excedentes
    excedentes = (energia_anual * (porcentaje_excedentes/100)) * precio_bolsa
    
    # beneficio tributario (solo primeros 5 años)
    beneficio = beneficio_ley1715 if año <= 5 else 0
    
    # costos operativos
    costos = aom
    
    flujo_neto = ahorro + excedentes + beneficio - costos
    flujos.append(flujo_neto)

# --- Indicadores financieros ---
vpn = npf.npv(tasa_descuento/100, flujos)
tir = npf.irr(flujos)

# Payback simple
flujo_acumulado = pd.Series(flujos).cumsum()
payback_simple = next((i for i, v in enumerate(flujo_acumulado) if v > 0), None)

# Payback descontado
flujos_desc = [f/(1+tasa_descuento/100)**i for i,f in enumerate(flujos)]
flujo_desc_acum = pd.Series(flujos_desc).cumsum()
payback_desc = next((i for i, v in enumerate(flujo_desc_acum) if v > 0), None)

# LCOE
energia_total = energia_anual_base * vida_util
lcoe = capex_neto / energia_total

# CO₂ evitado
factor_emision = 0.5  # kg CO2 por kWh (ejemplo)
co2_ev = sum(flujos[1:]) / tarifa_red * factor_emision / 1000  # toneladas aprox

# --- Mostrar métricas ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("VPN", f"{vpn:,.0f} COP")
col2.metric("TIR", f"{tir*100:.2f}%")
col3.metric("Payback simple", f"{payback_simple} años" if payback_simple else "No recupera")
if lcoe < tarifa_red:
    col4.metric("LCOE", f"{lcoe:.0f} $/kWh", "✅ competitivo")
else:
    col4.metric("LCOE", f"{lcoe:.0f} $/kWh", "⚠️ más caro que la red")

st.metric("CO₂ evitado", f"{co2_ev:,.0f} toneladas")

# --- Gráficas dinámicas ---
st.subheader("📊 Flujo de caja acumulado vs descontado")
plt.figure(figsize=(8,4))
plt.plot(range(len(flujo_acumulado)), flujo_acumulado, marker="o", label="Acumulado")
plt.plot(range(len(flujo_desc_acum)), flujo_desc_acum, marker="x", label="Descontado")
plt.axhline(0, color="red", linestyle="--")
plt.xlabel("Años")
plt.ylabel("COP")
plt.legend()
st.pyplot(plt)

st.subheader("📊 Flujo neto anual")
plt.figure(figsize=(8,4))
plt.bar(range(len(flujos)), flujos, color="green")
plt.axhline(0, color="red", linestyle="--")
plt.xlabel("Años")
plt.ylabel("COP")
plt.title("Flujos netos por año")
st.pyplot(plt)

st.subheader("⚡ Energía anual con degradación")
años = list(range(1, vida_util+1))
energia_degradada = []
energia_temp = energia_anual_base
for año in años:
    if año == 1:
        energia_temp *= (1 - degradacion_1/100)
    else:
        energia_temp *= (1 - degradacion_restante/100)
    energia_degradada.append(energia_temp)

plt.figure(figsize=(8,4))
plt.plot(años, energia_degradada, label="Energía generada (kWh)")
plt.xlabel("Años")
plt.ylabel("kWh")
plt.legend()
st.pyplot(plt)

# --- 📖 Resumen narrativo dinámico ---
st.subheader("📖 Resumen del escenario actual")

energia_temp = energia_anual_base
for i in range(1, 11):
    if i == 1:
        energia_temp *= (1 - degradacion_1/100)
    else:
        energia_temp *= (1 - degradacion_restante/100)

resumen_texto = f"""
Escenario: {escenario}
- El sistema inicia con {energia_anual_base:,.0f} kWh/año y en el año 10 produce {energia_temp:,.0f} kWh/año.
- El flujo de caja acumulado alcanza {flujo_acumulado.iloc[-1]:,.0f} COP al final de la vida útil.
- La inversión inicial de {capex_neto:,.0f} COP se recupera en aproximadamente {payback_simple} años.
- El VPN calculado es de {vpn:,.0f} COP y la TIR de {tir*100:.2f}% frente a una tasa de descuento de {tasa_descuento}%.
- El LCOE es de {lcoe:,.0f} $/kWh frente a una tarifa de red de {tarifa_red} $/kWh.
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
st.info("Criterios de viabilidad: VPN > 0, TIR > tasa de descuento, LCOE < tarifa de red, Pay
