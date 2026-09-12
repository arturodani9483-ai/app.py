import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime

st.set_page_config(
    page_title="Auditoría de Planillas Hacienda - Cooperativa 24 de Octubre", 
    layout="wide", 
    page_icon="🛡️"
)

st.title("🛡️ Sistema de Auditoría y Cruce de Planillas (Hacienda)")
st.markdown("Subí las planillas en formato **Excel (.xlsx / .xls)** o **CSV (.csv)** con los encabezados oficiales.")

# --- MÓDULO DE CARGA DE ARCHIVOS ---
st.subheader("1. Carga de Archivos (Excel o CSV)")
col1, col2 = st.columns(2)

with col1:
    file_anterior = st.file_uploader("📥 Planilla Mes Anterior (Referencia)", type=["xlsx", "xls", "csv"])
with col2:
    file_actual = st.file_uploader("📥 Planilla Mes Actual (A Auditar)", type=["xlsx", "xls", "csv"])

# --- FUNCIONES DE LIMPIEZA Y LECTURA ---
def limpiar_texto(val):
    if pd.isna(val) or val is None:
        return ""
    if isinstance(val, pd.Series):
        val = val.dropna().iloc[0] if not val.dropna().empty else ""
    return str(val).strip()

def limpiar_monto(val):
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, pd.Series):
        val = val.dropna().iloc[0] if not val.dropna().empty else 0.0
    try:
        return float(val)
    except:
        s = str(val).replace('.', '').replace(',', '.').strip()
        numeros = re.findall(r'[-+]?\d*\.\d+|\d+', s)
        return float(numeros[0]) if numeros else 0.0

def parsear_fecha(d_str):
    d_clean = limpiar_texto(d_str)
    if not d_clean:
        return None
    s = d_clean.split(' ')[0]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None

def cargar_archivo_universal(file_uploader):
    ext = file_uploader.name.lower().split('.')[-1]
    if ext in ['xlsx', 'xls']:
        df_raw = pd.read_excel(file_uploader, header=None, dtype=str)
        header_idx = 0
        for idx, row in df_raw.iterrows():
            row_str = " ".join([str(val).upper() for val in row.values if pd.notna(val)])
            if 'CEDULA' in row_str or 'C.I' in row_str or 'BENEFICIARIO' in row_str or 'OPERACION' in row_str:
                header_idx = idx
                break
        file_uploader.seek(0)
        return pd.read_excel(file_uploader, skiprows=header_idx, dtype=str)
    else:
        try:
            return pd.read_csv(file_uploader, dtype=str, sep=None, engine='python', encoding='utf-8')
        except:
            file_uploader.seek(0)
            return pd.read_csv(file_uploader, dtype=str, sep=None, engine='python', encoding='latin1')

def mapear_y_desduplicar_columnas(df):
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
            
    df_ren = df.rename(columns=cols_map)
    # Eliminar posibles columnas duplicadas manteniendo la primera aparición
    df_ren = df_ren.loc[:, ~df_ren.columns.duplicated()]
    return df_ren

# --- MÓDULO DE AUDITORÍA Y CRUCE ---
if file_anterior and file_actual:
    if st.button("🚀 Ejecutar Cruce y Auditoría de Planillas"):
        try:
            df_prev_raw = cargar_archivo_universal(file_anterior)
            df_curr_raw = cargar_archivo_universal(file_actual)

            df_prev = mapear_y_desduplicar_columnas(df_prev_raw)
            df_curr = mapear_y_desduplicar_columnas(df_curr_raw)

            req_cols = ['cedula', 'operacion', 'fecha_deuda']
            missing_prev = [c for c in req_cols if c not in df_prev.columns]
            missing_curr = [c for c in req_cols if c not in df_curr.columns]

            if missing_prev or missing_curr:
                st.error("No se pudieron identificar las columnas requeridas ('Cédula', 'Número de la Operación', 'Fecha de la Deuda') en uno o ambos archivos.")
            else:
                # Mapeo de referencia: (Cédula + N° Operación) -> Fecha Deuda
                ref_operaciones = {}
                for idx, row in df_prev.iterrows():
                    c_val = limpiar_texto(row.get('cedula'))
                    o_val = limpiar_texto(row.get('operacion'))
                    f_val = limpiar_texto(row.get('fecha_deuda'))
                    if c_val and o_val:
                        key = f"{c_val}_{o_val}"
                        ref_operaciones[key] = f_val

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

                    if not cedula or not operacion:
                        continue

                    key_op = f"{cedula}_{operacion}"
                    es_nuevo = key_op not in ref_operaciones

                    dt_deuda = parsear_fecha(fecha_deuda_str)
                    dt_comp = parsear_fecha(fecha_comp_str)

                    # 1. DETECCIÓN DE NUEVAS OPERACIONES
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

                    # 2. REGLA 1: Fecha de Deuda modificada respecto a la referencia
                    if not es_nuevo:
                        fecha_ref = ref_operaciones[key_op]
                        if fecha_deuda_str and fecha_ref and fecha_deuda_str != fecha_ref:
                            errores.append({
                                'Cédula Beneficiario': cedula,
                                'Nombre y Apellido': nombre,
                                'N° Operación': operacion,
                                'Tipo de Inconsistencia': 'Fecha de la deuda no coincide con lo informado previamente',
                                'Dato Mes Actual': fecha_deuda_str,
                                'Dato Correcto (Mes Anterior)': fecha_ref
                            })

                    # 3. REGLA 2: Fecha comprobante anterior inferior a Fecha de Deuda
                    if dt_deuda is not None and dt_comp is not None and dt_comp < dt_deuda:
                        errores.append({
                            'Cédula Beneficiario': cedula,
                            'Nombre y Apellido': nombre,
                            'N° Operación': operacion,
                            'Tipo de Inconsistencia': 'Fecha comprobante anterior es inferior a la fecha de la deuda',
                            'Dato Mes Actual': f"Comprobante: {fecha_comp_str}",
                            'Dato Correcto (Mes Anterior)': f"Fecha Deuda: {fecha_deuda_str}"
                        })

                    # 4. REGLA 3: Última cuota (ej: 12/12) -> Monto descuento debe ser igual al Saldo
                    if num_cuota_str.isdigit() and tot_cuota_str.isdigit() and int(num_cuota_str) == int(tot_cuota_str):
                        if abs(monto_desc - saldo_deuda) > 1.0:
                            errores.append({
                                'Cédula Beneficiario': cedula,
                                'Nombre y Apellido': nombre,
                                'N° Operación': operacion,
                                'Tipo de Inconsistencia': 'Monto a descontar en última cuota difiere del saldo pendiente',
                                'Dato Mes Actual': f"Monto Descuento: Gs. {int(monto_desc):,}",
                                'Dato Correcto (Mes Anterior)': f"Saldo Pendiente: Gs. {int(saldo_deuda):,}"
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
            st.error(f"Error al procesar las planillas: {e}")
