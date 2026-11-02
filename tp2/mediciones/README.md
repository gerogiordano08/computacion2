# Cómo ejecutar las mediciones

Ejecutar desde la carpeta `tp2`, con Python 3.11+ y las dependencias de
`requirements.txt` instaladas. Los scripts muestran resultados en la terminal
y guardan las muestras y las condiciones en `mediciones/resultados/`.

```bash
python -m mediciones.concurrencia_io
python -m mediciones.bloqueo_loop
python -m mediciones.techo_pool
```

El tercer script requiere la API encendida y sin otros trabajos activos.
Los dos primeros crean sus propios servidores temporales.

## Ejecutar usando Docker

Para usar las dependencias del contenedor, sin instalar Python en el host,
se puede montar esta carpeta en un contenedor temporal. El usuario del host
permite guardar los resultados en la carpeta montada:

```bash
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD/mediciones:/app/mediciones" \
  api python -m mediciones.concurrencia_io

docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD/mediciones:/app/mediciones" \
  api python -m mediciones.bloqueo_loop

docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  -v "$PWD/mediciones:/app/mediciones" \
  api python -m mediciones.techo_pool --base-url http://api:8000
```

Estos comandos son para macOS/Linux. Para el último, primero levantar la API
con `docker compose up -d --build`. Los contenedores de medición se eliminan
al terminar; los resultados permanecen en el host.

## Qué mide cada script

- `concurrencia_io.py`: por defecto, 20 peticiones HTTP reales con demora de
  0,2 segundos, tres repeticiones por modo y speedup entre medianas. Compara
  la función `descargar` del proyecto: una llamada por URL con un `for` y
  `await` para el modo secuencial, y una llamada con las 20 URLs para el
  concurrente. Incluye la creación de un cliente por llamada, tal como está
  implementada la función. No incluye endpoints, cola o workers.
  El servidor local evita que Internet cambie las condiciones. Para usar una
  dirección externa: `--url https://example.com`; se puede repetir `--url`.
- `bloqueo_loop.py`: levanta dos APIs aisladas con los endpoints del proyecto.
  Una ejecuta deliberadamente el hash en el event loop; la otra usa el executor
  del gestor. El GET se envía después de una marca de inicio escrita desde el
  cálculo. Verifica que efectivamente coincidieron y que los hashes finales
  sean iguales. El pool se calienta antes de medir. La variante bloqueante
  existe solo en el script; no modifica `src/` ni la API principal.
- `techo_pool.py`: envía lotes de 1, 2, 4, 8, 16 y 32 tareas a la API. Registra
  throughput de tareas completadas, latencia total media y p95, errores y
  tiempos de cola y ejecución. Usa hashes de 1.000.000 de iteraciones por
  defecto, manteniendo ese trabajo fijo al aumentar la carga. En paralelo
  sondea `GET /tareas` con una conexión separada y compara su latencia con una
  referencia sin carga. Para una prueba adicional del límite de workers con
  I/O simulado, ejecutar con `--tipo esperar` y otra ruta de `--salida`.

En el tercer script, el tiempo cliente incluye las consultas periódicas de
estado (por defecto cada 0,02 segundos). Los tiempos de cola y ejecución se
calculan usando las fechas del servidor. Con hashes, el tiempo de ejecución
incluye también la espera de un proceso libre del executor.
El sondeo de `GET /tareas` corre cada 0,1 segundos, más el tiempo de respuesta.
El JSON registra las muestras, errores HTTP y tareas del lote aún activas al
responder. Son peticiones enviadas durante el seguimiento del lote; la última
puede responder cuando ya terminaron sus cálculos. El generador y las consultas
también consumen recursos: se mantienen sus intervalos fijos entre cargas.

## Ajustar y registrar las condiciones

Todos aceptan `--help`, `--repeticiones` y `--salida`. Ejemplos:

```bash
python -m mediciones.bloqueo_loop --iteraciones 10000000 --repeticiones 5
python -m mediciones.techo_pool --cargas 1 4 8 16 32 64
```

Si el hash termina antes de enviar el GET, el script avisa y pide aumentar las
iteraciones: esa muestra no sirve para demostrar el bloqueo.

Anotar en el README principal los recursos asignados a Docker, los workers y
procesos de CPU, parámetros y ubicación del generador. El JSON registra las
versiones, CPU visibles y, si existen, límites de cgroup. No ejecutar otras
cargas mientras se mide ni interpretar fallos rápidos como buen rendimiento.

El script no declara automáticamente un punto de saturación. Comparar cuándo
el throughput deja de aumentar, mientras crecen la cola o la latencia, y si la
API conserva tiempos de respuesta bajos. Si los niveles probados no muestran
un techo, ampliar las cargas; no inventar un límite. Para reducir el efecto del
historial acumulado sobre `GET /tareas`, comenzar con la API recién iniciada y
sin otros trabajos. El historial inicial y los parámetros se guardan en el JSON.

Los JSON no reemplazan el informe: pasar las tablas, números e interpretación
al `README.md` principal. Los scripts no escriben conclusiones personales.
