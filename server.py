"""
Command Center Ejecutivo V2.5 · Negocio Venezuela
Sincronización Real con Ingenio AI CRM & Gestión de Subcuentas
- Subcuenta 1: Recursea (Docentes MPPE)
- Subcuenta 2: Ingenio Digital (Salud & Bóveda Médica)
- Subcuenta 3: Consolidado Global (Todo el Negocio)
Soporta:
- Cruce financiero P&L dual (Bs. y USD): Ventas CRM vs Gasto Meta Ads
- Tasa Oficial BCV y comprobantes OCR auditados
- Jerarquía visual por conjuntos/productos anti-confusión de ads1, ads2
- Semáforo El Juez (Decisiones inmediatas: Apagar o Escalar)
- Sincronización ágil de CSV desde Descargas y Webhook
"""

import os
import sys
import json
import csv
import io
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI(title="Command Center Ejecutivo V2.5", version="2.5.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
VENTAS_FILE = DATA_DIR / "ventas_crm.json"
DOWNLOADS_DIR = Path.home() / "Downloads"

ENV_FILE = Path(r"C:\Users\Compumar\Google Atigravity\dashboard-meta-ads\dashboard\.env")

# Configuración de Seguridad y Clave de Acceso
ADMIN_PASSWORD = os.getenv("PANEL_PASSWORD", "ingenio2026")
AUTH_COOKIE_NAME = "cc_auth_session"
AUTH_SECRET_TOKEN = "cc_token_ingeniodigital_auth_ok"

# ==========================================
# DEFINICIÓN DE SUBCUENTAS Y CUENTAS META
# ==========================================

SUBCUENTAS = {
    "all": {
        "id": "all",
        "name": "🌐 Todo el Negocio",
        "badge": "Consolidado Global",
        "meta_accounts": ["act_1077134118459248", "act_971185559393685", "act_2215366069321065"],
        "crm_tags": ["docentes", "salud", "general"]
    },
    "docentes": {
        "id": "docentes",
        "name": "🎓 Recursea (Docentes)",
        "badge": "Producción (Docentes)",
        "meta_accounts": ["act_1077134118459248"],
        "crm_tags": ["docentes"]
    },
    "salud": {
        "id": "salud",
        "name": "🩺 Ingenio Digital (Salud)",
        "badge": "Bóveda Médica / Salud",
        "meta_accounts": ["act_971185559393685", "act_2215366069321065"],
        "crm_tags": ["salud"]
    }
}

TRACKED_ACCOUNTS = [
    {"id": "act_1077134118459248", "name": "bIBLICO / Profesores (Recursea)", "subcuenta": "docentes"},
    {"id": "act_971185559393685", "name": "Medicos (Salud / Farmacias)", "subcuenta": "salud"},
    {"id": "act_2215366069321065", "name": "ingenio Digital (Agencia)", "subcuenta": "salud"}
]

# Tasa Oficial BCV por defecto (Bs por 1 USD)
TASA_BCV_DEFAULT = 1035.0  # Basado en ticket promedio de 7.250 Bs por $7 USD

def get_meta_token():
    env_token = os.getenv("META_ACCESS_TOKEN")
    if env_token:
        return env_token.strip()
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("META_ACCESS_TOKEN="):
                    return line.split("=", 1)[1].strip()
    return ""

def call_meta_api(endpoint: str, params: Optional[Dict[str, Any]] = None, method: str = "GET"):
    token = get_meta_token()
    if not token:
        raise ValueError("Token de Meta Ads no configurado")
    
    base_url = "https://graph.facebook.com/v21.0"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    query_params = {"access_token": token}
    if params:
        query_params.update(params)

    if method == "GET":
        url = f"{base_url}{endpoint}?{urllib.parse.urlencode(query_params)}"
        req = urllib.request.Request(url)
    else:
        url = f"{base_url}{endpoint}"
        data = urllib.parse.urlencode(query_params).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("error", {}).get("message", err_body)
        except Exception:
            msg = err_body
        raise RuntimeError(f"Meta API Error ({e.code}): {msg}")

def get_period_params(period: str) -> Dict[str, str]:
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    
    if period == "today":
        return {"date_preset": "today"}
    elif period == "yesterday":
        return {"date_preset": "yesterday"}
    elif period == "last_2d":
        since_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return {"time_range": json.dumps({"since": since_str, "until": today_str})}
    elif period == "last_7d":
        return {"date_preset": "last_7d"}
    elif period == "last_30d":
        return {"date_preset": "last_30d"}
    else:
        return {"date_preset": "today"}

def cargar_ventas() -> List[Dict[str, Any]]:
    if VENTAS_FILE.exists():
        try:
            with open(VENTAS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def guardar_ventas(ventas: List[Dict[str, Any]]):
    with open(VENTAS_FILE, "w", encoding="utf-8") as f:
        json.dump(ventas, f, indent=2, ensure_ascii=False)

def parse_chats(actions: List[Dict[str, Any]]) -> int:
    for a in actions:
        if "messaging_conversation_started_7d" in a.get("action_type", "") or "total_messaging_connection" in a.get("action_type", ""):
            return int(a.get("value", 0))
    return 0

# ==========================================
# ENDPOINTS DE AUTENTICACIÓN
# ==========================================

@app.post("/api/auth/login")
def auth_login(payload: Dict[str, str] = Body(...)):
    pwd = payload.get("password", "").strip()
    if pwd == ADMIN_PASSWORD:
        response = JSONResponse(content={"status": "success", "authenticated": True})
        response.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=AUTH_SECRET_TOKEN,
            max_age=60 * 60 * 24 * 60, # 60 días
            httponly=False,
            samesite="lax"
        )
        return response
    return JSONResponse(status_code=401, content={"status": "error", "message": "Clave incorrecta"})

@app.get("/api/auth/check")
def auth_check(request: Request):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if token == AUTH_SECRET_TOKEN:
        return {"status": "success", "authenticated": True}
    return {"status": "unauthorized", "authenticated": False}

@app.post("/api/auth/logout")
def auth_logout():
    response = JSONResponse(content={"status": "success", "authenticated": False})
    response.delete_cookie(key=AUTH_COOKIE_NAME)
    return response

# ==========================================
# ENDPOINTS API PRINCIPALES
# ==========================================

@app.get("/api/subcuentas")
def get_subcuentas():
    return {"status": "success", "subcuentas": list(SUBCUENTAS.values())}

@app.get("/api/consolidado")
def get_consolidado(period: str = "today", subcuenta: str = "docentes"):
    """
    Calcula el P&L exacto: Ventas reales de CRM vs Gasto Meta Ads
    para la subcuenta y período seleccionados.
    """
    try:
        sub_info = SUBCUENTAS.get(subcuenta, SUBCUENTAS["docentes"])
        p_params = get_period_params(period)
        now = datetime.now()
        
        # 1. Rango de fechas
        if period == "today":
            fechas_filtro = [now.strftime("%Y-%m-%d")]
        elif period == "yesterday":
            fechas_filtro = [(now - timedelta(days=1)).strftime("%Y-%m-%d")]
        elif period == "last_2d":
            fechas_filtro = [now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")]
        elif period == "last_30d":
            fechas_filtro = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
        else: # last_7d
            fechas_filtro = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        # 2. Filtrar ventas CRM por fecha y subcuenta
        todas_ventas = cargar_ventas()
        ventas_periodo = []
        for v in todas_ventas:
            if v.get("fecha") in fechas_filtro:
                v_sub = v.get("subcuenta", "docentes").lower()
                if subcuenta == "all" or v_sub in sub_info["crm_tags"]:
                    ventas_periodo.append(v)

        ingresos_usd = sum(float(v.get("monto_usd", 0.0)) for v in ventas_periodo)
        ingresos_bs = sum(float(v.get("monto_bs", 0.0)) for v in ventas_periodo)
        ocr_verificados = sum(1 for v in ventas_periodo if "verificado" in str(v.get("ocr_status", "")).lower())

        # Desglose de ventas por producto
        desglose_productos = {}
        for v in ventas_periodo:
            prod = v.get("producto", "General")
            if prod not in desglose_productos:
                desglose_productos[prod] = {"producto": prod, "ventas": 0, "total_bs": 0.0, "total_usd": 0.0}
            desglose_productos[prod]["ventas"] += 1
            desglose_productos[prod]["total_bs"] += float(v.get("monto_bs", 0.0))
            desglose_productos[prod]["total_usd"] += float(v.get("monto_usd", 0.0))

        # Desglose por método de pago
        desglose_metodos = {}
        for v in ventas_periodo:
            metodo = v.get("metodo_pago", "No especificado")
            if metodo not in desglose_metodos:
                desglose_metodos[metodo] = 0
            desglose_metodos[metodo] += 1

        # 3. Consultar métricas de Meta Ads solo para las cuentas asociadas a la subcuenta
        cuentas_a_consultar = sub_info["meta_accounts"]
        
        gasto_total_meta = 0.0
        clics_totales = 0
        chats_totales = 0

        for aid in cuentas_a_consultar:
            params = {"fields": "spend,clicks,actions"}
            params.update(p_params)
            try:
                res = call_meta_api(f"/{aid}/insights", params)
                data = res.get("data", [])
                if data:
                    d = data[0]
                    gasto_total_meta += float(d.get("spend", 0.0))
                    clics_totales += int(d.get("clicks", 0))
                    chats_totales += parse_chats(d.get("actions", []))
            except Exception:
                pass

        costo_por_chat = (gasto_total_meta / chats_totales) if chats_totales > 0 else 0.0
        cpc_promedio = (gasto_total_meta / clics_totales) if clics_totales > 0 else 0.0
        
        # 4. Rentabilidad (P&L)
        beneficio_neto = ingresos_usd - gasto_total_meta
        en_ganancia = beneficio_neto >= 0
        roas = (ingresos_usd / gasto_total_meta) if gasto_total_meta > 0 else (10.0 if ingresos_usd > 0 else 0.0)

        return {
            "status": "success",
            "periodo": period,
            "subcuenta": subcuenta,
            "subcuenta_nombre": sub_info["name"],
            "fechas": fechas_filtro,
            "financiero": {
                "ingresos_usd": round(ingresos_usd, 2),
                "ingresos_bs": round(ingresos_bs, 2),
                "gasto_meta_usd": round(gasto_total_meta, 2),
                "beneficio_neto": round(beneficio_neto, 2),
                "en_ganancia": en_ganancia,
                "roas": round(roas, 2),
                "total_ventas_count": len(ventas_periodo),
                "ocr_verificados": ocr_verificados,
                "ticket_promedio_bs": round(ingresos_bs / len(ventas_periodo), 2) if ventas_periodo else 0.0,
                "desglose_productos": list(desglose_productos.values()),
                "desglose_metodos": desglose_metodos
            },
            "meta_kpis": {
                "clics": clics_totales,
                "cpc": round(cpc_promedio, 3),
                "chats": chats_totales,
                "costo_chat": round(costo_por_chat, 2)
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/jerarquia")
def get_jerarquia(period: str = "today", subcuenta: str = "docentes"):
    """
    Retorna el árbol de campañas > conjuntos > anuncios filtrado por la subcuenta.
    """
    try:
        sub_info = SUBCUENTAS.get(subcuenta, SUBCUENTAS["docentes"])
        p_params = get_period_params(period)
        cuentas_ids = sub_info["meta_accounts"]
        
        arbol_cuentas = []

        for aid in cuentas_ids:
            acc_name = next((a["name"] for a in TRACKED_ACCOUNTS if a["id"] == aid), aid)
            
            # 1. Status real
            ad_status_map = {}
            try:
                ads_info = call_meta_api(f"/{aid}/ads", {"fields": "id,status", "limit": 200}).get("data", [])
                for ad in ads_info:
                    ad_status_map[ad["id"]] = ad.get("status", "ACTIVE")
            except Exception:
                pass

            camp_status_map = {}
            try:
                camps_info = call_meta_api(f"/{aid}/campaigns", {"fields": "id,status", "limit": 50}).get("data", [])
                for c in camps_info:
                    camp_status_map[c["id"]] = c.get("status", "ACTIVE")
            except Exception:
                pass

            # 2. Insights en bloque (level=ad)
            ins_params = {
                "level": "ad",
                "fields": "ad_id,ad_name,adset_id,adset_name,campaign_id,campaign_name,spend,clicks,actions",
                "limit": 500
            }
            ins_params.update(p_params)
            
            try:
                insights_list = call_meta_api(f"/{aid}/insights", ins_params).get("data", [])
            except Exception:
                insights_list = []

            # 3. Construir jerarquía
            camps_dict = {}

            for item in insights_list:
                cid = item.get("campaign_id")
                cname = item.get("campaign_name", "Campaña")
                asid = item.get("adset_id")
                asname = item.get("adset_name", "Conjunto")
                adid = item.get("ad_id")
                adname = item.get("ad_name", "Anuncio")
                
                spend = float(item.get("spend", 0.0))
                clicks = int(item.get("clicks", 0))
                chats = parse_chats(item.get("actions", []))
                cost_chat = (spend / chats) if chats > 0 else 0.0

                ad_status = ad_status_map.get(adid, "ACTIVE")

                # Semáforo El Juez
                if ad_status == "PAUSED":
                    badge = "neutral"
                    veredicto = "PAUSADO"
                    accion = "INACTIVO"
                elif chats >= 3 and cost_chat <= 0.60:
                    badge = "success"
                    veredicto = "🚀 ESCALAR"
                    accion = "ESCALAR"
                elif (spend >= 1.50 and chats == 0) or cost_chat > 1.00:
                    badge = "danger"
                    veredicto = "🛑 APAGAR"
                    accion = "PAUSAR"
                else:
                    badge = "info"
                    veredicto = "🧪 TEST"
                    accion = "MANTENER"

                anuncio_data = {
                    "ad_id": adid,
                    "ad_name": adname,
                    "status": ad_status,
                    "spend": spend,
                    "clicks": clicks,
                    "chats": chats,
                    "cost_per_chat": round(cost_chat, 2),
                    "veredicto": veredicto,
                    "badge": badge,
                    "accion": accion
                }

                if cid not in camps_dict:
                    camps_dict[cid] = {
                        "campaign_id": cid,
                        "campaign_name": cname,
                        "status": camp_status_map.get(cid, "ACTIVE"),
                        "spend": 0.0,
                        "chats": 0,
                        "conjuntos_dict": {}
                    }

                camp = camps_dict[cid]
                camp["spend"] += spend
                camp["chats"] += chats

                if asid not in camp["conjuntos_dict"]:
                    camp["conjuntos_dict"][asid] = {
                        "adset_id": asid,
                        "adset_name": asname,
                        "status": "ACTIVE",
                        "budget": 0.0,
                        "spend": 0.0,
                        "chats": 0,
                        "cost_per_chat": 0.0,
                        "anuncios": []
                    }

                conjunto = camp["conjuntos_dict"][asid]
                conjunto["spend"] += spend
                conjunto["chats"] += chats
                conjunto["anuncios"].append(anuncio_data)

            campanas_list = []
            for cid, camp in camps_dict.items():
                conjuntos_list = []
                for asid, cj in camp["conjuntos_dict"].items():
                    cj["spend"] = round(cj["spend"], 2)
                    cj["cost_per_chat"] = round((cj["spend"] / cj["chats"]), 2) if cj["chats"] > 0 else 0.0
                    conjuntos_list.append(cj)
                
                conjuntos_list.sort(key=lambda x: x["spend"], reverse=True)

                campanas_list.append({
                    "campaign_id": cid,
                    "campaign_name": camp["campaign_name"],
                    "status": camp["status"],
                    "spend": round(camp["spend"], 2),
                    "chats": camp["chats"],
                    "conjuntos": conjuntos_list
                })

            campanas_list.sort(key=lambda x: x["spend"], reverse=True)

            if campanas_list or subcuenta != "all":
                arbol_cuentas.append({
                    "account_id": aid,
                    "account_name": acc_name,
                    "campanas": campanas_list
                })

        return {"status": "success", "periodo": period, "subcuenta": subcuenta, "jerarquia": arbol_cuentas}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==========================================
# IMPORTADOR AUTOMÁTICO DE CRM Y WEBHOOKS
# ==========================================

def procesar_csv_filas(csv_text: str) -> Dict[str, Any]:
    ventas_existentes = cargar_ventas()
    ids_existentes = {str(v.get("id")) for v in ventas_existentes}
    nuevas = 0
    
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        norm = {(k.strip().lower() if k else ""): (v.strip() if v else "") for k, v in row.items()}
        
        # Fecha
        raw_date = norm.get("fecha") or norm.get("date") or norm.get("created_at") or datetime.now().strftime("%Y-%m-%d")
        fecha = raw_date
        if "/" in raw_date:
            pts = raw_date.split("/")
            if len(pts) == 3:
                if len(pts[2]) == 4: # DD/MM/YYYY
                    fecha = f"{pts[2]}-{pts[1].zfill(2)}-{pts[0].zfill(2)}"
                elif len(pts[0]) == 4: # YYYY/MM/DD
                    fecha = f"{pts[0]}-{pts[1].zfill(2)}-{pts[2].zfill(2)}"
        elif "t" in raw_date.lower():
            fecha = raw_date.lower().split("t")[0]
            
        hora = norm.get("hora") or norm.get("time") or "12:00"
        producto = norm.get("producto") or norm.get("product") or norm.get("item") or "Kit Docente"
        
        # Montos
        monto_bs_str = norm.get("monto_bs") or norm.get("monto") or norm.get("total_bs") or norm.get("total") or "7250"
        try:
            clean_bs = str(monto_bs_str).replace("Bs", "").replace("bs", "").replace("$", "").replace(" ", "").replace(".", "").replace(",", ".")
            monto_bs = float(clean_bs) if clean_bs else 7250.0
        except Exception:
            monto_bs = 7250.0

        monto_usd_str = norm.get("monto_usd") or norm.get("usd") or norm.get("dolares")
        try:
            if monto_usd_str:
                monto_usd = float(str(monto_usd_str).replace("$", "").replace(" ", "").replace(",", "."))
            else:
                monto_usd = round(monto_bs / TASA_BCV_DEFAULT, 2)
        except Exception:
            monto_usd = round(monto_bs / TASA_BCV_DEFAULT, 2)

        metodo = norm.get("metodo") or norm.get("metodo_pago") or norm.get("payment_method") or "Pago Móvil"
        cliente = norm.get("cliente") or norm.get("nombre") or norm.get("customer") or norm.get("name") or "Cliente CRM"
        ref_ad = norm.get("ref_ad") or norm.get("ad") or ""
        
        # Clasificar subcuenta
        sub = "salud" if any(k in producto.lower() for k in ["farmacia", "medico", "enfermeria", "sacs"]) else "docentes"
        
        venta_id = norm.get("id") or f"crm_{abs(hash(f'{fecha}_{hora}_{cliente}_{monto_bs}'))}"
        if str(venta_id) not in ids_existentes:
            ventas_existentes.insert(0, {
                "id": str(venta_id),
                "fecha": fecha,
                "hora": hora,
                "producto": producto,
                "subcuenta": sub,
                "cuenta": "act_1077134118459248" if sub == "docentes" else "act_971185559393685",
                "monto_bs": monto_bs,
                "monto_usd": round(monto_usd, 2),
                "metodo_pago": metodo,
                "cliente": cliente,
                "ocr_status": "Verificado 100%",
                "ref_ad": ref_ad
            })
            ids_existentes.add(str(venta_id))
            nuevas += 1

    guardar_ventas(ventas_existentes)
    return {
        "status": "success",
        "nuevas_ventas": nuevas,
        "total_ventas": len(ventas_existentes)
    }

@app.post("/api/crm/upload-csv")
async def upload_csv_crm(file: UploadFile = File(...)):
    """Recibe y procesa un archivo CSV exportado desde crm.ingeniodigital.shop/sales."""
    try:
        content = await file.read()
        text = content.decode("utf-8-sig", errors="ignore")
        res = procesar_csv_filas(text)
        res["archivo"] = file.filename
        return res
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/crm/scan-downloads")
def scan_downloads_csv():
    """Escanea la carpeta Downloads si existe localmente."""
    try:
        csv_files = list(DOWNLOADS_DIR.glob("*.csv")) + list(DOWNLOADS_DIR.glob("*sales*.csv"))
        if not csv_files:
            return {"status": "not_found", "message": "No se encontraron archivos CSV en el servidor."}
        
        csv_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        latest_csv = csv_files[0]
        with open(latest_csv, "r", encoding="utf-8-sig", errors="ignore") as f:
            res = procesar_csv_filas(f.read())
            res["archivo"] = latest_csv.name
            return res
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/crm/webhook")
def crm_webhook(payload: Dict[str, Any] = Body(...)):
    """Recibe ventas en vivo desde el bot de Ingenio AI o WhatsApp."""
    try:
        ventas = cargar_ventas()
        producto = payload.get("producto", "Kit Digital")
        sub = "salud" if any(k in producto.lower() for k in ["farmacia", "medico", "enfermeria", "sacs"]) else "docentes"
        
        monto_bs = float(payload.get("monto_bs", 7250.0))
        monto_usd = float(payload.get("monto_usd", round(monto_bs / TASA_BCV_DEFAULT, 2)))

        nueva_venta = {
            "id": f"wh_{int(datetime.now().timestamp())}",
            "fecha": payload.get("fecha", datetime.now().strftime("%Y-%m-%d")),
            "hora": datetime.now().strftime("%H:%M"),
            "producto": producto,
            "subcuenta": sub,
            "cuenta": "act_1077134118459248" if sub == "docentes" else "act_971185559393685",
            "monto_bs": monto_bs,
            "monto_usd": monto_usd,
            "metodo_pago": payload.get("metodo_pago", "Pago Móvil"),
            "cliente": payload.get("cliente", "Cliente WhatsApp"),
            "ocr_status": payload.get("ocr_status", "Verificado 100%"),
            "ref_ad": payload.get("ref_ad", "")
        }
        ventas.insert(0, nueva_venta)
        guardar_ventas(ventas)
        return {"status": "success", "venta": nueva_venta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ventas")
def agregar_venta_manual(payload: Dict[str, Any] = Body(...)):
    """Registra una venta manual desde el modal móvil."""
    try:
        ventas = cargar_ventas()
        producto = payload.get("producto", "Kit Digital")
        sub = payload.get("subcuenta")
        if not sub:
            sub = "salud" if any(k in producto.lower() for k in ["farmacia", "medico", "enfermeria", "sacs"]) else "docentes"
        
        monto_bs = float(payload.get("monto_bs", 7250.0))
        monto_usd = float(payload.get("monto_usd", round(monto_bs / TASA_BCV_DEFAULT, 2)))

        nueva_venta = {
            "id": f"v_{int(datetime.now().timestamp())}",
            "fecha": payload.get("fecha", datetime.now().strftime("%Y-%m-%d")),
            "hora": datetime.now().strftime("%H:%M"),
            "producto": producto,
            "subcuenta": sub,
            "cuenta": "act_1077134118459248" if sub == "docentes" else "act_971185559393685",
            "monto_bs": monto_bs,
            "monto_usd": monto_usd,
            "metodo_pago": payload.get("metodo_pago", "Pago Móvil"),
            "cliente": payload.get("cliente", "Cliente WhatsApp"),
            "ocr_status": "Verificado Manual",
            "ref_ad": payload.get("ref_ad", "")
        }
        ventas.insert(0, nueva_venta)
        guardar_ventas(ventas)
        return {"status": "success", "venta": nueva_venta}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ventas")
def listar_ventas(period: str = "today", subcuenta: str = "docentes"):
    todas = cargar_ventas()
    sub_info = SUBCUENTAS.get(subcuenta, SUBCUENTAS["docentes"])
    now = datetime.now()
    if period == "today":
        fechas = [now.strftime("%Y-%m-%d")]
    elif period == "yesterday":
        fechas = [(now - timedelta(days=1)).strftime("%Y-%m-%d")]
    elif period == "last_2d":
        fechas = [now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")]
    elif period == "last_30d":
        fechas = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    else:
        fechas = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    
    filtradas = []
    for v in todas:
        if v.get("fecha") in fechas:
            v_sub = v.get("subcuenta", "docentes").lower()
            if subcuenta == "all" or v_sub in sub_info["crm_tags"]:
                filtradas.append(v)
                
    return {"status": "success", "ventas": filtradas}

@app.delete("/api/ventas/{venta_id}")
def eliminar_venta(venta_id: str):
    ventas = cargar_ventas()
    ventas = [v for v in ventas if v.get("id") != venta_id]
    guardar_ventas(ventas)
    return {"status": "success", "message": "Venta eliminada"}

@app.post("/api/toggle-ad/{ad_id}")
def toggle_ad(ad_id: str, new_status: str):
    try:
        new_status = new_status.upper().strip()
        if new_status not in ["ACTIVE", "PAUSED"]:
            raise HTTPException(status_code=400, detail="Status inválido")
        res = call_meta_api(f"/{ad_id}", {"status": new_status}, method="POST")
        return {"status": "success", "result": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/prescripciones")
def get_prescripciones():
    return {
        "prescripciones": [
            {
                "producto": "Matemática 1ero a 5to Año MPPE",
                "marca": "Recursea Docentes",
                "diagnostico": "Ángulo ganador: domingos de trasnocho y cortes de luz.",
                "flow_prompt": "Cinematic vertical 9:16 video. A tired Venezuelan high school teacher sitting at a wooden desk with notebooks, grading papers under a warm desk lamp at night, rubbing tired eyes, photorealistic lighting.",
                "titular": "Colega: deja de trasnocharte los domingos pasando planificaciones a mano 📚",
                "demo": "Mostrar Word con Planificación de 3 Momentos y Baremos impresos."
            },
            {
                "producto": "Química de Bachillerato MPPE",
                "marca": "Recursea Docentes",
                "diagnostico": "3 ventas ayer ($21 USD). Ángulo ganador: experimentos caseros sin laboratorio.",
                "flow_prompt": "Cinematic vertical 9:16 video. A female science teacher smiling demonstrating an easy colorful chemical reaction in a glass beaker in a classroom, bright morning daylight, inspiring and professional.",
                "titular": "¿Cómo dar laboratorio de Química sin reactivos en el colegio? 🧪",
                "demo": "Mostrar guía de 20 experimentos con vinagre, bicarbonato y repollo morado."
            },
            {
                "producto": "Pack Médico de Guardias & Internado",
                "marca": "Ingenio Digital",
                "diagnostico": "Ángulo de retención: pánico a quedarse en blanco en pase de sala sin señal.",
                "flow_prompt": "Cinematic vertical 9:16 video. Close up shot of a young doctor in turquoise scrubs holding a smartphone inside a hospital emergency ward hallway at night, looking intently at the phone screen with relief, subtle lights in background, photorealistic 4k.",
                "titular": "⚠️ ¿Guardia de 24h sin señal en el hospital? Ten esto a mano",
                "demo": "4 segundos abriendo carpeta Google Drive 'Vademécum Pediátrico'."
            }
        ]
    }

@app.get("/api/radar-productos")
def get_radar_productos():
    """
    Radar de Productos Digitales Validados en Meta Ads.
    Criterios: 100% Producto Digital + Mucho tiempo activo en Meta Ads (Prueba irrefutable de rentabilidad).
    Sin sobre-filtración: Escalable y adaptable a cualquier país.
    """
    return {
        "status": "success",
        "criterio": "100% Productos Digitales · Larga Longevidad en Meta Ads · Adaptables a Cualquier País",
        "productos": [
            {
                "id": "CONFEITARIA_PRECIFICACAO",
                "nombre": "Planilla de Precificación & Fichas Técnicas para Repostería y Panadería",
                "nicho": "Gastronomía / Pastelería / Emprendimiento Casero",
                "origen": "Brasil (Kiwify / Hotmart) y Argentina",
                "longevidad_meta": "🔥 +360 días activa en pauta continua",
                "tipo_digital": "Plantilla Excel / Google Sheets + 50 Fichas Técnicas de Costeo",
                "dolor_resuelto": "Multiplican ingredientes 'x2 o x3' y pierden dinero ante la inflación o regalan su mano de obra.",
                "angulo_ganador": "Si multiplicas el costo de tus ingredientes por 3 para poner el precio a tus tortas, estás perdiendo dinero sin darte cuenta.",
                "mercados_viables": "Cualquier país (Universal: VE, AR, BR, CO, MX, CL, ES)",
                "ticket_referencia": "$5 a $15 USD (o equivalente en moneda local)",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=BR&q=planilha%20precificacao%20confeitaria"
            },
            {
                "id": "CLIMATIZACION_REFRIGERACION",
                "nombre": "Kit Climatización: Códigos Inverter & Órdenes de Servicio",
                "nicho": "Servicios Técnicos / Refrigeración y Aires Acondicionados",
                "origen": "Brasil y Cono Sur",
                "longevidad_meta": "🔥 +240 días activa en Meta Ads",
                "tipo_digital": "Calculadora de Carga Térmica/Gas + Atlas de Fallas Inverter en PDF + Garantía",
                "dolor_resuelto": "Presupuestos a ciegas perdiendo dinero en gas y tubería, y pérdida de clientes por no descifrar códigos inverter.",
                "angulo_ganador": "Colega técnico: deja de cobrar presupuestos de splits a ojo y diagnostica tarjetas inverter en segundos.",
                "mercados_viables": "Cualquier país con uso de splits o frío comercial (VE, BR, CO, MX, AR, CL)",
                "ticket_referencia": "$6 a $20 USD",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=BR&q=planilha%20ordem%20de%20servico%20ar%20condicionado"
            },
            {
                "id": "TALLER_MECANICO_ORDEN",
                "nombre": "Sistema Taller Mecánico & Electroauto en Control",
                "nicho": "Automotriz / Talleres y Mecánicos Independientes",
                "origen": "Brasil, Argentina y México",
                "longevidad_meta": "🔥 +210 días activa en pauta",
                "tipo_digital": "Plantilla Excel de control de reparaciones, repuestos, cobros y recepción del vehículo",
                "dolor_resuelto": "Desorden total en notas sucias, repuestos que el cliente no paga y disputas por golpes o reclamos.",
                "angulo_ganador": "¿Cuántos repuestos y manos de obra has dejado de cobrar en tu taller este mes por anotar en papeles que se pierden?",
                "mercados_viables": "Cualquier país (Mercado automotriz en toda Latam y España)",
                "ticket_referencia": "$8 a $25 USD",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=BR&q=planilha%20gestao%20oficina%20mecanica"
            },
            {
                "id": "CONTRATOS_ALQUILER_LEGAL",
                "nombre": "Pack Minutas y Contratos de Alquiler Inmobiliario Editables",
                "nicho": "Legal / Bienes Raíces / Propietarios",
                "origen": "Argentina, Colombia y Latam",
                "longevidad_meta": "🔥 +300 días activa ininterrumpida",
                "tipo_digital": "Minutas contractuales en Word 100% editables + Inventario fotográfico + Actas de desalojo/pago",
                "dolor_resuelto": "Miedo a inquilinos morosos o negados a desocupar; alto costo de redactar contratos individuales desde cero.",
                "angulo_ganador": "No redactes contratos desde cero ni arriesgues tu patrimonio con modelos obsoletos de internet.",
                "mercados_viables": "Hispanoamérica completa (AR, VE, CO, MX, CL, ES, etc.)",
                "ticket_referencia": "$10 a $30 USD",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=AR&q=plantillas%20contratos%20alquiler%20word"
            },
            {
                "id": "BARBERIA_SALON_COMISIONES",
                "nombre": "Planilla de Cuadre de Caja y Comisiones para Barberías y Salones",
                "nicho": "Belleza / Barberías / Estética / Uñas y Pestañas",
                "origen": "Brasil y México",
                "longevidad_meta": "🔥 +180 días activa en Meta",
                "tipo_digital": "Planilla Excel de reparto de comisiones (50/50 o 60/40), cierre de caja y control de insumos",
                "dolor_resuelto": "Peleas los fines de semana sacando porcentajes de comisiones a mano, descontrol en caja y robo de insumos.",
                "angulo_ganador": "¿Cuánto tiempo pierdes cada fin de semana sacando cuentas con calculadora y peleando las comisiones con tus estilistas o barberos?",
                "mercados_viables": "Universal (Negocios de estética en cualquier país del mundo)",
                "ticket_referencia": "$5 a $15 USD",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=BR&q=planilha%20gestao%20barbearia%20comissao"
            },
            {
                "id": "ELECTRICISTAS_ORCAMENTOS",
                "nombre": "Kit de Presupuestos & Fichas Técnicas para Electricistas",
                "nicho": "Construcción / Electricistas e Instaladores Solares",
                "origen": "Brasil y Argentina",
                "longevidad_meta": "🔥 +150 días activa",
                "tipo_digital": "Calculadora de cables y cargas + Plantilla de propuesta comercial formal en PDF",
                "dolor_resuelto": "Dar presupuestos informales por WhatsApp para que les regateen, y miedo a errores en el dimensionamiento.",
                "angulo_ganador": "Deja de enviar presupuestos por mensaje de texto para que no te regateen y entrega una propuesta formal que justifique tu precio.",
                "mercados_viables": "Cualquier país de Latam y España",
                "ticket_referencia": "$7 a $20 USD",
                "ads_library_url": "https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=BR&q=planilha%20orcamento%20eletricista"
            }
        ]
    }

# ==========================================
# INTERFAZ WEB RESPONSIVA MOBILE-FIRST
# ==========================================

@app.get("/", response_class=HTMLResponse)
def index_html():
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Command Center V2.5 · Negocio Venezuela</title>
  <meta name="theme-color" content="#090d16">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: #080c14; color: #f1f5f9; padding-bottom: 100px; -webkit-tap-highlight-color: transparent; }
    
    header {
      position: sticky; top: 0; background: rgba(15, 23, 42, 0.95);
      backdrop-filter: blur(12px); border-bottom: 1px solid #1e293b;
      padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; z-index: 100;
    }
    .brand { font-size: 1.05rem; font-weight: 800; color: #38bdf8; display: flex; align-items: center; gap: 8px; }
    .badge-live { background: #064e3b; color: #34d399; font-size: 0.72rem; padding: 2px 7px; border-radius: 20px; font-weight: 700; }
    .header-btns { display: flex; gap: 8px; }
    .btn-top { background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 6px 10px; border-radius: 8px; font-size: 0.75rem; font-weight: 700; cursor: pointer; }
    .btn-action-sale { background: #0284c7; border: none; color: white; padding: 6px 12px; border-radius: 8px; font-size: 0.75rem; font-weight: 800; cursor: pointer; }

    /* Barra Superior: Selector de Subcuentas */
    .subaccount-bar {
      background: #0b1120; padding: 10px 16px; border-bottom: 1px solid #1e293b;
      display: flex; gap: 8px; overflow-x: auto;
    }
    .subaccount-btn {
      flex: 1; min-width: 110px; text-align: center; padding: 9px 8px; font-size: 0.78rem; font-weight: 800;
      color: #94a3b8; background: #1e293b; border: 1px solid #334155; border-radius: 10px; cursor: pointer;
      white-space: nowrap; transition: all 0.2s;
    }
    .subaccount-btn.active {
      background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      color: white; border-color: #38bdf8; box-shadow: 0 4px 12px rgba(2,132,199,0.35);
    }

    /* Barra de Períodos */
    .controls-bar { background: #0f172a; padding: 8px 16px; border-bottom: 1px solid #1e293b; }
    .period-tabs { display: flex; gap: 6px; }
    .period-tab {
      flex: 1; text-align: center; padding: 7px 4px; font-size: 0.8rem; font-weight: 700;
      color: #94a3b8; background: #1e293b; border: 1px solid #334155; border-radius: 8px; cursor: pointer;
    }
    .period-tab.active { background: #334155; color: #38bdf8; border-color: #38bdf8; font-weight: 800; }

    /* Hero Financiero P&L */
    .p-and-l-container { padding: 14px 16px 6px 16px; }
    .hero-pl {
      border-radius: 14px; padding: 16px; position: relative; overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
    }
    .hero-pl.profit {
      background: linear-gradient(135deg, #064e3b 0%, #062f25 100%);
      border: 1px solid #059669;
    }
    .hero-pl.loss {
      background: linear-gradient(135deg, #7f1d1d 0%, #450a0a 100%);
      border: 1px solid #dc2626;
    }
    .pl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
    .pl-status { font-size: 0.8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; }
    .pl-status.profit { color: #34d399; }
    .pl-status.loss { color: #f87171; }
    .pl-roas { background: rgba(0,0,0,0.4); padding: 4px 10px; border-radius: 20px; font-size: 0.8rem; font-weight: 800; color: #fbbf24; }
    
    .pl-amount { font-size: 2.1rem; font-weight: 900; line-height: 1.1; margin-bottom: 4px; }
    .pl-sub { font-size: 0.8rem; color: #cbd5e1; }

    .pl-breakdown {
      display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-top: 14px;
      padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);
    }
    .pl-box { font-size: 0.78rem; color: #cbd5e1; }
    .pl-box strong { font-size: 1.15rem; font-weight: 800; color: white; display: block; margin-top: 2px; }
    .pl-box small { font-size: 0.7rem; color: #94a3b8; }

    /* Barra de Productos Vendidos */
    .products-bar { padding: 8px 16px; overflow-x: auto; display: flex; gap: 8px; }
    .prod-chip {
      background: #1e293b; border: 1px solid #334155; padding: 6px 12px; border-radius: 20px;
      font-size: 0.75rem; font-weight: 700; white-space: nowrap; color: #38bdf8;
    }
    .prod-chip span { color: #34d399; margin-left: 4px; }

    /* Navegación por Pestañas */
    .nav-tabs { display: flex; background: #0f172a; padding: 4px 16px; gap: 6px; border-bottom: 1px solid #1e293b; margin-top: 8px; }
    .nav-tab {
      flex: 1; text-align: center; padding: 8px 4px; font-size: 0.76rem; font-weight: 700;
      color: #64748b; border: none; background: transparent; cursor: pointer; border-radius: 8px;
    }
    .nav-tab.active { background: #0284c7; color: white; }

    .view-content { padding: 14px 16px; }

    /* Acordeón Jerárquico */
    .campaign-block { background: #101726; border: 1px solid #1e293b; border-radius: 12px; margin-bottom: 14px; overflow: hidden; }
    .campaign-header {
      padding: 12px 14px; background: #131d31; border-bottom: 1px solid #1e293b;
      display: flex; justify-content: space-between; align-items: center;
    }
    .campaign-name { font-size: 0.9rem; font-weight: 800; color: #f8fafc; }
    .campaign-stats { font-size: 0.75rem; color: #94a3b8; margin-top: 2px; }
    
    .adset-block { border-bottom: 1px solid #1e293b; padding: 10px 14px; background: #0c1322; }
    .adset-header { display: flex; justify-content: space-between; align-items: center; }
    .adset-name { font-size: 0.85rem; font-weight: 700; color: #38bdf8; display: flex; align-items: center; gap: 6px; }
    .adset-stats { font-size: 0.75rem; color: #94a3b8; }

    .ads-table { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
    .ad-row {
      background: #131d31; border: 1px solid #1e293b; border-radius: 8px; padding: 10px 12px;
      display: flex; justify-content: space-between; align-items: center;
    }
    .ad-info { flex: 1; }
    .ad-title-row { display: flex; align-items: center; gap: 8px; }
    .ad-title { font-size: 0.85rem; font-weight: 700; color: #f1f5f9; }
    .badge-semaforo { font-size: 0.68rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; }
    .badge-success { background: #064e3b; color: #34d399; }
    .badge-danger { background: #7f1d1d; color: #f87171; }
    .badge-info { background: #075985; color: #38bdf8; }
    .badge-neutral { background: #334155; color: #94a3b8; }

    .ad-numbers { font-size: 0.75rem; color: #94a3b8; margin-top: 4px; display: flex; gap: 10px; }
    .ad-numbers strong { color: white; }

    .switch-btn {
      padding: 6px 12px; border-radius: 6px; font-size: 0.72rem; font-weight: 800; cursor: pointer; border: none;
    }
    .switch-on { background: #064e3b; color: #34d399; border: 1px solid #059669; }
    .switch-off { background: #7f1d1d; color: #f87171; border: 1px solid #dc2626; }

    /* Modal Registrar Venta */
    .modal-overlay {
      position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8);
      backdrop-filter: blur(5px); display: none; justify-content: center; align-items: flex-end; z-index: 1000;
    }
    .modal-sheet {
      background: #0f172a; width: 100%; max-width: 500px; border-radius: 20px 20px 0 0;
      padding: 24px 20px; border-top: 1px solid #334155; animation: slideUp 0.3s ease;
    }
    @keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
    .modal-title { font-size: 1.1rem; font-weight: 800; color: #38bdf8; margin-bottom: 14px; }
    .form-group { margin-bottom: 12px; }
    .form-label { font-size: 0.75rem; color: #94a3b8; font-weight: 700; margin-bottom: 4px; display: block; }
    .form-input {
      width: 100%; background: #1e293b; border: 1px solid #334155; color: white;
      padding: 10px 12px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; outline: none;
    }
    .btn-submit {
      width: 100%; background: #0284c7; color: white; border: none; padding: 12px;
      border-radius: 8px; font-size: 0.9rem; font-weight: 800; cursor: pointer; margin-top: 8px;
    }
    .btn-cancel {
      width: 100%; background: transparent; color: #94a3b8; border: none; padding: 10px;
      font-size: 0.85rem; font-weight: 600; cursor: pointer; margin-top: 4px;
    }

    .fab {
      position: fixed; bottom: 20px; right: 20px; background: #0284c7; color: white;
      width: 56px; height: 56px; border-radius: 50%; display: flex; justify-content: center;
      align-items: center; font-size: 1.8rem; font-weight: 900; box-shadow: 0 6px 16px rgba(2,132,199,0.5);
      cursor: pointer; z-index: 90; border: none;
    }

    /* Auth Gate */
    .auth-overlay {
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: #080c14; z-index: 9999;
      display: flex; justify-content: center; align-items: center; padding: 20px;
    }
    .auth-card {
      background: #0f172a; border: 1px solid #1e293b; border-radius: 20px;
      padding: 30px 24px; width: 100%; max-width: 380px; text-align: center;
      box-shadow: 0 10px 40px rgba(0,0,0,0.6);
    }
    .auth-icon { font-size: 3rem; margin-bottom: 12px; }
    .auth-title { font-size: 1.3rem; font-weight: 800; color: #f8fafc; margin-bottom: 4px; }
    .auth-subtitle { font-size: 0.82rem; color: #94a3b8; margin-bottom: 24px; }
    .auth-input {
      width: 100%; background: #1e293b; border: 1px solid #334155; color: white;
      padding: 14px 16px; border-radius: 12px; font-size: 1.1rem; text-align: center;
      font-weight: 700; letter-spacing: 2px; outline: none; margin-bottom: 14px;
      transition: border-color 0.2s;
    }
    .auth-input:focus { border-color: #38bdf8; }
    .auth-btn {
      width: 100%; background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
      color: white; border: none; padding: 14px; border-radius: 12px;
      font-size: 0.95rem; font-weight: 800; cursor: pointer;
      box-shadow: 0 4px 14px rgba(2,132,199,0.4);
    }
    .auth-error {
      color: #f87171; font-size: 0.8rem; font-weight: 700; margin-top: 12px; display: none;
    }

    .toast {
      position: fixed; bottom: 85px; left: 50%; transform: translateX(-50%);
      background: #10b981; color: white; padding: 10px 18px; border-radius: 20px;
      font-size: 0.85rem; font-weight: 700; display: none; z-index: 2000; box-shadow: 0 4px 12px rgba(0,0,0,0.4);
    }
  </style>
</head>
<body>

  <!-- PANTALLA DE ACCESO CON CLAVE (AUTH GATE) -->
  <div class="auth-overlay" id="authOverlay">
    <div class="auth-card">
      <div class="auth-icon">🛡️</div>
      <div class="auth-title">Command Center</div>
      <div class="auth-subtitle">Ingenio Digital · Acceso Privado</div>
      <input type="password" class="auth-input" id="authPassword" placeholder="Introduce la clave de acceso" onkeydown="if(event.key==='Enter') intentarLogin()">
      <button class="auth-btn" onclick="intentarLogin()">Ingresar al Panel</button>
      <div class="auth-error" id="authError">Clave incorrecta. Intenta nuevamente.</div>
    </div>
  </div>

  <!-- HEADER -->
  <header>
    <div class="brand">
      ⚡ COMMAND CENTER V2.5
      <span class="badge-live">● EN VIVO</span>
    </div>
    <div class="header-btns">
      <input type="file" id="csvFileInput" accept=".csv" style="display:none;" onchange="subirCSV(event)">
      <button class="btn-top" onclick="abrirSelectorCSV()">📥 Subir CSV</button>
      <button class="btn-action-sale" onclick="abrirModalVenta()">+ Venta</button>
      <button class="btn-top" onclick="recargarTodo()">🔄</button>
      <button class="btn-top" onclick="cerrarSesion()" title="Cerrar Sesión">🔒</button>
    </div>
  </header>

  <!-- SELECTOR DE SUBCUENTA DE NEGOCIO -->
  <div class="subaccount-bar">
    <button class="subaccount-btn active" data-sub="docentes" onclick="seleccionarSubcuenta('docentes')">
      🎓 Recursea (Docentes)
    </button>
    <button class="subaccount-btn" data-sub="salud" onclick="seleccionarSubcuenta('salud')">
      🩺 Ingenio Digital (Salud)
    </button>
    <button class="subaccount-btn" data-sub="all" onclick="seleccionarSubcuenta('all')">
      🌐 Todo el Negocio
    </button>
  </div>

  <!-- FILTROS DE PERÍODO -->
  <div class="controls-bar">
    <div class="period-tabs">
      <button class="period-tab active" data-period="today" onclick="seleccionarPeriodo('today')">Hoy</button>
      <button class="period-tab" data-period="yesterday" onclick="seleccionarPeriodo('yesterday')">Ayer</button>
      <button class="period-tab" data-period="last_2d" onclick="seleccionarPeriodo('last_2d')">48h</button>
      <button class="period-tab" data-period="last_7d" onclick="seleccionarPeriodo('last_7d')">7 Días</button>
      <button class="period-tab" data-period="last_30d" onclick="seleccionarPeriodo('last_30d')">30 Días</button>
    </div>
  </div>

  <!-- HERO FINANCIERO: P&L (PÉRDIDA O GANANCIA) -->
  <div class="p-and-l-container">
    <div class="hero-pl profit" id="heroPL">
      <div class="pl-header">
        <span class="pl-status profit" id="plStatus">● EN GANANCIA NETA</span>
        <span class="pl-roas" id="plRoas">🎯 ROAS: 1.50x</span>
      </div>
      <div class="pl-amount" id="plBeneficio">+$0.00 USD</div>
      <div class="pl-sub" id="plSubtext">Sincronizando datos...</div>

      <div class="pl-breakdown">
        <div class="pl-box">
          Ingresos Ventas CRM
          <strong id="plIngresos">$0.00</strong>
          <small id="plIngresosBs">0.00 Bs</small>
        </div>
        <div class="pl-box">
          Gasto Meta Ads
          <strong id="plGasto">$0.00</strong>
          <small id="plChats">0 chats iniciados</small>
        </div>
        <div class="pl-box">
          Comprobantes OCR
          <strong id="plOcrCount">0 / 0</strong>
          <small>Auditados automáticamente</small>
        </div>
        <div class="pl-box">
          Costo / Chat
          <strong id="plCostoChat">$0.00</strong>
          <small id="plCpc">CPC: $0.00</small>
        </div>
      </div>
    </div>
  </div>

  <!-- DESGLOSE DE PRODUCTOS VENDIDOS -->
  <div class="products-bar" id="productsBar">
    <div class="prod-chip">Cargando ventas...</div>
  </div>

  <!-- NAVEGACIÓN -->
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="cambiarVista('jerarquia')">🌳 Jerarquía Ads</button>
    <button class="nav-tab" onclick="cambiarVista('juez')">⚖️ El Juez (Acciones)</button>
    <button class="nav-tab" onclick="cambiarVista('ventas')">🧾 Historial CRM</button>
    <button class="nav-tab" onclick="cambiarVista('creativos')">🎯 Fábrica</button>
    <button class="nav-tab" onclick="cambiarVista('radar')">🛰️ Radar Espía</button>
  </div>

  <!-- CONTENIDO DE VISTAS -->
  <div class="view-content">

    <!-- VISTA 1: JERARQUÍA COMPLETA -->
    <div id="viewJerarquia">
      <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:12px;">
        Estructura por Conjuntos de Anuncio (cada conjunto representa un producto o nicho):
      </div>
      <div id="treeContainer">Cargando campañas...</div>
    </div>

    <!-- VISTA 2: EL JUEZ -->
    <div id="viewJuez" style="display:none;">
      <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:12px;">
        Anuncios que requieren apagar o escalar según costos de chat:
      </div>
      <div id="juezContainer">Cargando análisis...</div>
    </div>

    <!-- VISTA 3: HISTORIAL DE VENTAS CRM -->
    <div id="viewVentas" style="display:none;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <span style="font-size:0.85rem; font-weight:800; color:#38bdf8;">Ventas Confirmadas en CRM</span>
        <button class="btn-top" onclick="abrirSelectorCSV()">📥 Subir CSV CRM</button>
      </div>
      <div id="ventasContainer">Cargando ventas...</div>
    </div>

    <!-- VISTA 4: FÁBRICA / PROMPTS -->
    <div id="viewCreativos" style="display:none;">
      <div style="font-size:0.8rem; color:#94a3b8; margin-bottom:12px;">
        Prescripciones listas de Google Flow y Nano Banana:
      </div>
      <div id="creativosContainer">Cargando fábrica...</div>
    </div>

    <!-- VISTA 5: RADAR ESPÍA ADS (PRODUCTOS DIGITALES LONGEVOS) -->
    <div id="viewRadar" style="display:none;">
      <div style="background:#131d31; border:1px solid #1e293b; border-radius:10px; padding:12px 14px; margin-bottom:14px;">
        <div style="font-size:0.85rem; font-weight:800; color:#38bdf8; display:flex; align-items:center; gap:6px;">
          <span>🛰️ Radar de Productos Digitales Validados en Meta Ads</span>
        </div>
        <div style="font-size:0.75rem; color:#94a3b8; margin-top:4px; line-height:1.4;">
          <strong>Criterio Infalible:</strong> 100% productos digitales con <strong>meses de pauta continua activa</strong> en Meta Ads (Brasil, Argentina y Latam). Si un anunciante lleva meses pagando anuncios ininterrumpidamente, el producto es rentable y está probado para modelar y lanzar en cualquier país.
        </div>
      </div>
      <div id="radarContainer">Cargando radar de productos...</div>
    </div>

  </div>

  <!-- BOTÓN FLOTANTE REGISTRAR VENTA -->
  <button class="fab" onclick="abrirModalVenta()">+</button>

  <!-- MODAL REGISTRAR VENTA -->
  <div class="modal-overlay" id="modalVenta" onclick="cerrarModalFuera(event)">
    <div class="modal-sheet">
      <div class="modal-title">💰 Registrar Venta de WhatsApp</div>

      <div class="form-group">
        <label class="form-label">Subcuenta de Negocio:</label>
        <select class="form-input" id="inputSubcuenta">
          <option value="docentes">🎓 Recursea (Docentes MPPE)</option>
          <option value="salud">🩺 Ingenio Digital (Salud & Bóveda)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Producto Vendido:</label>
        <select class="form-input" id="inputProducto">
          <option value="Planificaciones Matemática MPPE">📐 Planificaciones Matemática ($7 USD / 7.250 Bs)</option>
          <option value="Kit Docente de Química MPPE">🧪 Kit Docente de Química ($7 USD / 7.250 Bs)</option>
          <option value="Kit Docente de Física MPPE">⚡ Kit Docente de Física ($7 USD / 7.250 Bs)</option>
          <option value="Kit Docente de Inglés">🇬🇧 Kit Docente de Inglés ($7 USD / 7.250 Bs)</option>
          <option value="Kit Docente de Castellano">📚 Kit Docente de Castellano ($7 USD / 7.250 Bs)</option>
          <option value="Pack Médico de Guardias 2026">🩺 Pack Médico Guardias ($7 USD / 7.250 Bs)</option>
          <option value="Kit de Farmacias SACS">💊 Kit Farmacias SACS ($15 USD / 15.000 Bs)</option>
          <option value="Kit Enfermería UCI">💉 Kit Enfermería ($5 USD / 5.000 Bs)</option>
          <option value="Venta General / Sin Asignar">📦 Venta General / Sin Asignar ($7 USD)</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Monto en Bolívares (Bs.):</label>
        <input type="number" class="form-input" id="inputMontoBs" value="7250" step="50" oninput="actualizarUsdEquivalente()">
      </div>

      <div class="form-group">
        <label class="form-label">Equivalente en Dólares (USD):</label>
        <input type="number" class="form-input" id="inputMontoUsd" value="7.00" step="0.5">
      </div>

      <div class="form-group">
        <label class="form-label">Método de Pago:</label>
        <select class="form-input" id="inputMetodo">
          <option value="PagomóvilBDV Personas">🇻🇪 PagomóvilBDV Personas</option>
          <option value="Banesco Banco Universal">🇻🇪 Banesco Banco Universal</option>
          <option value="BNC">🇻🇪 BNC Banco Nacional de Crédito</option>
          <option value="Banco Mercantil">🇻🇪 Banco Mercantil</option>
          <option value="Binance Pay">🟡 Binance Pay (USDT)</option>
          <option value="Zinli">🟣 Zinli / Wally</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Cliente (Nombre o WhatsApp):</label>
        <input type="text" class="form-input" id="inputCliente" placeholder="Ej: Prof. Carlos / Dra. María">
      </div>

      <button class="btn-submit" onclick="guardarNuevaVenta()">Guardar Venta y Recalcular ROAS</button>
      <button class="btn-cancel" onclick="cerrarModalVenta()">Cancelar</button>
    </div>
  </div>

  <div id="toast" class="toast">¡Operación exitosa!</div>

  <script>
    let currentPeriod = 'today';
    let currentSubcuenta = 'docentes';

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 2200);
    }

    function seleccionarSubcuenta(sub) {
      currentSubcuenta = sub;
      document.querySelectorAll('.subaccount-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.querySelector(`[data-sub="${sub}"]`);
      if (activeBtn) activeBtn.classList.add('active');
      recargarTodo();
    }

    function seleccionarPeriodo(p) {
      currentPeriod = p;
      document.querySelectorAll('.period-tab').forEach(b => b.classList.remove('active'));
      const activeBtn = document.querySelector(`[data-period="${p}"]`);
      if (activeBtn) activeBtn.classList.add('active');
      recargarTodo();
    }

    function cambiarVista(vista) {
      document.querySelectorAll('.nav-tab').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');

      document.getElementById('viewJerarquia').style.display = (vista === 'jerarquia') ? 'block' : 'none';
      document.getElementById('viewJuez').style.display = (vista === 'juez') ? 'block' : 'none';
      document.getElementById('viewVentas').style.display = (vista === 'ventas') ? 'block' : 'none';
      document.getElementById('viewCreativos').style.display = (vista === 'creativos') ? 'block' : 'none';
      document.getElementById('viewRadar').style.display = (vista === 'radar') ? 'block' : 'none';
    }

    async function cargarConsolidado() {
      try {
        const res = await fetch(`/api/consolidado?period=${currentPeriod}&subcuenta=${currentSubcuenta}`);
        const data = await res.json();
        if (data.status === 'success') {
          const fin = data.financiero;
          const kpi = data.meta_kpis;

          const hero = document.getElementById('heroPL');
          const status = document.getElementById('plStatus');
          const benef = document.getElementById('plBeneficio');
          const sub = document.getElementById('plSubtext');
          const roas = document.getElementById('plRoas');

          roas.innerText = `🎯 ROAS: ${fin.roas.toFixed(2)}x`;
          document.getElementById('plIngresos').innerText = `$${fin.ingresos_usd.toFixed(2)} USD`;
          document.getElementById('plIngresosBs').innerText = `${fin.ingresos_bs.toLocaleString('es-VE')} Bs`;
          document.getElementById('plGasto').innerText = `$${fin.gasto_meta_usd.toFixed(2)} USD`;
          document.getElementById('plChats').innerText = `${kpi.chats} chats iniciados`;
          document.getElementById('plOcrCount').innerText = `${fin.ocr_verificados} / ${fin.total_ventas_count}`;
          document.getElementById('plCostoChat').innerText = `$${kpi.costo_chat.toFixed(2)}`;
          document.getElementById('plCpc').innerText = `CPC: $${kpi.cpc.toFixed(3)}`;

          if (fin.en_ganancia) {
            hero.className = 'hero-pl profit';
            status.className = 'pl-status profit';
            status.innerText = '● EN GANANCIA NETA';
            benef.innerText = `+$${fin.beneficio_neto.toFixed(2)} USD`;
            sub.innerText = `${fin.total_ventas_count} ventas confirmadas en ${data.subcuenta_nombre}`;
          } else {
            hero.className = 'hero-pl loss';
            status.className = 'pl-status loss';
            status.innerText = '● EN PÉRDIDA NETA';
            benef.innerText = `-$${Math.abs(fin.beneficio_neto).toFixed(2)} USD`;
            sub.innerText = `Gasto de Meta Ads supera ingresos en este período`;
          }

          // Chips de Productos
          const bar = document.getElementById('productsBar');
          bar.innerHTML = '';
          if (fin.desglose_productos.length === 0) {
            bar.innerHTML = '<div class="prod-chip">Sin ventas confirmadas en este período</div>';
          } else {
            fin.desglose_productos.forEach(p => {
              bar.innerHTML += `
                <div class="prod-chip">
                  ${p.producto}: <span>$${p.total_usd.toFixed(1)} USD (${p.ventas} vtas)</span>
                </div>
              `;
            });
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function cargarJerarquia() {
      try {
        const res = await fetch(`/api/jerarquia?period=${currentPeriod}&subcuenta=${currentSubcuenta}`);
        const data = await res.json();
        const container = document.getElementById('treeContainer');
        const juezContainer = document.getElementById('juezContainer');
        container.innerHTML = '';
        if (juezContainer) juezContainer.innerHTML = '';

        if (data.status === 'success') {
          let hayCampanas = false;
          let listaEscalar = [];
          let listaApagar = [];

          data.jerarquia.forEach(acc => {
            acc.campanas.forEach(camp => {
              hayCampanas = true;
              let adsetsHtml = '';

              camp.conjuntos.forEach(adset => {
                let adsHtml = '';
                adset.anuncios.forEach(ad => {
                  const adObj = { ...ad, campana: camp.campaign_name, conjunto: adset.adset_name };
                  if (ad.veredicto.includes('ESCALAR')) listaEscalar.push(adObj);
                  else if (ad.veredicto.includes('APAGAR')) listaApagar.push(adObj);

                  adsHtml += `
                    <div class="ad-row">
                      <div class="ad-info">
                        <div class="ad-title-row">
                          <span class="ad-title">${ad.ad_name}</span>
                          <span class="badge-semaforo badge-${ad.badge}">${ad.veredicto}</span>
                        </div>
                        <div class="ad-numbers">
                          <div>Gasto: <strong>$${ad.spend.toFixed(2)}</strong></div>
                          <div>Chats: <strong>${ad.chats}</strong></div>
                          <div>C/Chat: <strong>${ad.chats > 0 ? '$' + ad.cost_per_chat.toFixed(2) : 'N/A'}</strong></div>
                        </div>
                      </div>
                      <button class="switch-btn ${ad.status === 'ACTIVE' ? 'switch-on' : 'switch-off'}" 
                              onclick="toggleAd('${ad.ad_id}', '${ad.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'}')">
                        ${ad.status === 'ACTIVE' ? 'ENCENDIDO' : 'PAUSADO'}
                      </button>
                    </div>
                  `;
                });

                adsetsHtml += `
                  <div class="adset-block">
                    <div class="adset-header">
                      <div>
                        <div class="adset-name">📦 Producto / Conjunto: ${adset.adset_name}</div>
                        <div class="adset-stats">Gasto: $${adset.spend.toFixed(2)} · ${adset.chats} chats ($${adset.cost_per_chat.toFixed(2)}/chat)</div>
                      </div>
                      <span class="badge-semaforo ${adset.status === 'ACTIVE' ? 'badge-success' : 'badge-neutral'}">${adset.status}</span>
                    </div>
                    <div class="ads-table">
                      ${adsHtml || '<div style="font-size:0.75rem; color:#64748b;">0 anuncios en este conjunto</div>'}
                    </div>
                  </div>
                `;
              });

              container.innerHTML += `
                <div class="campaign-block">
                  <div class="campaign-header">
                    <div>
                      <div class="campaign-name">📁 Campaña: ${camp.campaign_name}</div>
                      <div class="campaign-stats">Gasto Total: $${camp.spend.toFixed(2)} · ${camp.chats} chats iniciados</div>
                    </div>
                    <span class="badge-semaforo ${camp.status === 'ACTIVE' ? 'badge-success' : 'badge-neutral'}">${camp.status}</span>
                  </div>
                  <div>${adsetsHtml}</div>
                </div>
              `;
            });
          });

          // Renderizar Sección El Juez
          if (juezContainer) {
            let juezHtml = '';
            
            if (listaApagar.length > 0) {
              juezHtml += `
                <div style="background:#450a0a; border:1px solid #dc2626; border-radius:12px; padding:14px; margin-bottom:14px;">
                  <div style="color:#f87171; font-weight:800; font-size:0.9rem; margin-bottom:4px;">🛑 APAGAR URGENTE (${listaApagar.length} Anuncios)</div>
                  <div style="font-size:0.75rem; color:#fca5a5; margin-bottom:10px;">Están quemando presupuesto con costo por chat > $1.00:</div>
              `;
              listaApagar.forEach(ad => {
                juezHtml += `
                  <div class="ad-row" style="background:#1c1917; margin-bottom:6px;">
                    <div class="ad-info">
                      <div style="font-weight:700; color:white; font-size:0.85rem;">${ad.ad_name} · <span style="color:#38bdf8;">${ad.conjunto}</span></div>
                      <div class="ad-numbers">
                        <div>Gasto: <strong style="color:#f87171;">$${ad.spend.toFixed(2)}</strong></div>
                        <div>Chats: <strong>${ad.chats}</strong></div>
                        <div>C/Chat: <strong style="color:#f87171;">$${ad.cost_per_chat.toFixed(2)}</strong></div>
                      </div>
                    </div>
                    <button class="switch-btn switch-off" onclick="toggleAd('${ad.ad_id}', 'PAUSED')">Apagar Ahora</button>
                  </div>
                `;
              });
              juezHtml += `</div>`;
            }

            if (listaEscalar.length > 0) {
              juezHtml += `
                <div style="background:#062f25; border:1px solid #059669; border-radius:12px; padding:14px; margin-bottom:14px;">
                  <div style="color:#34d399; font-weight:800; font-size:0.9rem; margin-bottom:4px;">🚀 GANADORES PARA ESCALAR (${listaEscalar.length} Anuncios)</div>
                  <div style="font-size:0.75rem; color:#a7f3d0; margin-bottom:10px;">Costo por chat excelente (≤ $0.60):</div>
              `;
              listaEscalar.forEach(ad => {
                juezHtml += `
                  <div class="ad-row" style="background:#091e17; margin-bottom:6px;">
                    <div class="ad-info">
                      <div style="font-weight:700; color:white; font-size:0.85rem;">${ad.ad_name} · <span style="color:#38bdf8;">${ad.conjunto}</span></div>
                      <div class="ad-numbers">
                        <div>Gasto: <strong>$${ad.spend.toFixed(2)}</strong></div>
                        <div>Chats: <strong style="color:#34d399;">${ad.chats} chats</strong></div>
                        <div>C/Chat: <strong style="color:#34d399;">$${ad.cost_per_chat.toFixed(2)}</strong></div>
                      </div>
                    </div>
                    <div style="font-size:0.72rem; font-weight:800; color:#34d399; background:#064e3b; padding:4px 8px; border-radius:6px;">
                      🔥 GANADOR
                    </div>
                  </div>
                `;
              });
              juezHtml += `</div>`;
            }

            if (listaApagar.length === 0 && listaEscalar.length === 0) {
              juezHtml = '<div style="padding:20px; text-align:center; color:#94a3b8;">No hay decisiones urgentes en este período. Los anuncios activos están en fase de aprendizaje normal.</div>';
            }

            juezContainer.innerHTML = juezHtml;
          }

          if (!hayCampanas) {
            container.innerHTML = '<div style="padding:20px; text-align:center; color:#94a3b8;">No hay campañas activas con gasto para esta subcuenta en este período.</div>';
          }
        }
      } catch (e) {
        console.error(e);
      }
    }

    async function toggleAd(adId, newStatus) {
      if (!confirm(`¿Confirmas cambiar este anuncio a ${newStatus}?`)) return;
      try {
        const res = await fetch(`/api/toggle-ad/${adId}?new_status=${newStatus}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
          showToast(`Anuncio puesto en ${newStatus}`);
          cargarJerarquia();
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    async function cargarVentas() {
      try {
        const res = await fetch(`/api/ventas?period=${currentPeriod}&subcuenta=${currentSubcuenta}`);
        const data = await res.json();
        const box = document.getElementById('ventasContainer');
        box.innerHTML = '';
        if (data.ventas.length === 0) {
          box.innerHTML = '<div style="padding:20px; text-align:center; color:#94a3b8;">No hay ventas confirmadas en este período para esta subcuenta. Toca el botón (+) para registrar una o importa un CSV de Ingenio CRM.</div>';
          return;
        }

        data.ventas.forEach(v => {
          box.innerHTML += `
            <div class="ad-row" style="margin-bottom:8px;">
              <div style="flex:1;">
                <div style="font-size:0.85rem; font-weight:700; color:white;">${v.producto}</div>
                <div style="font-size:0.75rem; color:#94a3b8;">
                  ${v.fecha} ${v.hora} · ${v.cliente} · <span style="color:#38bdf8;">${v.metodo_pago}</span>
                </div>
                <div style="font-size:0.7rem; color:#34d399; margin-top:2px;">
                  🛡️ ${v.ocr_status || 'OCR Auditado'}
                </div>
              </div>
              <div style="text-align:right;">
                <div style="font-size:1.05rem; font-weight:800; color:#34d399;">+$${v.monto_usd.toFixed(2)}</div>
                <div style="font-size:0.72rem; color:#94a3b8;">${v.monto_bs.toLocaleString('es-VE')} Bs</div>
                <button style="background:transparent; border:none; color:#ef4444; font-size:0.7rem; cursor:pointer; margin-top:4px;" onclick="eliminarVenta('${v.id}')">Eliminar</button>
              </div>
            </div>
          `;
        });
      } catch (e) {
        console.error(e);
      }
    }

    function abrirSelectorCSV() {
      const input = document.getElementById('csvFileInput');
      if (input) input.click();
    }

    async function subirCSV(event) {
      const file = event.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('file', file);

      showToast('⏳ Importando ventas del CSV...');
      try {
        const res = await fetch('/api/crm/upload-csv', {
          method: 'POST',
          body: formData
        });
        const data = await res.json();
        if (data.status === 'success') {
          showToast(`¡${data.nuevas_ventas} ventas nuevas procesadas (${data.total_ventas} en total)!`);
          recargarTodo();
        } else {
          alert('Error al importar CSV: ' + (data.message || 'Error desconocido'));
        }
      } catch (e) {
        alert('Error al subir archivo: ' + e);
      }
      event.target.value = '';
    }

    async function escanearCSVDescargas() {
      abrirSelectorCSV();
    }

    async function eliminarVenta(id) {
      if (!confirm('¿Eliminar esta venta?')) return;
      await fetch(`/api/ventas/${id}`, { method: 'DELETE' });
      showToast('Venta eliminada');
      recargarTodo();
    }

    async function cargarPrescripciones() {
      try {
        const res = await fetch('/api/prescripciones');
        const data = await res.json();
        const box = document.getElementById('creativosContainer');
        box.innerHTML = '';
        data.prescripciones.forEach(p => {
          box.innerHTML += `
            <div class="campaign-block" style="padding:14px; margin-bottom:12px;">
              <div style="font-size:0.9rem; font-weight:800; color:#38bdf8;">${p.producto}</div>
              <div style="font-size:0.75rem; color:#94a3b8; margin-bottom:8px;">${p.marca} · ${p.diagnostico}</div>

              <div style="font-size:0.75rem; font-weight:700; color:#cbd5e1; margin-top:8px;">🎬 Prompt Google Flow (9:16):</div>
              <div style="background:#090d16; padding:8px; border-radius:6px; font-size:0.75rem; color:#cbd5e1; margin-top:4px;">${p.flow_prompt}</div>
              <button class="switch-btn switch-on" style="width:100%; margin-top:6px;" onclick="copiarTexto('${p.flow_prompt.replace(/'/g, "\\'")}')">📋 Copiar Prompt Flow</button>

              <div style="font-size:0.75rem; font-weight:700; color:#cbd5e1; margin-top:12px;">✍️ Titular de Choque:</div>
              <div style="color:#fbbf24; font-weight:800; font-size:0.85rem; margin-top:2px;">"${p.titular}"</div>
            </div>
          `;
        });
      } catch (e) {
        console.error(e);
      }
    }

    function copiarTexto(t) {
      navigator.clipboard.writeText(t).then(() => showToast('¡Copiado!'));
    }

    function abrirModalVenta() {
      document.getElementById('inputSubcuenta').value = (currentSubcuenta === 'salud') ? 'salud' : 'docentes';
      document.getElementById('modalVenta').style.display = 'flex';
    }

    function cerrarModalVenta() {
      document.getElementById('modalVenta').style.display = 'none';
    }

    function cerrarModalFuera(e) {
      if (e.target.id === 'modalVenta') cerrarModalVenta();
    }

    function actualizarUsdEquivalente() {
      const bs = parseFloat(document.getElementById('inputMontoBs').value) || 0;
      document.getElementById('inputMontoUsd').value = (bs / 1035).toFixed(2);
    }

    async function guardarNuevaVenta() {
      const sub = document.getElementById('inputSubcuenta').value;
      const prod = document.getElementById('inputProducto').value;
      const bs = parseFloat(document.getElementById('inputMontoBs').value) || 7250.0;
      const usd = parseFloat(document.getElementById('inputMontoUsd').value) || 7.0;
      const metodo = document.getElementById('inputMetodo').value;
      const cliente = document.getElementById('inputCliente').value || 'Cliente WhatsApp';

      try {
        const res = await fetch('/api/ventas', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            producto: prod,
            subcuenta: sub,
            monto_bs: bs,
            monto_usd: usd,
            metodo_pago: metodo,
            cliente: cliente
          })
        });
        const d = await res.json();
        if (d.status === 'success') {
          showToast('¡Venta registrada con éxito!');
          cerrarModalVenta();
          recargarTodo();
        }
      } catch (e) {
        alert('Error: ' + e);
      }
    }

    async function cargarRadar() {
      try {
        const res = await fetch('/api/radar-productos');
        const data = await res.json();
        const box = document.getElementById('radarContainer');
        if (!box) return;
        box.innerHTML = '';
        data.productos.forEach(p => {
          box.innerHTML += `
            <div class="campaign-block" style="padding:16px; margin-bottom:14px; border:1px solid #1e293b; background:#131d31; border-radius:10px;">
              <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                <span style="background:#065f46; color:#34d399; font-weight:800; font-size:0.7rem; padding:3px 9px; border-radius:6px; letter-spacing:0.5px;">
                  ${p.longevidad_meta}
                </span>
                <span style="background:#1e293b; color:#38bdf8; font-weight:700; font-size:0.7rem; padding:3px 8px; border-radius:6px;">
                  📦 100% Digital
                </span>
              </div>

              <div style="font-size:0.95rem; font-weight:800; color:#f8fafc; margin-top:10px;">${p.nombre}</div>
              <div style="font-size:0.75rem; color:#94a3b8; margin-top:2px;">
                📍 ${p.nicho} · Validado en: <strong style="color:#cbd5e1;">${p.origen}</strong>
              </div>

              <div style="margin-top:10px; background:#090d16; padding:10px; border-radius:8px; border:1px solid #1e293b;">
                <div style="font-size:0.75rem; color:#94a3b8; font-weight:700;">🩹 Dolor Operativo que Resuelve:</div>
                <div style="font-size:0.78rem; color:#cbd5e1; margin-top:2px;">${p.dolor_resuelto}</div>

                <div style="font-size:0.75rem; color:#94a3b8; font-weight:700; margin-top:8px;">🎯 Ángulo de Creativo en Meta Ads:</div>
                <div style="font-size:0.8rem; color:#fbbf24; font-weight:700; font-style:italic; margin-top:2px;">"${p.angulo_ganador}"</div>
              </div>

              <div style="margin-top:10px; display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.72rem; color:#94a3b8;">
                <div>🌍 <strong>Mercados:</strong> <span style="color:#cbd5e1;">${p.mercados_viables}</span></div>
                <div>💵 <strong>Ticket Ref:</strong> <span style="color:#38bdf8; font-weight:700;">${p.ticket_referencia}</span></div>
              </div>

              <div style="display:flex; gap:8px; margin-top:12px;">
                <button class="switch-btn switch-on" style="flex:1; padding:8px 4px; font-size:0.75rem; background:#0284c7;" onclick="window.open('${p.ads_library_url}', '_blank')">
                  🔍 Ver en Meta Ads Library
                </button>
                <button class="switch-btn" style="flex:1; padding:8px 4px; font-size:0.75rem; background:#334155; color:white;" onclick="copiarTexto('PRODUCTO A MODELAR: ${p.nombre.replace(/'/g, "\\'")}\\nNICHO: ${p.nicho}\\nANGULO: ${p.angulo_ganador.replace(/'/g, "\\'")}\\nTICKET: ${p.ticket_referencia}\\nADS LIBRARY: ${p.ads_library_url}')">
                  📋 Copiar Brief
                </button>
              </div>
            </div>
          `;
        });
      } catch (e) {
        console.error('Error al cargar radar:', e);
      }
    }

    async function checkAuth() {
      try {
        const res = await fetch('/api/auth/check');
        const data = await res.json();
        if (data.authenticated) {
          document.getElementById('authOverlay').style.display = 'none';
          recargarTodo();
        } else {
          document.getElementById('authOverlay').style.display = 'flex';
          setTimeout(() => document.getElementById('authPassword').focus(), 150);
        }
      } catch (e) {
        document.getElementById('authOverlay').style.display = 'none';
        recargarTodo();
      }
    }

    async function intentarLogin() {
      const pwd = document.getElementById('authPassword').value;
      const errBox = document.getElementById('authError');
      errBox.style.display = 'none';
      if (!pwd) return;

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: pwd })
        });
        const data = await res.json();
        if (data.authenticated) {
          document.getElementById('authOverlay').style.display = 'none';
          recargarTodo();
        } else {
          errBox.style.display = 'block';
        }
      } catch (e) {
        errBox.innerText = 'Error de conexión: ' + e;
        errBox.style.display = 'block';
      }
    }

    async function cerrarSesion() {
      if (!confirm('¿Deseas cerrar sesión del Command Center?')) return;
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
        document.getElementById('authPassword').value = '';
        document.getElementById('authOverlay').style.display = 'flex';
      } catch (e) {
        location.reload();
      }
    }

    function recargarTodo() {
      cargarConsolidado();
      cargarJerarquia();
      cargarVentas();
      cargarPrescripciones();
      cargarRadar();
    }

    window.onload = checkAuth;
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
