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

# --- Mostrar métricas ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("VPN", f"{vpn:,.0f} COP")
col2.metric("TIR", f"{tir*100:.2f}%")
col3.metric("Payback simple", f"{payback_simple} años")
col4.metric("Payback descontado", f"{payback_desc} años")

# --- Gráficas ---
st.subheader("📊 Flujo de caja acumulado vs descontado")
plt.figure(figsize=(8,4))
plt.plot(range(len(flujo_acumulado)), flujo_acumulado, marker="o", label="Acumulado")
plt.plot(range(len(flujo_desc_acum)), flujo_desc_acum, marker="x", label="Descontado")
plt.axhline(0, color="red", linestyle="--")
plt.xlabel("Años")
plt.ylabel("COP")
plt.legend()
st.pyplot(plt)

st.subheader("⚡ Ahorro anual con degradación de paneles")
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

# --- Conclusión automática ---
st.subheader("✅ Conclusión")
if vpn > 0 and tir*100 > tasa_descuento:
    st.success("El proyecto es viable y competitivo frente a la red.")
else:
    st.warning("Revisar parámetros: el proyecto no cumple condiciones de viabilidad.")
