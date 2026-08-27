import { useState } from 'react';
import api, { mensajeDeError, VEREDICTOS } from '../api';

/**
 * Envío de la respuesta final y cierre del episodio.
 *
 * Es un formulario aparte y no la detección de un marcador en el diálogo. La
 * diferencia importa: si la corrección dependiera de que el participante escriba
 * cierta palabra, la variable dependiente principal mediría su disposición a
 * declararse exitoso en lugar de su acierto. Acá la respuesta se verifica por
 * equivalencia simbólica contra la clave canónica de la instancia.
 */
export default function CierreEpisodio({ episodio, onCerrado, deshabilitado }) {
  const [respuesta, setRespuesta] = useState('');
  const [resultado, setResultado] = useState(null);
  const [error, setError] = useState('');
  const [enviando, setEnviando] = useState(false);

  const abierto = episodio.estado === 'en_curso';

  async function enviar(evento) {
    evento.preventDefault();
    if (!respuesta.trim()) return;
    setError('');
    setEnviando(true);
    try {
      const { data } = await api.post(`/api/episodios/${episodio.id}/respuesta`, {
        respuesta,
      });
      setResultado(data);
      await onCerrado();
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo registrar la respuesta'));
    } finally {
      setEnviando(false);
    }
  }

  async function abandonar() {
    setError('');
    setEnviando(true);
    try {
      await api.post(`/api/episodios/${episodio.id}/abandonar`);
      await onCerrado();
    } catch (e) {
      setError(mensajeDeError(e, 'No se pudo cerrar el episodio'));
    } finally {
      setEnviando(false);
    }
  }

  if (!abierto) {
    const veredicto = resultado?.veredicto ?? episodio.veredicto;
    const acerto = resultado?.acerto ?? episodio.acerto;

    return (
      <div className={`cierre cerrado ${acerto ? 'acierto' : ''}`}>
        <h3>Episodio cerrado</h3>
        {veredicto ? (
          <p>
            Veredicto: <strong>{VEREDICTOS[veredicto] || veredicto}</strong>
            {resultado?.forma_normalizada && (
              <>
                {' '}· se interpretó como <code>{resultado.forma_normalizada}</code>
              </>
            )}
          </p>
        ) : (
          <p>Se cerró sin respuesta final: cuenta como dato faltante, no como error.</p>
        )}
      </div>
    );
  }

  return (
    <div className="cierre">
      <h3>Respuesta final</h3>
      <p className="ayuda">
        Se verifica por equivalencia simbólica contra la clave de la instancia, así que
        no importa la forma: <code>1/2</code>, <code>0.5</code> y <code>\frac{'{1}{2}'}</code>{' '}
        son la misma respuesta.
      </p>

      <form onSubmit={enviar} className="formulario-cierre">
        <input
          value={respuesta}
          onChange={(e) => setRespuesta(e.target.value)}
          placeholder="Sólo la respuesta, sin desarrollo"
          disabled={enviando || deshabilitado}
        />
        <button
          type="submit"
          className="boton-principal"
          disabled={enviando || deshabilitado || !respuesta.trim()}
        >
          {enviando ? 'Verificando…' : 'Enviar y cerrar'}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      <button
        className="boton-terciario"
        onClick={abandonar}
        disabled={enviando || deshabilitado}
      >
        Cerrar sin responder
      </button>
    </div>
  );
}
