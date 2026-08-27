# Instrumento experimental CPS

Plataforma para el estudio de la **resolución colaborativa de problemas con
partición de información**. Cada instancia del banco reparte entre dos
participantes datos complementarios tales que ninguno alcanza la solución por
separado, y la misma instancia se resuelve en dos modalidades comparables:

| Modalidad | Quiénes dialogan |
|---|---|
| `agente_agente` | Dos agentes artificiales, cada uno con un dato privado. |
| `agente_estudiante` | Un agente artificial y un estudiante, cada uno con un dato privado. |

Esto no es un producto educativo sino un instrumento de medición: lo que se
optimiza es la validez de los datos que produce, no la experiencia de uso.

---

## Puesta en marcha

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # completar CLAVE_SECRETA y, si hay, ANTHROPIC_API_KEY
alembic upgrade head          # crear el esquema
cps banco validar             # revisar el banco antes de publicarlo
cps banco sembrar --forzar    # ver la nota sobre --forzar más abajo
uvicorn cps.api.app:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

API en `http://localhost:8000` con documentación en `/docs`; interfaz en
`http://localhost:5173`.

Sin `ANTHROPIC_API_KEY` el sistema arranca igual y los modelos responden en modo
simulado. Sirve para desarrollar y para probar el circuito completo, pero los
episodios quedan marcados con `simulado=true` y se excluyen de la exportación:
no son dato experimental.

---

## Qué mide

Los indicadores se separan en dos perfiles, y la distinción es conceptual y no
organizativa.

### Perfil de diseño `Φ` — propiedad de la instancia

Depende sólo de la instancia y del solver de referencia, así que es **idéntico
bajo ambas modalidades**. Es la base común que hace que compararlas signifique
algo.

Todo se apoya en la *función de competencia*, estimada empíricamente:

```
v(S) = Pr[ solver_de_referencia(enunciado ∪ S) = respuesta_canónica ]
```

sobre las cuatro celdas de información `S ∈ {∅, {a}, {b}, {a,b}}`, con `N`
ejecuciones independientes por celda.

| Indicador | Definición | Qué responde |
|---|---|---|
| `IE` | `1 − maxᵢ[v({dᵢ}) − v(∅)] / Δ`, con `Δ = v(D) − v(∅)` | ¿Cuánta de la ganancia alcanzable no logra ningún dato por separado? |
| `IBC` | `1 − \|v({a}) − v({b})\| / Δ` | ¿Aportan lo mismo ambos datos, o uno es un validador pasivo? |
| `MEE` | fracción de pasos del DAG inalcanzables desde una sola parte | ¿Cuánto razonamiento sólo existe como deducción conjunta? |
| `t_min` | máximo de alternancias de lado en el DAG de solución | ¿Cuántos intercambios exige como mínimo la estructura? |
| dificultad | `1 − v(D)` | ¿Cuánto falla el solver aun teniendo ambos datos? |

Dos decisiones de diseño que conviene explicitar:

- **La normalización por `Δ` no es cosmética.** Sin ella, una instancia que nadie
  resuelve ni con ambos datos alcanzaría el máximo de interdependencia sin ser
  colaborativa: sería sólo imposible. Dividir por la ganancia alcanzable separa
  *dificultad* de *interdependencia* y deja la primera como indicador aparte.
- **`IBC` no usa entropía.** Para dos jugadores, la diferencia de valores de
  Shapley del juego `(D, v)` colapsa a `v({a}) − v({b})`, de modo que el índice
  se calcula con las mismas cuatro proporciones que `IE`, sin experimento
  adicional. Está demostrado y cubierto por tests de propiedad.

### Perfil de episodio `Ψ` — propiedad de la observación

Sí depende de la modalidad, y es lo que se compara.

| Indicador | Qué es |
|---|---|
| `CQI` | Calidad del proceso: doce celdas ordinales codificadas por modelos jueces. |
| corrección | Verificada simbólicamente contra la clave canónica. |
| eficiencia | `t_min / t_observado`. |
| divulgación | Turno en que cada dato privado quedó recuperable del transcript. |

---

## Decisiones que sostienen la validez

**La corrección nunca se autodeclara.** La versión anterior marcaba una sesión
como resuelta cuando aparecía el token `[RESUELTO]` en un mensaje; en el modo con
estudiante, ese mensaje lo escribe el propio participante. La variable
dependiente principal era falseable por el sujeto medido. Ahora la respuesta se
envía por un endpoint aparte y se compara por equivalencia simbólica contra una
clave registrada con la instancia: `1/2`, `0.5` y `\frac{1}{2}` son la misma
respuesta, y escribir `[RESUELTO]` no vuelve correcta ninguna.

**La divulgación prematura se mide, no se prohíbe.** Restringir por prompt que se
vuelque el dato en el primer turno sustituiría el fenómeno de interés —la
conducta comunicativa espontánea— por otro: la obediencia a la restricción. La
restricción existe como **condición experimental cruzada**, y el turno de
divulgación es una variable dependiente.

**El rol se contrabalancea.** En `agente_agente` ambos roles son artificiales. Si
en `agente_estudiante` el humano ocupara siempre el mismo lado, la comparación
entre modalidades quedaría confundida con el efecto del rol. La asignación de
`dato_a` o `dato_b` se balancea y queda registrada.

**Los jueces son ciegos, y esa ceguera se verifica.** Los transcripts se
presentan con roles neutros y normalización estilística. Además se le pregunta al
juez qué modalidad cree haber visto: si acierta por encima del azar, la ceguera
falló y hay que reportarlo en lugar de suponerla. El endpoint
`/api/investigacion/desenmascaramiento` expone esa tasa.

**Todo es reproducible o no cuenta.** Cada episodio y cada medición guardan una
*huella experimental*: el hash de los parámetros que pueden alterar un resultado
—modelos, esfuerzos, ensayos por celda, semilla—. Dos corridas con huellas
distintas no son comparables, y el sistema lo hace explícito en lugar de dejar
que haya que deducirlo. Las instancias se versionan por hash de contenido: editar
un enunciado publica una versión nueva en vez de invalidar mediciones en
silencio.

---

## El banco

Las instancias viven en `datos/instancias/*.yaml`, una por archivo. Son datos y
no código: se revisan en un diff, se validan contra un esquema y se citan por su
hash.

Cada archivo declara enunciado público, los dos datos privados, la respuesta
canónica, la resolución en LaTeX y el **DAG anotado** de la resolución, donde
cada paso indica de qué dato privado depende. De ese grafo salen `MEE` y `t_min`.

```bash
cps banco validar    # sin tocar la base
cps banco sembrar    # publica, versionando por contenido
```

### Sobre `--forzar`, y el primer hallazgo del instrumento

`cps banco sembrar` se niega a publicar instancias con advertencias de diseño. Al
migrar el banco heredado, las ocho instancias originales quedaron marcadas:

```
t_min = 1 en las 8 → se resuelven con un único intercambio
```

Es decir que cada parte enuncia su dato y cualquiera de las dos cierra. Son,
en los términos del propio README anterior, *problemas comunes partidos en dos*.
Que el instrumento lo detecte solo es la primera evidencia de que mide algo.

La instancia `cdi-cadena-encadenada` se agregó como referencia de lo que el
criterio exige: alcanza `t_min = 2` porque una parte no puede saber **qué**
evaluar hasta que la otra le pase un valor intermedio, y ésa no puede cerrar
hasta recibir la evaluación de vuelta. Sirve de patrón para las instancias que
falte escribir.

Mientras el banco conserve las ocho heredadas hay que sembrar con `--forzar`.

---

## Línea de comandos

El protocolo experimental vive acá y no en la interfaz. Calibrar una instancia
son 120 llamadas al modelo con la configuración por defecto: es un procedimiento
que se corre de forma deliberada, se registra y se puede repetir, no la acción de
un botón.

```
cps estado                 Configuración vigente y huella experimental
cps banco validar          Valida los archivos sin tocar la base
cps banco sembrar          Publica el banco, versionando por contenido
cps calibrar               Estima v(S) por celda y computa el perfil de diseño
cps codificar              Codifica transcripts con los modelos jueces
cps divulgacion            Localiza el turno de divulgación de cada dato
cps exportar               Vuelca los episodios a JSON por líneas
cps cuenta promover        Otorga rol de investigador
cps purgar-retirados       Borra episodios de quienes retiraron el consentimiento
```

### Dimensionamiento

`cps calibrar` usa 30 ensayos por celda por defecto. El número sale de la cota
exacta con cero eventos: si ninguna de `N` ejecuciones acierta, la cota superior
unilateral al 95 % es `1 − 0.05^(1/N)`.

| `N` | Certifica |
|---|---|
| 30 | `v ≲ 0.095` |
| 60 | `v ≲ 0.049` |

---

## Estructura

```
src/cps/
  dominio/        Funciones puras: indicadores, DAG, rúbrica, equivalencia,
                  verificación simbólica. No importa FastAPI ni SQLAlchemy.
  modelos/        Esquema relacional
  agentes/        Motor de modelos, protocolo versionado, solver, jueces
  servicios/      Banco, episodios, aleatorización
  api/            FastAPI: rutas, esquemas, seguridad
  cli/            Protocolo experimental
datos/instancias/ El banco, en YAML
migraciones/      Alembic
tests/            182 tests
paper/            Marco teórico
```

La capa `dominio/` no depende de nada del resto del sistema. Es deliberado: es lo
que tiene que poder auditarse y replicarse de forma independiente, y por eso
concentra la cobertura de tests.

---

## Consideraciones éticas

Consentimiento informado con versión y hash del texto aceptado, registrado en el
alta. Seudonimización en el momento de la captura: el correo electrónico no
aparece en ninguna exportación. Participación desvinculada de toda calificación.
Se informa a los participantes que su interlocutor es un sistema automático; el
engaño sobre ese punto no forma parte del diseño. El retiro del consentimiento se
registra al pedirlo y el borrado efectivo lo ejecuta el investigador con
`cps purgar-retirados`.

---

## Desarrollo

```bash
pytest                      # 182 tests
pytest -m propiedad         # sólo las propiedades formales del marco
ruff check src tests        # linter
cd frontend && npm run build
```

Los tests marcados `propiedad` verifican enunciados del marco teórico sobre un
espacio de entradas, no casos sueltos: la eficiencia del valor de Shapley, el
colapso de la diferencia a dos proporciones, y la acotación de los índices.

---

## Estado

Instrumentado y verificado de punta a punta en modo simulado. Lo que falta antes
de recolectar:

1. **Escribir instancias con `t_min ≥ 2`.** Es el cuello de botella real: el
   banco heredado no sirve para el estudio tal como está.
2. **Calibrar con credencial de modelo.** Sin `ANTHROPIC_API_KEY` no hay perfiles
   de diseño reales.
3. **Codificación humana de una submuestra**, para estimar el acuerdo con los
   jueces automáticos. Sin ese número, el `CQI` automático no tiene claim de
   validez.
4. **Aprobación del comité de ética** antes de trabajar con estudiantes.
