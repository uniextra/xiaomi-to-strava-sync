import os
import requests
import time
import shutil
import pandas as pd
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import warnings
import glob

warnings.filterwarnings('ignore')

# ==========================================
# CONFIGURACIÓN GENERAL (STRAVA Y ARCHIVOS)
# ==========================================
SECRETS_FILE = 'secrets.json'

def cargar_secretos():
    if not os.path.exists(SECRETS_FILE):
        default_secrets = {
            "CLIENT_ID": "",
            "CLIENT_SECRET": "",
            "REFRESH_TOKEN": ""
        }
        with open(SECRETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_secrets, f, indent=4)
        print(f"⚠️ Creado el archivo '{SECRETS_FILE}'. Por favor, ábrelo y rellénalo con tus credenciales de Strava.")
        import sys
        sys.exit(1)
        
    with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

secrets_dict = cargar_secretos()
CLIENT_ID = secrets_dict.get('CLIENT_ID', '')
CLIENT_SECRET = secrets_dict.get('CLIENT_SECRET', '')
REFRESH_TOKEN = secrets_dict.get('REFRESH_TOKEN', '')

# Buscar los CSV automáticamente sin importar el prefijo numérico del exportador (ej: 20260416_...)
_f_tracks = glob.glob('*_MiFitness_hlth_center_sport_track_data.csv')
FILE_TRACKS = _f_tracks[0] if _f_tracks else None

_f_hr = glob.glob('*_MiFitness_hlth_center_fitness_data.csv')
FILE_HR = _f_hr[0] if _f_hr else None

_f_sport = glob.glob('*_MiFitness_hlth_center_sport_record.csv')
FICHERO_SPORT = _f_sport[0] if _f_sport else None

CARPETA_RUTAS_CRUDAS = 'mis_rutas_strava'
CARPETA_GPX = 'gpx_perfectos_strava'
CARPETA_SUBIDOS = os.path.join(CARPETA_GPX, 'subidos')

for folder in [CARPETA_RUTAS_CRUDAS, CARPETA_GPX, CARPETA_SUBIDOS]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# ==========================================
# PASO 1: DESCARGAR GPX DESDE XIAOMI
# ==========================================
def paso1_descargar_rutas():
    print("\n" + "="*50)
    print("▶️ PASO 1: DESCARGANDO NUEVAS RUTAS DE XIAOMI")
    print("="*50)
    
    if not FILE_TRACKS:
        print("❌ ERROR: No se ha encontrado ningún archivo '*_MiFitness_hlth_center_sport_track_data.csv' en la carpeta.")
        return False
        
    try:
        df_tracks = pd.read_csv(FILE_TRACKS)
    except Exception as e:
        print(f"❌ Error al abrir {FILE_TRACKS}: {e}")
        return False
        
    nuevas = 0
    for index, row in df_tracks.iterrows():
        url = row['GPX']
        timestamp = row['Time']
        fecha_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d_%H-%M')
        nombre_archivo = f"actividad_{fecha_str}.gpx"
        ruta_cruda = os.path.join(CARPETA_RUTAS_CRUDAS, nombre_archivo)
        
        # Comprobar si ya existe en crudo, perfecta o subida para no redescargarla
        if (os.path.exists(ruta_cruda) or 
            os.path.exists(os.path.join(CARPETA_GPX, nombre_archivo)) or
            os.path.exists(os.path.join(CARPETA_SUBIDOS, nombre_archivo))):
            continue
            
        print(f"📥 Descargando nueva actividad del {fecha_str}...")
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(ruta_cruda, 'wb') as f:
                    f.write(r.content)
                nuevas += 1
            else:
                print(f"❌ Error al descargar (enlace probablemente expirado o privado)")
        except Exception as e:
            print(f"⚠️ Error en la descarga: {e}")
            
    if nuevas == 0:
        print("🤷 No ha habido descargas nuevas (todas las detectadas ya se habían bajado antes).")
    else:
        print(f"✅ {nuevas} rutas descargadas correctamente a '{CARPETA_RUTAS_CRUDAS}'.")
    return True

# ==========================================
# PASO 2: AÑADIR PULSACIONES AL GPX (Lo que hacía el 2.py)
# ==========================================
def cargar_pulsaciones():
    if not FILE_HR:
        raise FileNotFoundError("❌ ERROR: No se ha encontrado el archivo '*_MiFitness_hlth_center_fitness_data.csv'")
    df_raw = pd.read_csv(FILE_HR, low_memory=False)
    hr_df = df_raw[df_raw['Key'] == 'heart_rate'].copy()
    
    def extraer_bpm(val):
        try:
            d = json.loads(val)
            return pd.Series([int(d.get('bpm', 0)), int(d.get('time', 0))])
        except:
            return pd.Series([0, 0])
    
    hr_df[['bpm', 'unix_time']] = hr_df['Value'].apply(extraer_bpm)
    hr_df = hr_df[hr_df['bpm'] > 0]
    return hr_df.groupby('unix_time')['bpm'].mean().sort_index()

def cargar_actividades():
    if not FICHERO_SPORT:
        raise FileNotFoundError("❌ ERROR: No se ha encontrado el archivo '*_MiFitness_hlth_center_sport_record.csv'")
    df_sport = pd.read_csv(FICHERO_SPORT)
    actividades_diarias = {}
    for idx, row in df_sport.iterrows():
        try:
            val = json.loads(row['Value'])
            start_ts = int(val.get('start_time', 0))
            if start_ts > 0:
                fecha_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime('%Y-%m-%d')
                actividades_diarias[fecha_str] = start_ts
        except:
            pass
    return actividades_diarias

def paso2_procesar_pulsaciones():
    archivos = [f for f in os.listdir(CARPETA_RUTAS_CRUDAS) if f.endswith('.gpx')]
    if not archivos:
        return
        
    print("\n" + "="*50)
    print(f"▶️ PASO 2: AÑADIENDO PULSACIONES A LOS {len(archivos)} GPX PENDIENTES")
    print("="*50)
    
    print("📖 Cargando base de datos de pulsaciones de Xiaomi (esto puede tardar unos segundos)...")
    hr_db = cargar_pulsaciones()
    actividades_diarias = cargar_actividades()
    
    gpxtpx_url = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
    ET.register_namespace('gpxtpx', gpxtpx_url)
    
    procesados = 0
    for archivo in archivos:
        try:
            fecha_gpx = None
            for parte in archivo.split('_'):
                if len(parte) == 10 and parte.count('-') == 2:
                    fecha_gpx = parte
                    break
            
            if not fecha_gpx or fecha_gpx not in actividades_diarias:
                print(f"⏭️ {archivo}: No hay actividad en Xiaomi para el día {fecha_gpx}. Se queda sin pulsaciones pero lo movemos a perfectas igual.")
                # Lo movemos igualmente a perfectas para subirlo a Strava aunque sea sin HR
                shutil.move(os.path.join(CARPETA_RUTAS_CRUDAS, archivo), os.path.join(CARPETA_GPX, archivo))
                procesados += 1
                continue
                
            hora_real_utc = actividades_diarias[fecha_gpx]
            
            tree = ET.parse(os.path.join(CARPETA_RUTAS_CRUDAS, archivo))
            root = tree.getroot()
            ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
            
            trkpts = root.findall('.//gpx:trkpt', ns)
            if not trkpts:
                trkpts = root.findall('.//trkpt')
            
            primer_tiempo = trkpts[0].find('gpx:time', ns) if trkpts else None
            if primer_tiempo is None and trkpts:
                primer_tiempo = trkpts[0].find('time')
                    
            desfase_segundos = 0
            if primer_tiempo is not None:
                dt_gpx = datetime.fromisoformat(primer_tiempo.text.replace('Z', '+00:00'))
                ts_gpx = int(dt_gpx.timestamp())
                diferencia = ts_gpx - hora_real_utc
                desfase_segundos = round(diferencia / 3600) * 3600
            
            puntos_ok = 0
            for trkpt in trkpts:
                t_node = trkpt.find('gpx:time', ns) or trkpt.find('time')
                    
                if t_node is not None:
                    dt = datetime.fromisoformat(t_node.text.replace('Z', '+00:00'))
                    ts_gpx_falso = int(dt.timestamp())
                    ts_real = ts_gpx_falso - desfase_segundos
                    
                    idx = hr_db.index.get_indexer([ts_real], method='nearest')[0]
                    closest_ts = hr_db.index[idx]
                    
                    if abs(ts_real - closest_ts) <= 120:
                        bpm = int(hr_db.iloc[idx])
                        ext = trkpt.find('gpx:extensions', ns) or trkpt.find('extensions')
                            
                        if ext is None:
                            if '{' in root.tag:
                                ext = ET.SubElement(trkpt, '{http://www.topografix.com/GPX/1/1}extensions')
                            else:
                                ext = ET.SubElement(trkpt, 'extensions')
                        
                        tpe = ET.SubElement(ext, '{' + gpxtpx_url + '}TrackPointExtension')
                        hr = ET.SubElement(tpe, '{' + gpxtpx_url + '}hr')
                        hr.text = str(bpm)
                        puntos_ok += 1

            # Lo guardamos directamente en la carpeta de listos para Strava
            ruta_final = os.path.join(CARPETA_GPX, archivo)
            tree.write(ruta_final, encoding='utf-8', xml_declaration=True)
            print(f"✅ {archivo}: Creado perfecto en '{CARPETA_GPX}' ({puntos_ok} pulsaciones insertadas).")
            procesados += 1
            os.remove(os.path.join(CARPETA_RUTAS_CRUDAS, archivo)) # Borramos el original crudo
                
        except Exception as e:
            print(f"❌ Error al procesar pulsaciones en {archivo}: {e}")
            # En caso de fallo crítico en el archivo, lo movemos tal cual si no se ha convertido
            ruta_origen = os.path.join(CARPETA_RUTAS_CRUDAS, archivo)
            ruta_destino = os.path.join(CARPETA_GPX, archivo)
            if os.path.exists(ruta_origen) and not os.path.exists(ruta_destino):
                shutil.move(ruta_origen, ruta_destino)
            print(f"⚠️ El archivo {archivo} se ha pasado a listos para Strava SIN pulsaciones debido al error.")
            
    print(f"✨ Paso 2 completado.")

# ==========================================
# PASO 3: SUBIR A STRAVA
# ==========================================
def actualizar_archivo_con_token(nuevo_refresh):
    try:
        with open(SECRETS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        data['REFRESH_TOKEN'] = nuevo_refresh
                
        with open(SECRETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
        global REFRESH_TOKEN
        REFRESH_TOKEN = nuevo_refresh
        print("💾 Nuevo Refresh Token guardado en secrets.json automáticamente.")
    except Exception as e:
        print(f"⚠️ No se pudo guardar el Refresh Token: {e}")

def obtener_access_token_con_codigo():
    print("\n" + "="*70)
    print("⚠️  NECESITAS AUTORIZAR LA APLICACIÓN DE STRAVA ⚠️")
    print("="*70)
    print("1. Abre esta URL en tu navegador:")
    print(f"   https://www.strava.com/oauth/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=http://localhost&scope=activity:write,read_all")
    print("\n2. SELECCIONA LA CASILLA de 'Upload your activities' / 'Subir actividades' y acepta.")
    print("\n3. Llegarás a una página en blanco/error (http://localhost/?state=&code=XXXXXXX...)")
    print("   Copia SOLO la parte de las XXXXXXX (sin el &scope=...).")
    print("="*70)
    
    codigo = input("\n👉 PEGA AQUÍ EL CÓDIGO XXXXXXX Y PULSA ENTER: ").strip()
    
    if not codigo: return None
        
    print("\n🔄 Generando nuevos tokens...")
    response = requests.post('https://www.strava.com/api/v3/oauth/token', data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'code': codigo, 'grant_type': 'authorization_code'
    })
    
    if response.status_code == 200:
        data = response.json()
        print("✅ ¡ÉXITO! Permisos obtenidos correctamente.")
        actualizar_archivo_con_token(data['refresh_token'])
        return data['access_token']
        
    print(f"❌ Error al canjear el código: {response.text}")
    return None

def obtener_access_token():
    if REFRESH_TOKEN and REFRESH_TOKEN != 'PON_TU_REFRESH_TOKEN_AQUI' and str(REFRESH_TOKEN).strip() != '':
        print("\n🔄 Verificando autorización con Strava...")
        response = requests.post("https://www.strava.com/api/v3/oauth/token", data={
            'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET, 'refresh_token': REFRESH_TOKEN, 'grant_type': 'refresh_token'
        })
        if response.status_code == 200:
            data = response.json()
            if data['refresh_token'] != REFRESH_TOKEN:
                actualizar_archivo_con_token(data['refresh_token'])
            return data['access_token']
    return obtener_access_token_con_codigo()

def check_upload_status(upload_id, access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    while True:
        response = requests.get(f"https://www.strava.com/api/v3/uploads/{upload_id}", headers=headers)
        
        if response.status_code == 429 or 'Rate Limit Exceeded' in response.text:
            print("   ⏳ Límite de red de Strava (Rate Limit Exceeded). Esperando 15 minutos para continuar...")
            time.sleep(15 * 60)
            continue
            
        if response.status_code == 200:
            status = response.json()
            if status.get('error'):
                if 'duplicate' in status['error']: 
                    print(f"   ⚠️ Actividad duplicada: {status['error']}")
                    return True
                print(f"   ❌ Error en Strava: {status['error']}")
                return False
            
            if status['status'] == 'Your activity is ready.':
                print(f"   ✅ ¡Subida completada con éxito! Activity ID: {status['activity_id']}")
                return True
                
            # IMPORTANTE: Strava tiene un Read Rate Limit de 100 peticiones cada 15 min.
            # Esperar 10 segundos entre consultas nos asegura hacer como máximo 90 en 15 min, 
            # ¡y así nunca tocamos accidentalmente el límite local!
            time.sleep(10) 
        else:
            return False

def paso3_subir_a_strava():
    archivos = [f for f in os.listdir(CARPETA_GPX) if f.endswith('.gpx')]
    if not archivos:
        print("\n🤷 No hay rutas listas y pendientes de subir a Strava.")
        return
        
    print("\n" + "="*50)
    print(f"▶️ PASO 3: SUBIENDO {len(archivos)} RUTAS A STRAVA")
    print("="*50)

    access_token = obtener_access_token()
    if not access_token:
        print("❌ No se ha podido autorizar en Strava. Upload abortado.")
        return
        
    for index, archivo in enumerate(archivos):
        print(f"\n--- Subiendo [{index + 1}/{len(archivos)}] {archivo} ---")
        filepath = os.path.join(CARPETA_GPX, archivo)
        
        nombre_actividad = archivo.replace('.gpx', '').replace('_', ' ').replace('actividad', 'Actividad')
        data = {
            'name': nombre_actividad, 'description': 'Exportado de Xiaomi Mi Fitness',
            'trainer': 0, 'commute': 0, 'data_type': 'gpx'
        }
        
        while True:
            with open(filepath, 'rb') as f:
                response = requests.post("https://www.strava.com/api/v3/uploads", 
                                         headers={'Authorization': f'Bearer {access_token}'}, 
                                         data=data, files={'file': (archivo, f, 'application/gpx+xml')})
                
            if response.status_code == 429 or 'Rate Limit Exceeded' in response.text:
                print("   ⏳ Límite de subidas de Strava (Rate Limit Exceeded). Esperando 15 minutos para seguir...")
                time.sleep(15 * 60)
                continue
                
            if response.status_code == 201:
                if check_upload_status(response.json()['id'], access_token):
                    shutil.move(filepath, os.path.join(CARPETA_SUBIDOS, archivo))
                    print(f"📁 Movido correctamente a 'subidos'.")
                break
            else:
                print(f"❌ Error enviando {archivo}: {response.text}")
                break
            
        # Pausa de seguridad entre archivo y archivo para equilibrar el Overall Rate Limit de Strava
        time.sleep(5)
        
    print(f"\n✨ Paso 3 completado.")

# ==========================================
# RUTINA PRINCIPAL DE EJECUCIÓN
# ==========================================
def main():
    print("\n" + "🚀"*22)
    print("  SINCRONIZADOR TOTAL: XIAOMI ➡️ STRAVA")
    print("🚀"*22)
    
    print("\n¿Qué deseas hacer?")
    print("  [1] Ejecutar TODO el proceso (Descargar, Procesar HR y Subir)")
    print("  [2] Solo Fase Local (Descargar y añadir Pulsaciones a los GPX)")
    print("  [3] Solo Fase Nube (Subir los pendientes a Strava)")
    
    opcion = input("\n👉 Elige una opción [1/2/3] y pulsa ENTER (por defecto 1): ").strip()
    
    if opcion == "2":
        paso1_descargar_rutas()
        paso2_procesar_pulsaciones()
    elif opcion == "3":
        paso3_subir_a_strava()
    else:
        # Ejecuta todo por defecto
        paso1_descargar_rutas()
        paso2_procesar_pulsaciones()
        paso3_subir_a_strava()
    
    print("\n" + "="*50)
    print("🎉 ¡PROCESO FINALIZADO CON ÉXITO! 🎉")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
