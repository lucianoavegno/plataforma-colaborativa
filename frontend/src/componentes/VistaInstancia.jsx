import { useEffect, useState } from 'react';
import api, { mensajeDeError } from '../api';
import Mate from './Mate';
import Conversacion from './Conversacion';
import PerfilDiseno from './PerfilDiseno';
import CierreEpisodio from './CierreEpisodio';

const MODALIDADES = [
  {
    clave: 'agente_agente',
    titulo: 'Agente–agente',
    resumen:
      'Dos agentes reciben cada uno un dato distinto y dialogan entre sí. Vos observás el intercambio sin ver ninguno de los dos datos.',
  },
  {
    clave: 'agente_estudiante',
    titulo: 'Agente–estudiante',
    resumen:
      'Recibís uno de los dos datos y el agente se queda con el otro. Tenés que negociar con él para llegar al resultado.',
  },
];

export default function VistaInstancia({ instanciaId, onVolver }) {
  const [instancia, setInstancia] = useState(null);
  const [episodio, setEpisodio] = useState(null);
  const [resolucion, setResolucion] = useState(null);
  const [borrador, setBorrador] = useState('');
  const [turnos, setTurnos] = useState(4);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState('');
  const [confirmandoResolucion, setConfirmandoResolucion] = useState(false);

  useEffect(() => {
    api
      .get(`/api/instancias/${instanciaId}`)
      .then((r) => setInstancia(r.data))
      .catch((e) => setError(mensajeDeError(e)));
  }, [instanciaId]);

  async function abrirEpisodio(modalidad) {
    setError('');
    setOcupado(true);
    try {
      const { data } = await api.post('/api/episodios', {
        instancia_id: instanciaId,
        modalidad,
      });
      setEpisodio(data);
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo abrir el episodio'));
    } finally {
      setOcupado(false);
    }
  }

  async function verResolucion() {
    setError('');
    setOcupado(true);
    try {
      const { data } = await api.get(`/api/instancias/${instanciaId}/resolucion`);
      setResolucion(data);
      setConfirmandoResolucion(false);
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo obtener la resolución'));
    } finally {
      setOcupado(false);
    }
  }

  function reiniciar() {
    setEpisodio(null);
    setResolucion(null);
    setBorrador('');
    setError('');
    setConfirmandoResolucion(false);
  }

  async function correrTanda() {
    setError('');
    setOcupado(true);
    try {
      const { data } = await api.post(`/api/episodios/${episodio.id}/ejecutar`, { turnos });
      setEpisodio(data);
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo correr la tanda'));
    } finally {
      setOcupado(false);
    }
  }

  async function enviarMensaje(evento) {
    evento.preventDefault();
    if (!borrador.trim()) return;
    setError('');
    setOcupado(true);
    const texto = borrador;
    setBorrador('');
    try {
      const { data } = await api.post(`/api/episodios/${episodio.id}/mensajes`, {
        contenido: texto,
      });
      setEpisodio(data);
    } catch (e) {
      setBorrador(texto);
      setError(mensajeDeError(e, 'No se pudo enviar el mensaje'));
    } finally {
      setOcupado(false);
    }
  }

  async function recargarEpisodio() {
    const { data } = await api.get(`/api/episodios/${episodio.id}`);
    setEpisodio(data);
  }

  if (error && !instancia) return <p className="error">{error}</p>;
  if (!instancia) return <p className="cargando">Cargando instancia…</p>;

  const abierto = episodio?.estado === 'en_curso';

  return (
    <div className="vista-instancia">
      <button className="volver" onClick={onVolver}>
        ← Volver al banco
      </button>

      <header className="cabecera-instancia">
        <div className="cabecera-meta">
          <span className="etiqueta-area">{instancia.area_nombre}</span>
          <code className="codigo-instancia">
            {instancia.codigo} · v{instancia.version}
          </code>
        </div>
        <h1>{instancia.titulo}</h1>
        <p className="metadatos">
          {instancia.subtema} · dificultad declarada {instancia.dificultad_declarada}/5
        </p>
      </header>

      <section className="bloque enunciado">
        <h2>Enunciado común</h2>
        <Mate>{instancia.enunciado_publico}</Mate>
      </section>

      <PerfilDiseno perfil={instancia.perfil} />

      {error && <p className="error">{error}</p>}

      {!episodio && !resolucion && (
        <section className="selector-modalidades">
          <h2>Abrir un episodio</h2>
          <p className="ayuda">
            La condición experimental y, si corresponde, el rol se asignan de forma
            aleatorizada y quedan registrados con el episodio.
          </p>
          <div className="modalidades">
            {MODALIDADES.map((m) => (
              <button
                key={m.clave}
                className="tarjeta-modalidad"
                onClick={() => abrirEpisodio(m.clave)}
                disabled={ocupado}
              >
                <h3>{m.titulo}</h3>
                <p>{m.resumen}</p>
              </button>
            ))}
          </div>

          <div className="acceso-resolucion">
            {!confirmandoResolucion ? (
              <button
                className="boton-terciario"
                onClick={() => setConfirmandoResolucion(true)}
                disabled={ocupado}
              >
                Ver la resolución completa
              </button>
            ) : (
              <div className="confirmacion">
                <p>
                  Consultar la resolución queda registrado, y a partir de entonces tus
                  episodios sobre esta instancia dejan de ser válidos para el estudio.
                </p>
                <div className="confirmacion-acciones">
                  <button className="boton-secundario" onClick={() => setConfirmandoResolucion(false)}>
                    Cancelar
                  </button>
                  <button className="boton-principal" onClick={verResolucion} disabled={ocupado}>
                    Entiendo, mostrar
                  </button>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {episodio && (
        <section className="bloque episodio-activo">
          <header className="cabecera-episodio">
            <div>
              <h2>
                {episodio.modalidad === 'agente_agente'
                  ? 'Agente–agente'
                  : 'Agente–estudiante'}
              </h2>
              <p className="condiciones">
                episodio <code>#{episodio.id}</code> · divulgación{' '}
                <strong>{episodio.condicion_divulgacion}</strong>
                {episodio.lado_humano && (
                  <>
                    {' '}· tu dato es el <strong>{episodio.lado_humano.toUpperCase()}</strong>
                  </>
                )}
                {' '}· turnos {episodio.turnos_usados}
              </p>
            </div>
            <button className="boton-secundario" onClick={reiniciar}>
              Cerrar vista
            </button>
          </header>

          {episodio.simulado && (
            <p className="aviso">
              Episodio en modo simulado: no constituye dato experimental.
            </p>
          )}

          {episodio.dato_asignado && (
            <div className="dato-privado">
              <h3>Tu dato privado — el agente no lo conoce</h3>
              <Mate>{episodio.dato_asignado}</Mate>
              <p className="ayuda">
                El agente tiene el otro dato, igual de imprescindible. Escribí en LaTeX con{' '}
                <code>$...$</code> o <code>$$...$$</code>.
              </p>
            </div>
          )}

          <Conversacion
            turnos={episodio.turnos}
            pensando={ocupado}
            ladoHumano={episodio.lado_humano}
          />

          {episodio.modalidad === 'agente_agente' && (
            <div className="controles">
              <label>
                Turnos por tanda
                <select value={turnos} onChange={(e) => setTurnos(Number(e.target.value))}>
                  {[2, 4, 6, 8].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="boton-principal"
                onClick={correrTanda}
                disabled={ocupado || !abierto}
              >
                {ocupado ? 'Dialogando…' : 'Correr tanda'}
              </button>
            </div>
          )}

          {episodio.modalidad === 'agente_estudiante' && (
            <form className="entrada" onSubmit={enviarMensaje}>
              <textarea
                value={borrador}
                onChange={(e) => setBorrador(e.target.value)}
                placeholder="Compartí lo que necesites, planteá una ecuación, pedí lo que te falta…"
                rows={3}
                disabled={ocupado || !abierto}
              />
              <button
                type="submit"
                className="boton-principal"
                disabled={ocupado || !borrador.trim() || !abierto}
              >
                {ocupado ? 'Enviando…' : 'Enviar'}
              </button>
            </form>
          )}

          <CierreEpisodio
            episodio={episodio}
            onCerrado={recargarEpisodio}
            deshabilitado={ocupado}
          />
        </section>
      )}

      {resolucion && (
        <section className="bloque episodio-activo">
          <header className="cabecera-episodio">
            <h2>Resolución completa</h2>
            <button className="boton-secundario" onClick={reiniciar}>
              Cerrar vista
            </button>
          </header>

          <div className="datos-lado-a-lado">
            <div className="dato dato-a">
              <h3>Dato A</h3>
              <Mate>{resolucion.dato_a}</Mate>
            </div>
            <div className="dato dato-b">
              <h3>Dato B</h3>
              <Mate>{resolucion.dato_b}</Mate>
            </div>
          </div>

          <div className="respuesta-canonica">
            <h3>Respuesta canónica</h3>
            <code>{resolucion.respuesta_canonica}</code>
          </div>

          <div className="resolucion">
            <Mate>{resolucion.resolucion_latex}</Mate>
          </div>
        </section>
      )}
    </div>
  );
}
