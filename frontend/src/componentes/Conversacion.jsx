import { useEffect, useRef } from 'react';
import Mate from './Mate';

/**
 * Transcript del episodio.
 *
 * Las etiquetas de rol se resuelven contra el lado asignado al humano: en
 * agente–estudiante el participante puede ocupar cualquiera de los dos roles,
 * porque el rol se contrabalancea.
 */
function etiquetaDe(rol, ladoHumano) {
  if (rol === 'sistema') return 'Enunciado común';

  const esA = rol === 'participante_a';
  const nombre = esA ? 'Participante A' : 'Participante B';

  if (!ladoHumano) return `${nombre} · agente`;
  const humanoEsEste = (ladoHumano === 'a' && esA) || (ladoHumano === 'b' && !esA);
  return humanoEsEste ? `${nombre} · vos` : `${nombre} · agente`;
}

export default function Conversacion({ turnos, pensando, ladoHumano }) {
  const fin = useRef(null);

  useEffect(() => {
    fin.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [turnos, pensando]);

  return (
    <div className="conversacion">
      {turnos.map((t) => (
        <article key={t.id} className={`burbuja ${t.rol} autor-${t.tipo_autor}`}>
          <header className="burbuja-rol">
            <span>{etiquetaDe(t.rol, ladoHumano)}</span>
            {t.orden > 0 && <span className="numero-turno">turno {t.orden}</span>}
          </header>
          <Mate>{t.contenido}</Mate>
        </article>
      ))}
      {pensando && (
        <div className="burbuja pensando">
          <span className="punto" />
          <span className="punto" />
          <span className="punto" />
        </div>
      )}
      <div ref={fin} />
    </div>
  );
}
