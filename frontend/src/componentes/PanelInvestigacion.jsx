import { useEffect, useState } from 'react';
import api, { mensajeDeError, MODALIDADES } from '../api';

/**
 * Panel de investigación: estado del banco, mediciones y control de ceguera.
 *
 * No permite correr calibraciones ni codificaciones. Esos procedimientos son
 * cientos de llamadas a modelos y se ejecutan desde la línea de comandos, donde
 * quedan registrados y se pueden repetir. Un botón que dispara un experimento es
 * justamente lo que no conviene tener.
 */
export default function PanelInvestigacion() {
  const [banco, setBanco] = useState(null);
  const [mediciones, setMediciones] = useState([]);
  const [ceguera, setCeguera] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([
      api.get('/api/investigacion/banco'),
      api.get('/api/investigacion/mediciones'),
      api.get('/api/investigacion/desenmascaramiento'),
    ])
      .then(([b, m, d]) => {
        setBanco(b.data);
        setMediciones(m.data);
        setCeguera(d.data);
      })
      .catch((e) => setError(mensajeDeError(e)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!banco) return <p className="cargando">Cargando estado del banco…</p>;

  const codificadores = Object.entries(ceguera?.por_codificador ?? {});

  return (
    <div className="panel-investigacion">
      <header className="cabecera-perfil">
        <div>
          <h1>Investigación</h1>
          <p className="metadatos">
            huella experimental vigente <code>{banco.huella_experimental}</code>
          </p>
        </div>
      </header>

      <section className="metricas">
        <div className="metrica">
          <strong>{banco.total_instancias}</strong>
          <span>instancias activas</span>
        </div>
        <div className="metrica">
          <strong>{banco.calibradas}</strong>
          <span>calibradas</span>
        </div>
        <div className={`metrica ${banco.sin_calibrar > 0 ? 'alerta' : ''}`}>
          <strong>{banco.sin_calibrar}</strong>
          <span>sin calibrar</span>
        </div>
        <div className="metrica">
          <strong>{banco.cumplen_criterio}</strong>
          <span>cumplen el criterio</span>
        </div>
        <div className={`metrica ${banco.con_advertencias > 0 ? 'alerta' : ''}`}>
          <strong>{banco.con_advertencias}</strong>
          <span>con advertencias</span>
        </div>
        <div className="metrica secundaria">
          <strong>{banco.episodios_simulados}</strong>
          <span>episodios simulados</span>
        </div>
      </section>

      <section className="bloque">
        <h2>Episodios por modalidad</h2>
        {Object.keys(banco.episodios_por_modalidad).length === 0 ? (
          <p className="vacio">Todavía no hay episodios registrados.</p>
        ) : (
          <ul className="lista-simple">
            {Object.entries(banco.episodios_por_modalidad).map(([modalidad, cantidad]) => (
              <li key={modalidad}>
                <span>{MODALIDADES[modalidad] || modalidad}</span>
                <strong>{cantidad}</strong>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="bloque">
        <h2>Control de ceguera de los jueces</h2>
        <p className="ayuda">
          Con dos modalidades el azar da 0.50. Una tasa sustancialmente mayor indica que la
          ceguera falló y que los puntajes pueden estar contaminados por el conocimiento de
          la condición.
        </p>
        {codificadores.length === 0 ? (
          <p className="vacio">Todavía no hay codificaciones automáticas.</p>
        ) : (
          <ul className="lista-simple">
            {codificadores.map(([codificador, datos]) => (
              <li key={codificador}>
                <span>
                  <code>{codificador}</code>{' '}
                  <span className="tenue">n = {datos.n_con_respuesta}</span>
                </span>
                <strong className={datos.tasa_acierto > 0.65 ? 'alerta' : ''}>
                  {datos.tasa_acierto.toFixed(2)}
                </strong>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="bloque">
        <h2>Mediciones de diseño</h2>
        {mediciones.length === 0 ? (
          <p className="vacio">
            Todavía no hay ninguna instancia calibrada. Corré <code>cps calibrar</code>.
          </p>
        ) : (
          <div className="tabla-scroll">
            <table className="tabla-mediciones">
              <thead>
                <tr>
                  <th>Instancia</th>
                  <th title="Competencia sin ningún dato privado">v(∅)</th>
                  <th title="Competencia sólo con el dato A">v(A)</th>
                  <th title="Competencia sólo con el dato B">v(B)</th>
                  <th title="Competencia con ambos datos">v(AB)</th>
                  <th title="Interdependencia epistémica">IE</th>
                  <th title="Balance de carga informativa">IBC</th>
                  <th title="Emergencia epistémica">MEE</th>
                  <th title="Cota inferior de rondas">t mín</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {mediciones.map((m) => (
                  <tr key={`${m.instancia_id}-${m.huella_experimental}`}>
                    <td>
                      <code>{m.codigo}</code>
                      {!m.contenido_vigente && (
                        <span className="marca-simulado" title="Medida sobre otra versión del contenido">
                          desactualizada
                        </span>
                      )}
                    </td>
                    <td className="numero">{m.competencia.vacia.toFixed(2)}</td>
                    <td className="numero">{m.competencia.solo_a.toFixed(2)}</td>
                    <td className="numero">{m.competencia.solo_b.toFixed(2)}</td>
                    <td className="numero">{m.competencia.ambos.toFixed(2)}</td>
                    <td className="numero destacado">{m.perfil.interdependencia.toFixed(2)}</td>
                    <td className="numero">{m.perfil.balance_carga.toFixed(2)}</td>
                    <td className="numero">{m.perfil.emergencia.toFixed(2)}</td>
                    <td className={`numero ${m.perfil.rondas_minimas < 2 ? 'alerta' : ''}`}>
                      {m.perfil.rondas_minimas}
                    </td>
                    <td>
                      {m.advertencias.length > 0 ? (
                        <span className="insignia no-cumple" title={m.advertencias.join('\n')}>
                          {m.advertencias.length} advertencia(s)
                        </span>
                      ) : (
                        <span className="insignia cumple">sin advertencias</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bloque">
        <h2>Exportación</h2>
        <p className="ayuda">
          Una línea JSON por episodio, seudonimizada. Los episodios simulados y las
          consultas de resolución quedan excluidos.
        </p>
        <p>
          Desde la línea de comandos: <code>cps exportar</code>. Vía API:{' '}
          <code>GET /api/investigacion/exportacion.jsonl</code>
        </p>
      </section>
    </div>
  );
}
