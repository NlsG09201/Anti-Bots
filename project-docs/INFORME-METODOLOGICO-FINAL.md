# Informe metodológico final del Proyecto de Aula

## StreamShield: sistema de apoyo para detectar y analizar actividad automatizada en transmisiones en vivo

**Nelson David Herazo Iglesias**  
**Isaac David Mendoza Lora**  
**Jeremys Enrique Sierra Acuña**  
**Brian Restrepo Rios**

Fundación Universitaria Tecnológico Comfenalco  
Proyecto de Aula — VII semestre de Ingeniería de Sistemas  
20 de noviembre de 2026

### Nota de alcance documental

El repositorio no contiene el primer informe revisado ni las observaciones específicas formuladas por los docentes. Por ello, este documento integra el estado actual del producto y las orientaciones finales disponibles, pero no atribuye al profesorado recomendaciones que no se han proporcionado. La pregunta y los objetivos se redactan aquí como síntesis final coherente con el alcance implementado; deben cotejarse con la formulación aprobada en la primera entrega antes de presentar el archivo institucional.

## Resumen

StreamShield es una aplicación web orientada a ayudar a moderadores y analistas a investigar posibles patrones automatizados o coordinados en canales de streaming. El producto integra una interfaz Next.js/React, una API principal FastAPI, PostgreSQL, Redis y módulos analíticos. El sistema recibe y consulta señales de canales, sesiones, huellas, actividad y ataques; calcula o presenta puntajes de riesgo y permite priorizar sesiones sospechosas para revisión humana. La solución incluye un almacén dimensional en PostgreSQL, réplica tenant-scoped a BigQuery, un proyecto de informe Power BI (PBIP) y un modelo exacto de priorización basado en mochila binaria. También dispone de un asistente SOC que puede usar un modelo OpenAI configurado o responder mediante reglas locales.

El trabajo se presenta como desarrollo aplicado de un artefacto de software, con revisión de la implementación y de sus mecanismos de integración. El repositorio demuestra componentes y rutas concretas, pero no contiene un conjunto autorizado de actividad real ni resultados de evaluación del clasificador que permitan afirmar precisión, reducción de bots, mejora operativa medida o publicación efectiva del informe en Power BI Service. El CSV incluido en la tercera entrega de minería se identifica como sintético y no se utiliza como evidencia empírica en este informe.

**Palabras clave:** ciberseguridad, transmisiones en vivo, detección de actividad automatizada, análisis dimensional, priorización, revisión humana.

## Planteamiento del problema

Los canales de transmisión pueden experimentar aumentos coordinados de espectadores, spam, seguimientos masivos u otras señales compatibles con actividad automatizada. El análisis aislado de una sesión puede ser insuficiente: la cadencia de acceso, la concentración de red o huellas repetidas y el comportamiento colectivo aportan contexto que debe valorarse en conjunto. La literatura sobre spambots también documenta la evolución de estas cuentas y los límites de los detectores basados en señales individuales, lo que respalda tratar los resultados como indicios y mantener revisión humana (Cresci et al., 2017). Ese estudio se refiere a Twitter; su uso aquí es contextual y no valida por sí mismo el detector de StreamShield en plataformas de streaming.

El problema operativo abordado es la dispersión de señales en varias fuentes y la dificultad de priorizar qué sesiones o incidentes debe revisar primero un equipo con tiempo limitado. StreamShield reúne señales y operaciones en una aplicación; Power BI organiza datos históricos para su análisis; y el modelo matemático ordena una cola de revisión bajo restricciones configurables. Un puntaje elevado es una señal para investigar, no prueba concluyente de que una cuenta sea un bot.

### Pregunta orientadora

¿Cómo puede una aplicación web integrar señales operacionales, visualización analítica y priorización matemática para apoyar la investigación y revisión de actividad sospechosa en transmisiones en vivo, manteniendo aislamiento por organización y decisión final humana?

## Objetivos

### Objetivo general

Desarrollar e integrar StreamShield como herramienta de apoyo para registrar, analizar, visualizar y priorizar señales de actividad sospechosa en canales de transmisiones en vivo.

### Objetivos específicos

1. Implementar una aplicación web y una API que gestionen usuarios, canales y señales de seguridad con control de acceso por tenant.
2. Integrar datos operacionales en un almacén dimensional y disponer un modelo Power BI y vistas analíticas dentro de la aplicación.
3. Formular e implementar un modelo de optimización que priorice sesiones sospechosas para revisión humana, sujeto al tiempo disponible y a un presupuesto proxy de exposición.
4. Documentar la arquitectura, los flujos de datos, los mecanismos de validación y los límites de la evidencia del producto.

## Marco conceptual y tecnológico

La solución considera la detección como análisis de señales múltiples y de patrones colectivos; no presume que una sola característica identifique una cuenta maliciosa. La literatura revisada sobre spambots advierte que los comportamientos automatizados evolucionan y que el análisis grupal puede aportar contexto adicional (Cresci et al., 2017). La aplicación transforma eventos operacionales en atributos, puntajes y alertas que requieren interpretación contextual.

El componente analítico organiza medidas y dimensiones en un esquema estrella con granularidades diferenciadas por canal/día, sesión, ataque y actividad de chat. Esta separación busca hacer explícito qué representa cada fila y habilita análisis por fecha, canal, plataforma y streamer, siguiendo los principios del modelado dimensional (Kimball & Ross, 2013).

El módulo de Investigación de Operaciones formula una selección binaria de sesiones elegibles para una cola de revisión. El solucionador implementa programación dinámica exacta para la mochila 0–1, una técnica de optimización por etapas documentada en la literatura clásica de programación dinámica (Bellman, 1957). En este proyecto, el riesgo normalizado se usa como proxy de prioridad y no como probabilidad calibrada.

## Metodología

### Enfoque y tipo de trabajo

El trabajo es aplicado y de desarrollo tecnológico: el resultado principal es un artefacto de software que integra interfaz, API, persistencia y módulos de apoyo a la decisión. Para organizar la evaluación del artefacto, este informe usa como marco de lectura el enfoque de diseño de sistemas de información, que considera la construcción y evaluación de artefactos en relación con un problema y su entorno (Hevner et al., 2004). Esta caracterización metodológica del informe no afirma que el equipo haya ejecutado un protocolo formal de Design Science Research ni una metodología ágil documentada.

La evidencia se obtuvo mediante inspección de la estructura del repositorio, definiciones SQL/TMDL, configuración, rutas de API, componentes de interfaz y código del solucionador. Los documentos fuente consultados se enumeran en las referencias internas y en las referencias APA. No se realizó en este informe una prueba de campo con cuentas de streaming reales ni una evaluación estadística del detector.

### Etapas del trabajo reconstruidas desde los artefactos

1. **Caracterización del problema:** identificar las señales de audiencia, red, huella, chat e incidentes que la aplicación registra y presenta.
2. **Diseño de la solución:** separar presentación, API, servicios de dominio y persistencia; establecer aislamiento tenant-scoped y mantener FastAPI como API principal.
3. **Implementación:** desarrollar rutas y vistas para autenticación, canales, detección, alertas, inteligencia, asistente, analítica y cola de revisión.
4. **Integración analítica:** transformar PostgreSQL operacional al esquema `bi`, replicar a BigQuery cuando está configurado y definir el modelo PBIP y su dashboard web asociado.
5. **Evaluación técnica disponible:** revisar código, contratos, validación de entradas, límites de acceso por tenant y scripts de verificación existentes. El repositorio contiene suites automatizadas y `business-intelligence/scripts/validate_warehouse.py`; este informe no afirma que se hayan ejecutado en el entorno de producción ni reporta resultados que no estén guardados.
6. **Análisis de límites:** separar las capacidades implementadas de aquellas que requieren credenciales externas, datos autorizados, publicación del informe o validación con usuarios.

### Fuentes de información y tratamiento

Las fuentes del sistema son PostgreSQL operacional, eventos de plataformas/webhooks y señales disponibles mediante conectores habilitados. Redis se utiliza para funciones temporales, no como fuente histórica del análisis. El warehouse conserva hechos y dimensiones; el proceso de sincronización crea un dataset BigQuery derivado del tenant autenticado. El flujo no debe incluir claves API, tokens, credenciales Microsoft/Google ni datos personales en los documentos de entrega.

El repositorio contiene `TERCERA-ENTREGA-MINERIA-DATOS.csv`, un conjunto de 30 filas construido con fines demostrativos, con etiqueta `sospechoso_demo`. Sus medias y gráficas reflejan cómo se calcularía un resumen sobre datos fabricados y no son resultados observados. Por ese motivo se excluyen del análisis de resultados de este informe. No se adjunta una exportación anonimizada autorizada de datos reales; no se calculan métricas de precisión, exhaustividad, F1, tasa de falsos positivos ni impacto en moderación.

### Modelo matemático y criterio de decisión

Para cada sesión candidata (i), el solucionador define (x_i \in \{0,1\}), donde 1 indica que la sesión se incluye en la cola. La prioridad proxy se define como (p_i=\operatorname{clip}(risk\_score_i/100,0,1)). El tiempo (t), la capacidad (B), el costo relativo (c\geq0) y el presupuesto de exposición (F) son parámetros ingresados por el analista.

**Función objetivo:**

\[
\max \sum_i \left(p_i-c(1-p_i)\right)x_i
\]

**Restricciones:**

\[
\sum_i t x_i \leq B, \qquad
\sum_i c(1-p_i)x_i \leq F, \qquad
x_i\in\{0,1\}.
\]

La exposición calculada es un proxy de precaución, no una tasa observada de falsos positivos. La puntuación del producto no se ha demostrado calibrada como probabilidad. Cada revisión se modela con tiempo uniforme. El endpoint consulta sesiones activas y sospechosas del tenant autenticado; el solucionador ordena candidatos y no cambia registros ni aplica bloqueos.

## Desarrollo e integración interdisciplinaria

| Asignatura | Componente implementado | Aporte al problema | Evidencia en el repositorio |
| --- | --- | --- | --- |
| Desarrollo Web Avanzado | Next.js/React, FastAPI, PostgreSQL, Redis y servicio Spring complementario | Gestiona acceso, canales, señales, alertas, investigación y módulos de decisión desde el producto web. | `frontend/src/app/`, `backend/app/api/v1/`, `backend/app/services/`, `backend-spring/`; informe técnico en `DESARROLLO-WEB-AVANZADO.md`. |
| Visualización de Datos II | Warehouse PostgreSQL `bi`, ETL, BigQuery tenant-scoped, PBIP y dashboard web Power BI Analytics | Convierte registros en dimensiones/hechos, indicadores y visualizaciones filtrables para explorar riesgo y actividad. | `business-intelligence/sql/`, `business-intelligence/powerbi/`, `backend/app/services/analytics/`, `project-docs/POWERBI-ANALYTICS.md`. |
| Investigación de Operaciones | Modelo binario de priorización con programación dinámica exacta y página de resultados | Distribuye el tiempo de revisión disponible entre sesiones candidatas, con un presupuesto proxy explícito. | `backend/app/services/optimization/review_queue.py`, endpoint `POST /api/v1/operations-research/review-queue/optimize` y `frontend/src/app/dashboard/operations-research/`. |

La integración funcional se produce cuando las señales persistidas y autorizadas pueden consultarse desde la interfaz; los registros consolidados alimentan el warehouse y el dashboard; y las sesiones activas sospechosas alimentan la cola optimizada. Las salidas del modelo apoyan, pero no reemplazan, la decisión de moderación. Los tres componentes están conectados por datos operacionales del proyecto, aunque la publicación cloud de Power BI necesita configuración externa.

## Resultados verificables en el repositorio

1. **Aplicación web y API:** existen rutas de interfaz para SOC, alertas, canales, espectadores, inteligencia, asistente, Power BI y operaciones de investigación, con APIs organizadas por módulos y dependencias de autenticación.
2. **Analítica:** se encuentran los scripts del esquema dimensional y ETL, el servicio de BigQuery con separación por tenant y un PBIP con modelo semántico, relaciones, medidas DAX y páginas **Resumen ejecutivo** y **Amenazas y actividad**. La aplicación incluye una vista analítica y endpoints de sincronización/exportación.
3. **Optimización:** el endpoint obtiene candidatas reales del tenant y las entrega al algoritmo de mochila binaria exacta. Su respuesta incluye cantidad de candidatas/seleccionadas, tiempo consumido, exposición proxy, valor de objetivo y supuestos.
4. **Asistencia de IA:** FastAPI integra el cliente de OpenAI Responses de forma opcional y registra uso; el asistente limita historial/entrada, agrega contexto del tenant y mantiene fallback local. El servicio Spring complementario incorpora Spring AI, y solo se usa desde la interfaz si se configura la URL Java.

Estos son resultados de implementación revisables en el repositorio, no hallazgos de un estudio de campo. No se afirma que todos los módulos externos estén habilitados en producción, que BigQuery o Power BI Service hayan sido publicados en una cuenta particular, ni que el clasificador haya alcanzado una métrica determinada. El nombre del modelo LLM de FastAPI se configura por entorno; el servicio Spring define un modelo predeterminado configurable, pero no se puede inferir de ello qué modelo se usó en una ejecución real.

## Declaración de uso de herramientas de Inteligencia Artificial

### Uso de IA en la elaboración de este informe

Durante la preparación de esta versión se utilizó **OpenAI Codex**, asistente de programación basado en modelos de lenguaje, para organizar los requisitos, localizar evidencia en el repositorio, proponer redacción y revisar coherencia entre la documentación y la implementación. También se usó búsqueda web para verificar datos bibliográficos de las referencias incluidas. La asistencia no sustituyó la decisión académica del equipo ni generó resultados de producción. El contenido se contrastó con código, configuración y documentos existentes; las limitaciones de datos y de despliegue se declaran explícitamente. Los integrantes deben revisar el documento, corregirlo con las observaciones recibidas y aprobar la versión final antes de subirla.

No se dispone de un registro verificable sobre otras herramientas de IA usadas por el equipo para redactar entregas anteriores. Esta declaración cubre la asistencia empleada en esta actualización, sin atribuir usos no confirmados.

### Uso de IA en el producto de software

El producto contiene integraciones funcionales de modelos de lenguaje configurables. La API FastAPI usa el SDK de OpenAI y la API Responses cuando `AI_ENABLED`, la clave y el modelo están configurados; el identificador se suministra mediante `OPENAI_MODEL` y puede variar por entorno. El asistente resume u orienta la investigación con contexto de incidentes/canales autorizado por tenant; limita el historial y tamaño de mensajes, aplica límites de uso y mantiene una respuesta local de respaldo. El servicio Java complementario usa Spring AI con el starter OpenAI; su configuración declara `gpt-4o-mini` como valor predeterminado configurable por `AI_MODEL`, y la integración está desactivada por defecto. El repositorio no acredita qué modelo respondió en una ejecución desplegada.

La aplicación también contiene módulos de clasificación/análisis, entre ellos integración con Weka J48 y scikit-learn. El repositorio contempla entrenamiento e inferencia a partir de fuentes configuradas, pero la muestra CSV sintética no demuestra entrenamiento con datos reales ni desempeño estadístico. No se reportan métricas de modelo porque no se encontró evidencia de una evaluación final con un conjunto etiquetado autorizado.

Las salidas generativas y los puntajes se tratan como apoyo. El asistente no ejecuta bloqueos; la cola matemática no aplica sanciones; las decisiones irreversibles requieren revisión humana. La verificación técnica se apoya en validaciones de entrada, controles de tenant, fallback, registros de uso y pruebas automatizadas presentes en el código. La asistencia de Codex en esta actualización se limitó a inspeccionar el repositorio y preparar documentación; no se utilizó para programar componentes de ejecución. No se declara una tasa de exactitud de IA ni que las pruebas se hayan ejecutado en producción como parte de este informe.

## Limitaciones

- No se incorporaron las observaciones docentes del primer entregable porque no se encontraron en el repositorio ni se proporcionaron en esta conversación.
- No se dispone de datos reales anonimizados ni de una evaluación cuantitativa del detector. El dataset de demostración no se usa como resultado.
- El warehouse y el PBIP están en el repositorio, pero la carga a Google Cloud, la actualización de Power BI Desktop/Service y su publicación requieren cuentas y permisos externos.
- No hay capturas verificables del informe Power BI publicado ni salida de ejecución del optimizador sobre un dataset real adjuntas a este informe.
- Los adaptadores de plataformas y el LLM dependen de claves, permisos, límites y disponibilidad del proveedor.
- El servicio Spring es complementario; FastAPI mantiene la API principal y la mayoría de las capacidades del producto.
- No se presenta evaluación con usuarios, medición de desempeño, ni evidencia de impacto operativo. La eficacia debe validarse posteriormente con protocolo, datos y consentimiento apropiados.

## Conclusiones

StreamShield integra una aplicación web, servicios de datos, artefactos de análisis y una operación matemática para organizar la revisión de actividad sospechosa. La integración interdisciplinaria es visible en los flujos: la aplicación gestiona los registros, la analítica los consolida y muestra, y el solucionador prioriza una cola de revisión humana bajo límites definidos por el analista.

El resultado final verificable es la implementación y documentación de esos componentes, no una demostración estadística de que el producto identifica bots con determinada precisión ni una prueba de que reduce incidentes. La separación por tenant, la transparencia de los supuestos y la revisión humana son condiciones centrales para interpretar sus resultados. Para completar evidencia empírica, el equipo necesita ejecutar el producto con datos autorizados, registrar resultados reproducibles, actualizar Power BI con sus credenciales y conservar capturas/archivos de esa ejecución.

## Referencias

American Psychological Association. (2020). *Publication manual of the American Psychological Association* (7th ed.). https://doi.org/10.1037/0000165-000

Bellman, R. (1957). *Dynamic programming*. Princeton University Press.

Cresci, S., Di Pietro, R., Petrocchi, M., Spognardi, A., & Tesconi, M. (2017). The paradigm-shift of social spambots: Evidence, theories, and tools for the arms race. In *Proceedings of the 26th International Conference on World Wide Web Companion* (pp. 963–972). Association for Computing Machinery. https://doi.org/10.1145/3041021.3055135

Hevner, A. R., March, S. T., Park, J., & Ram, S. (2004). Design science in information systems research. *MIS Quarterly, 28*(1), 75–105. https://doi.org/10.2307/25148625

Kimball, R., & Ross, M. (2013). *The data warehouse toolkit: The definitive guide to dimensional modeling* (3rd ed.). Wiley.

StreamShield. (2026). *Anti-Bots* [Código fuente y documentación del proyecto]. GitHub. https://github.com/NlsG09201/Anti-Bots

## Trazabilidad de evidencias del producto

- Arquitectura y stack: [`DESARROLLO-WEB-AVANZADO.md`](DESARROLLO-WEB-AVANZADO.md).
- Integración y evidencia de analítica: [`POWERBI-ANALYTICS.md`](POWERBI-ANALYTICS.md) y [`business-intelligence/README.md`](../business-intelligence/README.md).
- Formulación y ejecución de la cola: [`ENTREGA-ACADEMICA.md`](ENTREGA-ACADEMICA.md), `backend/app/services/optimization/review_queue.py`.
- Asistente SOC y alcance de IA: [`ENTREGABLES-AGENTE-INTELIGENTE.md`](ENTREGABLES-AGENTE-INTELIGENTE.md), `backend/app/services/assistant/service.py`.
- Clasificación y límites de la muestra de demostración: [`TERCERA-ENTREGA-MINERIA-DATOS.md`](TERCERA-ENTREGA-MINERIA-DATOS.md), [`WEKA-J48.md`](WEKA-J48.md).

## Preparación de entrega en FERRUM

El grupo debe revisar el informe final contra la retroalimentación docente que tenga en sus actas, validar nombres y datos académicos, verificar acceso al repositorio, ejecutar los flujos con credenciales propias, adjuntar capturas y archivos reales y cargar los documentos identificados en el espacio final del Aula Virtual FERRUM. La carga en FERRUM no se realiza desde este repositorio.
