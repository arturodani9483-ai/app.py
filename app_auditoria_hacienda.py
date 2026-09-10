import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(page_title="Auditoría de Planillas Hacienda - Cooperativa 24 de Octubre", layout="wide", page_icon="🛡️")

st.title("🛡️ Sistema de Auditoría y Cruce de Planillas (Hacienda)")
st.write("Subí las planillas únicamente en formato **CSV** (Mes Anterior como referencia y Mes Actual a auditar).")

# --- MÓDULO DE CARGA ---
st.subheader("1. Carga de Archivos (.CSV)")
col1, col2 = st.columns(2)

with col1:
    file_anterior = st.file_uploader("📥 Planilla CSV MES ANTERIOR (Referencia Julio)", type=["csv"])
with col2:
    file_actual = st.file_uploader("📥 Planilla CSV MES ACTUAL (A Auditar Agosto)", type=["csv"])

# --- FUNCIONES DE LIMPIEZA Y FECHAS ---
def limpiar_texto(val):
    if pd.isna(val) or val is None:
        return ""
    return str(val).strip()

def limpiar_monto(val):
    if pd.isna(val) or val is None:
        return 0.0
    try:
        return float(val)
    except:
        s = str(val).replace('.', '').replace(',', '.').strip()
        numeros = re.findall(r'[-+]?\d*\.\d+|\d+', s)
        return float(numeros[0]) if numeros else 0.0

def parsear_fecha(d_str):
    if pd.isna(d_str) or not str(d_str).strip():
        return None
    s = str(d_str).strip().split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def mapear_columnas_oficiales(df):
    cols_map = {}
    for c in df.columns:
        c_clean = str(c).strip().upper().replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O').replace('Ú', 'U')
        
        if 'CEDULA' in c_clean or 'N° DE CEDULE' in c_clean or 'CEDULA DE IDENTIDAD' in c_clean:
            cols_map[c] = 'cedula'
        elif 'NOMBRES Y APELLIDOS' in c_clean or 'BENEFICIARIO' in c_clean:
            cols_map[c] = 'nombre'
        elif 'CONCEPTO' in c_clean and 'CONCEPTO DEL DESCUENTO' in c_clean:
            cols_map[c] = 'concepto'
        elif 'OPERACION' in c_clean or 'NUMERO DE LA OPERACION' in c_clean:
            cols_map[c] = 'operacion'
        elif 'FECHA DE LA DEUDA' in c_clean:
            cols_map[c] = 'fecha_deuda'
        elif 'NUMERO DE CUOTA' in c_clean:
            cols_map[c] = 'num_cuota'
        elif 'TOTAL CUOTA' in c_clean:
            cols_map[c] = 'total_cuota'
        elif 'MONTO POR DESCONTARSE' in c_clean:
            cols_map[c] = 'monto_desconto'
        elif 'SALDO (DEUDA)' in c_clean or 'SALDO' in c_clean:
            cols_map[c] = 'saldo_deuda'
        elif 'FECHA COMPROBANTE' in c_clean or 'FACTURA CREDITO' in c_clean:
            cols_map[c] = 'fecha_comprobante'
            
    return df.rename(columns=cols_map)

def leer_csv_flexible(file_uploader):
    try:
        return pd.read_csv(file_uploader, dtype=str, sep=None, engine='python', encoding='utf-8')
    except:
        file_uploader.seek(0)
        return pd.read_csv(file_uploader, dtype=str, sep=None, engine='python', encoding='latin1')

# --- AUDITORÍA DE DATOS ---
if file_anterior and file_actual:
    if st.button("🚀 Ejecutar Cruce y Auditoría de Planillas"):
        try:
            df_prev_raw = leer_csv_flexible(file_anterior)
            df_curr_raw = leer_csv_flexible(file_actual)

            df_prev = mapear_columnas_oficiales(df_prev_raw)
            df_curr = mapear_columnas_oficiales(df_curr_raw)

            req_cols = ['cedula', 'operacion', 'fecha_deuda']
            if not all(col in df_prev.columns for col in req_cols) or not all(col in df_curr.columns for col in req_cols):
                st.error("No se pudieron identificar las columnas requeridas ('Cédula', 'Número de la Operación', 'Fecha de la Deuda') en los archivos CSV.")
            else:
                # Diccionario de referencia: (Cedula + Operación) -> Fecha Deuda
                ref_operaciones = {}
                for idx, row in df_prev.iterrows():
                    key = f"{limpiar_texto(row.get('cedula'))}_{limpiar_texto(row.get('operacion'))}"
                    ref_operaciones[key] = limpiar_texto(row.get('fecha_deuda'))

                errores = []
                nuevos_registros = []

                for idx, row in df_curr.iterrows():
                    cedula = limpiar_texto(row.get('cedula', ''))
                    nombre = limpiar_texto(row.get('nombre', 'S/D'))
                    concepto = limpiar_texto(row.get('concepto', ''))
                    operacion = limpiar_texto(row.get('operacion', ''))
                    fecha_deuda_str = limpiar_texto(row.get('fecha_deuda', ''))
                    num_cuota_str = limpiar_texto(row.get('num_cuota', ''))
                    tot_cuota_str = limpiar_texto(row.get('total_cuota', ''))
                    monto_desc = limpiar_monto(row.get('monto_desconto', 0))
                    saldo_deuda = limpiar_monto(row.get('saldo_deuda', 0))
                    fecha_comp_str = limpiar_texto(row.get('fecha_comprobante', ''))

                    key_op = f"{cedula}_{operacion}"
                    es_nuevo = key_op not in ref_operaciones

                    dt_deuda = parsear_fecha(fecha_deuda_str)
                    dt_comp = parsear_fecha(fecha_comp_str)

                    # REGISTRO NUEVO
                    if es_nuevo:
                        nuevos_registros.append({
                            'Cédula Beneficiario': cedula,
                            'Nombre y Apellido': nombre,
                            'Concepto': concepto,
                            'N° Operación': operacion,
                            'Fecha Deuda': fecha_deuda_str,
                            'Cuota Actual': num_cuota_str,
                            'Total Cuota': tot_cuota_str,
                            'Monto Descuento': monto_desc,
                            'Saldo Deuda': saldo_deuda,
                            'Fecha Comprobante Anterior': fecha_comp_str
                        })

                    # REGLA 1: Fecha de Deuda no coincide con lo informado en el mes anterior
                    if not es_nuevo:
                        fecha_ref = ref_operaciones[key_op]
                        if fecha_deuda_str and fecha_ref and fecha_deuda_str != fecha_ref:
                            errores.append({
                                'Cédula Beneficiario': cedula,
                                'Nombre y Apellido': nombre,
                                'N° Operación': operacion,
                                'Tipo de Error / Inconsistencia': 'Fecha de la deuda no coincide con lo informado previamente',
                                'Dato Mes Actual': fecha_deuda_str,
                                'Dato Referencia (Mes Anterior)': fecha_ref
                            })

                    # REGLA 2: Fecha de comprobante anterior es inferior a la Fecha de Deuda
                    if dt_deuda and dt_comp and dt_comp < dt_deuda:
                        errores.append({
                            'Cédula Beneficiario': cedula,
                            'Nombre y Apellido': nombre,
                            'N° Operación': operacion,
                            'Tipo de Error / Inconsistencia': 'Fecha comprobante anterior es inferior a la fecha de la deuda',
                            'Dato Mes Actual': f"Comprobante: {fecha_comp_str}",
                            'Dato Referencia (Mes Anterior)': f"Fecha Deuda: {fecha_deuda_str}"
                        })

                    # REGLA 3: Última cuota -> Monto a descontar debe coincidir con el Saldo
                    if num_cuota_str.isdigit() and tot_cuota_str.isdigit() and int(num_cuota_str) == int(tot_cuota_str):
                        if abs(monto_desc - saldo_deuda) > 1.0:
                            errores.append({
                                'Cédula Beneficiario': cedula,
                                'Nombre y Apellido': nombre,
                                'N° Operación': operacion,
                                'Tipo de Error / Inconsistencia': 'Monto a descontar en última cuota difiere del saldo pendiente',
                                'Dato Mes Actual': f"Monto a descontar: Gs. {int(monto_desc):,}",
                                'Dato Referencia (Mes Anterior)': f"Saldo pendiente: Gs. {int(saldo_deuda):,}"
                            })

                df_errores = pd.DataFrame(errores)
                df_nuevos = pd.DataFrame(nuevos_registros)

                st.markdown("---")
                c1, c2 = st.columns(2)

                with c1:
                    st.subheader("🔴 Inconsistencias Encontradas")
                    if df_errores.empty:
                        st.success("✅ ¡Sin errores detectados!")
                    else:
                        st.warning(f"Se encontraron {len(df_errores)} errores.")
                        st.dataframe(df_errores, use_container_width=True)

                        out_e = io.BytesIO()
                        with pd.ExcelWriter(out_e, engine='openpyxl') as writer:
                            df_errores.to_excel(writer, sheet_name='Errores', index=False)
                        st.download_button(
                            label="📥 Descargar Excel de Errores (.xlsx)",
                            data=out_e.getvalue(),
                            file_name="Reporte_Inconsistencias_Hacienda.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )

                with c2:
                    st.subheader("🟢 Nuevos Registros / Operaciones")
                    if df_nuevos.empty:
                        st.info("No hay nuevas operaciones registradas.")
                    else:
                        st.success(f"Se encontraron {len(df_nuevos)} nuevos registros.")
                        st.dataframe(df_nuevos, use_container_width=True)

                        out_n = io.BytesIO()
                        with pd.ExcelWriter(out_n, engine='openpyxl') as writer:
                            df_nuevos.to_excel(writer, sheet_name='Nuevos_Registros', index=False)
                        st.download_button(
                            label="📥 Descargar Excel de Nuevos Registros (.xlsx)",
                            data=out_n.getvalue(),
                            file_name="Reporte_Nuevos_Registros_Hacienda.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )

        except Exception as e:
            st.error(f"Error al procesar los archivos CSV: {e}")
