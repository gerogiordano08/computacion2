# Monitor Multiproceso de Procesos y Threads en macOS

TP1 de Computacion II para macOS.

## Requisitos

- macOS 26 Tahoe o superior
- Python 3.11 o superior
- Herramientas nativas disponibles en macOS: `ps`, `vm_stat`, `vmmap`, `lsof`
- No requiere paquetes de terceros de Python

## Compatibilidad de macOS

Este proyecto corre directo en macOS, no dentro de Docker.

- Probado en macOS 26 Tahoe
- Versiones anteriores: no documentadas como compatibles

La compatibilidad puede cambiar entre versiones de macOS porque esta app no usa solo Python puro: depende de `libproc`, `sysctl`, APIs Mach/XNU y del formato de salida de herramientas del sistema como `ps`, `vmmap`, `vm_stat` y `lsof`. Si Apple cambia permisos, structs nativos o formatos de salida, el monitor puede seguir funcionando parcialmente pero con datos faltantes en alguna vista.

## Que hace

- Muestra una tabla superior de procesos con PID, PPID, usuario, estado, CPU, RSS, threads y comando.
- Tiene 7 vistas: `Resumen`, `Memoria`, `FDs`, `Threads`, `Senales`, `Scheduling`, `Sistema`.
- Usa un recolector, siete analizadores, un agregador y una TUI `curses`.
- Responde a `SIGINT`, `SIGTERM`, `SIGHUP`, `SIGUSR1` y `SIGUSR2`.

## Arquitectura

La app corre con este pipeline:

`recolector -> analizadores -> agregador -> display`

- El `recolector` enumera PIDs con `proc_listpids()`.
- Cada analizador corre en su propio proceso e informa por una cola de resultados.
- El `agregador` es el unico escritor del snapshot compartido (`Manager().dict()`).
- La TUI corre en el proceso principal y actualiza el PID enfocado para las vistas detalladas.

## Como correrlo

```bash
make install
make run
```

`make run` es el comando unico de arranque recomendado.

Tambien se puede ejecutar sin TUI:

```bash
python3 src/main.py --no-ui --duration 5
```

## Instalacion

```bash
python3 --version
pip install -r requirements.txt
make run
```

`requirements.txt` se conserva aunque no liste dependencias externas para mantener el flujo `pip install -r requirements.txt` y para dejar explicito que el proyecto usa solo la biblioteca estandar.

## Controles

- `1-7` o `r/m/f/t/s/p/g`: cambiar de vista
- `↑` / `↓`: mover seleccion
- `Enter`: pin/unpin del PID
- `/`: filtro por comando
- `u`: filtro por usuario
- `c`: alternar orden `CPU -> RSS -> PID`
- `+` / `-`: cambiar intervalo de la vista activa
- `h` o `?`: ayuda
- `q`: salir limpio

## Señales del monitor

- `SIGINT` / `SIGTERM`: shutdown limpio
- `SIGHUP`: recarga `config.json`
- `SIGUSR1`: escribe `dump_<timestamp>.json`
- `SIGUSR2`: toggle verbose

## Datos por vista

- `Resumen`: `libproc` + `sysctl(KERN_PROCARGS2)` + `proc_pid_rusage`
- `Memoria`: `proc_pidinfo`, `proc_pid_rusage` y `vmmap`
- `FDs`: `lsof -nP -p <pid> -Fpcfnt`
- `Threads`: `proc_pidinfo(PROC_PIDLISTTHREADS / PROC_PIDTHREADINFO)`
- `Senales`: documenta limitaciones de macOS y muestra datos reales del propio monitor
- `Scheduling`: `getpriority`, grupos/sesion, rusage y politica observada en threads
- `Sistema`: `host_statistics`, `host_statistics64`, `sysctl`, `vm_stat`

## Permisos, SIP y alcance real de inspeccion

Esta version corre directo en macOS, asi que los permisos del sistema importan mucho mas que en Linux.

- Procesos del mismo usuario: en general se pueden inspeccionar bastante bien
- Procesos de otros usuarios: pueden verse en la tabla, pero varias vistas detalladas pueden devolver datos parciales o no disponibles
- Procesos de `root` o protegidos por el sistema: suelen quedar limitados por SIP, el hardened runtime y restricciones de `task_for_pid`

En la practica eso significa que el monitor esta pensado para funcionar sin `sudo`, mostrando toda la informacion que macOS permita para cada PID visible y degradando con gracia cuando algo no es accesible.

### Correr con sudo

Si queres intentar ver mas procesos o mejorar la visibilidad sobre procesos ajenos, podes arrancarlo con privilegios:

```bash
sudo -E make run
```

o directamente:

```bash
sudo python3 src/main.py
```

Eso puede mejorar algunas vistas, pero no garantiza acceso total. Incluso con `sudo`, macOS puede seguir ocultando informacion de procesos protegidos por SIP o por el runtime firmado.

### Entitlements y firma del interprete

Segun la consigna del TP, `task_for_pid()` requiere permisos especiales. Un interprete firmado con `com.apple.security.cs.debugger` puede mejorar el acceso a algunos procesos, especialmente del mismo usuario, pero no evita las restricciones de SIP ni garantiza acceso a procesos protegidos o de `root`.

En las pruebas realizadas para este proyecto, el binario utilizado mostraba entitlements de depuracion, incluyendo `com.apple.security.cs.debugger` y `com.apple.security.get-task-allow`. Sin embargo, `codesign` informo que el blob de entitlements era invalido y que macOS podia ignorarlo. Al comparar `task_for_pid` contra otros interpretes, no se observo una mejora efectiva de acceso en los casos probados: las llamadas devolvieron acceso denegado de la misma manera. Por lo tanto, la visibilidad real depende tanto de como este firmado el interprete como del tipo de proceso objetivo.

## Limitaciones reales en macOS

- SIP y el hardened runtime pueden impedir ver datos profundos de procesos protegidos.
- `vmmap`, `lsof` y la inspeccion de threads pueden fallar para algunos PIDs aunque sean visibles.
- macOS no expone de forma portable al userland los handlers y mascaras de senales de otros procesos, a diferencia de Linux con `/proc`.
- No se usa afinidad de CPU porque no esta expuesta de forma util para procesos no privilegiados.
- Algunas vistas dependen de comandos nativos cuyo formato o visibilidad puede cambiar entre versiones de macOS.

## Comparacion con Linux

En Linux la mayoria de esta informacion vive en `/proc`, asi que el modelo pedagogico es "todo es archivo". En macOS eso no existe: la app mezcla llamadas tipo BSD (`sysctl`, `getpriority`, `pwd`) con APIs mas cercanas a XNU (`libproc`, `host_statistics`) y comandos nativos como `vmmap` o `lsof`.

La diferencia mas fuerte aparece en permisos y observabilidad. Linux suele dejar ver mucho mas de procesos externos desde `/proc/<pid>`, mientras que macOS protege mas cosas por SIP y por decisiones del runtime firmado. Eso obliga a manejar faltantes como parte del diseño, no como excepciones raras.

### Que puede no mostrar esta version respecto de Linux

- `Senales`: no expone de forma portable los handlers de otros procesos y la visibilidad de mascaras o senales pendientes ajenas es limitada.
- `Threads`: para procesos protegidos o no accesibles, la lista de threads y sus metricas puede quedar parcial o directamente no disponible.
- `Scheduling`: no muestra afinidad de CPU para procesos no privilegiados y algunas politicas por thread pueden quedar incompletas si falla el acceso Mach.
- `Memoria`: el detalle de regiones, footprint o memoria comprimida puede faltar si `vmmap` o `task_for_pid` no tienen acceso suficiente.
- `FDs`: algunos descriptores pueden no exponer path, tipo o destino completo si macOS restringe la inspeccion del proceso.
- Procesos de `root` o protegidos por el sistema: pueden aparecer en la tabla principal pero con vistas de detalle incompletas o vacias.
- A diferencia de Linux, no existe un equivalente general y abierto a `/proc/<pid>` que garantice el mismo nivel de observabilidad para todos los procesos visibles.


## Estructura

```text
src/
  main.py
  recolector.py
  agregador.py
  macos_api.py
  display.py
  senales.py
  analizadores/
docs/
  architecture.md
  learning-notes.md
tests/
```

## Tests

```bash
make test
```

Los tests cubren parseos y calculos puros. El smoke test multiproceso queda opt-in con `TP1_RUN_SMOKE=1` porque en entornos sandboxed puede fallar el `Manager()` o el acceso a comandos del sistema.
