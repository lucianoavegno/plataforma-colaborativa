import { useEffect, useState } from 'react';
import api, { mensajeDeError, MODALIDADES, ESTADOS, VEREDICTOS } from '../api';
import { useAuth } from '../contexto-auth';

function fecha(iso) {
  if (!iso) return '—';
  // Las marcas vienen en UTC con zona explícita, así que el navegador las
  // convierte bien a la hora local sin que haya que corregir nada acá.
  return new Date(iso).toLocaleString('es-AR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function MisEpisodios({ onAbrirInstancia }) {
  const { cuenta } = useAuth();
  const [episodios, setEpisodios] = useState(null);
  const [error, setError] = useState('');
  const [retirando, setRetirando] = useState(false);

  useEffect(() => {
    api
      .get('/api/episodios')
      .then((r) => setEpisodios(r.data))
      .catch((e) => setError(mensajeDeError(e)));
  }, []);

  async function retirarConsentimiento() {
    if (!window.confirm('¿Retirar el consentimiento? No vas a poder abrir episodios nuevos.')) {
      return;
    }
    setRetirando(true);
    try {
      await api.post('/api/auth/retirar-consentimiento');
      window.alert(
        'Consentimiento retirado. Pedile al equipo de investigación el borrado de tus episodios.',
      );
    } catch (e) {
      setError(mensajeDeError(e));
    } finally {
      setRetirando(false);
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!episodios) return <p className="cargando">Cargando episodios…</p>;

  const deEstudio = episodios.filter((e) => e.modalidad !== 'resolucion_directa');
  const resueltos = deEstudio.filter((e) => e.acerto === true).length;
  const consultas = episodios.length - deEstudio.length;

  return (
    <div className="perfil">
      <header className="cabecera-perfil">
        <div className="avatar">{cuenta.nombre.slice(0, 1).toUpperCase()}</div>
        <div>
          <h1>{cuenta.nombre}</h1>
          <p className="metadatos">
            seudónimo <code>{cuenta.seudonimo}</code> · desde {fecha(cuenta.creada_en)}
          </p>
        </div>
      </header>

      <section className="metricas">
        <div className="metrica">
          <strong>{deEstudio.length}</strong>
          <span>episodios de estudio</span>
        </div>
        <div className="metrica">
          <strong>{resueltos}</strong>
          <span>con respuesta correcta</span>
        </div>
        <div className="metrica">
          <strong>{new Set(deEstudio.map((e) => e.instancia_id)).size}</strong>
          <span>instancias distintas</span>
        </div>
        <div className="metrica secundaria">
          <strong>{consultas}</strong>
          <span>resoluciones consultadas</span>
        </div>
      </section>

      <section className="bloque">
        <h2>Historial</h2>
        {episodios.length === 0 && <p className="vacio">Todavía no abriste ningún episodio.</p>}
        {episodios.length > 0 && (
          <div className="tabla-scroll">
            <table className="tabla-episodios">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Instancia</th>
                  <th>Área</th>
                  <th>Modalidad</th>
                  <th>Condición</th>
                  <th>Lado</th>
                  <th>Turnos</th>
                  <th>Estado</th>
                  <th>Veredicto</th>
                  <th>Fecha</th>
                </tr>
              </thead>
              <tbody>
                {episodios.map((e) => (
                  <tr key={e.id} onClick={() => onAbrirInstancia(e.instancia_id)}>
                    <td className="tenue">{e.id}</td>
                    <td>
                      {e.instancia_titulo}
                      {e.simulado && <span className="marca-simulado">simulado</span>}
                    </td>
                    <td className="tenue">{e.area_nombre}</td>
                    <td>{MODALIDADES[e.modalidad] || e.modalidad}</td>
                    <td className="tenue">
                      {e.modalidad === 'resolucion_directa' ? '—' : e.condicion_divulgacion}
                    </td>
                    <td className="tenue">{e.lado_humano ? e.lado_humano.toUpperCase() : '—'}</td>
                    <td>{e.turnos_usados}</td>
                    <td>
                      <span className={`estado ${e.estado}`}>{ESTADOS[e.estado] || e.estado}</span>
                    </td>
                    <td>
                      {e.veredicto ? (
                        <span className={`veredicto ${e.veredicto}`}>
                          {VEREDICTOS[e.veredicto] || e.veredicto}
                        </span>
                      ) : (
                        <span className="tenue">—</span>
                      )}
                    </td>
                    <td className="tenue">{fecha(e.iniciado_en)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bloque zona-consentimiento">
        <h2>Tu consentimiento</h2>
        <p>
          Podés retirarlo cuando quieras. Al hacerlo dejás de poder abrir episodios nuevos y
          podés solicitar el borrado de los ya registrados.
        </p>
        <button className="boton-terciario" onClick={retirarConsentimiento} disabled={retirando}>
          {retirando ? 'Procesando…' : 'Retirar consentimiento'}
        </button>
      </section>
    </div>
  );
}
