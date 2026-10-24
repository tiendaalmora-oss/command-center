# Command Center Ejecutivo V2.5 · Meta Ads & CRM Venezuela

Panel de control mobile-first y motor analítico diseñado para negocios de productos digitales de bajo ticket en Venezuela.

## Características
- **Cruce P&L Dual (Bs y USD):** Cruce en tiempo real de ventas reales del CRM vs gasto publicitario en Meta Ads.
- **Selector de Subcuentas:**
  - Recursea (Docentes MPPE)
  - Ingenio Digital (Salud & Bóveda Médica)
  - Todo el Negocio (Consolidado Global)
- **Filtros Temporales:** Hoy, Ayer, 48h, 7 Días, 30 Días.
- **Semáforo "El Juez":** Decisiones automáticas para apagar o escalar anuncios.
- **Seguridad:** Acceso protegido mediante clave y sesión encriptada de 60 días.

## Despliegue en Easypanel / Docker
1. Puerto: `8080`
2. Variables de Entorno:
   - `META_ACCESS_TOKEN`: Token de larga duración de Meta Graph API.
   - `PANEL_PASSWORD`: Clave de acceso al panel (por defecto `ingenio2026`).
3. Dominio asignado: `panel.ingeniodigital.shop`.
