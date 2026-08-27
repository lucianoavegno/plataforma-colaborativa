import { useEffect, useState } from 'react';
import api from '../api';

/**
 * Franja permanente con el estado del instrumento.
 *
 * Muestra la huella experimental y advierte cuando los modelos corren en modo
 * simulado. Que esté siempre a la vista es deliberado: un episodio simulado no
 * es dato experimental, y quien recolecta tiene que poder verlo sin ir a buscarlo.
 */
export default function BarraEstado() {
  const [estado, setEstado] = useState(null);

  useEffect(() => {
    api.get('/api/estado').then((r) => setEstado(r.data)).catch(() => setEstado(null));
  }, []);

  if (!estado) return null;

  return (
    <div className={`barra-estado ${estado.modelos_simulados ? 'simulado' : ''}`}>
      {estado.modelos_simulados && (
        <span className="aviso-simulado">
          Modo simulado — {estado.motivo_simulacion}. Los episodios quedan marcados y se
          excluyen de la exportación.
        </span>
      )}
      <span className="metadato">
        protocolo <code>{estado.version_protocolo}</code>
      </span>
      <span className="metadato">
        huella <code>{estado.huella_experimental}</code>
      </span>
    </div>
  );
}
