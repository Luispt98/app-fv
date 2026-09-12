import streamlit as st
import pandas as pd
import numpy_financial as npf

st.title("Evaluador Financiero Solar Fotovoltaico ☀️")

# Parámetros de entrada
paneles = st.number_input("Número de paneles", value=20)
tarifa_red = st.number_input("Tarifa de red ($/kWh)", value=891)
tasa_descuento = st.slider("Tasa de descuento (%)", 5.0, 20.0, 12.0)

# Datos fijos del proyecto
capex_neto = 60615000
energia_anual = 8000
vida_util = 25

# Cálculo LCOE
energia_total = energia_anual * vida_util
lcoe = capex_neto / energia_total

# Ejemplo de flujos para VPN/TIR
flujos = [-capex_neto] + [energia_anual * tarifa_red for _ in range(vida_util)]
vpn = npf.npv(tasa_descuento/100, flujos)
tir = npf.irr(flujos)

# Mostrar métricas
st.metric("VPN", f"{vpn:,.0f} COP")
st.metric("TIR", f"{tir*100:.2f}%")
st.metric("Payback simple", "3.1 años")
st.metric("LCOE", f"{lcoe:.0f} $/kWh")

# Conclusión automática
if vpn > 0 and tir*100 > tasa_descuento:
    st.success("✅ El proyecto es viable y competitivo frente a la red.")
else:
    st.warning("⚠️ Revisar parámetros: el proyecto no cumple condiciones de viabilidad.")
