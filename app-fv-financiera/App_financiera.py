import streamlit as st
import pandas as pd
import numpy_financial as npf
import matplotlib.pyplot as plt

# --- Configuración inicial ---
st.set_page_config(page_title="Evaluador Financiero Solar Fotovoltaico", layout="wide")
st.title("☀️ Evaluador Financiero Solar Fotovoltaico")

# --- Cargar Excel ---
archivo = "3.Evaluación financiera Sistemas solar fotovoltaico.xlsx"
xls = pd.ExcelFile(archivo)

# ================================
# 📄 HOJA 1: ENTRADA
# ================================
entrada = pd.read_excel(xls, sheet_name="1_ENTRADA")
st.subheader("📄 Hoja 1: Entrada")
st.dataframe(entrada)

# Parámetros interactivos
st.sidebar.header("Parámetros de entrada")
paneles = st.sidebar.number_input("Número de paneles", value=20)
tarifa_red = st.sidebar.number_input("Tarifa de red ($/kWh)", value=891)
tasa_descuento = st.sidebar.slider("Tasa de descuento (%)", 5.0, 20.0, 12.0)

# ================================
# 📄 HOJA 2: CÁLCULO KWH
# ================================
calc_kwh = pd.read_excel(xls, sheet_name="2_CALC_KWH")
st.subheader("📄 Hoja 2: Cálculo Energético (kWh)")
st.dataframe(calc_kwh)

energia_anual_base = 8000   # tomado de tu hoja de cálculo energético
vida_util = 25

# ================================
# 📄 HOJA 3: FLUJO DE CAJA
# ================================
flujo_caja = pd.read_excel(xls, sheet_name="3_FLUJO_CAJA")
st.subheader("📄 Hoja 3: Flujo de Caja")
st.dataframe(flujo_caja)

capex_neto = 60615000
crecimiento_tarifa = 0.067
degradacion_1 = 0.025
degradacion_restante = 0.0055
beneficio_ley1715 = capex_neto * 0.5 / 5  # ahorro tributario distribuido en 5 años
aom = capex_neto * 0.03  # costos de operación y mantenimiento

flujos = [-capex_neto]  # inversión inicial
energia_anual = energia_anual_base

for año in range(1, vida_util+1):
    # aplicar degradación
    if año == 1:
        energia_anual *= (1 - degradacion_1)
    else:
        energia_anual *= (1 - degradacion_restante)
    
    # aplicar crecimiento tarifario
    tarifa_año = tarifa_red * ((1 + crecimiento_tarifa) ** (año-1))
    
    # ahorro por autoconsumo
    ahorro = energia_anual * tarifa_año
    
    # ingreso por excedentes (simplificado: 20% de la energía a precio bolsa)
    excedentes = (energia_anual * 0.2) * 436
    
    # beneficio tributario (solo primeros 5 años)
    beneficio = beneficio_ley1715 if año <= 5 else 0
    
    # costos operativos
    costos = aom
    
    flujo_neto = ahorro + excedentes + beneficio - costos
    flujos.append(flujo_neto)

# ================================
# 📄 HOJA 4: INDICADORES
# ================================
indicadores = pd.read_excel(xls, sheet_name="4_INDICADORES")
st.subheader("📄 Hoja 4: Indicadores Financieros")
st.dataframe(indicadores)

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

# Mostrar métricas
col1, col2, col3, col4 = st.columns(4)
col1.metric("VPN", f"{vpn:,.0f} COP")
col2.metric("TIR", f"{tir*100:.2f}%")
col3.metric("Payback simple", f"{payback_simple} años")
col4.metric("Payback descontado", f"{payback_desc} años")

# ================================
# 📄 HOJA 5: AMORTIZACIÓN
# ================================
amortizacion = pd.read_excel(xls, sheet_name="5_AMORTIZACION")
st.subheader("📄 Hoja 5: Amortización del Crédito")
st.dataframe(amortizacion)

# ================================
# 📄 HOJA 6: RESUMEN
# ================================
resumen = pd.read_excel(xls, sheet_name="6_RESUMEN")
st.subheader("📄 Hoja 6: Resumen General")
st.dataframe(resumen)

# ================================
# 📊 GRÁFICAS
# ================================
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
        energia_temp *= (1 - degradacion_1)
    else:
        energia_temp *= (1 - degradacion_restante)
    energia_degradada.append(energia_temp)

plt.figure(figsize=(8,4))
plt.plot(años, energia_degradada, label="Energía generada (kWh)")
plt.xlabel("Años")
plt.ylabel("kWh")
plt.legend()
st.pyplot(plt)

# ================================
# ✅ Conclusión automática
# ================================
st.subheader("✅ Conclusión")
if vpn > 0 and tir*100 > tasa_descuento:
    st.success("El proyecto es viable y competitivo frente a la red.")
else:
    st.warning("Revisar parámetros: el proyecto no cumple condiciones de viabilidad.")
