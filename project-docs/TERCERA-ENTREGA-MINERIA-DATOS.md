# Tercera entrega de PA — Minería de datos aplicada a StreamShield

**Actividad:** análisis de datos, identificación de patrones y toma de decisiones aplicadas al proyecto  
**Proyecto:** StreamShield — monitoreo y análisis de amenazas en transmisiones en vivo  
**Equipo:** [completar integrantes] · **Programa/curso:** [completar] · **Fecha:** 7 de noviembre de 2026

> **Alcance de esta evidencia.** El repositorio describe StreamShield y sus variables, pero no incluye una exportación autorizada de sesiones reales para esta entrega. Por eso, el conjunto adjunto de 30 filas es **sintético, construido para demostrar el procedimiento**. No representa usuarios reales, no acredita resultados de producción y no debe usarse para sancionar cuentas. Reemplácese con una extracción anonimizada del tenant del proyecto antes de afirmar hallazgos empíricos.

## 1. Identificación y descripción del proyecto

StreamShield es una plataforma de seguridad para canales de streaming. Reúne eventos y sesiones de espectadores, calcula señales de riesgo y permite a un analista investigar alertas de viewbotting, spam o actividad coordinada. El flujo de análisis es: evento de plataforma/widget → perfil de sesión y señales → transformación a atributos → revisión de patrones y clasificación → alerta y decisión humana. PostgreSQL conserva entidades operacionales; Redis apoya eventos y datos temporales. La disponibilidad de conectores externos depende de sus credenciales y permisos.

El problema analítico abordado es **priorizar sesiones que merecen revisión** cuando un canal recibe una ráfaga de actividad. Una puntuación o predicción es una señal, no una prueba de automatización.

## 2. Variables relacionadas con el proyecto

Las primeras diez son el mínimo solicitado; las restantes reflejan el vector de características documentado por el pipeline de IA y la integración J48. Las razones se expresan como proporciones entre 0 y 1 cuando aplique.

| Variable | Significado y tipo | Uso analítico |
|---|---|---|
| `joins_per_minute` | Entradas por minuto; numérica | Detectar ráfagas anormales de conexión. |
| `viewer_growth_rate` | Tasa de crecimiento de audiencia; numérica | Comparar el crecimiento con el contexto del canal. |
| `follow_velocity` | Seguimientos por intervalo; numérica | Identificar episodios coordinados de followbotting. |
| `chat_message_rate` | Mensajes por minuto; numérica | Distinguir audiencia silenciosa de participación; no es concluyente sola. |
| `silent_viewer_ratio` | Proporción de sesiones sin mensajes; numérica | Señal contextual para revisar junto con otras variables. |
| `proxy_ratio` | Proporción de eventos asociados con proxy; numérica | Medir concentración de infraestructura de red. |
| `vpn_ratio` | Proporción asociada con VPN; numérica | Enriquecer el contexto de red, nunca etiquetar por sí sola. |
| `datacenter_ratio` | Proporción asociada con centro de datos; numérica | Buscar posible automatización o servicios compartidos. |
| `fingerprint_collision_ratio` | Repetición de huellas de navegador; numérica | Detectar grupos de sesiones con huellas coincidentes. |
| `session_duration_avg_sec` | Duración media de sesión en segundos; numérica | Comparar permanencia y actividad de sesiones. |
| `mouse_entropy` | Variabilidad de interacción observada; numérica | Aportar contexto de interacción cuando la señal esté disponible. |
| `connection_sync_score` | Sincronía temporal de conexiones; numérica | Detectar llegadas coordinadas. |
| `historical_risk_avg` | Riesgo histórico agregado (0–100); numérica | Ordenar revisión y contextualizar episodios. |
| `unique_ip_ratio` | Proporción de IP únicas; numérica | Medir diversidad de red. |
| `asn_diversity` | Diversidad normalizada de ASN; numérica | Medir concentración de proveedores/redes. |
| `etiqueta_demo` | Clase didáctica: humano / sospechoso_demo; categórica | Etiqueta artificial para ilustrar análisis; no es ground truth. |

En el backend, varias características se extraen de `viewer_sessions`, `stream_events` y señales agregadas. Para un estudio real deben documentarse ventana temporal, granularidad por sesión/canal, reglas de anonimización y procedencia de cada etiqueta.

## 3. De datos a información

Un registro aislado es un dato: por ejemplo, una tasa de 24 entradas/minuto. Al validar unidades y faltantes, agrupar sesiones por canal e intervalo, calcular proporciones y comparar con el comportamiento habitual, se transforma en información: “en este intervalo hay un crecimiento rápido junto con alta sincronía y concentración de huellas”. Al contrastar varias señales y revisar el contexto operativo, esa información puede sustentar una decisión: abrir una alerta para revisión humana. Se evita inferir “es un bot” a partir de una sola variable.

Preparación recomendada para datos reales: (1) excluir identificadores directos y usar claves seudónimas; (2) normalizar tiempos a una zona horaria y ventana común; (3) revisar faltantes y duplicados; (4) normalizar conteos por duración y tamaño del canal; (5) conservar origen y fecha de extracción; (6) separar datos de entrenamiento y evaluación por canal/periodo para evitar fuga de información.

## 4. Patrones que se buscarían

1. **Ráfaga coordinada:** aumento de `joins_per_minute` y `connection_sync_score`, más crecimiento de audiencia en una ventana corta.
2. **Concentración de huellas/red:** `fingerprint_collision_ratio`, `proxy_ratio` o `datacenter_ratio` elevados junto con baja diversidad de IP/ASN.
3. **Audiencia de baja interacción:** `silent_viewer_ratio` alto combinado con señales temporales o de red. El silencio solo no indica automatización; puede describir espectadores legítimos.

En la muestra sintética, las 15 filas `sospechoso_demo` fueron construidas con valores altos en varias señales de ráfaga y concentración. Por construcción, no es un descubrimiento independiente ni una validación estadística de StreamShield.

## 5. Algoritmo seleccionado: árbol J48

Se propone **J48**, implementación de C4.5 en Weka, porque produce reglas de árbol que el equipo puede explicar a moderadores: una secuencia de condiciones sobre actividad, sincronía y señales de red. El repositorio ya documenta un pipeline J48 que construye características de sesiones/eventos y contempla etiquetas desde veredictos, bots conocidos y señales locales (`project-docs/WEKA-J48.md`).

Flujo propuesto para la entrega: obtener sesiones etiquetadas con fuente y revisión documentadas → preparar características y partición por canal/tiempo → entrenar J48 → medir matriz de confusión, precisión, exhaustividad y F1 en datos no usados para entrenar → inspeccionar reglas y errores → presentar predicciones como alertas para revisión humana. Con solo 30 ejemplos sintéticos no se afirma que el modelo haya sido entrenado ni que tenga precisión válida. Para una evaluación real se necesitan más registros, etiquetas revisadas y validación sin fuga entre canales.

## 6. Conjunto de datos y análisis estadístico

El archivo [`TERCERA-ENTREGA-MINERIA-DATOS.csv`](TERCERA-ENTREGA-MINERIA-DATOS.csv) tiene **30 registros**, 16 características y una etiqueta de demostración. La separación didáctica es 15 `humano` y 15 `sospechoso_demo`. Variables de medición continua, proporciones y la etiqueta permiten explorar el flujo del proyecto; ningún valor describe una cuenta real.

| Clase de demostración | n | Media de entradas/min | Media de riesgo histórico | Media proxy | Media sincronía | Media espectadores silenciosos |
|---|---:|---:|---:|---:|---:|---:|
| humano | 15 | 2,40 | 13,60 | 0,02 | 0,11 | 0,21 |
| sospechoso_demo | 15 | 24,00 | 84,73 | 0,70 | 0,89 | 0,92 |

Las medias se calcularon directamente agrupando las filas del CSV por `etiqueta_demo`. Las diferencias son deliberadas en la construcción de la muestra. No representan asociación observada en producción ni sirven para estimar falsos positivos/negativos. En datos reales se reportarían también mediana, dispersión, distribución por canal/periodo y conteo de faltantes.

### Gráfico 1. Media de entradas por minuto

```text
humano            2,40  ██
sospechoso_demo  24,00  ████████████████████████
```

### Gráfico 2. Medias de señales seleccionadas (0–1)

```text
Señal                       humano     sospechoso_demo
Proxy                         0,02  ▏  0,70  ██████████████
Sincronía                     0,11  ██ 0,89  ██████████████████
Espectadores silenciosos      0,21  ████ 0,92 ██████████████████
```

Ambos gráficos resumen exclusivamente la muestra didáctica y tienen escala lineal; no constituyen evidencia empírica. Para la versión con datos reales, las barras deben regenerarse desde la exportación autorizada y declarar periodo, canales incluidos y tratamiento de faltantes.

## 7. Interpretación y decisiones sustentadas

La muestra ilustra cómo una combinación de velocidad de entradas, sincronía y concentración de red podría priorizar un intervalo para inspección. Una decisión operativa prudente sería abrir una alerta, conservar evidencia temporal y pedir revisión contextual al moderador. Antes de cualquier sanción se deben corroborar señales independientes, verificar si había una campaña legítima o una promoción del canal y permitir corrección de falsos positivos. La decisión se registra con motivo, responsable y resultado para mejorar etiquetas futuras.

No se recomienda bloquear automáticamente a partir de estas medias ni usar la etiqueta sintética en el sistema. Con datos reales, acordar umbrales con el equipo, comparar costos de falsos positivos y falsos negativos y probar el procedimiento en modo observación.

## 8. Conclusiones

- StreamShield reúne variables temporales, de interacción, reputación de red y huellas que permiten investigar actividad coordinada.
- El análisis convierte eventos en señales agregadas y luego en alertas explicables; la validación humana conecta el resultado con una decisión responsable.
- J48 es apropiado para explorar reglas interpretables y ya está contemplado por el proyecto, pero el CSV de esta evidencia solo ilustra el formato y no valida el modelo.
- El paso pendiente para una conclusión real es exportar una muestra anonimizada autorizada, revisar etiquetas y recalcular estadísticas y gráficos sobre datos observados.

## Fuentes y trazabilidad

- `project-docs/GUIA-DEL-PROYECTO.md`: propósito, fuentes y señales de StreamShield.
- `project-docs/WEKA-J48.md`: pipeline, fuentes y características del clasificador J48.
- `backend/app/ai_intel/training/pipeline.py`: variables del pipeline de IA.
- `backend/app/ml/weka_j48/sources.py`: extracción de sesiones/eventos y fuentes de etiqueta.
- `business-intelligence/README.md`: almacén y fuentes operacionales.

**Pendiente del grupo:** completar integrantes y datos del curso; sustituir o complementar la demostración sintética con evidencia real autorizada; regenerar los dos gráficos; revisar la plantilla y exportar un único PDF final con nombre `TERCERA_ENTREGA_PA_StreamShield.pdf`.
