import { useEffect, useState } from 'react';
import api, { mensajeDeError } from '../api';
import PerfilDiseno from './PerfilDiseno';

/**
 * Banco de instancias.
 *
 * Muestra el perfil de diseño de cada instancia cuando existe. Una instancia sin
 * calibrar no se oculta: se marca como tal, porque no tener medición es
 * información y no una ausencia que convenga disimular.
 */
export default function Catalogo({ onAbrir }) {
  const [areas, setAreas] = useState([]);
  const [instancias, setInstancias] = useState([]);
  const [areaActiva, setAreaActiva] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [minInterdependencia, setMinInterdependencia] = useState(0);
  const [soloCalibradas, setSoloCalibradas] = useState(false);
  const [error, setError] = useState('');
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    api.get('/api/areas').then((r) => setAreas(r.data)).catch((e) => setError(mensajeDeError(e)));
  }, []);

  useEffect(() => {
    const params = {};
    if (areaActiva) params.area = areaActiva;
    if (busqueda.trim()) params.q = busqueda.trim();
    if (minInterdependencia > 0) params.interdependencia_minima = minInterdependencia / 100;
    if (soloCalibradas) params.solo_calibradas = true;

    setCargando(true);
    const id = setTimeout(() => {
      api
        .get('/api/instancias', { params })
        .then((r) => {
          setInstancias(r.data);
          setError('');
        })
        .catch((e) => setError(mensajeDeError(e)))
        .finally(() => setCargando(false));
    }, 200);
    return () => clearTimeout(id);
  }, [areaActiva, busqueda, minInterdependencia, soloCalibradas]);

  const total = areas.reduce((suma, a) => suma + a.cantidad_instancias, 0);

  return (
    <div className="catalogo">
      <aside className="panel-filtros">
        <h2>Áreas</h2>
        <button
          className={`chip-area ${areaActiva === '' ? 'activa' : ''}`}
          onClick={() => setAreaActiva('')}
        >
          Todas <span className="conteo">{total}</span>
        </button>
        {areas.map((a) => (
          <button
            key={a.clave}
            className={`chip-area ${areaActiva === a.clave ? 'activa' : ''}`}
            onClick={() => setAreaActiva(a.clave)}
          >
            {a.nombre} <span className="conteo">{a.cantidad_instancias}</span>
          </button>
        ))}

        <h2 className="separador">Filtros</h2>
        <label className="campo">
          Buscar
          <input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="título o enunciado"
          />
        </label>
        <label className="campo">
          Interdependencia mínima: <strong>{(minInterdependencia / 100).toFixed(2)}</strong>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={minInterdependencia}
            onChange={(e) => setMinInterdependencia(Number(e.target.value))}
          />
        </label>
        <label className="casilla">
          <input
            type="checkbox"
            checked={soloCalibradas}
            onChange={(e) => setSoloCalibradas(e.target.checked)}
          />
          <span>Sólo instancias calibradas</span>
        </label>
      </aside>

      <section className="lista-instancias">
        <header className="encabezado-lista">
          <h2>Instancias</h2>
          <span className="contador">{instancias.length} resultado(s)</span>
        </header>

        {error && <p className="error">{error}</p>}
        {cargando && <p className="cargando">Cargando…</p>}
        {!cargando && instancias.length === 0 && !error && (
          <p className="vacio">No hay instancias que cumplan estos filtros.</p>
        )}

        <div className="grilla">
          {instancias.map((i) => (
            <article key={i.id} className="tarjeta" onClick={() => onAbrir(i.id)}>
              <div className="tarjeta-encabezado">
                <span className="etiqueta-area">{i.area_nombre}</span>
                <code className="codigo-instancia">{i.codigo}</code>
              </div>
              <h3>{i.titulo}</h3>
              <p className="subtema">{i.subtema}</p>
              <PerfilDiseno perfil={i.perfil} compacto />
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
